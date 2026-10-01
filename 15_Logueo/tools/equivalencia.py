"""Equivalencia de DATOS SSIS <-> Python (solo lectura, no escribe en la base).

Toma el CSV (SharePoint o --archivo-local), lo procesa con el pipeline en modo
--solo-validar y compara, columna a columna, las filas que Python insertaria
con las que SSIS ya inserto en [TBL_CONEXIONES] para las mismas fechas
([FECHA ANSI] del archivo). Como el archivo es el que SSIS cargo, deben
coincidir el 100% como multiconjunto de filas (46 columnas mapeadas; [DNI]
se excluye: la completa 'AGREGA DNI' despues de la carga).

Tambien reporta el resultado del Lookup: con el archivo ya cargado por SSIS,
Python debe encontrar 0 filas nuevas.

Salida en evidencias/:
Ademas SIMULA la insercion en una tabla temporal de sesion (#SIM) para
ejercitar el camino de escritura (el Lookup descarta todo si SSIS ya cargo).

    python/TBL_CONEXIONES.csv.gz   filas transformadas por Python
    ssis/TBL_CONEXIONES.csv.gz     filas cargadas por SSIS (mismas fechas)
    resumen.json, reporte_ssis_vs_python.md

Uso:
    python tools/equivalencia.py [--archivo-local RUTA] [--periodo YYYYMM]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src" / "logueo"))
sys.path.insert(0, str(RAIZ))

import mappings  # noqa: E402
import sql  # noqa: E402
from carga.loader import LogueoLoader  # noqa: E402
from config import cargar_configuracion  # noqa: E402
from db import DatabaseGateway, crear_conexion  # noqa: E402
from extraccion.extractor import FuenteLocal  # noqa: E402
from logging_setup import configurar_logging  # noqa: E402
from main import crear_fuente_sharepoint  # noqa: E402
from periodo import resolver_periodo  # noqa: E402
from pipeline import LogueoPipeline  # noqa: E402

COLUMNAS = list(mappings.COLUMNAS_INSERT)
CLAVE = [c for c, _ in mappings.CLAVE_LOOKUP]


def comparar(df_python: pd.DataFrame, df_ssis: pd.DataFrame) -> dict:
    """Comparacion como multiconjunto de filas + diferencias por columna en
    las filas cuya clave del Lookup coincide pero el resto no."""
    py = Counter(tuple(f) for f in df_python[COLUMNAS].itertuples(index=False, name=None))
    ss = Counter(tuple(f) for f in df_ssis[COLUMNAS].itertuples(index=False, name=None))
    solo_py, solo_ss = py - ss, ss - py

    diferencias_columna: Counter = Counter()
    ejemplos: list[dict] = []
    por_clave_ss = {tuple(f[COLUMNAS.index(c)] for c in CLAVE): f for f in solo_ss.elements()}
    for fila in solo_py.elements():
        otra = por_clave_ss.get(tuple(fila[COLUMNAS.index(c)] for c in CLAVE))
        if otra is None:
            continue
        for col, a, b in zip(COLUMNAS, fila, otra):
            if a != b:
                diferencias_columna[col] += 1
                if len(ejemplos) < 20:
                    ejemplos.append({"clave": [fila[COLUMNAS.index(c)] for c in CLAVE], "columna": col, "python": a, "ssis": b})
    return {
        "filas_python": sum(py.values()),
        "filas_ssis": sum(ss.values()),
        "filas_identicas": sum((py & ss).values()),
        "solo_python": sum(solo_py.values()),
        "solo_ssis": sum(solo_ss.values()),
        "diferencias_por_columna": dict(diferencias_columna),
        "ejemplos": ejemplos,
        "equivalente": not solo_py and not solo_ss,
    }


def simular_insercion(db: DatabaseGateway, df_python: pd.DataFrame) -> pd.DataFrame:
    """Ejercita el camino de ESCRITURA sin tocar produccion: inserta TODAS las
    filas transformadas en una tabla temporal de sesion (#SIM, misma
    estructura que TBL_CONEXIONES) con el mismo INSERT y los mismos tamanos
    de parametro que usa la carga real, y las relee tal como las guardo SQL
    Server (conversion nvarchar -> varchar Modern_Spanish_CI_AS, NULLs)."""
    columnas_sql = ", ".join(f"[{c}]" for c in mappings.COLUMNAS_DESTINO)
    db.execute_autocommit(f"DROP TABLE IF EXISTS #SIM; SELECT TOP 0 {columnas_sql} INTO #SIM FROM [dbo].[TBL_CONEXIONES]")
    insert_sim = sql.INSERT_DESTINO.replace(f"[{mappings.SCHEMA}].[{mappings.TABLA_DESTINO}]", "#SIM")
    filas = [tuple(f) for f in df_python[COLUMNAS].itertuples(index=False, name=None)]
    db.insertar_todo_o_nada(insert_sim, filas, [mappings.ANCHO_CONVERSION] * len(COLUMNAS))
    return db.run_query(f"SELECT {columnas_sql} FROM #SIM")


def _reporte(resumen: dict) -> str:
    c = resumen["comparacion"]
    estado = "EQUIVALENTE" if c["equivalente"] else "CON DIFERENCIAS"
    lineas = [
        "# Equivalencia SSIS vs Python - Cl_Proc_Logueo",
        "",
        f"- Fecha de la prueba: {resumen['fecha']}",
        f"- Origen Python: `{resumen['origen']}`",
        f"- Fechas del archivo ([FECHA ANSI]): {', '.join(resumen['fechas'])}",
        f"- Periodo (User::Periodo): {resumen['periodo']}",
        "",
        f"## Resultado: **{estado}**",
        "",
        "| Medida | Valor |",
        "|---|---:|",
        f"| Filas del archivo (Flat File Source) | {resumen['filas_archivo']} |",
        f"| Filas transformadas por Python | {c['filas_python']} |",
        f"| Filas cargadas por SSIS en TBL_CONEXIONES (mismas fechas) | {c['filas_ssis']} |",
        f"| Filas identicas (46 columnas) | {c['filas_identicas']} |",
        f"| Solo en Python | {c['solo_python']} |",
        f"| Solo en SSIS | {c['solo_ssis']} |",
        f"| Lookup: coincidentes (ya cargadas) | {resumen['lookup_coincidentes']} |",
        f"| Lookup: no coincidentes (Python insertaria) | {resumen['lookup_no_coincidentes']} |",
        "",
        "Conteo por [FECHA ANSI]:",
        "",
        "| FECHA ANSI | Python | SSIS |",
        "|---|---:|---:|",
    ]
    lineas += [f"| {f} | {p} | {s} |" for f, (p, s) in resumen["por_fecha"].items()]
    sim = resumen["simulacion_insercion"]
    lineas += [
        "",
        "## Simulacion de insercion (tabla temporal #SIM, sin tocar produccion)",
        "",
        "Todas las filas de Python se insertan con el mismo INSERT y tamanos de parametro de la carga real",
        "y se releen tal como las guardo SQL Server.",
        "",
        "| Medida | Valor |",
        "|---|---:|",
        f"| Filas insertadas en #SIM | {sim['filas_python']} |",
        f"| Identicas a SSIS (46 columnas) | {sim['filas_identicas']} |",
        f"| Solo en #SIM / solo en SSIS | {sim['solo_python']} / {sim['solo_ssis']} |",
        f"| [DNI] NULL tras la insercion (lo completa AGREGA DNI) | {sim['dni_nulos']} |",
        f"| Resultado | **{'EQUIVALENTE' if sim['equivalente'] else 'CON DIFERENCIAS'}** |",
    ]
    if c["diferencias_por_columna"]:
        lineas += ["", "Diferencias por columna (filas con la misma clave del Lookup):", ""]
        lineas += [f"- {col}: {n}" for col, n in c["diferencias_por_columna"].items()]
    return "\n".join(lineas) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--archivo-local", type=Path)
    parser.add_argument("--periodo")
    args = parser.parse_args()

    settings = cargar_configuracion(RAIZ)
    configurar_logging(settings.log_dir)
    periodo = resolver_periodo(args.periodo, settings.periodo_env, date.today())
    db = DatabaseGateway(lambda: crear_conexion(settings.db), settings.batch_size, settings.db.database)
    try:
        fuente = FuenteLocal(args.archivo_local) if args.archivo_local else crear_fuente_sharepoint(settings)
        r = LogueoPipeline(LogueoLoader(db), fuente, periodo).run(solo_validar=True)
        df_py = r.df_transformado
        fechas = sorted({f for f in df_py["FECHA ANSI"] if f is not None})
        marcas = ", ".join("?" for _ in fechas)
        columnas_sql = ", ".join(f"[{c}]" for c in COLUMNAS)
        df_ss = db.run_query(
            f"SELECT {columnas_sql} FROM [{mappings.SCHEMA}].[{mappings.TABLA_DESTINO}] WHERE [FECHA ANSI] IN ({marcas})",
            fechas,
        )
        df_sim = simular_insercion(db, r.df_transformado)
    finally:
        db.cerrar()

    comparacion = comparar(df_py, df_ss)
    comparacion_sim = comparar(df_sim, df_ss)
    comparacion_sim["dni_nulos"] = int(df_sim["DNI"].isna().sum())
    por_fecha = {
        f: (int((df_py["FECHA ANSI"] == f).sum()), int((df_ss["FECHA ANSI"] == f).sum())) for f in fechas
    }
    resumen = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "origen": fuente.descripcion,
        "periodo": str(periodo),
        "fechas": fechas,
        "filas_archivo": r.filas_archivo,
        "lookup_coincidentes": r.filas_coincidentes,
        "lookup_no_coincidentes": r.filas_no_coincidentes,
        "por_fecha": por_fecha,
        "comparacion": comparacion,
        "simulacion_insercion": {k: v for k, v in comparacion_sim.items() if k != "ejemplos"},
    }

    destino = RAIZ / "evidencias"
    for sub, df in (("python", df_py), ("ssis", df_ss)):
        (destino / sub).mkdir(parents=True, exist_ok=True)
        df.sort_values(CLAVE).to_csv(destino / sub / "TBL_CONEXIONES.csv.gz", index=False, sep=";", encoding="utf-8")
    (destino / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (destino / "reporte_ssis_vs_python.md").write_text(_reporte(resumen), encoding="utf-8")

    print(_reporte(resumen))
    ok = comparacion["equivalente"] and comparacion_sim["equivalente"] and r.filas_no_coincidentes == 0
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

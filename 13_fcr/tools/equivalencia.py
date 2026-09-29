"""Herramienta para demostrar la equivalencia SSIS vs Python sobre datos reales.

Uso:

    # A) Oraculo (SOLO LECTURA; no escribe en TBL_FCR ni en LOGS_PROCESOS):
    #    corre el T-SQL ORIGINAL de 'Alimenta Tabla' redirigido a una #temp y,
    #    en la misma sesion, la extraccion + transformacion de Python; compara.
    python tools/equivalencia.py oraculo --periodo 202608

    # B) Antes/despues de la corrida real:
    python tools/equivalencia.py foto ssis --periodo 202608     # estado que dejo SSIS
    python main.py --periodo 202608                             # ETL Python (escribe)
    python tools/equivalencia.py foto python --periodo 202608
    python tools/equivalencia.py comparar ssis python

Una 'foto' guarda en evidencias/<etiqueta>/ las filas de TBL_FCR con
YEAR(FECHA)*100+MONTH(FECHA) >= periodo, normalizadas a texto (NULL = '\\N').
'comparar' confronta dos fotos como multiconjuntos de filas (el orden no
importa). Si difieren, prueba la comparacion TOLERANTE A EMPATES: cuando un
mismo ANI tiene dos atenciones en el mismo [FECHA/HORA], el LEAD de SQL
Server no garantiza a cual LOGINID le toca el 'proximo' (ORDER BY no es
unico); en ese caso difiere solo el emparejamiento LOGINID <-> resto de la
fila y el resultado es 'EQUIVALENTE (empates)'.

evidencias/ contiene datos personales (telefonos/ANI): esta en .gitignore.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR / "src" / "fcr"))

import mappings  # noqa: E402
import sql  # noqa: E402

EVIDENCIAS = BASE_DIR / "evidencias"
NULO = "\\N"
COLUMNAS_EMPATE = ("BASE", "ANI", "SERVICIO", "FECHA/HORA")


def normalizar(valor) -> str:
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)):
        return NULO
    if isinstance(valor, datetime):  # incluye pd.Timestamp
        return valor.isoformat(sep=" ", timespec="milliseconds")
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor)


def filas_normalizadas(df: pd.DataFrame) -> list[tuple]:
    return [tuple(normalizar(v) for v in f) for f in df[list(mappings.NOMBRES_DESTINO)].itertuples(index=False, name=None)]


# --------------------------------------------------------------------------- #
# Comparacion (pura: sin base de datos)
# --------------------------------------------------------------------------- #
def comparar_filas(a: list[tuple], b: list[tuple], cabecera=mappings.NOMBRES_DESTINO) -> dict:
    ca, cb = Counter(a), Counter(b)
    res = {
        "filas_a": len(a),
        "filas_b": len(b),
        "identicas": sum((ca & cb).values()),
        "solo_a": sum((ca - cb).values()),
        "solo_b": sum((cb - ca).values()),
    }
    if ca == cb:
        res["resultado"] = "IDENTICA"
        return res
    i_login = cabecera.index("LOGINID")
    sin_login = lambda fs: Counter(f[:i_login] + f[i_login + 1 :] for f in fs)  # noqa: E731
    idx = [cabecera.index(c) for c in COLUMNAS_EMPATE] + [i_login]
    login_por_clave = lambda fs: Counter(tuple(f[i] for i in idx) for f in fs)  # noqa: E731
    if sin_login(a) == sin_login(b) and login_por_clave(a) == login_por_clave(b):
        res["resultado"] = "EQUIVALENTE (empates)"
    else:
        res["resultado"] = "DIFERENTE"
    res["columnas"] = {
        col: (sum((Counter(f[i] for f in a) - Counter(f[i] for f in b)).values()),
              sum((Counter(f[i] for f in b) - Counter(f[i] for f in a)).values()))
        for i, col in enumerate(cabecera)
        if Counter(f[i] for f in a) != Counter(f[i] for f in b)
    }
    res["ejemplos_a"] = [dict(zip(cabecera, f)) for f in list((ca - cb).elements())[:3]]
    res["ejemplos_b"] = [dict(zip(cabecera, f)) for f in list((cb - ca).elements())[:3]]
    return res


def _reporte(titulo: str, a: str, b: str, res: dict, extra: list[str] | None = None) -> str:
    lineas = [f"# {titulo}", "", *(extra or []), "",
              f"| Filas {a} | Filas {b} | Identicas | Solo en {a} | Solo en {b} | Resultado |",
              "|---:|---:|---:|---:|---:|---|",
              f"| {res['filas_a']} | {res['filas_b']} | {res['identicas']} | {res['solo_a']} | {res['solo_b']} | **{res['resultado']}** |"]
    if res.get("columnas"):
        lineas += ["", "Columnas cuyo multiconjunto de valores difiere:", ""]
        lineas += [f"- `{c}`: {x} valores solo en {a}, {y} solo en {b}" for c, (x, y) in res["columnas"].items()]
    for etiqueta, clave in ((a, "ejemplos_a"), (b, "ejemplos_b")):
        if res.get(clave):
            lineas += ["", f"Ejemplos solo en '{etiqueta}':"] + [f"- `{e}`" for e in res[clave]]
    return "\n".join(lineas) + "\n"


# --------------------------------------------------------------------------- #
# Fotos
# --------------------------------------------------------------------------- #
def _guardar(etiqueta: str, periodo: int, cabecera: list[str], filas: list[tuple], origen: str) -> Path:
    destino = EVIDENCIAS / etiqueta
    destino.mkdir(parents=True, exist_ok=True)
    with gzip.open(destino / "TBL_FCR.csv.gz", "wt", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(cabecera)
        w.writerows(filas)
    resumen = {"etiqueta": etiqueta, "periodo": periodo, "tomada": datetime.now().isoformat(), "origen": origen, "filas": len(filas)}
    (destino / "resumen.json").write_text(json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Foto '{etiqueta}': {len(filas)} filas -> {destino}")
    return destino


def _leer(etiqueta: str) -> tuple[dict, list[str], list[tuple]]:
    resumen = json.loads((EVIDENCIAS / etiqueta / "resumen.json").read_text(encoding="utf-8"))
    with gzip.open(EVIDENCIAS / etiqueta / "TBL_FCR.csv.gz", "rt", encoding="utf-8", newline="") as fh:
        r = csv.reader(fh, delimiter=";")
        cabecera = next(r)
        return resumen, cabecera, [tuple(f) for f in r]


def _db():
    from config import cargar_configuracion
    from db import DatabaseGateway, crear_conexion

    settings = cargar_configuracion(BASE_DIR)
    return DatabaseGateway(lambda: crear_conexion(settings.db_trafico), settings.batch_size, "CL_TRAFICO")


def foto(etiqueta: str, periodo: int) -> None:
    db = _db()
    try:
        cols = ", ".join(f"[{c}]" for c in mappings.NOMBRES_DESTINO)
        df = db.run_query(f"SELECT {cols} FROM [CL_TRAFICO].[dbo].[TBL_FCR] WHERE YEAR(FECHA)*100+MONTH(FECHA)>=?", (periodo,))
        _guardar(etiqueta, periodo, list(mappings.NOMBRES_DESTINO), filas_normalizadas(df), "TBL_FCR")
    finally:
        db.cerrar()


def comparar(a: str, b: str) -> int:
    ra, cab_a, fa = _leer(a)
    rb, cab_b, fb = _leer(b)
    if cab_a != cab_b:
        print("Las fotos tienen columnas distintas.")
        return 1
    res = comparar_filas(fa, fb, tuple(cab_a))
    reporte = _reporte(
        f"TBL_FCR: '{a}' vs '{b}'", a, b, res,
        [f"- Foto '{a}': {ra['tomada']} (periodo >= {ra['periodo']}, {ra['origen']})",
         f"- Foto '{b}': {rb['tomada']} (periodo >= {rb['periodo']}, {rb['origen']})"],
    )
    salida = EVIDENCIAS / f"reporte_{a}_vs_{b}.md"
    salida.write_text(reporte, encoding="utf-8")
    print(reporte + f"\nReporte: {salida}")
    return 0 if res["resultado"] != "DIFERENTE" else 1


def oraculo(periodo: int) -> int:
    """T-SQL original (SSIS) vs Python sobre los MISMOS datos de origen, en
    la misma sesion y uno inmediatamente despues del otro."""
    from extraccion import extractor
    from transformacion import transformer
    from validacion import validator

    db = _db()
    try:
        inicio = datetime.now()
        # Un solo lote: con parametros pyodbc lo ejecuta como RPC y las #temp
        # mueren al terminar la llamada, asi que el SELECT va en el mismo lote.
        cols = ", ".join(f"[{c}]" for c in mappings.NOMBRES_DESTINO)
        df_sql = db.run_query(
            sql.alimenta_tabla_oraculo() + f"\nSELECT {cols} FROM {sql.TABLA_ORACULO};", (periodo,)
        )
        t_sql = datetime.now()

        validator.validar_esquemas(db)
        extraidos = extractor.extraer_bases(db, periodo)
        for base in mappings.BASES:
            validator.validar_extraccion(extraidos[base.tabla_temporal], base)
        df_py = transformer.transformar(extraidos)
        validator.validar_resultado(df_py)
        t_py = datetime.now()
    finally:
        db.cerrar()

    f_sql, f_py = filas_normalizadas(df_sql), filas_normalizadas(df_py)
    _guardar("oraculo_sql", periodo, list(mappings.NOMBRES_DESTINO), f_sql, "T-SQL original de Alimenta Tabla (#temp)")
    _guardar("oraculo_python", periodo, list(mappings.NOMBRES_DESTINO), f_py, "extraccion + transformacion Python")
    res = comparar_filas(f_sql, f_py)

    por_base = []
    i_base, i_serv = mappings.NOMBRES_DESTINO.index("BASE"), mappings.NOMBRES_DESTINO.index("SERVICIO")
    cs, cp = Counter((f[i_base], f[i_serv]) for f in f_sql), Counter((f[i_base], f[i_serv]) for f in f_py)
    for b in mappings.BASES:
        k = (b.base, b.servicio)
        por_base.append(f"| {b.base} | {b.servicio} | {cs[k]} | {cp[k]} |")
    i_tramo = mappings.NOMBRES_DESTINO.index("TRAMO_QUIEBRE")
    ts, tp = Counter(f[i_tramo] for f in f_sql), Counter(f[i_tramo] for f in f_py)
    tramos = [f"| {t} | {ts[t]} | {tp[t]} |" for t in [u.tramo for u in mappings.UMBRALES] + [mappings.SIN_QUIEBRE]]

    reporte = _reporte(
        f"Oraculo: T-SQL original de 'Alimenta Tabla' vs Python (periodo >= {periodo})", "sql", "python", res,
        [f"- Ejecutado: {inicio:%Y-%m-%d %H:%M:%S} (SQL {(t_sql - inicio).total_seconds():.1f} s, Python {(t_py - t_sql).total_seconds():.1f} s)",
         "- SQL: literal del .dtsx; solo cambia el destino del INSERT (#TBL_FCR_ORACULO, misma estructura que TBL_FCR).",
         "- Python: extraccion/extractor.py + transformacion/transformer.py + validacion/validator.py.",
         "- Comparacion fila a fila de las 23 columnas, como multiconjunto.", "",
         "| BASE | SERVICIO | Filas SQL | Filas Python |", "|---|---|---:|---:|", *por_base, "",
         "| TRAMO_QUIEBRE | SQL | Python |", "|---|---:|---:|", *tramos],
    )
    salida = EVIDENCIAS / f"reporte_oraculo_{periodo}.md"
    salida.write_text(reporte, encoding="utf-8")
    print(reporte + f"\nReporte: {salida}")
    return 0 if res["resultado"] != "DIFERENTE" else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("foto")
    f.add_argument("etiqueta")
    f.add_argument("--periodo", type=int, required=True)
    c = sub.add_parser("comparar")
    c.add_argument("a")
    c.add_argument("b")
    o = sub.add_parser("oraculo")
    o.add_argument("--periodo", type=int, required=True)
    args = p.parse_args()
    if args.cmd == "foto":
        foto(args.etiqueta, args.periodo)
        return 0
    if args.cmd == "oraculo":
        return oraculo(args.periodo)
    return comparar(args.a, args.b)


if __name__ == "__main__":
    sys.exit(main())

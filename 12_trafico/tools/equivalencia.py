"""Herramienta para demostrar la equivalencia SSIS vs Python sobre datos reales.

Uso (SOLO LECTURA sobre la base):

    # 1) Despues de una corrida de SSIS (antes de correr Python):
    python tools/equivalencia.py foto ssis --periodo 202609
    # 2) Correr el ETL Python:  python main.py --periodo 202609
    # 3) Foto del resultado Python y comparacion:
    python tools/equivalencia.py foto python --periodo 202609
    python tools/equivalencia.py comparar ssis python

Una 'foto' guarda, en evidencias/<etiqueta>/:
  - las 7 tablas temporales completas (CL_TEMPORALES.TBL_TRAFICO_*), y
  - las filas del periodo (CONVERT(VARCHAR(6),FECHA,112) >= periodo) de las
    8 tablas de CL_TRAFICO,
normalizadas a texto (NULL = '\\N'). 'comparar' confronta ambas fotos como
multiconjuntos de filas (el orden de las filas no importa) y, si hay
diferencias, indica que columnas las explican. El reporte se escribe en
evidencias/reporte_<a>_vs_<b>.md.

evidencias/ contiene datos personales (RUT, telefonos): esta en .gitignore.
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

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR / "src" / "trafico"))

import mappings  # noqa: E402
from config import cargar_configuracion  # noqa: E402
from db import DatabaseGateway, crear_conexion  # noqa: E402

EVIDENCIAS = BASE_DIR / "evidencias"
NULO = "\\N"


def _normalizar(valor) -> str:
    if valor is None:
        return NULO
    if isinstance(valor, datetime):
        return valor.isoformat(sep=" ", timespec="milliseconds")
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor)


def _tablas(periodo: int) -> list[tuple[str, str, str]]:
    """(base, tabla, consulta)"""
    tablas = [
        ("CL_TEMPORALES", o.tabla_temporal, f"SELECT * FROM [CL_TEMPORALES].[dbo].[{o.tabla_temporal}]")
        for o in mappings.ORIGENES
    ]
    tablas += [
        (
            "CL_TRAFICO",
            d.tabla,
            f"SELECT * FROM [CL_TRAFICO].[dbo].[{d.tabla}] WHERE CONVERT(VARCHAR(6),FECHA,112) >= '{int(periodo)}'",
        )
        for d in mappings.DESTINOS
    ]
    return tablas


def foto(etiqueta: str, periodo: int) -> None:
    settings = cargar_configuracion(BASE_DIR)
    db = DatabaseGateway(lambda: crear_conexion(settings.db_temporales))
    try:
        destino = EVIDENCIAS / etiqueta
        destino.mkdir(parents=True, exist_ok=True)
        resumen = {"etiqueta": etiqueta, "periodo": periodo, "tomada": datetime.now().isoformat(), "tablas": {}}
        for base, tabla, consulta in _tablas(periodo):
            df = db.run_query(consulta)
            with gzip.open(destino / f"{base}.{tabla}.csv.gz", "wt", encoding="utf-8", newline="") as fh:
                w = csv.writer(fh, delimiter=";")
                w.writerow(df.columns)
                for fila in df.itertuples(index=False, name=None):
                    w.writerow([_normalizar(v) for v in fila])
            resumen["tablas"][f"{base}.{tabla}"] = len(df)
            print(f"{base}.{tabla}: {len(df)} filas")
        (destino / "resumen.json").write_text(json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Foto '{etiqueta}' guardada en {destino}")
    finally:
        db.cerrar()


def _leer(path: Path) -> tuple[list[str], list[tuple]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        r = csv.reader(fh, delimiter=";")
        cabecera = next(r)
        return cabecera, [tuple(f) for f in r]


def comparar(a: str, b: str) -> int:
    ra = json.loads((EVIDENCIAS / a / "resumen.json").read_text(encoding="utf-8"))
    rb = json.loads((EVIDENCIAS / b / "resumen.json").read_text(encoding="utf-8"))
    lineas = [
        f"# Equivalencia '{a}' vs '{b}'",
        "",
        f"- Foto '{a}': {ra['tomada']} (periodo {ra['periodo']})",
        f"- Foto '{b}': {rb['tomada']} (periodo {rb['periodo']})",
        "",
        f"| Tabla | Filas {a} | Filas {b} | Filas identicas | Solo en {a} | Solo en {b} | Resultado |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    detalles = []
    total_dif = 0
    for nombre in ra["tablas"]:
        cab_a, filas_a = _leer(EVIDENCIAS / a / f"{nombre}.csv.gz")
        cab_b, filas_b = _leer(EVIDENCIAS / b / f"{nombre}.csv.gz")
        if cab_a != cab_b:
            lineas.append(f"| {nombre} | {len(filas_a)} | {len(filas_b)} | - | - | - | columnas distintas |")
            total_dif += 1
            continue
        ca, cb = Counter(filas_a), Counter(filas_b)
        solo_a, solo_b = ca - cb, cb - ca
        iguales = sum((ca & cb).values())
        ok = not solo_a and not solo_b
        total_dif += 0 if ok else 1
        lineas.append(
            f"| {nombre} | {len(filas_a)} | {len(filas_b)} | {iguales} | {sum(solo_a.values())} | "
            f"{sum(solo_b.values())} | {'IDENTICA' if ok else 'DIFERENTE'} |"
        )
        if not ok:
            # Columnas cuyo multiconjunto de valores difiere: explican la diferencia.
            cols = []
            for i, col in enumerate(cab_a):
                va, vb = Counter(f[i] for f in filas_a), Counter(f[i] for f in filas_b)
                if va != vb:
                    cols.append(f"`{col}` ({sum((va - vb).values())} valores solo en {a}, {sum((vb - va).values())} solo en {b})")
            detalles += [f"## {nombre}", "", "Columnas con diferencias: " + (", ".join(cols) or "ninguna (difiere la combinacion)"), ""]
            for etiqueta, resto in ((a, solo_a), (b, solo_b)):
                if resto:
                    detalles.append(f"Ejemplos solo en '{etiqueta}':")
                    for fila in list(resto.elements())[:3]:
                        detalles.append(f"- `{dict(zip(cab_a, fila))}`")
                    detalles.append("")
    reporte = "\n".join(lineas + [""] + detalles)
    salida = EVIDENCIAS / f"reporte_{a}_vs_{b}.md"
    salida.write_text(reporte, encoding="utf-8")
    print(reporte)
    print(f"\nReporte: {salida}")
    return 0 if total_dif == 0 else 1


def _tipificar_foto(tabla: str, cabecera: list[str], filas: list[tuple]):
    """Reconstruye los tipos Python de una tabla temporal de la foto."""
    import pandas as pd

    from extraccion.extractor import parsear_datetime

    esquema = mappings.TIPOS_TEMPORALES[tabla]
    conv = {}
    for col in cabecera:
        tipo = esquema[col][0]
        if tipo == "int":
            conv[col] = int
        elif tipo == "date":
            conv[col] = date.fromisoformat
        elif tipo == "datetime":
            conv[col] = parsear_datetime
        else:
            conv[col] = str
    datos = {
        col: pd.Series([None if f[i] == NULO else conv[col](f[i]) for f in filas], dtype=object)
        for i, col in enumerate(cabecera)
    }
    return pd.DataFrame(datos, columns=cabecera)


def _emular_update_wsp(df):
    """Emulacion (SOLO para esta verificacion) de 31_cl_trafico_update_wsp.sql,
    que en el proceso real corre en SQL Server despues de CARGA. LIKE es
    case-insensitive por la collation *_CI_AS del servidor."""
    df = df.copy()
    for i in df.index:
        fecha = df.at[i, "FECHA"]
        if fecha is None or fecha < date(2024, 12, 1):
            continue
        cola = df.at[i, "COLA"]
        c = cola.lower() if cola is not None else None
        df.at[i, "INTERACTION_TYPE"] = "OUTBOUND_WSP" if c is not None and "out" in c else "INBOUND_WSP"
        if c is not None and "micro" in c:
            df.at[i, "SEGMENTO COLA"] = "MICRO"
        elif c is not None and "pyme" in c:
            df.at[i, "SEGMENTO COLA"] = "PYME"
        else:
            df.at[i, "SEGMENTO COLA"] = df.at[i, "SEGMENTO_AGRUPADO"]
    return df


def carga_offline(etiqueta: str) -> int:
    """Pasa las temporales de la foto por el Data Flow CARGA de Python y compara
    el resultado con las tablas CL_TRAFICO de la MISMA foto (producidas por
    SSIS a partir de esas mismas temporales). No toca la base."""
    from transformacion import transformer

    resumen = json.loads((EVIDENCIAS / etiqueta / "resumen.json").read_text(encoding="utf-8"))
    temporales = {}
    for o in mappings.ORIGENES:
        cab, filas = _leer(EVIDENCIAS / etiqueta / f"CL_TEMPORALES.{o.tabla_temporal}.csv.gz")
        temporales[o.tabla_temporal] = _tipificar_foto(o.tabla_temporal, cab, filas)
    transformados = transformer.transformar_carga(temporales)
    transformados["TBL_CHAT"] = _emular_update_wsp(transformados["TBL_CHAT"])

    lineas = [
        f"# Data Flow CARGA: Python vs SSIS (foto '{etiqueta}', {resumen['tomada']})",
        "",
        "Entrada: las 7 temporales de la foto (estado final que dejo SSIS tras LIMPIA TEMPORALES).",
        "Esperado: las filas del periodo que SSIS escribio en CL_TRAFICO en esa misma corrida.",
        "",
        "| Tabla CL_TRAFICO | Filas SSIS | Filas Python | Identicas | Resultado |",
        "|---|---:|---:|---:|---|",
    ]
    dif = 0
    for d in mappings.DESTINOS:
        cab, esperado = _leer(EVIDENCIAS / etiqueta / f"CL_TRAFICO.{d.tabla}.csv.gz")
        df = transformados[d.tabla][cab]
        obtenido = [tuple(_normalizar(v) for v in f) for f in df.itertuples(index=False, name=None)]
        ce, co = Counter(esperado), Counter(obtenido)
        ok = ce == co
        dif += 0 if ok else 1
        lineas.append(f"| {d.tabla} | {len(esperado)} | {len(obtenido)} | {sum((ce & co).values())} | {'IDENTICA' if ok else 'DIFERENTE'} |")
        if not ok:
            for i, col in enumerate(cab):
                ve, vo = Counter(f[i] for f in esperado), Counter(f[i] for f in obtenido)
                if ve != vo:
                    lineas.append(f"|  - columna `{col}` difiere | {sum((ve - vo).values())} | {sum((vo - ve).values())} | | |")
    reporte = "\n".join(lineas)
    salida = EVIDENCIAS / f"reporte_carga_offline_{etiqueta}.md"
    salida.write_text(reporte, encoding="utf-8")
    print(reporte)
    print(f"\nReporte: {salida}")
    return 0 if dif == 0 else 1


# Columnas que las tareas SQL posteriores (TEMPORALES\UPDATE y LIMPIA
# TEMPORALES) reescriben sobre la temporal: su valor final ya no es el que se
# inserto, asi que no sirven para verificar la extraccion.
_MODIFICADAS_POR_SQL = {"LOGINID", "STOP_ACTION", "PLACE", "RUT_USUARIO", "CALC_NUM_TELEFONO", "ANI"}


def extraccion_offline(etiqueta: str) -> int:
    """Extrae los 7 CSV actuales de SharePoint con el extractor de Python y
    compara, en las columnas que ninguna tarea SQL modifica despues, contra lo
    que los scripts .py originales insertaron en las temporales (foto). No
    escribe en la base."""
    from extraccion import extractor
    from sharepoint.auth import get_graph_token
    from sharepoint.client import SharePointClient
    from sharepoint.reader import CsvReader

    settings = cargar_configuracion(BASE_DIR)
    sp = settings.sharepoint
    token = get_graph_token(sp.tenant_id, sp.client_id, sp.client_secret, sp.timeout_ms)
    client = SharePointClient(token, sp.timeout_ms)
    reader = CsvReader(client, client.resolve_drive(client.resolve_site(sp.hostname, sp.site_path), sp.drive_name), sp.folder_path)
    resumen = json.loads((EVIDENCIAS / etiqueta / "resumen.json").read_text(encoding="utf-8"))

    lineas = [
        f"# Extraccion: CSV SharePoint (Python) vs [Externos_Frac] (scripts .py originales) -- foto '{etiqueta}'",
        "",
        f"Columnas comparadas: todas las insertadas salvo {sorted(_MODIFICADAS_POR_SQL)} (las reescriben tareas SQL posteriores).",
        "",
        "| Origen | Filas SSIS | Filas Python | Filas SSIS encontradas en Python | Resultado |",
        "|---|---:|---:|---:|---|",
    ]
    dif = 0
    for o in mappings.ORIGENES:
        df = extractor.extraer_origen(reader, o, resumen["periodo"])
        cab, filas = _leer(EVIDENCIAS / etiqueta / f"CL_TEMPORALES.{o.tabla_temporal}.csv.gz")
        cols = [c for c in o.columnas if c not in _MODIFICADAS_POR_SQL]
        idx = [cab.index(c) for c in cols]
        esperado = Counter(tuple(f[i] for i in idx) for f in filas)
        obtenido = Counter(tuple(_normalizar(v) for v in f) for f in df[cols].itertuples(index=False, name=None))
        encontradas = sum((esperado & obtenido).values())
        if esperado == obtenido:
            res = "IDENTICA"
        elif encontradas == sum(esperado.values()):
            res = f"SSIS contenido en Python (+{sum((obtenido - esperado).values())} filas que SSIS no cargo)"
        else:
            res = "DIFERENTE"
            dif += 1
        lineas.append(f"| {o.archivo} | {len(filas)} | {len(df)} | {encontradas} | {res} |")
        if res == "DIFERENTE":
            for c, i in zip(cols, idx):
                ve = Counter(f[i] for f in filas)
                vo = Counter(_normalizar(v) for v in df[c])
                if ve != vo:
                    ej = list((ve - vo).elements())[:2], list((vo - ve).elements())[:2]
                    lineas.append(f"|  - `{c}` | {sum((ve - vo).values())} | {sum((vo - ve).values())} | ej. SSIS={ej[0]} Python={ej[1]} | |")
    reporte = "\n".join(lineas)
    salida = EVIDENCIAS / f"reporte_extraccion_offline_{etiqueta}.md"
    salida.write_text(reporte, encoding="utf-8")
    print(reporte)
    print(f"\nReporte: {salida}")
    return 0 if dif == 0 else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("foto")
    f.add_argument("etiqueta")
    f.add_argument("--periodo", type=int, required=True)
    c = sub.add_parser("comparar")
    c.add_argument("a")
    c.add_argument("b")
    o = sub.add_parser("carga-offline")
    o.add_argument("etiqueta")
    e = sub.add_parser("extraccion-offline")
    e.add_argument("etiqueta")
    args = p.parse_args()
    if args.cmd == "foto":
        foto(args.etiqueta, args.periodo)
        return 0
    if args.cmd == "carga-offline":
        return carga_offline(args.etiqueta)
    if args.cmd == "extraccion-offline":
        return extraccion_offline(args.etiqueta)
    return comparar(args.a, args.b)


if __name__ == "__main__":
    sys.exit(main())

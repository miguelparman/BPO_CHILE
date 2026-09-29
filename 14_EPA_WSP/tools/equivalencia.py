"""Herramienta para demostrar la equivalencia SSIS vs Python sobre datos reales.

Uso:

    # A) Sin escribir nada (SOLO LECTURA):
    python tools/equivalencia.py simular     # CSV de SharePoint -> transformacion Python
                                             #   vs lo que SSIS dejo en las tablas (mismos periodos)
    python tools/equivalencia.py medallia    # CL_Carga_de_encuestas_MEDALLIA.py (oraculo literal)
                                             #   vs transformacion Python, sobre el mismo CSV

    # B) Antes y despues de una corrida real:
    python tools/equivalencia.py foto ssis       # estado que dejo SSIS
    python main.py                               # corrida Python
    python tools/equivalencia.py foto python
    python tools/equivalencia.py comparar ssis python

Una 'foto' guarda en evidencias/<etiqueta>/ las 2 tablas temporales que
alimentan SP.EPA_ISN_CHILE (TBL_ENCUESTAS_CHILE y TBL_ENCUESTAS_WSP_MEDALLIA,
completas) normalizadas a texto (NULL = '\\N'), y los conteos por periodo de
las tablas finales de CL_CALIDAD. 'comparar' confronta ambas fotos como
multiconjuntos de filas y, si hay diferencias, indica que columnas las
explican (cruzando por la clave de la encuesta).

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
sys.path.insert(0, str(BASE_DIR / "src" / "epa_wsp"))
sys.path.insert(0, str(BASE_DIR))

import mappings  # noqa: E402
from config import cargar_configuracion  # noqa: E402
from db import DatabaseGateway, crear_conexion  # noqa: E402
from tools import oraculos  # noqa: E402

EVIDENCIAS = BASE_DIR / "evidencias"
NULO = "\\N"
CLAVES = {mappings.ENCUESTA.tabla: "id_encuesta_registro", mappings.WSP.tabla: "SurveyID"}
TABLAS_CALIDAD = (
    ("TBL_CALIDAD_RETENCIONES", "periodo_encuesta"),
    ("TBL_CALIDAD_TRIADAS", "periodo_evento"),
    ("TBL_CALIDAD_USUARIOS", "periodo_encuesta"),
    ("TBL_CALIDAD_ISN_CARTERIZADOS", "periodo_encuesta"),
    ("TBL_EPA_WSP_TRIADAS_CARTERIZADOS_MEDALLIA", "PERIODO"),
    ("TBL_ENCUESTAS_MEDALLIA", "periodo_encuesta"),
)


def normalizar(valor) -> str:
    if valor is None:
        return NULO
    try:
        if valor != valor:  # NaN / NaT
            return NULO
    except TypeError:
        pass
    if isinstance(valor, datetime):
        return valor.isoformat(sep=" ", timespec="milliseconds")
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor)


def _db(settings, cual: str) -> DatabaseGateway:
    return DatabaseGateway(lambda: crear_conexion(getattr(settings, cual)), settings.batch_size, cual)


def _filas_tabla(db, tabla: str, where: str = "", params=()) -> tuple[list[str], list[tuple]]:
    df = db.run_query(f"SELECT * FROM [dbo].[{tabla}] {where}", params)
    return list(df.columns), [tuple(normalizar(v) for v in fila) for fila in df.itertuples(index=False, name=None)]


def _guardar(destino: Path, columnas: list[str], filas: list[tuple]) -> None:
    with gzip.open(destino, "wt", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(columnas)
        w.writerows(sorted(filas))


def _leer(origen: Path) -> tuple[list[str], list[tuple]]:
    with gzip.open(origen, "rt", encoding="utf-8", newline="") as fh:
        r = csv.reader(fh)
        columnas = next(r)
        return columnas, [tuple(f) for f in r]


def diferencias(columnas: list[str], a: list[tuple], b: list[tuple], clave: str | None) -> dict:
    """Compara multiconjuntos de filas; si difieren, explica por columna
    cruzando por la clave."""
    ca, cb = Counter(a), Counter(b)
    solo_a, solo_b = ca - cb, cb - ca
    res = {"filas_a": len(a), "filas_b": len(b), "solo_a": sum(solo_a.values()), "solo_b": sum(solo_b.values())}
    if clave and (solo_a or solo_b):
        i = columnas.index(clave)
        ia = {f[i]: f for f in solo_a.elements()}
        ib = {f[i]: f for f in solo_b.elements()}
        comunes = set(ia) & set(ib)
        por_col = Counter()
        ejemplos: dict[str, list] = {}
        for k in comunes:
            for j, col in enumerate(columnas):
                if ia[k][j] != ib[k][j]:
                    por_col[col] += 1
                    ejemplos.setdefault(col, [])
                    if len(ejemplos[col]) < 3:
                        ejemplos[col].append((k, ia[k][j], ib[k][j]))
        res.update(
            claves_solo_a=len(set(ia) - set(ib)),
            claves_solo_b=len(set(ib) - set(ia)),
            columnas_distintas=dict(por_col),
            ejemplos=ejemplos,
        )
    return res


def veredicto(d: dict) -> str:
    """IDENTICO; IDENTICO + filas nuevas (b tiene encuestas que a aun no tenia,
    ninguna fila de a cambio ni falta); o DIFERENCIAS."""
    if d.get("solo_a", 0) == 0 and d.get("solo_b", 0) == 0:
        return "IDENTICO"
    if d.get("solo_a", 0) == 0 and not d.get("columnas_distintas"):
        return f"IDENTICO en todas las filas de a (+{d['solo_b']} encuestas nuevas en b)"
    return "DIFERENCIAS"


def por_periodo(columnas: list[str], a: list[tuple], b: list[tuple], col_periodo: str) -> dict:
    i = columnas.index(col_periodo)
    periodos = sorted({f[i] for f in a} | {f[i] for f in b})
    res = {}
    for p in periodos:
        fa = Counter(f for f in a if f[i] == p)
        fb = Counter(f for f in b if f[i] == p)
        res[p] = {"a": sum(fa.values()), "b": sum(fb.values()),
                  "solo_a": sum((fa - fb).values()), "solo_b": sum((fb - fa).values())}
    return res


def _reporte(nombre: str, titulo: str, secciones: list[tuple[str, dict]], notas: list[str] = ()) -> Path:
    lineas = [f"# {titulo}", "", f"Generado: {datetime.now():%Y-%m-%d %H:%M:%S}", ""]
    for tabla, d in secciones:
        lineas += [f"## {tabla}: {veredicto(d)}", ""]
        lineas += [f"- {k}: {v}" for k, v in d.items() if k != "por_periodo"]
        if "por_periodo" in d:
            lineas += ["", "| periodo | filas a | filas b | solo a | solo b |", "|---|---|---|---|---|"]
            lineas += [f"| {p} | {x['a']} | {x['b']} | {x['solo_a']} | {x['solo_b']} |" for p, x in d["por_periodo"].items()]
        lineas.append("")
    lineas += list(notas)
    EVIDENCIAS.mkdir(parents=True, exist_ok=True)
    ruta = EVIDENCIAS / nombre
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print("\n".join(lineas))
    print(f"\nReporte: {ruta}")
    return ruta


# --------------------------------------------------------------------------- #
def foto(etiqueta: str) -> None:
    settings = cargar_configuracion(BASE_DIR)
    ind, cal = _db(settings, "db_indicadores"), _db(settings, "db_calidad")
    destino = EVIDENCIAS / etiqueta
    destino.mkdir(parents=True, exist_ok=True)
    resumen = {"etiqueta": etiqueta, "tomada": datetime.now().isoformat(), "tablas": {}, "cl_calidad": {}}
    try:
        for t in (mappings.ENCUESTA, mappings.WSP):
            columnas, filas = _filas_tabla(ind, t.tabla)
            _guardar(destino / f"{t.tabla}.csv.gz", columnas, filas)
            por_periodo = Counter(f[columnas.index(t.columna_periodo)] for f in filas)
            resumen["tablas"][t.tabla] = {"filas": len(filas), "por_periodo": dict(sorted(por_periodo.items()))}
            print(f"{t.tabla}: {len(filas)} filas")
        for tabla, col in TABLAS_CALIDAD:
            df = cal.run_query(f"SELECT CAST([{col}] AS varchar(10)) p, COUNT(*) n FROM [dbo].[{tabla}] GROUP BY [{col}]")
            resumen["cl_calidad"][tabla] = {str(p): int(n) for p, n in sorted(df.itertuples(index=False, name=None), key=lambda x: str(x[0]))}
    finally:
        ind.cerrar()
        cal.cerrar()
    (destino / "resumen.json").write_text(json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Foto '{etiqueta}' en {destino}")


def comparar(a: str, b: str) -> None:
    secciones = []
    for t in (mappings.ENCUESTA, mappings.WSP):
        ca, fa = _leer(EVIDENCIAS / a / f"{t.tabla}.csv.gz")
        cb, fb = _leer(EVIDENCIAS / b / f"{t.tabla}.csv.gz")
        assert ca == cb, f"{t.tabla}: columnas distintas"
        d = diferencias(ca, fa, fb, CLAVES[t.tabla])
        d["por_periodo"] = por_periodo(ca, fa, fb, t.columna_periodo)
        secciones.append((t.tabla, d))
    ra = json.loads((EVIDENCIAS / a / "resumen.json").read_text(encoding="utf-8"))
    rb = json.loads((EVIDENCIAS / b / "resumen.json").read_text(encoding="utf-8"))
    notas = ["## Conteos por periodo en CL_CALIDAD (salida de los SP)", "", f"| tabla | {a} | {b} |", "|---|---|---|"]
    for tabla in ra["cl_calidad"]:
        notas.append(f"| {tabla} | {sum(ra['cl_calidad'][tabla].values())} | {sum(rb['cl_calidad'].get(tabla, {}).values())} |")
    _reporte(f"reporte_{a}_vs_{b}.md", f"Equivalencia: foto '{a}' vs foto '{b}'", secciones, notas)


def _sharepoint(settings):
    """(CsvReader de '13 SERVIDOR CHILE', CarpetaSharePoint '16 MEDALLIA')."""
    from sharepoint.auth import get_graph_token
    from sharepoint.carpeta import CarpetaSharePoint
    from sharepoint.client import SharePointClient
    from sharepoint.reader import CsvReader

    sp = settings.sharepoint
    client = SharePointClient(get_graph_token(sp.tenant_id, sp.client_id, sp.client_secret, sp.timeout_ms), sp.timeout_ms)
    drive = client.resolve_drive(client.resolve_site(sp.hostname, sp.site_path), sp.drive_name)
    return CsvReader(client, drive, sp.folder_path), CarpetaSharePoint(client, drive, sp.folder_medallia, sp.web_drive)


def simular() -> None:
    """Transformacion Python (sin escribir) vs las filas que SSIS dejo en la
    tabla para los mismos periodos."""
    from pipeline import EpaWspPipeline

    settings = cargar_configuracion(BASE_DIR)
    reader, carpeta = _sharepoint(settings)
    ind = _db(settings, "db_indicadores")
    p = EpaWspPipeline(
        db_general=None, db_calidad=None, db_indicadores=ind, csv_reader=reader,
        medallia=settings.medallia, carpeta_medallia=carpeta,
        periodo_desde_encuesta=settings.periodo_desde_encuesta,
    )
    secciones = []
    try:
        for t, desde in ((mappings.WSP, None), (mappings.ENCUESTA, settings.periodo_desde_encuesta)):
            df, periodos = p._preparar(t, desde)
            marcas = ", ".join("?" for _ in periodos)
            params = [str(x) if t.tipo_periodo == "nvarchar" else x for x in periodos]
            columnas, en_tabla = _filas_tabla(ind, t.tabla, f"WHERE [{t.columna_periodo}] IN ({marcas})", params)
            idx = {c: i for i, c in enumerate(df.columns)}
            python = [
                tuple(normalizar(f[idx[c]]) if c in idx else NULO for c in columnas)
                for f in df.itertuples(index=False, name=None)
            ]
            d = diferencias(columnas, en_tabla, python, CLAVES[t.tabla])
            d["periodos"] = periodos
            d["por_periodo"] = por_periodo(columnas, en_tabla, python, t.columna_periodo)
            secciones.append((t.tabla, d))
    finally:
        ind.cerrar()
    _reporte(
        "reporte_simulacion_ssis_vs_python.md",
        "Simulacion: tabla cargada por SSIS vs transformacion Python (mismos periodos)",
        secciones,
        ["a = filas de la tabla (SSIS, desde [Externos_Frac]); b = Python (desde el CSV de SharePoint)."],
    )


def medallia() -> None:
    """Oraculo literal de CL_Carga_de_encuestas_MEDALLIA.py vs Python, sobre el
    Encuestas_Medallia.csv que esta en SharePoint ('16 MEDALLIA')."""
    import io

    from extraccion.extractor import extraer_csv_medallia
    from transformacion import transformer

    settings = cargar_configuracion(BASE_DIR)
    _, carpeta = _sharepoint(settings)
    nombre = settings.medallia.archivo
    original = oraculos.medallia_datos(io.BytesIO(carpeta.leer(nombre)))
    # En el original las filas con Responsedate NaT fallaban al insertar (error 242).
    original_insertables = [f for f in original if not (f[3] is None or f[3] != f[3])]
    df, rechazadas = transformer.medallia(extraer_csv_medallia(carpeta, nombre))
    columnas = list(df.columns)
    a = [tuple(normalizar(v) for v in f) for f in original_insertables]
    b = [tuple(normalizar(v) for v in f) for f in df.itertuples(index=False, name=None)]
    d = diferencias(columnas, a, b, "ID de encuesta")
    d["filas_csv"] = len(original)
    d["rechazadas_original"] = len(original) - len(original_insertables)
    d["rechazadas_python"] = len(rechazadas)
    _reporte(
        "reporte_medallia_oraculo_vs_python.md",
        f"Medallia: CL_Carga_de_encuestas_MEDALLIA.py (oraculo) vs Python sobre {carpeta.url(nombre)}",
        [(mappings.MEDALLIA.tabla, d)],
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("foto")
    f.add_argument("etiqueta")
    c = sub.add_parser("comparar")
    c.add_argument("a")
    c.add_argument("b")
    sub.add_parser("simular")
    sub.add_parser("medallia")
    args = ap.parse_args()
    if args.cmd == "foto":
        foto(args.etiqueta)
    elif args.cmd == "comparar":
        comparar(args.a, args.b)
    elif args.cmd == "simular":
        simular()
    else:
        medallia()


if __name__ == "__main__":
    main()

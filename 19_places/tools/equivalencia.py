"""Evidencia de equivalencia SSIS <-> Python sobre datos reales.

Subcomandos:
  foto <etiqueta>       Vuelca TBL_PLACES y TBL_HISTORICO_PLACES de CL_DATA a
                        evidencias/<etiqueta>/<tabla>.csv.gz (solo lectura).
                        Antes de la primera carga Python: 'foto ssis'.
  simular <etiqueta>    Ejecuta extraccion -> validacion -> transformacion SIN escribir en SQL
                        y aplica el equivalente en Python de LIMPIA TABLA para las 5 columnas que
                        no dependen de la base (ID, Etiqueta, Plataforma, Rut, Asesor). Origen:
                        --archivo o SharePoint (ReportingFractalia).
  comparar <a> <b>      Compara dos fotos fila a fila (multiconjunto) sobre las columnas que
                        tienen en comun y escribe evidencias/reporte_<a>_vs_<b>.md + resumen.json.
                        DNI y fechas dependen de TBL_PERSONAL_CONSOLIDADO y del dia (fecha de baja =
                        hoy): solo se comparan entre dos fotos de BD, no contra 'simular'.

Uso:
    python -m tools.equivalencia foto ssis
    python -m tools.equivalencia simular python_simulado
    python -m tools.equivalencia comparar ssis python_simulado --columnas base
    python main.py && python -m tools.equivalencia foto python
    python -m tools.equivalencia comparar ssis python --columnas base
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src" / "places"))

import mappings  # noqa: E402
from config import cargar_configuracion  # noqa: E402
from db import DatabaseGateway, crear_conexion  # noqa: E402
from extraccion.extractor import Extractor, FuenteLocal, FuenteSharePoint  # noqa: E402
from sharepoint.client import ConexionGraph  # noqa: E402
from transformacion.transformer import Transformer  # noqa: E402
from validacion.validator import Validator  # noqa: E402

EVIDENCIAS = RAIZ / "evidencias"
NULO = "<NULL>"
_MAX_DIFERENCIAS = 20

# Columnas de TBL_PLACES (las del INSERT + las que completa LIMPIA TABLA) y de la tabla historica.
COLUMNAS_PLACES = mappings.COLUMNAS_DESTINO + mappings.COLUMNAS_LIMPIA
COLUMNAS_HISTORICO = (
    "ID", "DNI", "Fecha Ingeso Empresa", "Fecha Baja Empresa", "Asesor", "Etiqueta", "Plataforma", "Rut", "Fecha Impacto"
)
TABLAS = {mappings.TABLA_PLACES: COLUMNAS_PLACES, mappings.TABLA_HISTORICO: COLUMNAS_HISTORICO}
COLUMNAS_BASE = ("ID", "Etiqueta", "Plataforma", "Rut", "Asesor")  # independientes de la BD y de la fecha


def _texto(valor) -> str:
    return NULO if valor is None else str(valor)


def _normalizar(filas: Iterable[Sequence]) -> list[tuple[str, ...]]:
    return sorted(tuple(_texto(v) for v in f) for f in filas)


def _guardar(etiqueta: str, tabla: str, columnas: Sequence[str], filas: Iterable[Sequence]) -> Path:
    destino = EVIDENCIAS / etiqueta
    destino.mkdir(parents=True, exist_ok=True)
    ruta = destino / f"{tabla}.csv.gz"
    with gzip.open(ruta, "wt", encoding="utf-8", newline="") as fh:
        escritor = csv.writer(fh)
        escritor.writerow(columnas)
        escritor.writerows(_normalizar(filas))
    return ruta


def _leer(etiqueta: str, tabla: str) -> tuple[list[str], list[tuple[str, ...]]]:
    with gzip.open(EVIDENCIAS / etiqueta / f"{tabla}.csv.gz", "rt", encoding="utf-8", newline="") as fh:
        lector = csv.reader(fh)
        columnas = next(lector)
        return columnas, [tuple(f) for f in lector]


def foto(etiqueta: str) -> None:
    settings = cargar_configuracion(RAIZ)
    db = DatabaseGateway(lambda: crear_conexion(settings.db), nombre=settings.db.database)
    try:
        for tabla, columnas in TABLAS.items():
            lista = ", ".join(f"[{c}]" for c in columnas)
            _, filas = db.run_query(f"SELECT {lista} FROM [dbo].[{tabla}]")
            print(f"{tabla}: {len(filas)} fila(s) -> {_guardar(etiqueta, tabla, columnas, filas)}")
    finally:
        db.cerrar()


def _limpia(fila: tuple) -> tuple | None:
    """LIMPIA TABLA para las 5 columnas independientes de la BD: DELETE ID IS NULL, LTRIM/RTRIM
    y Rut '' -> NULL (SQL Server ignora los espacios finales al comparar con '')."""
    id_, etiqueta, plataforma, rut, asesor, _dni = fila
    if id_ is None:
        return None
    rec = lambda v: None if v is None else v.strip(" ")  # noqa: E731 - LTRIM/RTRIM solo quitan espacios
    rut = None if rut is not None and rut.rstrip(" ") == "" else rec(rut)
    return rec(id_), rec(etiqueta), rec(plataforma), rut, rec(asesor)


def simular(etiqueta: str, archivo: Path | None) -> None:
    settings = cargar_configuracion(RAIZ)
    fuente = FuenteLocal(archivo) if archivo else FuenteSharePoint(ConexionGraph(settings.sharepoint))
    filas = Extractor(fuente).extraer()
    Validator().validar(filas)
    convertidas = Transformer().transformar(filas)
    finales = [r for r in map(_limpia, convertidas) if r is not None]
    ruta = _guardar(etiqueta, mappings.TABLA_PLACES, COLUMNAS_BASE, finales)
    print(f"{mappings.TABLA_PLACES}: {len(convertidas)} convertidas, {len(finales)} tras LIMPIA TABLA -> {ruta}")


def comparar(a: str, b: str, solo_base: bool) -> bool:
    resumen: dict[str, dict] = {}
    lineas = [f"# Equivalencia `{a}` vs `{b}`", "", f"Generado: {datetime.now():%Y-%m-%d %H:%M:%S}", ""]
    lineas += [f"| Tabla | Columnas | Filas {a} | Filas {b} | Solo en {a} | Solo en {b} | Resultado |",
               "|---|---|---|---|---|---|---|"]
    detalle: list[str] = []
    todo_ok = True
    for tabla in TABLAS:
        try:
            (ca, fa), (cb, fb) = _leer(a, tabla), _leer(b, tabla)
        except FileNotFoundError:
            continue  # la foto 'simular' solo tiene TBL_PLACES
        comunes = [c for c in ca if c in cb and (not solo_base or c in COLUMNAS_BASE)]
        ia, ib = [ca.index(c) for c in comunes], [cb.index(c) for c in comunes]
        pa = Counter(tuple(f[i] for i in ia) for f in fa)
        pb = Counter(tuple(f[i] for i in ib) for f in fb)
        solo_a, solo_b = pa - pb, pb - pa
        ok = not solo_a and not solo_b
        todo_ok &= ok
        n_sa, n_sb = sum(solo_a.values()), sum(solo_b.values())
        resumen[tabla] = {"columnas": comunes, f"filas_{a}": len(fa), f"filas_{b}": len(fb),
                          f"solo_{a}": n_sa, f"solo_{b}": n_sb, "identicas": ok}
        lineas.append(f"| {tabla} | {len(comunes)} | {len(fa)} | {len(fb)} | {n_sa} | {n_sb} | "
                      f"{'IDENTICAS' if ok else 'DIFERENCIAS'} |")
        if not ok:
            detalle += ["", f"## {tabla}", "", "Columnas: " + " | ".join(comunes), ""]
            for nombre, dif in ((a, solo_a), (b, solo_b)):
                detalle += [f"- solo en `{nombre}`: `{' | '.join(f)}`" for f in list(dif.elements())[:_MAX_DIFERENCIAS]]
    (EVIDENCIAS / f"reporte_{a}_vs_{b}.md").write_text("\n".join(lineas + detalle) + "\n", encoding="utf-8")
    (EVIDENCIAS / f"resumen_{a}_vs_{b}.json").write_text(json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n".join(lineas))
    print(f"\nReporte: {EVIDENCIAS / f'reporte_{a}_vs_{b}.md'}")
    return todo_ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="comando", required=True)
    p = sub.add_parser("foto")
    p.add_argument("etiqueta")
    p = sub.add_parser("simular")
    p.add_argument("etiqueta")
    p.add_argument("--archivo", type=Path)
    p = sub.add_parser("comparar")
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--columnas", choices=["todas", "base"], default="todas")
    args = parser.parse_args(argv)
    if args.comando == "foto":
        foto(args.etiqueta)
    elif args.comando == "simular":
        simular(args.etiqueta, args.archivo)
    else:
        return 0 if comparar(args.a, args.b, args.columnas == "base") else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Evidencia de equivalencia SSIS <-> Python sobre datos reales.

Subcomandos:
  foto <etiqueta>       Vuelca las 4 tablas de CL_MOVIL a evidencias/<etiqueta>/<tabla>.csv.gz
                        (solo lectura). Antes de la primera carga Python: 'foto ssis'.
  simular <etiqueta>    Ejecuta extraccion -> validacion -> transformacion SIN escribir en SQL
                        y aplica el DELETE ... IS NULL; deja el resultado esperado de la carga
                        Python en evidencias/<etiqueta>/. Origen: --archivo-dir o SharePoint
                        (ReportingFractalia).
  comparar <a> <b>      Compara dos fotos fila a fila (multiconjunto: las tablas no tienen
                        clave ni orden) y escribe evidencias/reporte_<a>_vs_<b>.md + resumen.json.

Uso:
    python -m tools.equivalencia foto ssis
    python -m tools.equivalencia simular python_simulado --archivo-dir "D:\\...\\Especializados"
    python -m tools.equivalencia comparar ssis python_simulado
    python main.py && python -m tools.equivalencia foto python
    python -m tools.equivalencia comparar ssis python
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
from typing import Iterable, Sequence

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src" / "gerencia"))

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


def _texto(valor) -> str:
    if valor is None:
        return NULO
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()[:10]
    return str(valor)


def _normalizar(filas: Iterable[Sequence]) -> list[tuple[str, ...]]:
    return sorted(tuple(_texto(v) for v in f) for f in filas)


def _guardar(etiqueta: str, flujo: mappings.FlujoSpec, filas: Iterable[Sequence]) -> Path:
    destino = EVIDENCIAS / etiqueta
    destino.mkdir(parents=True, exist_ok=True)
    ruta = destino / f"{flujo.tabla}.csv.gz"
    with gzip.open(ruta, "wt", encoding="utf-8", newline="") as fh:
        escritor = csv.writer(fh)
        escritor.writerow(flujo.columnas_destino)
        escritor.writerows(_normalizar(filas))
    return ruta


def _leer(etiqueta: str, flujo: mappings.FlujoSpec) -> list[tuple[str, ...]]:
    with gzip.open(EVIDENCIAS / etiqueta / f"{flujo.tabla}.csv.gz", "rt", encoding="utf-8", newline="") as fh:
        lector = csv.reader(fh)
        next(lector)
        return [tuple(f) for f in lector]


def foto(etiqueta: str) -> None:
    settings = cargar_configuracion(RAIZ)
    db = DatabaseGateway(lambda: crear_conexion(settings.db), nombre=settings.db.database)
    try:
        for flujo in mappings.FLUJOS:
            columnas = ", ".join(f"[{c}]" for c in flujo.columnas_destino)
            _, filas = db.run_query(f"SELECT {columnas} FROM [dbo].[{flujo.tabla}]")
            ruta = _guardar(etiqueta, flujo, filas)
            print(f"{flujo.tabla}: {len(filas)} fila(s) -> {ruta}")
    finally:
        db.cerrar()


def simular(etiqueta: str, archivo_dir: Path | None) -> None:
    settings = cargar_configuracion(RAIZ)
    fuente = FuenteLocal(archivo_dir) if archivo_dir else FuenteSharePoint(ConexionGraph(settings.destino))
    extractor, validador, transformador = Extractor(fuente), Validator(), Transformer()
    for flujo in mappings.FLUJOS:
        filas = extractor.extraer(flujo)
        validador.validar(flujo, filas)
        convertidas = transformador.transformar(flujo, filas)
        finales = [f for f in convertidas if f[0] is not None]  # DELETE ... WHERE [Número del caso] IS NULL
        ruta = _guardar(etiqueta, flujo, finales)
        print(f"{flujo.tabla}: {len(convertidas)} convertidas, {len(finales)} tras el DELETE -> {ruta}")


def comparar(a: str, b: str) -> bool:
    resumen: dict[str, dict] = {}
    lineas = [f"# Equivalencia `{a}` vs `{b}`", "", f"Generado: {datetime.now():%Y-%m-%d %H:%M:%S}", ""]
    lineas += ["| Tabla | Filas " + a + " | Filas " + b + " | Solo en " + a + " | Solo en " + b + " | Resultado |",
               "|---|---|---|---|---|---|"]
    detalle: list[str] = []
    todo_ok = True
    for flujo in mappings.FLUJOS:
        fa, fb = Counter(_leer(a, flujo)), Counter(_leer(b, flujo))
        solo_a, solo_b = fa - fb, fb - fa
        ok = not solo_a and not solo_b
        todo_ok &= ok
        n_sa, n_sb = sum(solo_a.values()), sum(solo_b.values())
        resumen[flujo.tabla] = {"filas_" + a: sum(fa.values()), "filas_" + b: sum(fb.values()),
                                "solo_" + a: n_sa, "solo_" + b: n_sb, "identicas": ok}
        lineas.append(f"| {flujo.tabla} | {sum(fa.values())} | {sum(fb.values())} | {n_sa} | {n_sb} | "
                      f"{'IDENTICAS' if ok else 'DIFERENCIAS'} |")
        if not ok:
            detalle += ["", f"## {flujo.tabla}", "", "Columnas: " + " | ".join(flujo.columnas_destino), ""]
            for nombre, dif in ((a, solo_a), (b, solo_b)):
                for fila in list(dif.elements())[:_MAX_DIFERENCIAS]:
                    detalle.append(f"- solo en `{nombre}`: `{' | '.join(fila)}`")
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
    p.add_argument("--archivo-dir", type=Path)
    p = sub.add_parser("comparar")
    p.add_argument("a")
    p.add_argument("b")
    args = parser.parse_args(argv)
    if args.comando == "foto":
        foto(args.etiqueta)
    elif args.comando == "simular":
        simular(args.etiqueta, args.archivo_dir)
    else:
        return 0 if comparar(args.a, args.b) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

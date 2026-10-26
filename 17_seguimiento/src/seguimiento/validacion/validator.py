"""Validaciones previas a la carga (antes de escribir NADA en la staging).

  - validar_estructura: cada fila del CSV tiene tantas columnas como el Flat
    File Connection Manager (SSIS mapea por POSICION, no por nombre: los
    encabezados que publica el bot no coinciden con los del .dtsx).
  - validar_esquema: la tabla staging existe y tiene todas las columnas que
    mapea el OLE DB Destination.
  - validar_anchos_destino: ningun texto supera el ancho REAL de su columna
    (INFORMATION_SCHEMA). Varias Data Conversion son mas anchas que la
    columna (p.ej. Estado DT_WSTR 50 -> nvarchar(25)): en SSIS el fast load
    falla en ese caso, aqui se detiene antes de cargar.
"""

from __future__ import annotations

from typing import Sequence

from exceptions import ValidacionError
from mappings import ArchivoSpec, FlujoSpec

MAX_EJEMPLOS = 10


def validar_estructura(archivo: ArchivoSpec, filas: Sequence[Sequence[str]]) -> None:
    esperado = len(archivo.columnas)
    malas = [(n, len(f)) for n, f in enumerate(filas, start=2) if len(f) != esperado]
    if malas:
        ejemplos = ", ".join(f"fila {n}: {c} columnas" for n, c in malas[:MAX_EJEMPLOS])
        raise ValidacionError(
            f"'{archivo.nombre}': {len(malas)} fila(s) no tienen las {esperado} columnas del Flat File "
            f"Connection Manager '{archivo.conexion}' ({ejemplos})."
        )


def validar_esquema(flujo: FlujoSpec, esquema: dict[str, tuple[str, int | None]]) -> None:
    if not esquema:
        raise ValidacionError(f"La tabla staging [{flujo.tabla}] no existe.")
    faltan = [c for c in flujo.columnas_insert if c not in esquema]
    if faltan:
        raise ValidacionError(f"[{flujo.tabla}] no tiene las columnas {faltan} que mapea '{flujo.componente}'.")


def validar_anchos_destino(
    flujo: FlujoSpec, filas: Sequence[tuple], esquema: dict[str, tuple[str, int | None]]
) -> None:
    problemas = []
    for i, columna in enumerate(flujo.columnas_insert):  # incluye las que completa el cruce
        _, largo = esquema[columna]
        if largo is None or largo == -1:
            continue
        excedidas = [(n, f[i]) for n, f in enumerate(filas, start=2) if isinstance(f[i], str) and len(f[i]) > largo]
        if excedidas:
            n, valor = excedidas[0]
            problemas.append(
                f"[{columna}] ({largo}): {len(excedidas)} valor(es) mas largos, p.ej. fila {n} "
                f"({len(valor)} caracteres: {valor[:60]!r})"
            )
    if problemas:
        raise ValidacionError(
            f"{flujo.componente} -> [{flujo.tabla}]: datos mas anchos que la columna destino (en SSIS el "
            "OLE DB Destination falla):\n  " + "\n  ".join(problemas[:MAX_EJEMPLOS])
        )

"""Validacion (no existia en el .dtsx: es la salvaguarda que reemplaza el
"si falla, sigue" de los scripts originales).

Todo corre ANTES del TRUNCATE de las temporales, asi un problema de datos o
de esquema detiene el proceso sin haber borrado nada:

1) validar_esquemas: el esquema real (INFORMATION_SCHEMA) de las 7 tablas
   temporales y las 8 de CL_TRAFICO sigue siendo el que asume mappings.py
   (mismos tipos y anchos). Si alguien altera una tabla, el proceso lo
   detecta en vez de truncar o convertir datos con reglas desactualizadas.
2) validar_origen: cada valor de texto cabe en su columna temporal. En el
   script original un valor mas largo hacia fallar el INSERT de todo el
   lote, y ese lote se descartaba en silencio (Transfer, Outbound, Callback)
   o se hacia rollback de la tabla completa (Atendida, Abandono).
"""

from __future__ import annotations

import logging

import pandas as pd

import mappings
from exceptions import ValidacionError
from mappings import OrigenCsv

logger = logging.getLogger("trafico")

_TIPOS_TEXTO = {"varchar", "nvarchar", "char", "nchar"}


def _comparar(tabla: str, esperado: dict[str, tuple[str, int | None]], real: dict) -> list[str]:
    if not real:
        return [f"{tabla}: la tabla no existe"]
    problemas = []
    for col, (tipo, largo) in esperado.items():
        if col not in real:
            problemas.append(f"{tabla}.[{col}]: no existe")
        elif real[col] != (tipo, largo):
            problemas.append(f"{tabla}.[{col}]: se esperaba {tipo}({largo}) y es {real[col][0]}({real[col][1]})")
    return problemas


def validar_esquemas(db_temporales, db_trafico) -> None:
    problemas: list[str] = []
    for origen in mappings.ORIGENES:
        esperado = mappings.TIPOS_TEMPORALES[origen.tabla_temporal]
        real = db_temporales.columnas_de_tabla(origen.tabla_temporal, mappings.SCHEMA)
        problemas += _comparar(f"CL_TEMPORALES.{origen.tabla_temporal}", esperado, real)
    for destino in mappings.DESTINOS:
        esperado = {c.destino: (c.tipo_destino, c.largo_destino) for c in destino.columnas}
        real = db_trafico.columnas_de_tabla(destino.tabla, mappings.SCHEMA)
        problemas += _comparar(f"CL_TRAFICO.{destino.tabla}", esperado, real)
        # Columnas de la tabla real que el Data Flow no alimenta: en SSIS
        # quedaban NULL; si ademas son NOT NULL el INSERT fallaria.
        sobrantes = set(real) - set(esperado)
        if sobrantes:
            logger.warning("CL_TRAFICO.%s tiene columnas no mapeadas en CARGA: %s", destino.tabla, sorted(sobrantes))
    if problemas:
        raise ValidacionError("El esquema real difiere del esperado:\n  " + "\n  ".join(problemas))
    logger.info("Esquema de las 15 tablas (7 temporales + 8 CL_TRAFICO) verificado.")


def validar_origen(df: pd.DataFrame, origen: OrigenCsv) -> None:
    esquema = mappings.TIPOS_TEMPORALES[origen.tabla_temporal]
    problemas = []
    for col in origen.columnas:
        tipo, largo = esquema[col]
        if tipo not in _TIPOS_TEXTO or largo in (None, -1):
            continue
        largos = df[col].dropna().astype(str).str.len()
        if len(largos) and int(largos.max()) > largo:
            n = int((largos > largo).sum())
            problemas.append(f"[{col}] {tipo}({largo}): {n} valores exceden el ancho (max {int(largos.max())})")
    if problemas:
        raise ValidacionError(
            f"{origen.archivo} -> CL_TEMPORALES.{origen.tabla_temporal}:\n  " + "\n  ".join(problemas)
        )
    if df.empty:
        logger.warning("%s: 0 filas para el periodo (la temporal quedara vacia).", origen.archivo)

"""Cruce en Python que reemplaza, en el paquete 02, la staging
TBL_SALESFORCE_DATOS_CONTACTO y la tarea 'Agrega Nombre de Contacto':

    UPDATE X0 SET
      [Nombre de contacto] = CASE WHEN X1.[Nombre de contacto] = '' THEN NULL ELSE X1.[Nombre de contacto] END,
      ... (Correo, Telefono, Movil igual)
    FROM [CL_TEMPORALES].[dbo].[TBL_SALESFORCE_CASOS] X0
    LEFT JOIN [CL_TEMPORALES].[dbo].[TBL_SALESFORCE_DATOS_CONTACTO] X1
    ON X0.[Numero del caso] = X1.[Numero del caso]

Semantica reproducida:
  - LEFT JOIN: caso sin contacto -> las 4 columnas en NULL.
  - '' -> NULL.
  - Igualdad de SQL Server con Modern_Spanish_CI_AS: sin distinguir
    mayusculas y sin contar espacios finales.
  - Si un caso tuviera varios contactos, el UPDATE de SQL Server toma uno
    cualquiera; aqui se toma el primero del archivo y se avisa en el log
    (al 2026-10-26 no hay casos repetidos).
"""

from __future__ import annotations

import logging
from typing import Sequence

from logging_setup import NOMBRE_LOGGER
from mappings import CruceSpec, FlujoSpec

logger = logging.getLogger(NOMBRE_LOGGER)


def _clave(valor) -> str | None:
    return None if valor is None else str(valor).rstrip(" ").casefold()


def aplicar_cruce(flujo: FlujoSpec, filas: Sequence[tuple], filas_cruce: Sequence[tuple]) -> list[tuple]:
    """Agrega a cada fila de 'flujo' las columnas de 'flujo.cruce' (en el
    orden de cruce.columnas). 'filas_cruce' son las filas ya transformadas
    del flujo cruzado (orden de cruce.flujo.columnas)."""
    cruce: CruceSpec = flujo.cruce
    nombres_cruce = [c.destino for c in cruce.flujo.columnas]
    i_clave_cruce = nombres_cruce.index(cruce.clave)
    i_columnas = [nombres_cruce.index(c) for c in cruce.columnas]
    i_clave = [c.destino for c in flujo.columnas].index(cruce.clave)

    indice: dict[str, tuple] = {}
    repetidos = 0
    for fila in filas_cruce:
        clave = _clave(fila[i_clave_cruce])
        if clave in indice:
            repetidos += 1
            continue
        indice[clave] = tuple(None if fila[i] == "" else fila[i] for i in i_columnas)
    if repetidos:
        logger.warning(
            "%s: %s caso(s) repetidos en '%s'; se usa el primero (SQL Server tomaria uno cualquiera).",
            cruce.tarea_reemplazada.rsplit("\\", 1)[-1],
            repetidos,
            cruce.flujo.archivo.nombre,
        )
    vacio = (None,) * len(cruce.columnas)
    return [tuple(fila) + indice.get(_clave(fila[i_clave]), vacio) for fila in filas]

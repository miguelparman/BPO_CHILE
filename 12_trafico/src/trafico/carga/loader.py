"""Carga.

- Log Inicio / Log Fin: [BBDD_GENERAL].[dbo].[LOGS_PROCESOS] (Nombre='Chile_Trafico').
- TEMPORALES: TRUNCA TABLAS + INSERT de cada origen, en UNA transaccion.
  (Los scripts originales ademas hacian 'DELETE ... WHERE DATE_YYYYMM >= ?'
  sobre la temporal recien truncada: era un no-op y no se replica.)
- CL_TRAFICO: DELETE PERIODO + los 8 OLE DB Destination del Data Flow
  CARGA, en UNA transaccion. En SSIS eran tareas separadas: si CARGA
  fallaba, el periodo quedaba borrado; aqui un fallo deja la tabla como estaba.
"""

from __future__ import annotations

import logging

import pandas as pd

import mappings
import sql

logger = logging.getLogger("trafico")


def registrar_inicio(db_trafico) -> None:
    """Package\\Log Inicio."""
    db_trafico.execute_script(sql.LOG_INICIO)


def registrar_fin(db_trafico) -> None:
    """Package\\Log Fin."""
    db_trafico.execute_script(sql.LOG_FIN)


def cargar_temporales(db_temporales, extraidos: dict[str, pd.DataFrame]) -> dict[str, int]:
    """Package\\TEMPORALES: TRUNCA TABLAS -> Atendidas -> Abandono -> Transfer ->
    Outbound -> Cleared -> Callback -> Cross_In."""
    filas: dict[str, int] = {}
    with db_temporales.transaccion():
        db_temporales.execute_script(sql.TEMPORALES_TRUNCA_TABLAS)
        logger.info("[Trafico]   TEMPORALES / TRUNCA TABLAS (7 tablas)")
        for origen in mappings.ORIGENES:
            logger.info("[Trafico]   TEMPORALES / %s -> %s", origen.paso, origen.tabla_temporal)
            filas[origen.tabla_temporal] = db_temporales.bulk_insert(
                origen.tabla_temporal, extraidos[origen.tabla_temporal], mappings.SCHEMA
            )
    return filas


def cargar_cl_trafico(db_trafico, periodo: int, transformados: dict[str, pd.DataFrame]) -> dict[str, int]:
    """Package\\CL_TRAFICO: DELETE PERIODO (? = User::Periodo) -> CARGA."""
    filas: dict[str, int] = {}
    with db_trafico.transaccion():
        db_trafico.execute_script(sql.CL_TRAFICO_DELETE_PERIODO, (periodo,))
        logger.info("[Trafico]   CL_TRAFICO / DELETE PERIODO >= %s (8 tablas)", periodo)
        for destino in mappings.DESTINOS:
            filas[destino.tabla] = db_trafico.bulk_insert(destino.tabla, transformados[destino.tabla], mappings.SCHEMA)
    return filas

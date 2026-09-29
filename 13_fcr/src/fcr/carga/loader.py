"""Carga.

- Log Inicio / Log Fin: [BBDD_GENERAL].[dbo].[LOGS_PROCESOS] (Nombre='Chile_FCR').
- Proceso Carga Tabla: Limpia Tabla (DELETE >= User::Periodo) + el INSERT
  de Alimenta Tabla, en UNA transaccion. En SSIS eran dos tareas separadas
  sin transaccion: si Alimenta Tabla fallaba, el periodo quedaba borrado;
  aqui un fallo deja TBL_FCR como estaba.
"""

from __future__ import annotations

import logging

import pandas as pd

import mappings
import sql

logger = logging.getLogger("fcr")


def registrar_inicio(db) -> None:
    """Package\\Log Inicio."""
    db.execute_script(sql.LOG_INICIO)


def registrar_fin(db) -> None:
    """Package\\Log Fin."""
    db.execute_script(sql.LOG_FIN)


def cargar_fcr(db, periodo: int, filas: pd.DataFrame) -> tuple[int, int]:
    """Package\\Proceso Carga Tabla: Limpia Tabla -> Alimenta Tabla (INSERT).
    Devuelve (filas borradas, filas insertadas)."""
    with db.transaccion():
        borradas = int(db.fetch_scalar(sql.CONTAR_PERIODO, (periodo,)) or 0)
        db.execute_script(sql.LIMPIA_TABLA, (periodo,))
        logger.info("[FCR]   Limpia Tabla: %s filas borradas de TBL_FCR (periodo >= %s)", borradas, periodo)
        insertadas = db.bulk_insert(mappings.TABLA_DESTINO, filas, mappings.SCHEMA)
    return borradas, insertadas

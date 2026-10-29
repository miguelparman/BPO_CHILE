"""Tareas 'Log Inicio' y 'Log Fin' del .dtsx sobre [BBDD_GENERAL].[dbo].[LOGS_PROCESOS].

Log Inicio inserta la fila con Estado 'exec...'; Log Fin la marca 'OK'. Como
en SSIS, si el proceso falla no hay Log Fin y la fila queda en 'exec...'.
"""

from __future__ import annotations

import logging

import mappings
from db import DatabaseGateway
from logging_setup import NOMBRE_LOGGER

logger = logging.getLogger(NOMBRE_LOGGER)


class LogsProceso:
    def __init__(self, db: DatabaseGateway) -> None:
        self._db = db

    def inicio(self) -> None:
        self._db.ejecutar_en_transaccion([(mappings.SQL_LOG_INICIO, None)])
        logger.info("Log Inicio registrado en LOGS_PROCESOS (%s).", mappings.NOMBRE_PROCESO)

    def fin(self) -> None:
        self._db.ejecutar_en_transaccion([(mappings.SQL_LOG_FIN, None)])
        logger.info("Log Fin registrado en LOGS_PROCESOS (%s: OK).", mappings.NOMBRE_PROCESO)

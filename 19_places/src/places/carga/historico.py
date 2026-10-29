"""CARGA HISTORICO: contenedor 'CARGA PLACES HISTORICO' del .dtsx.

    ELIMINA FECHA ACTUAL TABLA -> CARGA TABLA

Ambas tareas reciben como parametro User::Fecha_Actual (DT_DATE, la fecha de
hoy), que se guarda en [Fecha Impacto]. Reejecutar el mismo dia reemplaza la
foto del dia. Van en una transaccion (en SSIS son dos tareas separadas).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Callable

import mappings
from db import DatabaseGateway
from logging_setup import NOMBRE_LOGGER

logger = logging.getLogger(NOMBRE_LOGGER)


@dataclass(frozen=True)
class ResultadoHistorico:
    fecha: date
    eliminadas: int
    insertadas: int


class HistoricoLoader:
    def __init__(self, db: DatabaseGateway, hoy: Callable[[], date] = date.today) -> None:
        self._db = db
        self._hoy = hoy

    def cargar(self) -> ResultadoHistorico:
        fecha = self._hoy()  # User::Fecha_Actual
        eliminadas, insertadas = self._db.ejecutar_en_transaccion(
            [(mappings.SQL_HISTORICO_ELIMINA, (fecha,)), (mappings.SQL_HISTORICO_INSERTA, (fecha,))]
        )
        resultado = ResultadoHistorico(fecha, max(eliminadas, 0), max(insertadas, 0))
        logger.info(
            "%s: %s fila(s) del %s eliminadas, %s insertadas.",
            mappings.TABLA_HISTORICO,
            resultado.eliminadas,
            fecha.isoformat(),
            resultado.insertadas,
        )
        return resultado

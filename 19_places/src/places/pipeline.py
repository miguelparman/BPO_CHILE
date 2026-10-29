"""Orquestador: el Control Flow de CL_Proc_Carga_Places.dtsx.

    0. Validar conexiones (conexiones.py; reintento cada 5 min, max. 3)
    1. Log Inicio                            (logs_proceso.py)
    2. 'CARGA PLACES': extraer -> validar -> transformar -> TRUNCATE + INSERT + LIMPIA TABLA
    3. 'CARGA PLACES HISTORICO': DELETE fecha actual + INSERT en TBL_HISTORICO_PLACES
    4. Log Fin

Todas las restricciones del .dtsx son Success: si una etapa falla, las
siguientes no se ejecutan y no hay Log Fin (la fila de LOGS_PROCESOS queda
en 'exec...', como en SSIS). Los errores esperados (PlacesError) se propagan
a main.py, que los registra y devuelve exit 1.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Protocol, Sequence

from carga.historico import ResultadoHistorico
from carga.loader import ResultadoCarga
from extraccion.extractor import Fila
from logging_setup import NOMBRE_LOGGER
from validacion.validator import ResultadoValidacion

logger = logging.getLogger(NOMBRE_LOGGER)


class Extractor(Protocol):
    def extraer(self) -> list[Fila]: ...


class Validador(Protocol):
    def validar(self, filas: Sequence[Fila]) -> ResultadoValidacion: ...


class Transformador(Protocol):
    def transformar(self, filas: Sequence[Fila]) -> list[tuple]: ...


class Cargador(Protocol):
    def cargar(self, filas: Sequence[tuple]) -> ResultadoCarga: ...


class CargadorHistorico(Protocol):
    def cargar(self) -> ResultadoHistorico: ...


class Logs(Protocol):
    def inicio(self) -> None: ...

    def fin(self) -> None: ...


@dataclass(frozen=True)
class ResultadoPipeline:
    filas_leidas: int = 0
    carga: ResultadoCarga | None = None  # None = --solo-validar
    historico: ResultadoHistorico | None = None


class PlacesPipeline:
    def __init__(
        self,
        validar_conexiones: Callable[[], None] | None,
        extractor: Extractor,
        validador: Validador,
        transformador: Transformador,
        cargador: Cargador | None,
        historico: CargadorHistorico | None,
        logs: Logs | None,
    ) -> None:
        """cargador/historico/logs None = --solo-validar (no escribe en SQL)."""
        self._validar_conexiones = validar_conexiones
        self._extractor = extractor
        self._validador = validador
        self._transformador = transformador
        self._cargador = cargador
        self._historico = historico
        self._logs = logs

    def run(self) -> ResultadoPipeline:
        if self._validar_conexiones is not None:
            self._validar_conexiones()  # ConexionError -> no se ejecuta nada
        if self._logs is not None:
            self._logs.inicio()

        logger.info("=== CARGA PLACES ===")
        filas = self._extractor.extraer()
        self._validador.validar(filas)
        convertidas = self._transformador.transformar(filas)
        if self._cargador is None:
            logger.info("--solo-validar: %s fila(s) listas, no se escribe en SQL.", len(convertidas))
            return ResultadoPipeline(len(filas))
        carga = self._cargador.cargar(convertidas)

        logger.info("=== CARGA PLACES HISTORICO ===")
        historico = self._historico.cargar() if self._historico is not None else None

        if self._logs is not None:
            self._logs.fin()
        return ResultadoPipeline(len(filas), carga, historico)

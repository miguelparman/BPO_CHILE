"""Orquestador del proceso FCR (CL_Proc_Trafico_FCR_02.dtsx).

Llama a las capas -- extraccion/, validacion/, transformacion/, carga/ -- en
el orden del Control Flow; no conoce pyodbc (recibe el gateway ya construido).

Control Flow original (todas las restricciones "On Success", en serie):

    Log Inicio
      -> Proceso Carga Tabla          Limpia Tabla (DELETE >= periodo)
                                      -> Alimenta Tabla (5 bases -> INSERT TBL_FCR)
      -> Log Fin

Unico cambio de orden: las 5 bases se leen, transforman y validan ANTES del
DELETE. Es equivalente porque Alimenta Tabla lee TBL_LLAMADAS_ATENDIDAS_INBOUND
y TBL_CHAT, nunca TBL_FCR, y evita borrar el periodo si algo falla. Si el
proceso falla, 'Log Fin' no se ejecuta y LOGS_PROCESOS queda en 'exec...',
igual que en SSIS.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

import mappings
from carga import loader
from exceptions import PipelineError
from extraccion import extractor
from models import ResultadoPipeline
from transformacion import transformer
from validacion import validator

logger = logging.getLogger("fcr")


@dataclass
class FcrPipeline:
    """Orquesta: extraccion -> validacion -> transformacion -> carga."""

    name = "fcr"

    db: object  # DatabaseGateway sobre CL_TRAFICO

    def run(self, periodo: int, solo_validar: bool = False) -> ResultadoPipeline:
        resultado = ResultadoPipeline(periodo=periodo)
        logger.info("[FCR] Inicio del pipeline (User::Periodo=%s%s)", periodo, ", solo validar" if solo_validar else "")

        if not solo_validar:
            self._step("Log Inicio", lambda: loader.registrar_inicio(self.db))

        filas = self._step("Alimenta Tabla / extraccion, validacion y transformacion", lambda: self._preparar(periodo, resultado))
        if solo_validar:
            logger.info("[FCR] Validacion completada sin escribir en la base: %s filas listas. %s", len(filas), resultado)
            return resultado

        resultado.filas_borradas, resultado.filas_insertadas = self._step(
            "Proceso Carga Tabla / Limpia Tabla + Alimenta Tabla (INSERT TBL_FCR)",
            lambda: loader.cargar_fcr(self.db, periodo, filas),
        )
        self._step("Log Fin", lambda: loader.registrar_fin(self.db))

        logger.info("[FCR] Pipeline finalizado correctamente: %s", resultado)
        return resultado

    def _preparar(self, periodo: int, resultado: ResultadoPipeline):
        validator.validar_esquemas(self.db)
        extraidos = extractor.extraer_bases(self.db, periodo)
        for base in mappings.BASES:
            validator.validar_extraccion(extraidos[base.tabla_temporal], base)
            resultado.filas_por_base[base.tabla_temporal] = len(extraidos[base.tabla_temporal])
        filas = transformer.transformar(extraidos)
        validator.validar_resultado(filas)
        return filas

    def _step(self, descripcion: str, accion: Callable):
        logger.info("[FCR] %s", descripcion)
        try:
            return accion()
        except Exception as exc:  # noqa: BLE001 - se re-lanza tipado como PipelineError
            raise PipelineError(self.name, descripcion, exc) from exc

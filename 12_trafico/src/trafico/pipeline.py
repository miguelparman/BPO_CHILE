"""Orquestador del pipeline de Trafico.

Migracion de CL_Proc_Trafico_01.dtsx. Llama en orden a las 4 capas del
proceso -- extraccion/, validacion/, transformacion/ y carga/ -- y a la
alerta; no conoce pyodbc ni Microsoft Graph (los recibe ya construidos).

Control Flow original (todas las restricciones "On Success", en serie):

    Log Inicio
      -> enviar_alerta_trafico            (Execute Process; si falla, sigue)
      -> TEMPORALES                       TRUNCA TABLAS -> Atendidas -> Abandono -> Transfer
                                          -> Outbound -> Cleared -> Callback -> Cross_In -> UPDATE
      -> LIMPIA TEMPORALES                FORMATEANDO ANI -> UPDATE RUT -> UPDATE COD_DNI
                                          -> UPDATE SEGMENTO -> SEGMENTO COLA -> LLAMA CCAA?
      -> CL_TRAFICO                       DELETE PERIODO -> CARGA (Data Flow) -> UPDATE_WSP
      -> Log Fin
    Log Inicio -> MENSAJES WSP -> Log Fin  (secuencia DESHABILITADA en el .dtsx: no se migra)

Unico cambio de orden: los 7 CSV se descargan y validan ANTES del TRUNCATE
de las temporales (en SSIS cada script leia su origen despues del truncado,
y un origen que fallaba dejaba su temporal vacia sin detener el paquete).
Si el proceso falla, 'Log Fin' no se ejecuta y LOGS_PROCESOS queda en
'exec...', igual que en SSIS.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import alerta
import mappings
from carga import loader
from exceptions import PipelineError
from extraccion import extractor
from models import ResultadoPipeline
from transformacion import transformer
from validacion import validator

logger = logging.getLogger("trafico")


@dataclass
class TraficoPipeline:
    """Orquesta: extraccion -> validacion -> transformacion -> carga."""

    name = "trafico"

    db_temporales: object  # DatabaseGateway sobre CL_TEMPORALES
    db_trafico: object  # DatabaseGateway sobre CL_TRAFICO
    csv_reader: object  # sharepoint.reader.CsvReader
    alerta_txt_path: Path
    alerta_segundos_espera: int = 30
    enviar_alerta: Callable[..., bool] = alerta.enviar_alerta

    def run(self, periodo: int, solo_validar: bool = False) -> ResultadoPipeline:
        resultado = ResultadoPipeline(periodo=periodo)
        logger.info("[Trafico] Inicio del pipeline (User::Periodo=%s%s)", periodo, ", solo validar" if solo_validar else "")

        if not solo_validar:
            self._step("Log Inicio", lambda: loader.registrar_inicio(self.db_trafico))
            resultado.alerta_ok = self._step(
                "enviar_alerta_trafico",
                lambda: self.enviar_alerta(self.csv_reader, self.alerta_txt_path, self.alerta_segundos_espera),
            )

        extraidos = self._step("TEMPORALES / extraccion y validacion de los 7 CSV", lambda: self._extraer(periodo))
        if solo_validar:
            resultado.filas_temporales = {t: len(df) for t, df in extraidos.items()}
            logger.info("[Trafico] Validacion completada sin escribir en la base: %s", resultado)
            return resultado

        resultado.filas_temporales = self._step(
            "TEMPORALES / TRUNCA TABLAS + carga de las 7 temporales",
            lambda: loader.cargar_temporales(self.db_temporales, extraidos),
        )
        self._step("TEMPORALES / UPDATE", lambda: transformer.actualizar_temporales(self.db_temporales))
        self._step("LIMPIA TEMPORALES", lambda: transformer.limpiar_temporales(self.db_temporales))

        transformados = self._step("CL_TRAFICO / CARGA (lectura y transformacion)", self._transformar_carga)
        resultado.filas_cl_trafico = self._step(
            "CL_TRAFICO / DELETE PERIODO + CARGA (8 destinos)",
            lambda: loader.cargar_cl_trafico(self.db_trafico, periodo, transformados),
        )
        self._step("CL_TRAFICO / UPDATE_WSP", lambda: transformer.actualizar_wsp(self.db_temporales))
        self._step("Log Fin", lambda: loader.registrar_fin(self.db_trafico))

        logger.info("[Trafico] Pipeline finalizado correctamente: %s", resultado)
        return resultado

    def _extraer(self, periodo: int) -> dict:
        validator.validar_esquemas(self.db_temporales, self.db_trafico)
        extraidos = {}
        for origen in mappings.ORIGENES:
            df = extractor.extraer_origen(self.csv_reader, origen, periodo)
            validator.validar_origen(df, origen)
            extraidos[origen.tabla_temporal] = df
        return extraidos

    def _transformar_carga(self) -> dict:
        temporales = {
            origen.tabla_temporal: extractor.leer_temporal(self.db_temporales, origen.tabla_temporal)
            for origen in mappings.ORIGENES
        }
        return transformer.transformar_carga(temporales)

    def _step(self, descripcion: str, accion: Callable):
        logger.info("[Trafico] %s", descripcion)
        try:
            return accion()
        except Exception as exc:  # noqa: BLE001 - se re-lanza tipado como PipelineError
            raise PipelineError(self.name, descripcion, exc) from exc

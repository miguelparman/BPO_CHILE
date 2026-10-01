"""Orquestador: reproduce el Control Flow de Cl_Proc_Logueo.dtsx.

    Log Inicio -> [LOGUEO CHILE: CARGA TABLA -> AGREGA DNI] -> Log Fin -> SP   (BK: deshabilitada)

Todas las Precedence Constraints son 'Success' (no hay ramas de error), asi
que el primer paso que falla DETIENE el proceso, como el paquete: Log Fin no
se ejecuta y LOGS_PROCESOS queda en 'exec...'. Los pasos son seriales: cada
uno espera a que termine el anterior.

CARGA TABLA (Data Flow), por componentes:
    extraccion   Flat File Source 'Logueo'          (SharePoint/Graph)
    validacion   puntos FailComponent del Data Flow + controles previos
    transformacion  Dia_mes -> FechaAnsi -> Conversion de datos -> Lookup
    carga        Destino de OLE DB (fast load, un solo commit)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, TypeVar

import pandas as pd

from carga.loader import LogueoLoader
from exceptions import PipelineError
from extraccion.extractor import FuenteArchivo, extraer
from periodo import Periodo
from transformacion import lookup
from transformacion.transformer import transformar
from validacion import validator

logger = logging.getLogger("logueo")
T = TypeVar("T")

# refId de cada tarea del .dtsx, en el orden en que se ejecutan.
PASO_LOG_INICIO = "Log Inicio"
PASO_CARGA_TABLA = "LOGUEO CHILE\\CARGA TABLA"
PASO_AGREGA_DNI = "LOGUEO CHILE\\AGREGA DNI"
PASO_LOG_FIN = "Log Fin"
PASO_SP = "SP"
ORDEN_PASOS = (PASO_LOG_INICIO, PASO_CARGA_TABLA, PASO_AGREGA_DNI, PASO_LOG_FIN, PASO_SP)


@dataclass
class ResultadoPipeline:
    periodo: Periodo
    solo_validar: bool = False
    filas_archivo: int = 0
    filas_referencia: int = 0
    filas_coincidentes: int = 0
    filas_no_coincidentes: int = 0
    filas_insertadas: int = 0
    filas_dni: int | None = None
    pasos_ejecutados: list[str] = field(default_factory=list)
    df_transformado: pd.DataFrame | None = None  # todas las filas tras la Conversion
    df_nuevas: pd.DataFrame | None = None  # salida 'no coincidentes' del Lookup


class LogueoPipeline:
    def __init__(self, loader: LogueoLoader, fuente: FuenteArchivo, periodo: Periodo) -> None:
        self._loader = loader
        self._fuente = fuente
        self._periodo = periodo

    def run(self, solo_validar: bool = False) -> ResultadoPipeline:
        r = ResultadoPipeline(periodo=self._periodo, solo_validar=solo_validar)
        logger.info("Periodo (User::Periodo): %s", self._periodo)
        if solo_validar:
            logger.info("Modo --solo-validar: se extrae, valida, transforma y cruza con la referencia; no se escribe nada.")
            self._paso(r, PASO_CARGA_TABLA, lambda: self._carga_tabla(r, insertar=False))
            return r

        self._paso(r, PASO_LOG_INICIO, self._loader.log_inicio)
        self._paso(r, PASO_CARGA_TABLA, lambda: self._carga_tabla(r, insertar=True))
        r.filas_dni = self._paso(r, PASO_AGREGA_DNI, lambda: self._loader.agregar_dni(self._periodo.valor))
        logger.info("AGREGA DNI: %s filas actualizadas (periodo %s).", r.filas_dni, self._periodo.valor)
        self._paso(r, PASO_LOG_FIN, self._loader.log_fin)
        self._paso(r, PASO_SP, self._loader.sp_logueo)
        logger.info("BK (BACKUP DATABASE): deshabilitada en el .dtsx, no se ejecuta.")
        return r

    # ------------------------------------------------------------------ #
    def _carga_tabla(self, r: ResultadoPipeline, insertar: bool) -> None:
        # Pre-Execute del Data Flow: esquema del destino y cache del Lookup.
        esquema = self._loader.esquema_destino()
        validator.validar_esquema_destino(esquema)
        cache = lookup.construir_cache(self._loader.leer_referencia())
        r.filas_referencia = len(cache)
        logger.info("Lookup (Full Cache): %s claves de referencia en TBL_CONEXIONES.", r.filas_referencia)

        # Flat File Source
        logger.info("Leyendo %s", self._fuente.descripcion)
        archivo = extraer(self._fuente)
        validator.validar_archivo(archivo.cabecera, archivo.filas)
        df = archivo.a_dataframe()
        r.filas_archivo = len(df)
        logger.info("Flat File Source: %s filas.", r.filas_archivo)

        # Dia_mes -> FechaAnsi -> Conversion de datos
        validator.validar_casts(df)
        destino = transformar(df)
        validator.validar_conversion(destino)
        r.df_transformado = destino

        # Lookup: solo las NO coincidentes van al destino
        nuevas = lookup.filas_no_coincidentes(destino, cache)
        r.df_nuevas = nuevas
        r.filas_no_coincidentes = len(nuevas)
        r.filas_coincidentes = len(destino) - len(nuevas)
        logger.info("Lookup: %s coincidentes (descartadas), %s no coincidentes.", r.filas_coincidentes, r.filas_no_coincidentes)

        if insertar:
            r.filas_insertadas = self._loader.insertar(nuevas, esquema)
            logger.info("Destino de OLE DB: %s filas insertadas en TBL_CONEXIONES.", r.filas_insertadas)

    def _paso(self, r: ResultadoPipeline, paso: str, accion: Callable[[], T]) -> T:
        logger.info(">> %s", paso)
        try:
            resultado = accion()
        except Exception as exc:  # noqa: BLE001 - se identifica la tarea y se detiene (como SSIS)
            logger.error("<< %s FALLO: %s", paso, exc)
            raise PipelineError(paso, exc) from exc
        r.pasos_ejecutados.append(paso)
        logger.info("<< %s OK", paso)
        return resultado

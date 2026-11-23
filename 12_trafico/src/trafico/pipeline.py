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
from datetime import date
from pathlib import Path
from typing import Callable

import alerta
import mappings
import previsto
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
    # Previsto (TBL_PREVISTO_CL): opcional; sin db_data/previsto_reader el pipeline funciona como antes.
    db_data: object | None = None  # DatabaseGateway sobre CL_DATA
    previsto_reader: object | None = None  # CsvReader sobre la carpeta '15 PORTAL COMERCIAL'
    hoy: Callable[[], date] = previsto.hoy_chile

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
        archivo_previsto = self._previsto_extraer()
        if solo_validar:
            resultado.filas_temporales = {t: len(df) for t, df in extraidos.items()}
            resultado.previsto = self._previsto_ensayo(archivo_previsto)
            logger.info("[Trafico] Validacion completada sin escribir en la base: %s", resultado)
            return resultado

        resultado.filas_temporales = self._step(
            "TEMPORALES / TRUNCA TABLAS + carga de las 7 temporales",
            lambda: loader.cargar_temporales(self.db_temporales, extraidos),
        )
        resultado.previsto = self._previsto_cargar(archivo_previsto)
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

    # ------------------------------------------------------------------ #
    # Previsto (TBL_PREVISTO_CL). Un fallo aqui se REGISTRA y el trafico sigue: el previsto es
    # independiente y su carga es transaccional (si falla, la tabla queda como estaba).
    # ------------------------------------------------------------------ #
    def run_previsto(self, solo_validar: bool = False, solo_faltantes: bool = False) -> dict | None:
        """Solo el previsto (sin Log, alerta ni trafico): python main.py --solo-previsto.
        solo_faltantes=True (carga unica de relleno): inserta unicamente las llaves que faltan con
        Fecha <= hoy; no toca ni borra nada con Fecha > hoy y nunca modifica lo existente."""
        logger.info("[Trafico] Previsto: inicio%s%s", " (solo validar)" if solo_validar else "",
                    " (solo faltantes)" if solo_faltantes else "")
        archivo = self._previsto_extraer()
        if solo_validar:
            return self._previsto_ensayo(archivo, solo_faltantes)
        return self._previsto_cargar(archivo, solo_faltantes)

    def _previsto_activo(self) -> bool:
        return self.db_data is not None and self.previsto_reader is not None

    def _previsto_extraer(self):
        """Descarga y valida el CSV del previsto. None si no esta configurado; dict de error si fallo."""
        if not self._previsto_activo():
            return None
        try:
            logger.info("[Trafico] TEMPORALES / PREVISTO extraccion y validacion (%s)", previsto.ARCHIVO)
            return previsto.transformar(self.previsto_reader.read_csv(previsto.ARCHIVO))
        except Exception as exc:  # noqa: BLE001 - el previsto no detiene el trafico
            logger.error("[Trafico] PREVISTO fallo en extraccion/validacion (se omite, tabla intacta): %s", exc)
            return {"ok": False, "error": str(exc)}

    def _previsto_planificar(self, archivo, solo_faltantes: bool = False):
        hoy = self.hoy()
        existente, futuras = loader.leer_previsto_existente(self.db_data, archivo["Fecha"].min(), hoy)
        if solo_faltantes:  # relleno unico: el futuro no se toca (ni se borra ni se inserta)
            return previsto.planificar(archivo[archivo["Fecha"] <= hoy], existente, hoy, 0)
        return previsto.planificar(archivo, existente, hoy, futuras)

    def _previsto_omitir(self, archivo, solo_faltantes: bool) -> dict | None:
        """Condicion de ejecucion (pedido del usuario, 2026-11-23): el previsto solo se carga si el archivo
        trae registros con Fecha >= hoy (Chile); si no, se OMITE y la tabla queda como esta. No aplica al
        relleno unico --solo-faltantes, que por definicion usa archivos historicos. Devuelve el resultado
        de la omision, o None si hay que cargar."""
        if solo_faltantes:
            return None
        hoy = self.hoy()
        ultima = archivo["Fecha"].max()
        if ultima >= hoy:
            return None
        logger.info(
            "[Trafico] PREVISTO omitido: el archivo no trae registros con Fecha >= %s (ultima fecha: %s); la tabla se mantiene",
            hoy, ultima,
        )
        return {"ok": True, "omitido": f"sin registros >= {hoy} (ultima fecha del archivo: {ultima})"}

    def _previsto_ensayo(self, archivo, solo_faltantes: bool = False) -> dict | None:
        """--solo-validar: calcula que insertaria/reemplazaria, SIN escribir."""
        if not self._previsto_activo():
            return None
        if isinstance(archivo, dict):
            return archivo
        omitido = self._previsto_omitir(archivo, solo_faltantes)
        if omitido:
            return omitido
        try:
            plan = self._previsto_planificar(archivo, solo_faltantes)
        except Exception as exc:  # noqa: BLE001
            logger.error("[Trafico] PREVISTO fallo al planificar (se omite): %s", exc)
            return {"ok": False, "error": str(exc)}
        logger.info("[Trafico] PREVISTO (ensayo, sin escribir): %s", plan.resumen())
        return {"ok": True, "ensayo": True, "plan": plan.resumen()}

    def _previsto_cargar(self, archivo, solo_faltantes: bool = False) -> dict | None:
        if not self._previsto_activo():
            return None
        if isinstance(archivo, dict):  # fallo previo (ya registrado)
            return archivo
        omitido = self._previsto_omitir(archivo, solo_faltantes)
        if omitido:
            return omitido
        try:
            logger.info("[Trafico] TEMPORALES / PREVISTO carga acumulativa en CL_DATA")
            plan = self._previsto_planificar(archivo, solo_faltantes)
            logger.info("[Trafico]   PREVISTO plan: %s", plan.resumen())
            filas = loader.cargar_previsto(self.db_data, plan)
            logger.info("[Trafico]   PREVISTO cargado: %s", filas)
            return {"ok": True, **filas}
        except Exception as exc:  # noqa: BLE001
            logger.error("[Trafico] PREVISTO fallo en la carga (revertido, tabla intacta): %s", exc)
            return {"ok": False, "error": str(exc)}

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

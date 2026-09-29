"""Orquestador del pipeline EPA/WSP.

Migracion de CL_Proc_EPA_WSP.dtsx. Llama a las capas extraccion/,
validacion/, transformacion/ y carga/ (y a la alerta) en el orden del
Control Flow; no conoce pyodbc, Playwright ni Microsoft Graph (los recibe ya
construidos).

Control Flow original (Precedence Constraints "On Success"):

    Log_Inicio -> enviar_alerta_encuesta_py -+-> WSP     : TRUNCATE -> Traslado_..._WSP_MEDALLIA_py -+
                                             +-> EPA_ISN : TRUNCATE -> Traslado_..._EPA_ISN_py ------+-> SP_EPA_ISN_CHILE -> [Carga Azure] -+
                                             +-> MEDALIA : DESCARGA -> CARGA BASE -> SP_PROCESO_ENCUESTAS_MEDALLIA ----------------------+-> Log_Fin

Aqui se ejecuta EN SERIE, cada paso espera al anterior:

    1 Log_Inicio  2 alerta  3 WSP  4 EPA_ISN  5 SP_EPA_ISN_CHILE
    6 Carga Azure (DESHABILITADA en el .dtsx: no se ejecuta)  7 MEDALIA  8 Log_Fin

Manejo de fallos, igual que el .dtsx:
- Los 5 Execute Process tienen FailTaskIfReturnCodeIsNotSuccessValue=False:
  si el script falla, SSIS sigue. Aqui alerta, traslados WSP/EPA_ISN,
  descarga y carga de Medallia son pasos TOLERANTES: el error se registra y
  el proceso continua. Diferencia: un traslado que falla deja su tabla
  intacta (antes quedaba truncada).
- Las Execute SQL Task si detienen su rama: si falla Log_Inicio no se
  ejecuta nada mas; si falla un SP, Log_Fin no se ejecuta (LOGS_PROCESOS
  queda en 'exec...'), pero la otra rama (MEDALIA) se ejecuta igual, como en
  SSIS donde corria en paralelo.
- Con estricto=True (--estricto) cualquier fallo detiene el proceso.
El codigo de salida (main.py) es 1 si fallo cualquier paso, aunque sea tolerante.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

import alerta
import mappings
import sql
from carga import loader
from config import MedalliaSettings
from exceptions import PipelineError
from extraccion import extractor, medallia_descarga
from models import ResultadoPipeline
from transformacion import transformer
from validacion import validator

logger = logging.getLogger("epa_wsp")


@dataclass
class EpaWspPipeline:
    """Orquesta: extraccion -> validacion -> transformacion -> carga."""

    name = "epa_wsp"

    db_general: object  # DatabaseGateway '162.BBDD_GENERAL'
    db_calidad: object  # DatabaseGateway '162.CL_CALIDAD'
    db_indicadores: object  # DatabaseGateway '162.CL_TEMPORALES_INDICADORES'
    csv_reader: object  # sharepoint.reader.CsvReader
    medallia: MedalliaSettings
    carpeta_medallia: object  # sharepoint.carpeta.CarpetaSharePoint '16 MEDALLIA' (Encuestas_Medallia.csv y resultado.txt)
    alerta_archivo: str = "resultado.txt"
    alerta_segundos_espera: int = 30
    periodo_desde_encuesta: int = 202601
    estricto: bool = False
    enviar_alerta: Callable[..., bool] = alerta.enviar_alerta
    descargar_medallia: Callable[[MedalliaSettings, object], str] = medallia_descarga.descargar_encuestas
    leer_medallia: Callable[[object, str], object] = extractor.extraer_csv_medallia

    # ------------------------------------------------------------------ #
    def run(self, solo_validar: bool = False) -> ResultadoPipeline:
        r = ResultadoPipeline()
        logger.info("[EPA_WSP] Inicio del pipeline%s", " (solo validar)" if solo_validar else "")
        if solo_validar:
            return self._solo_validar(r)

        self._fatal("Log_Inicio", lambda: loader.registrar_inicio(self.db_general))
        r.alerta_ok = self._tolerante(
            r,
            "enviar_alerta_encuesta_py",
            lambda: self.enviar_alerta(
                self.csv_reader, self.carpeta_medallia, self.alerta_archivo, self.alerta_segundos_espera
            ),
        )

        # Rama WSP + EPA_ISN -> SP_EPA_ISN_CHILE
        self._tolerante(r, "WSP", lambda: self._trasladar(r, mappings.WSP))
        self._tolerante(r, "EPA_ISN", lambda: self._trasladar(r, mappings.ENCUESTA, self.periodo_desde_encuesta))
        rama_isn_ok = self._sql(r, "SP_EPA_ISN_CHILE", lambda: loader.ejecutar_sp(self.db_calidad, sql.SP_EPA_ISN_CHILE))
        logger.info("[EPA_WSP] Carga Azure: tarea DESHABILITADA en el .dtsx (Disabled=True); no se ejecuta.")

        # Rama MEDALIA
        r.medallia_descargado = self._tolerante(
            r, "MEDALIA / DESCARGA_MEDALLIA", lambda: self.descargar_medallia(self.medallia, self.carpeta_medallia) is not None
        )
        self._tolerante(r, "MEDALIA / CARGA BASE", lambda: self._cargar_medallia(r))
        rama_medallia_ok = self._sql(
            r,
            "MEDALIA / SP_PROCESO_ENCUESTAS_MEDALLIA",
            lambda: loader.ejecutar_sp(self.db_calidad, sql.SP_PROCESO_ENCUESTAS_MEDALLIA),
        )

        if rama_isn_ok and rama_medallia_ok:
            self._fatal("Log_Fin", lambda: loader.registrar_fin(self.db_general))
            r.log_fin = True
        else:
            logger.error("[EPA_WSP] Log_Fin no se ejecuta: fallo un SP (LOGS_PROCESOS queda en 'exec...').")

        nivel = logging.INFO if r.exitoso else logging.WARNING
        logger.log(nivel, "[EPA_WSP] Pipeline finalizado %s: %s", "correctamente" if r.exitoso else "CON ERRORES", r)
        return r

    # ------------------------------------------------------------------ #
    # Pasos
    # ------------------------------------------------------------------ #
    def _preparar(self, traslado: mappings.Traslado, periodo_desde: int | None = None):
        """Extraccion + validacion + transformacion de un traslado de SharePoint."""
        validator.validar_esquemas(self.db_indicadores, (traslado,))
        crudo = extractor.extraer_csv_sharepoint(self.csv_reader, traslado)
        if traslado is mappings.ENCUESTA:
            df = transformer.encuestas_chile(crudo, periodo_desde)
        else:
            df = transformer.wsp_medallia(crudo)
        validator.validar_anchos(df, traslado)
        periodos = validator.validar_periodos(df, traslado)
        return df, periodos

    def _trasladar(self, r: ResultadoPipeline, traslado: mappings.Traslado, periodo_desde: int | None = None) -> None:
        df, periodos = self._preparar(traslado, periodo_desde)
        r.filas[traslado.tabla] = loader.cargar_ventana(self.db_indicadores, traslado, df, periodos, periodo_desde)
        r.periodos[traslado.tabla] = periodos

    def _preparar_medallia(self, r: ResultadoPipeline):
        validator.validar_esquemas(self.db_indicadores, (mappings.MEDALLIA,))
        df, rechazadas = transformer.medallia(self.leer_medallia(self.carpeta_medallia, self.medallia.archivo))
        r.medallia_rechazadas = len(rechazadas)
        return df

    def _cargar_medallia(self, r: ResultadoPipeline) -> None:
        df = self._preparar_medallia(r)
        insertadas, errores = loader.cargar_medallia(self.db_indicadores, df)
        r.filas[mappings.MEDALLIA.tabla] = insertadas
        r.medallia_rechazadas += len(errores)
        logger.info(
            "[EPA_WSP]   Insercion Medallia finalizada. Registros con error: %s / %s",
            r.medallia_rechazadas, insertadas + r.medallia_rechazadas,
        )

    def _solo_validar(self, r: ResultadoPipeline) -> ResultadoPipeline:
        for traslado, desde in ((mappings.WSP, None), (mappings.ENCUESTA, self.periodo_desde_encuesta)):
            df, periodos = self._fatal(f"{traslado.tabla} (validar)", lambda t=traslado, d=desde: self._preparar(t, d))
            r.filas[traslado.tabla], r.periodos[traslado.tabla] = len(df), periodos
        df = self._fatal("TBL_ENCUESTAS_MEDALLIA (validar)", lambda: self._preparar_medallia(r))
        r.filas[mappings.MEDALLIA.tabla] = len(df)
        logger.info("[EPA_WSP] Validacion completada sin escribir en la base: %s", r)
        return r

    # ------------------------------------------------------------------ #
    # Politicas de fallo
    # ------------------------------------------------------------------ #
    def _fatal(self, paso: str, accion: Callable):
        logger.info("[EPA_WSP] %s", paso)
        try:
            return accion()
        except Exception as exc:  # noqa: BLE001 - se re-lanza tipado como PipelineError
            raise PipelineError(self.name, paso, exc) from exc

    def _tolerante(self, r: ResultadoPipeline, paso: str, accion: Callable):
        """Execute Process con FailTaskIfReturnCodeIsNotSuccessValue=False."""
        logger.info("[EPA_WSP] %s", paso)
        try:
            return accion()
        except Exception as exc:  # noqa: BLE001
            if self.estricto:
                raise PipelineError(self.name, paso, exc) from exc
            logger.error("[EPA_WSP] Fallo en '%s' (se continua, como en el .dtsx): %s", paso, exc)
            r.pasos_fallidos.append((paso, str(exc)))
            return None

    def _sql(self, r: ResultadoPipeline, paso: str, accion: Callable) -> bool:
        """Execute SQL Task: su fallo detiene la rama (no se ejecuta Log_Fin)."""
        logger.info("[EPA_WSP] %s", paso)
        try:
            accion()
            return True
        except Exception as exc:  # noqa: BLE001
            if self.estricto:
                raise PipelineError(self.name, paso, exc) from exc
            logger.error("[EPA_WSP] Fallo en '%s': %s", paso, exc)
            r.pasos_fallidos.append((paso, str(exc)))
            return False

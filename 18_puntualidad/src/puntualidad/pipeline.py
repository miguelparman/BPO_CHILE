"""Orquestador: ejecuta el Control Flow de SSIS_CL_Puntualidad.dtsx en su orden.

    SLA PRUEBA (TRUNCA TABLA -> TBL_SLA_CHILE -> UPDATE)  ->  PUNTUALIDAD

Reglas (las del .dtsx, con restriccion de precedencia 'Exito'):
  - PUNTUALIDAD empieza solo si SLA PRUEBA termino OK.
  - Si una tarea falla se detiene todo (PipelineError).

Diferencias con SSIS (ver docs/EQUIVALENCIA.md):
  - El Excel se descarga, valida y transforma ANTES de tocar la base. En SSIS el
    TRUNCATE corria primero, asi que un Excel malo dejaba TBL_SLA vacia.
  - Las 3 tareas de SLA PRUEBA van en una sola transaccion (TBL_SLA nunca queda
    vacia ni a medio actualizar).
  - PUNTUALIDAD se calcula con aritmetica de calendario en vez de llamar fila por
    fila a las funciones con WHILE (mismo resultado, verificado en equivalencia/).

solo_validar: lee, valida y transforma el Excel; no ejecuta ningun T-SQL de escritura.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Sequence

from carga.loader import PuntualidadLoader
from exceptions import PipelineError
from extraccion.extractor import FuenteExcel, leer_excel
from logging_setup import NOMBRE_LOGGER
from transformacion.transformer import transformar
from validacion.validator import validar_anchos_destino, validar_encabezados, validar_esquema_destino

logger = logging.getLogger(NOMBRE_LOGGER)

TAREA_SLA = "SLA PRUEBA"
TAREA_PUNTUALIDAD = "PUNTUALIDAD"
TAREAS = (TAREA_SLA, TAREA_PUNTUALIDAD)

OK = "OK"
OMITIDA = "OMITIDA"


@dataclass
class ResultadoTarea:
    tarea: str
    estado: str
    filas: int | None = None
    segundos: float = 0.0
    detalle: str = ""


@dataclass
class ResultadoCorrida:
    tareas: list[ResultadoTarea] = field(default_factory=list)


class PuntualidadPipeline:
    def __init__(self, loader: PuntualidadLoader, fuente: FuenteExcel | None, hoja: str) -> None:
        self._loader = loader
        self._fuente = fuente
        self._hoja = hoja

    def run(self, tareas: Sequence[str] = TAREAS, solo_validar: bool = False) -> ResultadoCorrida:
        resultado = ResultadoCorrida()
        destino = self._loader.destino
        logger.info("Destino (%s): %s | %s", destino.modo.upper(), destino.tbl_sla, destino.tbl_puntualidad)
        for tarea in tareas:
            logger.info("=" * 70)
            logger.info("Tarea %s%s", tarea, " (solo validar)" if solo_validar else "")
            inicio = time.monotonic()
            try:
                r = self._ejecutar(tarea, solo_validar)
            except Exception as exc:
                logger.error("[%s] -> FALLO", tarea)
                raise PipelineError(tarea, exc) from exc
            r.segundos = time.monotonic() - inicio
            resultado.tareas.append(r)
            filas = "" if r.filas is None else f" ({r.filas} filas)"
            logger.info("[%s] -> %s%s %.1f s %s", tarea, r.estado, filas, r.segundos, r.detalle)
        return resultado

    def _ejecutar(self, tarea: str, solo_validar: bool) -> ResultadoTarea:
        if tarea == TAREA_SLA:
            return self._sla(solo_validar)
        if tarea == TAREA_PUNTUALIDAD:
            if solo_validar:
                return ResultadoTarea(tarea, OMITIDA, detalle="(T-SQL no se ejecuta en solo validar)")
            return ResultadoTarea(tarea, OK, self._loader.generar_puntualidad())
        raise ValueError(f"Tarea desconocida: {tarea!r}")

    def preparar_sla(self) -> list[tuple]:
        """Excel Source -> Data Conversion: filas listas para TBL_SLA."""
        if self._fuente is None:
            raise ValueError("La tarea SLA necesita una fuente de Excel.")
        logger.info("  Origen: %s (hoja '%s')", self._fuente.describir(), self._hoja)
        encabezados, filas = leer_excel(self._fuente.leer(), self._hoja)
        posiciones = validar_encabezados(encabezados)
        esquema = self._loader.esquema_sla()
        validar_esquema_destino(esquema)
        convertidas = transformar(filas, posiciones)
        validar_anchos_destino(convertidas, esquema)
        logger.info("  %s filas validas para %s.", len(convertidas), self._loader.destino.tbl_sla)
        return convertidas

    def _sla(self, solo_validar: bool) -> ResultadoTarea:
        filas = self.preparar_sla()
        if solo_validar:
            return ResultadoTarea(TAREA_SLA, OMITIDA, len(filas), detalle="(validado, sin cargar)")
        return ResultadoTarea(TAREA_SLA, OK, self._loader.cargar_sla(filas), detalle="(TRUNCATE + carga + UPDATE)")

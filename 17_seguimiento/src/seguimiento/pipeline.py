"""Orquestador: ejecuta los paquetes CL_Seguimiento en el orden declarado
(02 -> 03 -> 04 -> 06 -> 07), cada uno con sus tareas en serie, como el
Control Flow de su .dtsx (sin las tareas redundantes, ver paquetes/).

Reglas (decision del usuario):
  - Un paquete empieza solo cuando el anterior termino OK.
  - Si una tarea falla, se detiene TODO: no se ejecutan las tareas
    siguientes del paquete (su 'Log Fin' tampoco, asi que LOGS_PROCESOS
    queda en 'exec...', como en SSIS) ni los paquetes siguientes.
  - Excepcion: 'Carga Descripciones NC' (06) registra su error como
    advertencia y el paquete continua (asi se comporta hoy en SSIS).

Optimizaciones (mismo resultado):
  - Todos los CSV se descargan EN PARALELO al empezar (FuentePrecargada);
    un error de descarga se informa recien cuando el paquete usa el archivo.
  - Cada paquete usa una sesion: sus staging son #temporales.
  - Data Flow: primero se leen, validan y transforman todos sus destinos y
    recien despues se carga, para no dejar una staging a medias.

solo_validar: lee, valida y transforma cada Data Flow contra el esquema real
de la staging; no ejecuta ningun T-SQL ni escribe nada.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Sequence

from carga.loader import SeguimientoLoader
from exceptions import PipelineError
from extraccion.extractor import FuenteArchivo, FuentePrecargada, leer_csv
from logging_setup import NOMBRE_LOGGER
from mappings import ARCHIVO_DESCRIPCIONES_NC, FlujoSpec
from paquetes import archivos_de
from paquetes.base import Paquete, TareaDataFlow, TareaDescripcionesNC, TareaSql, TareaTransaccion
from transformacion.cruce import aplicar_cruce
from transformacion.descripciones_nc import leer_descripciones_nc
from transformacion.transformer import transformar
from validacion.validator import validar_anchos_destino, validar_esquema, validar_estructura

logger = logging.getLogger(NOMBRE_LOGGER)

OK = "OK"
OMITIDA = "OMITIDA"
ADVERTENCIA = "ADVERTENCIA"


@dataclass
class ResultadoTarea:
    paquete: str
    tarea: str
    estado: str
    filas: int | None = None
    segundos: float = 0.0
    detalle: str = ""


@dataclass
class ResultadoCorrida:
    tareas: list[ResultadoTarea] = field(default_factory=list)

    @property
    def advertencias(self) -> list[ResultadoTarea]:
        return [t for t in self.tareas if t.estado == ADVERTENCIA]


class SeguimientoPipeline:
    def __init__(
        self, loader: SeguimientoLoader, fuente: FuenteArchivo, paquetes: Sequence[Paquete], descargas_paralelas: int = 4
    ) -> None:
        self._loader = loader
        self._fuente = fuente
        self._paquetes = tuple(paquetes)
        self._paralelas = descargas_paralelas

    def run(self, solo_validar: bool = False) -> ResultadoCorrida:
        archivos = archivos_de(self._paquetes)
        inicio = time.monotonic()
        fuente = FuentePrecargada(self._fuente, archivos, self._paralelas)
        if archivos:
            logger.info("%s archivo(s) descargados en paralelo en %.1f s.", len(archivos), time.monotonic() - inicio)
        resultado = ResultadoCorrida()
        for paquete in self._paquetes:
            logger.info("=" * 70)
            logger.info("Paquete %s: %s%s", paquete.codigo, paquete.dtsx, " (solo validar)" if solo_validar else "")
            inicio_paquete = time.monotonic()
            if not solo_validar:
                try:
                    self._loader.iniciar_paquete()
                except Exception as exc:
                    raise PipelineError(paquete.codigo, "(apertura de la sesion)", exc) from exc
            for tarea in paquete.tareas:
                inicio = time.monotonic()
                try:
                    r = self._ejecutar(paquete, tarea, fuente, solo_validar)
                except Exception as exc:
                    logger.error("[%s] %s -> FALLO", paquete.codigo, tarea.nombre)
                    raise PipelineError(paquete.codigo, tarea.nombre, exc) from exc
                r.segundos = time.monotonic() - inicio
                resultado.tareas.append(r)
                filas = "" if r.filas is None else f" ({r.filas} filas)"
                nivel = logging.WARNING if r.estado == ADVERTENCIA else logging.INFO
                logger.log(nivel, "[%s] %s -> %s%s %.1f s %s", paquete.codigo, tarea.nombre, r.estado, filas, r.segundos, r.detalle)
            logger.info("Paquete %s terminado en %.1f s.", paquete.codigo, time.monotonic() - inicio_paquete)
        return resultado

    # ------------------------------------------------------------------ #
    def _ejecutar(self, paquete: Paquete, tarea, fuente: FuenteArchivo, solo_validar: bool) -> ResultadoTarea:
        if isinstance(tarea, (TareaSql, TareaTransaccion)):
            if solo_validar:
                return ResultadoTarea(paquete.codigo, tarea.nombre, OMITIDA, detalle="(T-SQL no se ejecuta en solo validar)")
            if isinstance(tarea, TareaSql):
                filas = self._loader.ejecutar_sql(tarea.script)
                return ResultadoTarea(paquete.codigo, tarea.nombre, OK, None if filas < 0 else filas)
            filas = self._loader.ejecutar_transaccion([t.script for t in tarea.tareas])
            return ResultadoTarea(paquete.codigo, tarea.nombre, OK, None if filas[-1] < 0 else filas[-1])
        if isinstance(tarea, TareaDataFlow):
            return self._data_flow(paquete, tarea, fuente, solo_validar)
        if isinstance(tarea, TareaDescripcionesNC):
            return self._descripciones_nc(paquete, tarea, fuente, solo_validar)
        raise TypeError(f"Tarea desconocida: {tarea!r}")

    def _leer_transformar(self, flujo: FlujoSpec, fuente: FuenteArchivo) -> list[tuple]:
        """Flat File Source -> Derived Column -> Data Conversion de un archivo."""
        logger.info("  Origen: %s", fuente.describir(flujo.archivo))
        filas = leer_csv(fuente.leer(flujo.archivo), flujo.archivo)
        validar_estructura(flujo.archivo, filas)
        return transformar(flujo, filas)

    def preparar(self, flujo: FlujoSpec, fuente: FuenteArchivo) -> list[tuple]:
        """Filas validas para la #temporal del flujo (con el cruce, si tiene)."""
        esquema = self._loader.esquema(flujo.tabla)
        validar_esquema(flujo, esquema)
        filas = self._leer_transformar(flujo, fuente)
        if flujo.cruce:
            filas = aplicar_cruce(flujo, filas, self._leer_transformar(flujo.cruce.flujo, fuente))
        validar_anchos_destino(flujo, filas, esquema)
        logger.info("  %s: %s filas validas para [%s].", flujo.archivo.nombre, len(filas), flujo.tabla)
        return filas

    def _data_flow(self, paquete: Paquete, tarea: TareaDataFlow, fuente: FuenteArchivo, solo_validar: bool) -> ResultadoTarea:
        preparados = [(flujo, self.preparar(flujo, fuente)) for flujo in tarea.flujos]
        if solo_validar:
            return ResultadoTarea(paquete.codigo, tarea.nombre, OMITIDA, sum(len(f) for _, f in preparados), "(validado, sin cargar)")
        total = sum(self._loader.cargar_temporal(flujo, filas) for flujo, filas in preparados)
        return ResultadoTarea(paquete.codigo, tarea.nombre, OK, total)

    def _descripciones_nc(
        self, paquete: Paquete, tarea: TareaDescripcionesNC, fuente: FuenteArchivo, solo_validar: bool
    ) -> ResultadoTarea:
        try:
            logger.info("  Origen: %s", fuente.describir(ARCHIVO_DESCRIPCIONES_NC))
            filas = leer_descripciones_nc(fuente.leer(ARCHIVO_DESCRIPCIONES_NC))
            if solo_validar:
                return ResultadoTarea(paquete.codigo, tarea.nombre, OMITIDA, len(filas), "(leido, sin cargar)")
            insertadas = self._loader.cargar_descripciones_nc(filas)
            self._loader.ejecutar_sp_folios_nc()
            return ResultadoTarea(paquete.codigo, tarea.nombre, OK, insertadas, "(+ SP_FOLIOS_NC)")
        except Exception as exc:  # noqa: BLE001 - el script original atrapa todo y SSIS no falla la tarea
            return ResultadoTarea(
                paquete.codigo,
                tarea.nombre,
                ADVERTENCIA,
                detalle=f"Error al cargar los datos o ejecutar SP_FOLIOS_NC (el paquete continua, como en SSIS): {exc}",
            )

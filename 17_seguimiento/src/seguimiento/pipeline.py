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
  - Frescura (frescura.py): un archivo viejo, a medio publicar o sin filas
    no se carga; se omiten solo los bloques que lo usan (paquetes/base.Bloque)
    como advertencia, y la corrida continua. Si se omiten todos los bloques
    de un paquete, el paquete completo se omite (sin Log Inicio/Fin). El 07
    no tiene bloques: siempre corre.

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
from exceptions import ExtraccionError, PipelineError
from extraccion.extractor import FuenteArchivo, FuentePrecargada, leer_csv
from logging_setup import NOMBRE_LOGGER
from mappings import ARCHIVO_DESCRIPCIONES_NC, ArchivoSpec, FlujoSpec
from paquetes import archivos_de
from paquetes.base import Paquete, TareaDataFlow, TareaDescripcionesNC, TareaSql, TareaTransaccion
from transformacion.cruce import aplicar_cruce
from transformacion.descripciones_nc import leer_descripciones_nc
from transformacion.transformer import transformar
from validacion.validator import validar_anchos_destino, validar_esquema, validar_estructura

logger = logging.getLogger(NOMBRE_LOGGER)


def _sin_filas(fuente: FuenteArchivo, archivos: Sequence[ArchivoSpec]) -> dict[ArchivoSpec, str]:
    """Archivos descargados que no traen filas de datos (o ni encabezado):
    cargarlos vaciaria/no actualizaria nada util (y en Descripciones NC el
    TRUNCATE dejaria la tabla vacia), asi que se omiten como los viejos.
    Un error de descarga NO se trata aqui: se informa al usarlo, como antes."""
    vacios = {}
    for archivo in archivos:
        try:
            datos = fuente.leer(archivo)
        except Exception:  # noqa: BLE001 - error de descarga: lo levanta la tarea que lo use
            continue
        try:
            sin_filas = not leer_csv(datos, archivo)
        except ExtraccionError:
            sin_filas = True
        if sin_filas:
            vacios[archivo] = "el archivo no trae filas de datos"
            logger.warning("  [OMITIR] %s: el archivo no trae filas de datos.", archivo.nombre)
    return vacios


def _bloques_omitidos(paquete: Paquete, omitir: dict[ArchivoSpec, str]) -> dict[str, str]:
    """{bloque: motivo} de los bloques del paquete que usan un archivo omitido."""
    salida = {}
    for bloque in paquete.bloques:
        motivos = [f"{a.nombre}: {omitir[a]}" for a in bloque.archivos if a in omitir]
        if motivos:
            salida[bloque.nombre] = "; ".join(motivos)
    return salida


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

    def run(self, solo_validar: bool = False, omitir: dict[ArchivoSpec, str] | None = None) -> ResultadoCorrida:
        """'omitir': archivos que no se cargan (frescura.py) -> motivo. Se
        omiten solo los bloques que los usan; el resto continua."""
        omitir = dict(omitir or {})
        archivos = [a for a in archivos_de(self._paquetes) if a not in omitir]
        inicio = time.monotonic()
        fuente = FuentePrecargada(self._fuente, archivos, self._paralelas)
        if archivos:
            logger.info("%s archivo(s) descargados en paralelo en %.1f s.", len(archivos), time.monotonic() - inicio)
        omitir.update(_sin_filas(fuente, archivos))
        resultado = ResultadoCorrida()
        for paquete in self._paquetes:
            logger.info("=" * 70)
            logger.info("Paquete %s: %s%s", paquete.codigo, paquete.dtsx, " (solo validar)" if solo_validar else "")
            omitidos = _bloques_omitidos(paquete, omitir)
            if paquete.bloques and len(omitidos) == len(paquete.bloques):
                detalle = "paquete omitido completo (sin Log Inicio/Fin): " + "; ".join(omitidos.values())
                logger.warning("[%s] %s", paquete.codigo, detalle)
                resultado.tareas.append(ResultadoTarea(paquete.codigo, "(paquete completo)", ADVERTENCIA, detalle=detalle))
                continue
            inicio_paquete = time.monotonic()
            if not solo_validar:
                try:
                    self._loader.iniciar_paquete()
                except Exception as exc:
                    raise PipelineError(paquete.codigo, "(apertura de la sesion)", exc) from exc
            for tarea in paquete.tareas:
                bloque = paquete.bloque_de(tarea)
                if bloque and bloque.nombre in omitidos:
                    r = ResultadoTarea(paquete.codigo, tarea.nombre, ADVERTENCIA, detalle=f"omitida (bloque {bloque.nombre}): {omitidos[bloque.nombre]}")
                    resultado.tareas.append(r)
                    logger.warning("[%s] %s -> OMITIDA %s", paquete.codigo, tarea.nombre, r.detalle)
                    continue
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

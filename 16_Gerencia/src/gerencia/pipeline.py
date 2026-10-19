"""Orquestador: el Control Flow de CL_Proc_Volumetria_Gerencia.dtsx mas las
etapas nuevas de la migracion.

    0. Validar conexiones (conexiones.py; reintento cada 5 min, max. 3)
    1. Copia BPO -> ReportingFractalia (ingesta/copiar.py)
    2. 'Contenedor de secuencias 1': por cada flujo
         extraer -> validar -> transformar -> cargar (TRUNCATE+INSERT+DELETE)
    3. Resumen

En el .dtsx los 4 contenedores no tienen Precedence Constraints entre si
(corren en paralelo): un contenedor que falla no detiene a los otros, pero el
paquete termina en error. Aqui corren en serie con la misma semantica: un
flujo que falla (o cuyo archivo no se pudo copiar) se registra y se sigue con
el siguiente; ResultadoPipeline.ok es False si alguno fallo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Protocol, Sequence

from carga.loader import ResultadoCarga
from exceptions import GerenciaError
from extraccion.extractor import Fila
from ingesta.copiar import ResultadoCopia
from logging_setup import NOMBRE_LOGGER
from mappings import FlujoSpec
from validacion.validator import ResultadoValidacion

logger = logging.getLogger(NOMBRE_LOGGER)


class Copiador(Protocol):
    def copiar(self, flujos: Sequence[FlujoSpec]) -> list[ResultadoCopia]: ...


class Extractor(Protocol):
    def extraer(self, flujo: FlujoSpec) -> list[Fila]: ...


class Validador(Protocol):
    def validar(self, flujo: FlujoSpec, filas: Sequence[Fila]) -> ResultadoValidacion: ...


class Transformador(Protocol):
    def transformar(self, flujo: FlujoSpec, filas: Sequence[Fila]) -> list[tuple]: ...


class Cargador(Protocol):
    def cargar(self, flujo: FlujoSpec, filas: Sequence[tuple]) -> ResultadoCarga: ...


@dataclass(frozen=True)
class ResultadoFlujo:
    flujo: str
    filas_leidas: int = 0
    carga: ResultadoCarga | None = None
    error: str | None = None
    omitido: bool = False  # su archivo no se pudo copiar

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class ResultadoPipeline:
    copias: list[ResultadoCopia] = field(default_factory=list)
    flujos: list[ResultadoFlujo] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.copias) and all(f.ok for f in self.flujos)


class GerenciaPipeline:
    def __init__(
        self,
        flujos: Sequence[FlujoSpec],
        validar_conexiones: Callable[[], None] | None,
        copiador: Copiador | None,
        extractor: Extractor | None,
        validador: Validador,
        transformador: Transformador,
        cargador: Cargador | None,
    ) -> None:
        """copiador None = sin copia; extractor/cargador None = solo copia;
        cargador None con extractor = --solo-validar (no escribe en SQL)."""
        self._flujos = list(flujos)
        self._validar_conexiones = validar_conexiones
        self._copiador = copiador
        self._extractor = extractor
        self._validador = validador
        self._transformador = transformador
        self._cargador = cargador

    def run(self) -> ResultadoPipeline:
        resultado = ResultadoPipeline()
        if self._validar_conexiones is not None:
            self._validar_conexiones()  # ConexionError -> no se ejecuta nada

        omitidos: set[str] = set()
        if self._copiador is not None:
            logger.info("=== Copia BPO -> ReportingFractalia (%s archivo(s)) ===", len(self._flujos))
            resultado.copias = self._copiador.copiar(self._flujos)
            omitidos = {c.flujo for c in resultado.copias if not c.ok}

        if self._extractor is None:
            return resultado

        for flujo in self._flujos:
            logger.info("=== Contenedor '%s' -> %s ===", flujo.nombre, flujo.tabla)
            if flujo.nombre in omitidos:
                logger.error("[%s] No se carga: fallo la copia de su archivo (la tabla conserva su contenido).", flujo.nombre)
                resultado.flujos.append(
                    ResultadoFlujo(flujo.nombre, error="fallo la copia del archivo", omitido=True)
                )
                continue
            resultado.flujos.append(self._ejecutar_flujo(flujo))
        return resultado

    def _ejecutar_flujo(self, flujo: FlujoSpec) -> ResultadoFlujo:
        leidas = 0
        try:
            filas = self._extractor.extraer(flujo)
            leidas = len(filas)
            self._validador.validar(flujo, filas)
            convertidas = self._transformador.transformar(flujo, filas)
            if self._cargador is None:
                logger.info("[%s] --solo-validar: %s fila(s) listas, no se escribe en SQL.", flujo.nombre, len(convertidas))
                return ResultadoFlujo(flujo.nombre, leidas)
            return ResultadoFlujo(flujo.nombre, leidas, self._cargador.cargar(flujo, convertidas))
        except GerenciaError as exc:
            logger.error("[%s] Fallo el contenedor: %s", flujo.nombre, exc)
            return ResultadoFlujo(flujo.nombre, leidas, error=str(exc))

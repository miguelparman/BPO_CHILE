"""Orquestador: validar conexiones -> extraer -> transformar -> historico CSV ->
analisis de cruces -> Excel."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

import pandas as pd

from analisis import analizar
from extractor import Extractor
from logging_setup import NOMBRE_LOGGER
from salida import actualizar_historico, escribir_libro
from transformer import transformar

logger = logging.getLogger(NOMBRE_LOGGER)


@dataclass
class ResultadoPipeline:
    workspaces: int = 0
    datasets: int = 0
    informes: int = 0
    actualizaciones: int = 0
    horarios: int = 0
    errores: list[dict] = field(default_factory=list)
    hojas: dict[str, pd.DataFrame] = field(default_factory=dict)
    excel: Path | None = None
    csv: Path | None = None
    total_historico: int = 0
    nuevas_historico: int = 0


class BIServicePipeline:
    def __init__(
        self,
        validar: Callable[[], None] | None,
        extractor: Extractor,
        zona_horaria: str,
        salida_dir: Path | None,
        dias_analisis: int = 60,
    ) -> None:
        self._validar = validar
        self._extractor = extractor
        self._zona = zona_horaria
        self._salida_dir = salida_dir  # None = no escribe (--solo-leer)
        self._dias = dias_analisis

    def run(self, filtro_workspaces: Sequence[str] | None = None) -> ResultadoPipeline:
        if self._validar:
            self._validar()

        inventario = self._extractor.extraer(filtro_workspaces)
        tablas = transformar(inventario, self._zona)
        resultado = ResultadoPipeline(
            workspaces=len(tablas.workspaces),
            datasets=len(tablas.datasets),
            informes=len(tablas.informes),
            actualizaciones=len(tablas.actualizaciones),
            horarios=int(tablas.programacion["HORA_ORIGEN"].notna().sum()),
            errores=inventario.errores,
        )
        if not resultado.workspaces:
            logger.warning(
                "La app no ve ningun workspace: agregarla como miembro de los workspaces y habilitar "
                "'Las entidades de servicio pueden usar las API de Fabric' en el portal de administracion."
            )

        historico = tablas.actualizaciones
        if self._salida_dir is not None:
            historico, resultado.csv, resultado.nuevas_historico = actualizar_historico(
                tablas.actualizaciones, self._salida_dir, self._zona
            )
            resultado.total_historico = len(historico)

        resultado.hojas = {
            **analizar(tablas.programacion, historico, self._dias),
            "Datasets": tablas.datasets,
            "Actualizaciones": historico,
            "Informes": tablas.informes,
            "Workspaces": tablas.workspaces,
            "Errores": tablas.errores,
        }
        if self._salida_dir is not None:
            resultado.excel = escribir_libro(self._salida_dir, resultado.hojas)
        return resultado

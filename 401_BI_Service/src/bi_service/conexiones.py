"""Validacion de conexiones ANTES de ejecutar (mismo criterio que 16_Gerencia):
  - Se prueban todas las conexiones de la corrida.
  - Si alguna falla, se espera ESPERA_REINTENTO_S (300 s) y se vuelven a
    probar las que fallaron, hasta REINTENTOS_CONEXION (3) veces.
  - Si tras el ultimo reintento sigue fallando alguna -> ConexionError (exit 1).
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from config import PowerBISettings
from exceptions import ConexionError
from logging_setup import NOMBRE_LOGGER
from powerbi.client import PowerBIClient

logger = logging.getLogger(NOMBRE_LOGGER)

_LARGO_DETALLE = 200


@dataclass(frozen=True)
class Verificacion:
    nombre: str
    probar: Callable[[], None]  # levanta una excepcion si la conexion no responde


@dataclass(frozen=True)
class ResultadoConexion:
    nombre: str
    ok: bool
    segundos: float
    detalle: str | None = None


def _probar_powerbi(settings: PowerBISettings) -> None:
    """Token de la app + que la API responda a GET /groups."""
    PowerBIClient(settings).ping()


def _probar_salida(salida_dir: Path) -> None:
    """La carpeta de salida existe (o se puede crear) y se puede escribir."""
    salida_dir.mkdir(parents=True, exist_ok=True)
    prueba = salida_dir / f"~prueba_{uuid.uuid4().hex}.tmp"
    prueba.write_text("ok", encoding="utf-8")
    prueba.unlink()


def verificaciones_para(powerbi: PowerBISettings, salida_dir: Path | None) -> list[Verificacion]:
    verificaciones = [Verificacion("Power BI Service (API REST)", lambda: _probar_powerbi(powerbi))]
    if salida_dir is not None:
        verificaciones.append(Verificacion(f"Carpeta de salida {salida_dir}", lambda: _probar_salida(salida_dir)))
    return verificaciones


def _detalle(exc: Exception) -> str:
    texto = " ".join((str(exc) or type(exc).__name__).split())
    return texto if len(texto) <= _LARGO_DETALLE else texto[: _LARGO_DETALLE - 3] + "..."


def probar(verificaciones: Sequence[Verificacion]) -> list[ResultadoConexion]:
    resultados = []
    for verificacion in verificaciones:
        inicio = time.monotonic()
        try:
            verificacion.probar()
            resultados.append(ResultadoConexion(verificacion.nombre, True, time.monotonic() - inicio))
        except Exception as exc:  # cualquier fallo de la conexion cuenta como no disponible
            resultados.append(ResultadoConexion(verificacion.nombre, False, time.monotonic() - inicio, _detalle(exc)))
    return resultados


def _registrar(resultados: Sequence[ResultadoConexion]) -> None:
    for r in resultados:
        if r.ok:
            logger.info("  [OK]    %s (%.1f s)", r.nombre, r.segundos)
        else:
            logger.error("  [FALLO] %s (%.1f s): %s", r.nombre, r.segundos, r.detalle)


def validar_conexiones(
    verificaciones: Sequence[Verificacion],
    reintentos: int = 3,
    espera_s: float = 300,
    esperar: Callable[[float], None] = time.sleep,
) -> None:
    pendientes = list(verificaciones)
    logger.info("Validando %s conexion(es) antes de ejecutar...", len(pendientes))
    for intento in range(reintentos + 1):
        if intento:
            logger.warning(
                "Reintento %s de %s: se vuelven a probar %s conexion(es).", intento, reintentos, len(pendientes)
            )
        resultados = probar(pendientes)
        _registrar(resultados)
        fallidas = {r.nombre for r in resultados if not r.ok}
        if not fallidas:
            logger.info("Todas las conexiones responden.")
            return
        pendientes = [v for v in pendientes if v.nombre in fallidas]
        if intento < reintentos:
            logger.warning("Esperando %s s antes del siguiente reintento...", espera_s)
            esperar(espera_s)

    raise ConexionError(
        f"Sin conexion tras {reintentos} reintento(s) cada {espera_s} s: {', '.join(v.nombre for v in pendientes)}. "
        "No se ejecuto ninguna etapa."
    )

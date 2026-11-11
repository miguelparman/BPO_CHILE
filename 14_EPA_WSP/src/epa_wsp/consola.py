"""Avisos destacados en la consola cuando hay un error, y pregunta de reintento.

El proceso corre desatendido (tarea programada): si no hay una persona
delante (stdin no es una consola interactiva) NO se pregunta nada y se sigue
como antes. Con consola interactiva se muestran dos opciones: reintentar o no.
"""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger("epa_wsp")

_LINEA = "!" * 78


def avisar_error(titulo: str, detalle: object, accion: str = "") -> None:
    """Banner destacado (consola y .log) para que el error no pase desapercibido."""
    partes = [_LINEA, f"  ERROR: {titulo}", f"  Detalle: {detalle}"]
    if accion:
        partes.append(f"  {accion}")
    partes.append(_LINEA)
    logger.error("\n%s", "\n".join(partes))


def es_interactivo() -> bool:
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def preguntar_reintento(titulo: str) -> bool:
    """Pregunta en consola: [R] reintentar / [N] no reintentar. True = reintentar.

    Sin consola interactiva (tarea programada, pytest) devuelve False sin preguntar.
    """
    if not es_interactivo():
        return False
    while True:
        try:
            resp = input(f"\n>>> {titulo}\n>>> Elegir:  [R] Reintentar   [N] No reintentar  : ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        if resp in ("r", "s", "si", "y", "reintentar"):
            logger.info("Opcion elegida: reintentar.")
            return True
        if resp in ("n", "no"):
            logger.info("Opcion elegida: no reintentar.")
            return False
        print("Opcion no valida: escribir R o N.", flush=True)

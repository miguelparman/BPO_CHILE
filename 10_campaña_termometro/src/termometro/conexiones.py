"""
Validación de conexiones ANTES de ejecutar: si alguna no responde, no se
descarga, trunca ni carga nada.

- Se prueban TODAS las conexiones (aunque falle la primera) para dejar el
  panorama completo en el log.
- Si alguna falla, se espera ESPERA_REINTENTO_S (300 s = 5 min) y se vuelven a
  probar solo las que fallaron, hasta REINTENTOS_CONEXION (3) veces.
- Si tras el último reintento sigue fallando alguna, se levanta ConexionError
  y el proceso termina con error (exit 1).

Basado en 16_Gerencia/src/gerencia/conexiones.py.
"""
import logging
import re
import time
from dataclasses import dataclass
from typing import Callable, Sequence

from sqlalchemy import text

import db

logger = logging.getLogger(__name__)

_LARGO_DETALLE = 200


class ConexionError(RuntimeError):
    pass


@dataclass(frozen=True)
class Verificacion:
    nombre: str
    probar: Callable[[], None]  # levanta una excepción si la conexión no responde


def probar_sql(database_cartera: str) -> None:
    """Login en la BD principal + SELECT 1 + acceso a la BD de cartera (JOIN del paso final)."""
    with db.get_engine().connect() as conn:
        conn.execute(text("SELECT 1")).fetchall()
        acceso = conn.execute(text("SELECT HAS_DBACCESS(:bd)"), {"bd": database_cartera}).scalar()
        if acceso != 1:
            raise ConexionError(f"Sin acceso a la base de datos {database_cartera}")


def _detalle(exc: Exception) -> str:
    texto = str(exc) or type(exc).__name__
    respuesta = getattr(exc, "response", None)
    if respuesta is not None and getattr(respuesta, "status_code", None):
        texto = f"{texto} (HTTP {respuesta.status_code})"
    texto = re.sub(r"\(Background on this error at: [^)]*\)", "", texto)
    texto = " ".join(texto.replace("\\r", " ").replace("\\n", " ").split())
    texto = re.sub(r"\[Microsoft\]\[ODBC Driver [^\]]*\](\[SQL Server\])?", "", texto)
    return texto if len(texto) <= _LARGO_DETALLE else texto[: _LARGO_DETALLE - 3] + "..."


def _fallidas(verificaciones: Sequence[Verificacion]) -> list[Verificacion]:
    fallidas = []
    for verificacion in verificaciones:
        inicio = time.monotonic()
        try:
            verificacion.probar()
            logger.info("  [OK]    %s (%.1f s)", verificacion.nombre, time.monotonic() - inicio)
        except Exception as exc:  # cualquier fallo cuenta como conexión no disponible
            logger.error("  [FALLO] %s (%.1f s): %s", verificacion.nombre, time.monotonic() - inicio, _detalle(exc))
            fallidas.append(verificacion)
    return fallidas


def validar_conexiones(
    verificaciones: Sequence[Verificacion],
    reintentos: int = 3,
    espera_s: float = 300,
    esperar: Callable[[float], None] = time.sleep,
) -> None:
    """Prueba las conexiones; si alguna falla reintenta 'reintentos' veces cada
    'espera_s' segundos (solo las que fallaron). Levanta ConexionError si en el
    último reintento alguna sigue sin responder."""
    pendientes = list(verificaciones)
    logger.info("Validando %s conexión(es) antes de ejecutar...", len(pendientes))
    for intento in range(reintentos + 1):
        if intento:
            logger.warning("Reintento %s de %s: se vuelven a probar %s conexión(es).", intento, reintentos, len(pendientes))
        pendientes = _fallidas(pendientes)
        if not pendientes:
            logger.info("Todas las conexiones responden.")
            return
        if intento < reintentos:
            logger.warning("Esperando %s s antes del siguiente reintento...", espera_s)
            esperar(espera_s)

    raise ConexionError(
        f"Sin conexión tras {reintentos} reintento(s) cada {espera_s} s: {', '.join(v.nombre for v in pendientes)}. "
        "No se ejecutó ninguna etapa."
    )

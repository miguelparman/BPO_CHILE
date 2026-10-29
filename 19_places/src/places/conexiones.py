"""Validacion de conexiones ANTES de ejecutar: si alguna no responde, no se
lee, borra ni carga nada.

Politica (requerimiento del usuario), 100% automatica:
  - Se prueban TODAS las conexiones que usara la corrida (aunque falle la
    primera) para mostrar el panorama completo en el log.
  - Si alguna falla, se espera ESPERA_REINTENTO_S (300 s = 5 min) y se
    vuelven a probar las que fallaron, hasta REINTENTOS_CONEXION (3) veces.
  - Si tras el ultimo reintento sigue fallando alguna, se levanta
    ConexionError y el proceso termina (exit 1).

Misma politica que 16_Gerencia/conexiones.py.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Callable, Sequence

import mappings
from config import DbSettings, GraphSettings
from db import crear_conexion
from exceptions import ConexionError
from logging_setup import NOMBRE_LOGGER
from sharepoint.client import conectar

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


def _probar_sql(db: DbSettings) -> None:
    """Login + SELECT 1 + que existan las tablas que usa el paquete (TOP 0)."""
    conn = crear_conexion(db, reintentos=0)
    try:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT 1").fetchall()
            for tabla in (
                f"[{db.database}].[dbo].[{mappings.TABLA_PLACES}]",
                f"[{db.database}].[dbo].[{mappings.TABLA_HISTORICO}]",
                "[{}].[dbo].[{}]".format(*mappings.TABLA_PERSONAL),
                "[{}].[dbo].[{}]".format(*mappings.TABLA_LOGS),
            ):
                cursor.execute(f"SELECT TOP 0 * FROM {tabla}").fetchall()
        finally:
            cursor.close()
        conn.rollback()
    finally:
        conn.close()


def _probar_sharepoint(sp: GraphSettings) -> None:
    """Token del tenant + que exista el Excel 'Place utilizados.xlsx'."""
    cliente, drive_id = conectar(sp)
    cliente.get_item(drive_id, mappings.RUTA_REPORTING)


def verificaciones_para(leer_sharepoint: bool, cargar: bool, db: DbSettings, sp: GraphSettings) -> list[Verificacion]:
    """Conexiones que necesita la corrida:
    - lectura del Excel desde SharePoint (Microsoft Graph).
    - carga en las tablas: SQL Server."""
    verificaciones: list[Verificacion] = []
    if cargar:
        verificaciones.append(Verificacion(f"SQL Server {db.database} ({db.server})", lambda: _probar_sql(db)))
    if leer_sharepoint:
        verificaciones.append(
            Verificacion(
                f"Microsoft Graph {sp.site_path} / {sp.drive_name}", lambda: _probar_sharepoint(sp)
            )
        )
    return verificaciones


def _detalle(exc: Exception) -> str:
    texto = str(exc) or type(exc).__name__
    respuesta = getattr(exc, "response", None)
    if respuesta is not None and getattr(respuesta, "status_code", None):
        texto = f"{texto} (HTTP {respuesta.status_code})"
    # str() de un error pyodbc es el repr de una tupla: los saltos de linea
    # llegan escritos como '\r\n' literal.
    texto = " ".join(texto.replace("\\r", " ").replace("\\n", " ").split())
    texto = re.sub(r"\[Microsoft\]\[ODBC Driver [^\]]*\](\[SQL Server\])?", "", texto)
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
    """Prueba las conexiones; si alguna falla reintenta 'reintentos' veces
    cada 'espera_s' segundos (solo las que fallaron). Levanta ConexionError
    si en el ultimo reintento alguna sigue sin responder."""
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

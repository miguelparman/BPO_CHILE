"""Validacion de conexiones ANTES de ejecutar: si alguna no responde, no se
copia, borra ni carga nada.

Politica (requerimiento del usuario), 100% automatica:
  - Se prueban TODAS las conexiones que usara la corrida (aunque falle la
    primera) para mostrar el panorama completo en el log.
  - Si alguna falla, se espera ESPERA_REINTENTO_S (300 s = 5 min) y se
    vuelven a probar las que fallaron, hasta REINTENTOS_CONEXION (3) veces.
  - Si tras el ultimo reintento sigue fallando alguna, se levanta
    ConexionError y el proceso termina (exit 1).

Basado en 11_correos/src/correos/comun/conexiones.py, sin la pregunta
interactiva [R]eintentar/[C]ancelar (aqui no hay nadie frente a la consola).
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Callable, Sequence

from config import DbSettings, GraphSettings
from db import crear_conexion
from exceptions import ConexionError
from logging_setup import NOMBRE_LOGGER
from mappings import FlujoSpec
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


def _probar_sql(db: DbSettings, flujos: Sequence[FlujoSpec]) -> None:
    """Login + SELECT 1 + que existan las tablas destino (TOP 0)."""
    conn = crear_conexion(db, reintentos=0)
    try:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT 1").fetchall()
            for flujo in flujos:
                cursor.execute(f"SELECT TOP 0 * FROM [dbo].[{flujo.tabla}]").fetchall()
        finally:
            cursor.close()
        conn.rollback()
    finally:
        conn.close()


def _probar_origen(origen: GraphSettings, flujos: Sequence[FlujoSpec]) -> None:
    """Token del tenant 'BPO' + que existan los Excel a copiar."""
    cliente, drive_id = conectar(origen)
    for flujo in flujos:
        cliente.get_item(drive_id, flujo.ruta_bpo)


def _probar_destino(destino: GraphSettings, flujos: Sequence[FlujoSpec], exigir_archivos: bool) -> None:
    """Token del tenant 'ReportingFractalia' + que existan las carpetas
    destino (y los Excel, si no se copiaran en esta corrida)."""
    cliente, drive_id = conectar(destino)
    for flujo in flujos:
        if exigir_archivos:
            cliente.get_item(drive_id, flujo.ruta_reporting)
        else:
            cliente.resolve_folder(drive_id, flujo.carpeta_reporting)


def verificaciones_para(
    flujos: Sequence[FlujoSpec],
    copiar: bool,
    leer_sharepoint: bool,
    cargar: bool,
    db: DbSettings,
    origen: GraphSettings,
    destino: GraphSettings,
) -> list[Verificacion]:
    """Conexiones que necesita la corrida:
    - copia (BPO -> Reporting): BPO y Reporting.
    - lectura de los Excel desde SharePoint: Reporting.
    - carga en la tabla: SQL Server.
    """
    verificaciones: list[Verificacion] = []
    if cargar:
        verificaciones.append(
            Verificacion(f"SQL Server {db.database} ({db.server})", lambda: _probar_sql(db, flujos))
        )
    if copiar:
        verificaciones.append(
            Verificacion(f"SharePoint origen {origen.site_path}", lambda: _probar_origen(origen, flujos))
        )
    if copiar or leer_sharepoint:
        verificaciones.append(
            Verificacion(
                f"SharePoint destino {destino.site_path} / {destino.drive_name}",
                lambda: _probar_destino(destino, flujos, exigir_archivos=not copiar),
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

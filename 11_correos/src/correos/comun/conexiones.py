"""Validacion de conexiones ANTES de ejecutar cualquier etapa: si alguna no
responde, el ETL no se ejecuta (no se copia, borra ni carga nada) y se
pregunta en consola si reintentar o cancelar.

- Solo se prueban las conexiones que usan las etapas de la corrida (ver
  verificaciones_para()).
- Se prueban TODAS (aunque falle la primera), para mostrar el panorama
  completo; un reintento vuelve a probar solo las que fallaron.
- Sin respuesta en ESPERA_RESPUESTA_S (o sin consola, ej. tarea programada
  sin nadie frente al PC): se reintenta solo hasta REINTENTOS_AUTOMATICOS
  veces, cada ESPERA_ENTRE_REINTENTOS_S, y si sigue fallando se cancela.
- La cancelacion queda solo en el archivo de logs/ (no en
  TBL_CORREO_LOG_EJECUCION: decision del usuario).
"""

from __future__ import annotations

import logging
import re
import sys
import time
from dataclasses import dataclass
from typing import Callable

from comun.config import DbSettings, Settings
from comun.db import crear_conexion
from comun.logging_setup import NOMBRE_LOGGER
from comun.sharepoint_auth import get_graph_token
from comun.sharepoint_client import SharePointClient, conectar_destino
from silver.mappings import TABLA_HISTORICO_PLACES, TABLA_SEGUIMIENTO

logger = logging.getLogger(NOMBRE_LOGGER)

ESPERA_RESPUESTA_S = 300
REINTENTOS_AUTOMATICOS = 3
ESPERA_ENTRE_REINTENTOS_S = 300

REINTENTAR = "R"
CANCELAR = "C"

_LARGO_DETALLE = 200
_SEPARADOR = "=" * 60


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


def _probar_sql(db: DbSettings, consulta: str) -> None:
    conn = crear_conexion(db)
    try:
        cursor = conn.cursor()
        try:
            cursor.execute(consulta)
            if cursor.description:
                cursor.fetchall()
        finally:
            cursor.close()
    finally:
        conn.close()


def _probar_origen(settings: Settings) -> None:
    origen = settings.origen
    token = get_graph_token(origen.tenant_id, origen.client_id, origen.client_secret, origen.timeout_ms)
    cliente = SharePointClient(token, origen.timeout_ms)
    drive_id = cliente.resolve_default_drive(cliente.resolve_site(origen.hostname, origen.site_path))
    cliente.resolve_folder(drive_id, origen.folder_path)


def _probar_destino(settings: Settings) -> None:
    cliente, drive_id = conectar_destino(settings.destino)
    cliente.resolve_folder(drive_id, settings.destino.folder_path)


def verificaciones_para(
    etapas: list[str], verificar_copia: bool, settings: Settings, db: DbSettings | None
) -> list[Verificacion]:
    """Conexiones que necesita la corrida. --verificar-copia solo usa
    SharePoint; el resto siempre usa CL_MOVIL (log de ejecucion)."""
    destino = f"SharePoint destino {settings.destino.site_path} / {settings.destino.folder_path}"
    origen = f"SharePoint origen {settings.origen.site_path} / {settings.origen.folder_path}"
    if verificar_copia:
        return [
            Verificacion(origen, lambda: _probar_origen(settings)),
            Verificacion(destino, lambda: _probar_destino(settings)),
        ]

    verificaciones = [Verificacion(f"SQL Server {db.database} ({db.server})", lambda: _probar_sql(db, "SELECT 1"))]
    if "silver" in etapas:
        for tabla in (TABLA_HISTORICO_PLACES, TABLA_SEGUIMIENTO):
            verificaciones.append(
                Verificacion(f"SQL {tabla}", lambda tabla=tabla: _probar_sql(db, f"SELECT TOP 0 * FROM {tabla}"))
            )
    if "ingesta" in etapas:
        verificaciones.append(Verificacion(origen, lambda: _probar_origen(settings)))
    if "ingesta" in etapas or "bronze" in etapas:
        verificaciones.append(Verificacion(destino, lambda: _probar_destino(settings)))
    return verificaciones


def _detalle(exc: Exception) -> str:
    texto = str(exc) or type(exc).__name__
    respuesta = getattr(exc, "response", None)
    if respuesta is not None and getattr(respuesta, "status_code", None):
        texto = f"{texto} (HTTP {respuesta.status_code})"
    # str() de un error pyodbc es el repr de una tupla: los saltos de linea
    # llegan escritos como '\r\n' literal.
    texto = " ".join(texto.replace("\\r", " ").replace("\\n", " ").split())
    # pyodbc: "('28000', '[28000] [Microsoft][ODBC Driver 18 for SQL Server][SQL Server]Mensaje (18456) ...')"
    texto = re.sub(r"\[Microsoft\]\[ODBC Driver [^\]]*\](\[SQL Server\])?", "", texto)
    return texto if len(texto) <= _LARGO_DETALLE else texto[: _LARGO_DETALLE - 3] + "..."


def probar(verificaciones: list[Verificacion]) -> list[ResultadoConexion]:
    resultados = []
    for verificacion in verificaciones:
        inicio = time.monotonic()
        try:
            verificacion.probar()
            resultados.append(ResultadoConexion(verificacion.nombre, True, time.monotonic() - inicio))
        except Exception as exc:  # cualquier fallo de la conexion cuenta como no disponible
            resultados.append(ResultadoConexion(verificacion.nombre, False, time.monotonic() - inicio, _detalle(exc)))
    return resultados


def _mostrar(resultados: dict[str, ResultadoConexion]) -> None:
    ancho = max(len(nombre) for nombre in resultados)
    logger.info(_SEPARADOR)
    logger.info(" VALIDACION DE CONEXIONES")
    logger.info(_SEPARADOR)
    for r in resultados.values():
        if r.ok:
            logger.info(" [OK]    %s (%.1f s)", r.nombre.ljust(ancho), r.segundos)
        else:
            logger.error(" [FALLA] %s -> %s", r.nombre.ljust(ancho), r.detalle)
    logger.info("-" * 60)


def hay_consola() -> bool:
    """True si stdin es una consola donde alguien puede responder. En Windows
    isatty() tambien es True con stdin redirigido a NUL, por eso se pregunta
    a la API de consola."""
    if sys.stdin is None or not sys.stdin.isatty():
        return False
    if sys.platform != "win32":
        return True
    import ctypes
    import msvcrt

    modo = ctypes.c_uint32()
    return bool(ctypes.windll.kernel32.GetConsoleMode(msvcrt.get_osfhandle(sys.stdin.fileno()), ctypes.byref(modo)))


def leer_con_timeout(mensaje: str, timeout_s: float) -> str | None:
    """Lee una linea de la consola esperando como maximo timeout_s. None si
    no hay respuesta a tiempo o no hay consola (ver hay_consola())."""
    if not hay_consola():
        logger.warning("Sin consola para responder: se toma como sin respuesta.")
        return None
    print(mensaje, end="", flush=True)
    if sys.platform == "win32":
        import msvcrt

        fin = time.monotonic() + timeout_s
        texto = ""
        while time.monotonic() < fin:
            if not msvcrt.kbhit():
                time.sleep(0.1)
                continue
            caracter = msvcrt.getwche()
            if caracter in ("\r", "\n"):
                print(flush=True)
                return texto
            texto = texto[:-1] if caracter == "\b" else texto + caracter
        print(flush=True)
        return None

    import select

    listo, _, _ = select.select([sys.stdin], [], [], timeout_s)
    if not listo:
        print(flush=True)
        return None
    return sys.stdin.readline()


def preguntar_reintento(leer: Callable[[str, float], str | None] = leer_con_timeout) -> str | None:
    """REINTENTAR / CANCELAR, o None si no hubo respuesta a tiempo. Una
    respuesta invalida vuelve a preguntar."""
    while True:
        respuesta = leer(
            f" El ETL NO se ejecutara. ¿Reintentar? [R] Reintentar / [C] Cancelar "
            f"(sin respuesta en {ESPERA_RESPUESTA_S // 60} min se reintenta solo): ",
            ESPERA_RESPUESTA_S,
        )
        if respuesta is None:
            return None
        respuesta = respuesta.strip().upper()
        if respuesta in (REINTENTAR, CANCELAR):
            return respuesta
        print(f" Opcion no valida: '{respuesta}'. Escribe R o C.", flush=True)


def validar_conexiones(
    verificaciones: list[Verificacion],
    preguntar: Callable[[], str | None] = preguntar_reintento,
    esperar: Callable[[float], None] = time.sleep,
) -> bool:
    """True si todas las conexiones responden (a la primera o tras
    reintentar). False si el usuario cancela o se agotan los reintentos
    automaticos: en ese caso el ETL no debe ejecutarse."""
    resultados = {r.nombre: r for r in probar(verificaciones)}
    _mostrar(resultados)
    reintentos_automaticos = 0
    modo_automatico = False

    while True:
        fallidas = [v for v in verificaciones if not resultados[v.nombre].ok]
        if not fallidas:
            logger.info("Todas las conexiones responden: se ejecuta el ETL.")
            return True

        if modo_automatico:
            if reintentos_automaticos >= REINTENTOS_AUTOMATICOS:
                logger.error(
                    "Conexiones no disponibles tras %s reintento(s) automatico(s): %s. El ETL NO se ejecuta.",
                    REINTENTOS_AUTOMATICOS,
                    ", ".join(v.nombre for v in fallidas),
                )
                return False
            if reintentos_automaticos:
                logger.info("Esperando %s s antes del siguiente reintento...", ESPERA_ENTRE_REINTENTOS_S)
                esperar(ESPERA_ENTRE_REINTENTOS_S)
            reintentos_automaticos += 1
            logger.warning("Reintento automatico %s de %s.", reintentos_automaticos, REINTENTOS_AUTOMATICOS)
        else:
            respuesta = preguntar()
            if respuesta == CANCELAR:
                logger.error(
                    "Cancelado por el usuario: conexiones no disponibles (%s). El ETL NO se ejecuta.",
                    ", ".join(v.nombre for v in fallidas),
                )
                return False
            if respuesta is None:
                logger.warning(
                    "Sin respuesta (o sin consola): se reintenta automaticamente hasta %s vez/veces, cada %s s.",
                    REINTENTOS_AUTOMATICOS,
                    ESPERA_ENTRE_REINTENTOS_S,
                )
                modo_automatico = True
                continue
            logger.info("Reintentando las conexiones que fallaron...")

        resultados.update({r.nombre: r for r in probar(fallidas)})
        _mostrar(resultados)

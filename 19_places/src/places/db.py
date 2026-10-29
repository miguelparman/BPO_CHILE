"""Acceso a SQL Server: fabrica de conexiones (pyodbc) y el gateway que usan
las capas de carga y la herramienta de equivalencia.

Reutilizado de 16_Gerencia/15_Logueo (reintento de login, reconexion ante
conexiones cortadas por inactividad, rollback silencioso). Una instancia de
DatabaseGateway equivale al Connection Manager OLE DB '162.CL_DATA' del
.dtsx, que usan todas las tareas del paquete.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Sequence

import pyodbc

from config import DbSettings
from exceptions import CargaError
from logging_setup import NOMBRE_LOGGER

logger = logging.getLogger(NOMBRE_LOGGER)

_DRIVERS_PREFERIDOS = ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server")


def _resolver_driver(configurado: str) -> str:
    """Devuelve el driver ODBC a usar: el configurado (DB_DRIVER) si esta
    instalado en esta maquina; si no, el mas nuevo de los instalados."""
    instalados = pyodbc.drivers()
    nombre = configurado.strip().strip("{}")
    if nombre in instalados:
        return nombre
    for candidato in _DRIVERS_PREFERIDOS:
        if candidato in instalados:
            logger.warning("Driver ODBC '%s' no instalado; se usa '%s'.", nombre, candidato)
            return candidato
    return nombre


def cadena_conexion(settings: DbSettings) -> str:
    return (
        f"DRIVER={{{_resolver_driver(settings.driver)}}};"
        f"SERVER={settings.server};"
        f"DATABASE={settings.database};"
        f"UID={settings.user};"
        f"PWD={settings.password};"
        f"Encrypt={settings.encrypt};"
        f"TrustServerCertificate={settings.trust_server_certificate}"
    )


def crear_conexion(
    settings: DbSettings,
    reintentos: int = 1,
    espera_s: float = 5,
    dormir: Callable[[float], None] = time.sleep,
    conectar: Callable[..., pyodbc.Connection] = pyodbc.connect,
) -> pyodbc.Connection:
    """Abre la conexion con un reintento corto (un login puede fallar
    puntualmente con error 4060 y funcionar al segundo intento). Los
    reintentos largos (5 min) son de conexiones.py, antes de empezar."""
    for intento in range(reintentos + 1):
        try:
            conn = conectar(cadena_conexion(settings), autocommit=False)
            break
        except pyodbc.Error as exc:
            if intento >= reintentos:
                raise
            logger.warning("No se pudo conectar a %s (%s); reintento en %s s.", settings.database, exc, espera_s)
            dormir(espera_s)
    conn.timeout = 0  # sin limite por consulta, como CommandTimeout=0 de las tareas
    return conn


def _rollback_silencioso(conn: pyodbc.Connection) -> None:
    try:
        conn.rollback()
    except pyodbc.Error as exc:
        logger.warning("No se pudo hacer rollback (conexion caida, el servidor descarta la transaccion): %s", exc)


# Tipos de parametro para setinputsizes (fast_executemany infiere el buffer
# del primer valor del lote y truncaria/fallaria con valores mas largos).
PARAM_TEXTO = "texto"


def _input_size(ancho: int | None) -> tuple:
    # NVARCHAR: el servidor convierte a la code page de la columna (1252),
    # igual que el destino OLE DB con DT_STR 1252.
    return (pyodbc.SQL_WVARCHAR, ancho or 255, 0)


class DatabaseGateway:
    """Envuelve una conexion pyodbc con las operaciones del paquete.

    Recibe una FABRICA de conexiones: antes de cada operacion se verifica la
    conexion con 'SELECT 1' y, si el servidor la corto por inactividad, se
    abre una nueva."""

    def __init__(self, fabrica_conexion: Callable[[], pyodbc.Connection], batch_size: int = 5000, nombre: str = "") -> None:
        self._fabrica = fabrica_conexion
        self._conn: pyodbc.Connection | None = None
        self._batch_size = batch_size
        self.nombre = nombre

    def _asegurar_conexion(self) -> pyodbc.Connection:
        if self._conn is not None:
            try:
                cursor = self._conn.cursor()
                try:
                    cursor.execute("SELECT 1").fetchall()
                finally:
                    cursor.close()
                return self._conn
            except pyodbc.Error as exc:
                logger.warning("Conexion a %s caida (%s); se abre una nueva.", self.nombre or "SQL Server", exc)
                self.cerrar()
        self._conn = self._fabrica()
        return self._conn

    def cerrar(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except pyodbc.Error:
                pass
            self._conn = None

    def run_query(self, sql: str, params: Sequence[Any] | None = None) -> tuple[list[str], list[tuple]]:
        """(columnas, filas) de una consulta de lectura."""
        try:
            conn = self._asegurar_conexion()
            cursor = conn.cursor()
            try:
                cursor.execute(sql, tuple(params) if params else ())
                columnas = [col[0] for col in cursor.description]
                filas = [tuple(f) for f in cursor.fetchall()]
            finally:
                cursor.close()
            conn.commit()  # cierra la transaccion implicita de lectura
        except Exception as exc:
            raise CargaError(f"Fallo la consulta: {exc}") from exc
        return columnas, filas

    def ejecutar_en_transaccion(self, pasos: Sequence[tuple[str, Sequence[Any] | None]]) -> list[int]:
        """Sentencias (o lotes T-SQL) en UNA transaccion: commit al final o
        rollback completo. Devuelve el rowcount de cada una. Una sola
        sentencia equivale a una Execute SQL Task."""
        conn = self._asegurar_conexion()
        conteos: list[int] = []
        try:
            cursor = conn.cursor()
            try:
                for sql, params in pasos:
                    cursor.execute(sql, tuple(params) if params else ())
                    conteos.append(cursor.rowcount)
                    while cursor.nextset():  # consumir los conteos de un lote de varias sentencias
                        pass
            finally:
                cursor.close()
            conn.commit()
        except Exception as exc:
            _rollback_silencioso(conn)
            raise CargaError(f"Fallo la ejecucion (rollback completo): {exc}") from exc
        return conteos

    def recargar_tabla(
        self,
        sql_truncate: str,
        insert_sql: str,
        filas: Sequence[tuple],
        anchos: Sequence[int],
        sql_limpia: str,
    ) -> tuple[int, int]:
        """TRUNCATE -> INSERT por lotes -> limpieza en UNA transaccion: commit
        al final o rollback completo (la tabla conserva los datos anteriores).
        Devuelve (filas_insertadas, filas_borradas_por_el_DELETE_de_la_limpieza)."""
        conn = self._asegurar_conexion()
        insertadas = 0
        try:
            cursor = conn.cursor()
            try:
                cursor.execute(sql_truncate)
                if filas:
                    cursor.fast_executemany = True
                    cursor.setinputsizes([_input_size(a) for a in anchos])
                    for inicio in range(0, len(filas), self._batch_size):
                        lote = list(filas[inicio : inicio + self._batch_size])
                        cursor.executemany(insert_sql, lote)
                        insertadas += len(lote)
                cursor.execute(sql_limpia)
                borradas = cursor.rowcount  # primera sentencia del lote: DELETE ... WHERE ID IS NULL
                while cursor.nextset():  # consumir los conteos del UPDATE
                    pass
            finally:
                cursor.close()
            conn.commit()
        except Exception as exc:
            _rollback_silencioso(conn)
            raise CargaError(f"Fallo la recarga (rollback completo, la tabla queda como estaba): {exc}") from exc
        return insertadas, max(borradas, 0)

"""Acceso a SQL Server: fabrica de conexiones (pyodbc) y el gateway que usan
las capas de carga y la herramienta de equivalencia.

Reutilizado de 15_Logueo/14_EPA_WSP (reintento de login, reconexion ante
conexiones cortadas por inactividad, rollback silencioso). Una instancia de
DatabaseGateway equivale al Connection Manager OLE DB '162.CL_MOVIL' del
.dtsx, que usan las 12 tareas del paquete.
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


def cadena_conexion(settings: DbSettings) -> str:
    return (
        f"DRIVER={{{settings.driver}}};"
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
PARAM_FECHA = "fecha"


def _input_size(tipo: str, ancho: int | None) -> tuple:
    if tipo == PARAM_FECHA:
        return (pyodbc.SQL_TYPE_DATE, 0, 0)
    # NVARCHAR: el servidor convierte a la code page de la columna (1252),
    # igual que el destino OLE DB con DT_STR 1252.
    return (pyodbc.SQL_WVARCHAR, ancho or 255, 0)


class DatabaseGateway:
    """Envuelve una conexion pyodbc con las operaciones del paquete.

    Recibe una FABRICA de conexiones: antes de cada operacion se verifica la
    conexion con 'SELECT 1' y, si el servidor la corto por inactividad (visto
    en 12_trafico mientras se descargaba de SharePoint), se abre una nueva."""

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

    def columnas_de_tabla(self, table: str, schema: str = "dbo") -> dict[str, tuple[str, int | None]]:
        """{columna: (tipo, largo)} segun INFORMATION_SCHEMA (largo -1 = MAX)."""
        _, filas = self.run_query(
            "SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH "
            "FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? "
            "ORDER BY ORDINAL_POSITION",
            (schema, table),
        )
        return {nombre: (tipo, None if largo is None else int(largo)) for nombre, tipo, largo in filas}

    def recargar_tabla(
        self,
        sql_truncate: str,
        insert_sql: str,
        filas: Sequence[tuple],
        tipos: Sequence[tuple[str, int | None]],
        sql_delete: str,
    ) -> tuple[int, int]:
        """TRUNCATE -> INSERT por lotes -> DELETE en UNA transaccion: commit
        al final o rollback completo (la tabla conserva los datos anteriores).
        Devuelve (filas_insertadas, filas_borradas_por_el_delete)."""
        conn = self._asegurar_conexion()
        insertadas = 0
        try:
            cursor = conn.cursor()
            try:
                cursor.execute(sql_truncate)
                if filas:
                    cursor.fast_executemany = True
                    cursor.setinputsizes([_input_size(t, a) for t, a in tipos])
                    for inicio in range(0, len(filas), self._batch_size):
                        lote = list(filas[inicio : inicio + self._batch_size])
                        cursor.executemany(insert_sql, lote)
                        insertadas += len(lote)
                cursor.execute(sql_delete)
                borradas = cursor.rowcount
            finally:
                cursor.close()
            conn.commit()
        except Exception as exc:
            _rollback_silencioso(conn)
            raise CargaError(f"Fallo la recarga (rollback completo, la tabla queda como estaba): {exc}") from exc
        return insertadas, borradas

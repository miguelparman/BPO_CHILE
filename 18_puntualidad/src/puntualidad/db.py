"""Acceso a SQL Server: fabrica de conexiones (pyodbc) y el gateway que usan
las capas de validacion y carga.

Reutilizado de 17_seguimiento (reintento de login, reconexion ante conexiones
cortadas por inactividad, separacion de batches 'GO', tamanos de parametro para
fast_executemany).

Una sesion por corrida de PUNTUALIDAD: sus tablas auxiliares (#cal, #base, ...)
son #temporales y solo existen en la sesion que las crea, asi que el loader
abre una sesion nueva (nueva_sesion()) antes de ese paquete y ejecuta todos
sus scripts en UNA transaccion (DDL transaccional de SQL Server: si algo falla,
la tabla anterior queda intacta).
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Callable, Sequence

import pyodbc

from config import DbSettings
from exceptions import CargaError
from logging_setup import NOMBRE_LOGGER

logger = logging.getLogger(NOMBRE_LOGGER)

# 'GO' no es T-SQL: el Execute SQL Task lo interpreta como separador de
# batches; pyodbc no. Se reconoce solo en su propia linea.
_GO_RE = re.compile(r"^[ \t]*GO[ \t]*(?:--[^\r\n]*)?\r?$", re.IGNORECASE | re.MULTILINE)

_TIPOS_TEXTO = {"varchar", "nvarchar", "char", "nchar", "text", "ntext"}


def dividir_en_batches(sql: str) -> list[str]:
    return [b for b in (parte.strip() for parte in _GO_RE.split(sql)) if b]


def crear_conexion(
    settings: DbSettings,
    reintentos: int = 1,
    espera_s: float = 5,
    dormir: Callable[[float], None] = time.sleep,
    conectar: Callable[..., pyodbc.Connection] = pyodbc.connect,
) -> pyodbc.Connection:
    """Abre la conexion con un reintento (un login puede fallar puntualmente
    con error 4060 y funcionar al segundo intento)."""
    conn_str = (
        f"DRIVER={{{settings.driver}}};"
        f"SERVER={settings.server};"
        f"DATABASE={settings.database};"
        f"UID={settings.user};"
        f"PWD={settings.password};"
        f"Encrypt={settings.encrypt};"
        f"TrustServerCertificate={settings.trust_server_certificate};"
        f"Language={settings.language}"  # el de las sesiones SSIS (ver config.DbSettings)
    )
    for intento in range(reintentos + 1):
        try:
            conn = conectar(conn_str, autocommit=False)
            break
        except pyodbc.Error as exc:
            if intento >= reintentos:
                raise
            logger.warning("No se pudo conectar a %s (%s); reintento en %s s.", settings.database, exc, espera_s)
            dormir(espera_s)
    conn.timeout = 0  # sin limite por consulta, como CommandTimeout=0 (los SP del paquete 07 tardan minutos)
    return conn


def tamanos_parametros(
    columnas: Sequence[str],
    esquema: dict[str, tuple[str, int | None]],
    decimales: dict[str, tuple[int, int]] | None = None,
) -> list:
    """setinputsizes para cada columna del INSERT segun el tipo REAL de la
    columna destino. fast_executemany infiere el buffer del primer valor del
    lote (y el tipo, si es None): sin esto truncaria/fallaria con valores mas
    largos o con una fecha despues de un NULL.
      texto     -> (SQL_WVARCHAR, largo, 0)  (largo 0 = MAX); el servidor
                   convierte a la code page de la columna si es varchar.
      datetime  -> (SQL_TYPE_TIMESTAMP, 23, 3)
      numeric   -> (SQL_DECIMAL, 18, 0)
    'decimales' = {columna: (precision, escala)}: para las columnas decimales con decimales
    (con escala 0 el driver truncaria 13,5 a 13); manda sobre el tipo de 'esquema'.
    """
    tamanos = []
    for col in columnas:
        tipo, largo = esquema[col]
        if decimales and col in decimales:
            tamanos.append((pyodbc.SQL_DECIMAL, decimales[col][0], decimales[col][1]))
        elif tipo in _TIPOS_TEXTO:
            tamanos.append((pyodbc.SQL_WVARCHAR, 0 if largo in (None, -1) else int(largo), 0))
        elif tipo in ("datetime", "datetime2", "smalldatetime"):
            tamanos.append((pyodbc.SQL_TYPE_TIMESTAMP, 23, 3))
        elif tipo in ("numeric", "decimal"):
            tamanos.append((pyodbc.SQL_DECIMAL, 18, 0))
        else:
            tamanos.append(None)
    return tamanos


def _consumir_resultados(cursor: pyodbc.Cursor) -> None:
    """Un batch con varias sentencias (o un SP) devuelve un resultado por
    sentencia; pyodbc solo levanta el error de una sentencia posterior a la
    primera al avanzar con nextset()."""
    while cursor.nextset():
        pass


def _rollback_silencioso(conn: pyodbc.Connection) -> None:
    try:
        conn.rollback()
    except pyodbc.Error as exc:
        logger.warning("No se pudo hacer rollback (conexion caida, el servidor descarta la transaccion): %s", exc)


class DatabaseGateway:
    """Envuelve una conexion pyodbc con las operaciones de los paquetes.

    Recibe una FABRICA de conexiones: antes de cada operacion se verifica la
    conexion con 'SELECT 1' y, si el servidor la corto por inactividad (visto
    en 12_trafico: 08S01/10054 mientras se descargaba de SharePoint), se abre
    una nueva."""

    def __init__(self, fabrica_conexion: Callable[[], pyodbc.Connection], batch_size: int = 5000, nombre: str = "") -> None:
        self._fabrica = fabrica_conexion
        self._conn: pyodbc.Connection | None = None
        self._batch_size = batch_size
        self.nombre = nombre
        self.sesion = 0  # se incrementa cada vez que se abre una conexion

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
        self.sesion += 1
        return self._conn

    def nueva_sesion(self) -> None:
        """La proxima operacion abre una conexion (sesion) nueva."""
        self.cerrar()

    def cerrar(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except pyodbc.Error:
                pass
            self._conn = None

    # ------------------------------------------------------------------ #
    # Execute SQL Task
    # ------------------------------------------------------------------ #
    def execute_autocommit(self, sql: str) -> int:
        """Execute SQL Task con la semantica del Connection Manager OLE DB
        (autocommit, sin transaccion de paquete). Devuelve el rowcount del
        ultimo batch (-1 si el driver no lo informa)."""
        conn = self._asegurar_conexion()
        conn.autocommit = True
        filas = -1
        try:
            cursor = conn.cursor()
            try:
                for batch in dividir_en_batches(sql):
                    cursor.execute(batch)
                    filas = cursor.rowcount
                    _consumir_resultados(cursor)
            finally:
                cursor.close()
        except Exception as exc:
            raise CargaError(f"Fallo la ejecucion del script T-SQL: {exc}") from exc
        finally:
            try:
                conn.autocommit = False
            except pyodbc.Error:
                self.cerrar()
        return filas

    def execute_transaccion(self, scripts: Sequence[str]) -> list[int]:
        """Varias Execute SQL Tasks en UNA transaccion: commit al final o
        rollback completo (p.ej. borrar + reinsertar los casos). Devuelve el
        rowcount del ultimo batch de cada script."""
        conn = self._asegurar_conexion()
        filas = []
        try:
            cursor = conn.cursor()
            try:
                for script in scripts:
                    ultimo = -1
                    for batch in dividir_en_batches(script):
                        cursor.execute(batch)
                        ultimo = cursor.rowcount
                        _consumir_resultados(cursor)
                    filas.append(ultimo)
            finally:
                cursor.close()
            conn.commit()
        except Exception as exc:
            _rollback_silencioso(conn)
            raise CargaError(f"Fallo la transaccion (rollback completo): {exc}") from exc
        return filas

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

    def columnas_de_tabla(self, base: str, tabla: str, esquema: str = "dbo") -> dict[str, tuple[str, int | None]]:
        """{columna: (tipo, largo)} segun INFORMATION_SCHEMA (largo -1 = MAX)."""
        _, filas = self.run_query(
            f"SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH FROM [{base}].INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? ORDER BY ORDINAL_POSITION",
            (esquema, tabla),
        )
        return {c: (t, None if largo is None else int(largo)) for c, t, largo in filas}

    # ------------------------------------------------------------------ #
    # OLE DB Destination (fast load)
    # ------------------------------------------------------------------ #
    def insertar_todo_o_nada(self, insert_sql: str, filas: Sequence[tuple], tamanos: Sequence) -> int:
        """INSERT por lotes (fast_executemany) en UNA transaccion: commit al
        final o rollback completo. Equivale a FastLoadMaxInsertCommitSize =
        2147483647 (un solo commit). 'tamanos' viene de tamanos_parametros()."""
        if not filas:
            return 0
        conn = self._asegurar_conexion()
        total = 0
        try:
            cursor = conn.cursor()
            try:
                cursor.fast_executemany = True
                cursor.setinputsizes(list(tamanos))
                for inicio in range(0, len(filas), self._batch_size):
                    lote = list(filas[inicio : inicio + self._batch_size])
                    cursor.executemany(insert_sql, lote)
                    total += len(lote)
            finally:
                cursor.close()
            conn.commit()
        except Exception as exc:
            _rollback_silencioso(conn)
            raise CargaError(f"No se pudieron insertar las filas (rollback completo): {exc}") from exc
        return total

    def cargar_en_transaccion(
        self,
        antes: Sequence[str],
        insert_sql: str,
        filas: Sequence[tuple],
        tamanos: Sequence,
        despues: Sequence[str] = (),
    ) -> int:
        """Execute SQL (antes) + OLE DB Destination (fast load) + Execute SQL
        (despues) en UNA transaccion: commit al final o rollback completo
        (p.ej. TRUNCATE + INSERT + UPDATE de una tabla: nunca queda vacia ni a
        medio actualizar). Devuelve las filas insertadas."""
        conn = self._asegurar_conexion()
        total = 0
        try:
            cursor = conn.cursor()
            try:
                for script in antes:
                    for batch in dividir_en_batches(script):
                        cursor.execute(batch)
                        _consumir_resultados(cursor)
                if filas:
                    cursor.fast_executemany = True
                    cursor.setinputsizes(list(tamanos))
                    for inicio in range(0, len(filas), self._batch_size):
                        lote = list(filas[inicio : inicio + self._batch_size])
                        cursor.executemany(insert_sql, lote)
                        total += len(lote)
                    cursor.fast_executemany = False
                for script in despues:
                    for batch in dividir_en_batches(script):
                        cursor.execute(batch)
                        _consumir_resultados(cursor)
            finally:
                cursor.close()
            conn.commit()
        except Exception as exc:
            _rollback_silencioso(conn)
            raise CargaError(f"Fallo la carga (rollback completo): {exc}") from exc
        return total

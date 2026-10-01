"""Acceso a SQL Server: fabrica de conexiones (pyodbc) y el gateway que usan
las capas de validacion y carga.

Reutilizado de 14_EPA_WSP/13_fcr/12_trafico (reintento de login,
reconexion ante conexiones cortadas por inactividad, separacion de batches
'GO', saneo de parametros). Una instancia de DatabaseGateway equivale al
Connection Manager OLE DB 'CL_LOGUEO' del .dtsx: todas las tareas usan esa
conexion (LOGS_PROCESOS y TBL_HISTORICO_PLACES se alcanzan con nombres de 3
partes, igual que en el paquete).
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Callable, Sequence

import pandas as pd
import pyodbc

from config import DbSettings
from exceptions import CargaError

logger = logging.getLogger("logueo")

# 'GO' no es T-SQL: el Execute SQL Task lo interpreta como separador de
# batches; pyodbc no. Se reconoce solo en su propia linea.
_GO_RE = re.compile(r"^[ \t]*GO[ \t]*(?:--[^\r\n]*)?\r?$", re.IGNORECASE | re.MULTILINE)


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
        f"TrustServerCertificate={settings.trust_server_certificate}"
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
    conn.timeout = 0  # sin limite por consulta, como CommandTimeout=0 del destino (SP_LOGUEO tarda ~1 min)
    return conn


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
    """Envuelve una conexion pyodbc con las operaciones del paquete.

    Recibe una FABRICA de conexiones: antes de cada operacion se verifica la
    conexion con 'SELECT 1' y, si el servidor la corto por inactividad (visto
    en 12_trafico: 08S01/10054 mientras se descargaba de SharePoint), se abre
    una nueva."""

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

    # ------------------------------------------------------------------ #
    # Execute SQL Task
    # ------------------------------------------------------------------ #
    def execute_autocommit(self, sql: str, params: Sequence[Any] | None = None) -> int:
        """Execute SQL Task con la semantica del Connection Manager OLE DB
        (autocommit, sin transaccion de paquete). Los parametros '?' se
        bindean en el batch que los contiene. Devuelve el rowcount del ultimo
        batch (-1 si el driver no lo informa)."""
        conn = self._asegurar_conexion()
        conn.autocommit = True
        filas = -1
        try:
            cursor = conn.cursor()
            try:
                for batch in dividir_en_batches(sql):
                    if params and "?" in batch:
                        cursor.execute(batch, tuple(params))
                    else:
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

    def run_query(self, sql: str, params: Sequence[Any] | None = None) -> pd.DataFrame:
        """Resultado como DataFrame de dtype 'object' (valores tal cual pyodbc)."""
        try:
            cursor = self._asegurar_conexion().cursor()
            try:
                cursor.execute(sql, tuple(params) if params else ())
                columnas = [col[0] for col in cursor.description]
                filas = cursor.fetchall()
            finally:
                cursor.close()
            self._conn.commit()  # cierra la transaccion implicita de lectura
        except Exception as exc:
            raise CargaError(f"Fallo la consulta: {exc}") from exc
        datos = {c: pd.Series([f[i] for f in filas], dtype=object) for i, c in enumerate(columnas)}
        return pd.DataFrame(datos, columns=columnas)

    def columnas_de_tabla(self, table: str, schema: str = "dbo") -> dict[str, tuple[str, int | None]]:
        """{columna: (tipo, largo)} segun INFORMATION_SCHEMA (largo -1 = MAX)."""
        df = self.run_query(
            "SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH "
            "FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? "
            "ORDER BY ORDINAL_POSITION",
            (schema, table),
        )
        return {
            r.COLUMN_NAME: (r.DATA_TYPE, None if r.CHARACTER_MAXIMUM_LENGTH is None else int(r.CHARACTER_MAXIMUM_LENGTH))
            for r in df.itertuples(index=False)
        }

    # ------------------------------------------------------------------ #
    # OLE DB Destination (fast load)
    # ------------------------------------------------------------------ #
    def insertar_todo_o_nada(self, insert_sql: str, filas: Sequence[tuple], anchos: Sequence[int]) -> int:
        """INSERT por lotes (fast_executemany) en UNA transaccion: commit al
        final o rollback completo. Equivale a FastLoadMaxInsertCommitSize =
        2147483647 (un solo commit). 'anchos' fija el buffer de cada
        parametro de texto (fast_executemany lo infiere del primer valor del
        lote y truncaria/fallaria con valores mas largos)."""
        if not filas:
            return 0
        conn = self._asegurar_conexion()
        total = 0
        try:
            cursor = conn.cursor()
            try:
                cursor.fast_executemany = True
                cursor.setinputsizes([(pyodbc.SQL_WVARCHAR, ancho, 0) for ancho in anchos])
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

"""Acceso a SQL Server: fabrica de conexiones (pyodbc) y el gateway que usan
las capas extraccion/validacion/transformacion/carga.

Reutilizado de 12_trafico (misma logica de lotes 'GO', transacciones y
reconexion ante cortes por inactividad). Una instancia de DatabaseGateway
equivale al Connection Manager OLE DB 'PEOPEDESK0328.CL_TRAFICO' del .dtsx.
"""

from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Sequence

import numpy as np
import pandas as pd
import pyodbc

from config import DbSettings
from exceptions import CargaError

logger = logging.getLogger("fcr")

# 'GO' no es T-SQL: es el separador de batches de SSMS/sqlcmd. El Execute SQL
# Task de SSIS lo interpreta y ejecuta cada batch por separado; pyodbc no, y
# falla con "Incorrect syntax near 'GO'". Se reconoce solo en su propia linea.
_GO_RE = re.compile(r"^[ \t]*GO[ \t]*(?:--[^\r\n]*)?\r?$", re.IGNORECASE | re.MULTILINE)


def dividir_en_batches(sql: str) -> list[str]:
    """Divide un script por sus separadores 'GO', igual que el Execute SQL
    Task. Descarta los batches vacios (p.ej. el que queda tras un GO final)."""
    return [b for b in (parte.strip() for parte in _GO_RE.split(sql)) if b]


def _fila_a_parametros(fila: tuple) -> tuple:
    """Sanea una fila antes de bindearla en pyodbc: NaN/NaT/pd.NA -> None (el
    driver no acepta NaN crudo) y escalares numpy -> tipo nativo de Python
    (pyodbc no los sabe describir). Mismo helper que 04_usuarios_y_retenciones/db.py."""
    saneada = []
    for valor in fila:
        if valor is None or (not isinstance(valor, (str, bytes)) and pd.isna(valor)):
            saneada.append(None)
        elif isinstance(valor, np.generic):
            saneada.append(valor.item())
        elif isinstance(valor, pd.Timestamp):
            saneada.append(valor.to_pydatetime())
        else:
            saneada.append(valor)
    return tuple(saneada)


def _rollback_silencioso(conn: pyodbc.Connection) -> None:
    """Rollback que no tapa el error original si la conexion ya esta caida
    (en ese caso SQL Server ya descarto la transaccion)."""
    try:
        conn.rollback()
    except pyodbc.Error as exc:
        logger.warning("No se pudo hacer rollback (conexion caida, el servidor descarta la transaccion): %s", exc)


def crear_conexion(settings: DbSettings) -> pyodbc.Connection:
    conn_str = (
        f"DRIVER={{{settings.driver}}};"
        f"SERVER={settings.server};"
        f"DATABASE={settings.database};"
        f"UID={settings.user};"
        f"PWD={settings.password};"
        f"Encrypt={settings.encrypt};"
        f"TrustServerCertificate={settings.trust_server_certificate}"
    )
    conn = pyodbc.connect(conn_str, autocommit=False)
    conn.timeout = 0  # sin limite por consulta (igual que el Execute SQL Task, TimeOut=0)
    return conn


class DatabaseGateway:
    """Envuelve una conexion pyodbc con las operaciones que el pipeline
    necesita (Execute SQL Task, OLE DB Source y OLE DB Destination).

    Recibe una FABRICA de conexiones, no una conexion: el servidor (o la red)
    corta las conexiones inactivas -- en la primera corrida real la de
    CL_TEMPORALES se corto tras ~30 s de inactividad mientras se descargaban
    los CSV en 12_trafico (error 08S01 / 10054). Por eso, antes de cada operacion FUERA de
    una transaccion se verifica la conexion con 'SELECT 1' y, si esta caida,
    se abre una nueva. Dentro de una transaccion nunca se reconecta (se
    perderia la atomicidad): un corte ahi hace fallar la transaccion entera.
    """

    def __init__(
        self, fabrica_conexion: Callable[[], pyodbc.Connection], batch_size: int = 5000, nombre: str = ""
    ) -> None:
        self._fabrica = fabrica_conexion
        self._conn: pyodbc.Connection | None = None
        self._batch_size = batch_size
        self._en_transaccion = False
        self.nombre = nombre

    # ------------------------------------------------------------------ #
    # Conexion
    # ------------------------------------------------------------------ #
    def _asegurar_conexion(self) -> pyodbc.Connection:
        if self._en_transaccion:
            return self._conn
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
    # Transacciones
    # ------------------------------------------------------------------ #
    @contextmanager
    def transaccion(self) -> Iterator[None]:
        """Agrupa varias operaciones en una sola transaccion: commit al final
        o rollback completo si cualquiera falla."""
        if self._en_transaccion:
            yield
            return
        conn = self._asegurar_conexion()
        self._en_transaccion = True
        try:
            yield
            conn.commit()
        except Exception:
            _rollback_silencioso(conn)
            raise
        finally:
            self._en_transaccion = False

    def _commit(self) -> None:
        if not self._en_transaccion:
            self._conn.commit()

    def _rollback(self) -> None:
        if not self._en_transaccion and self._conn is not None:
            _rollback_silencioso(self._conn)

    # ------------------------------------------------------------------ #
    # Execute SQL Task
    # ------------------------------------------------------------------ #
    def execute_script(self, sql: str, params: Sequence[Any] | None = None) -> None:
        """Ejecuta un script T-SQL completo, batch por batch (separados por
        'GO'), como el Execute SQL Task. Los parametros '?' se bindean en el
        batch que los contiene (Limpia Tabla y Alimenta Tabla usan uno)."""
        batches = dividir_en_batches(sql)
        try:
            cursor = self._asegurar_conexion().cursor()
            try:
                for i, batch in enumerate(batches, start=1):
                    if params and "?" in batch:
                        cursor.execute(batch, tuple(params))
                    else:
                        cursor.execute(batch)
                    # Un batch con varias sentencias devuelve un resultado por
                    # sentencia; pyodbc solo levanta el error de una sentencia
                    # posterior a la primera al avanzar con nextset().
                    while cursor.nextset():
                        pass
                    logger.debug("batch %s/%s ejecutado", i, len(batches))
            finally:
                cursor.close()
            self._commit()
        except Exception as exc:
            self._rollback()
            raise CargaError(f"Fallo la ejecucion del script T-SQL: {exc}") from exc

    def fetch_scalar(self, sql: str, params: Sequence[Any] | None = None) -> Any:
        try:
            cursor = self._asegurar_conexion().cursor()
            try:
                cursor.execute(sql, tuple(params) if params else ())
                fila = cursor.fetchone()
                return fila[0] if fila is not None else None
            finally:
                cursor.close()
        except Exception as exc:
            raise CargaError(f"Fallo la consulta escalar: {exc}") from exc

    def run_query(self, sql: str, params: Sequence[Any] | None = None) -> pd.DataFrame:
        """Devuelve el resultado como DataFrame de dtype 'object': los valores
        quedan tal cual los entrega pyodbc (int, str, date, datetime, None),
        sin que pandas convierta un int con NULL en float ni None en NaN."""
        try:
            cursor = self._asegurar_conexion().cursor()
            try:
                cursor.execute(sql, tuple(params) if params else ())
                # Lote con varias sentencias: avanzar hasta el primer resultado con filas.
                while cursor.description is None and cursor.nextset():
                    pass
                columnas = [col[0] for col in cursor.description]
                filas = cursor.fetchall()
            finally:
                cursor.close()
        except Exception as exc:
            raise CargaError(f"Fallo la consulta: {exc}") from exc
        datos = {c: pd.Series([f[i] for f in filas], dtype=object) for i, c in enumerate(columnas)}
        return pd.DataFrame(datos, columns=columnas)

    # ------------------------------------------------------------------ #
    # OLE DB Source (AccessMode=0, tabla completa)
    # ------------------------------------------------------------------ #
    def read_table(self, table: str, schema: str = "dbo") -> pd.DataFrame:
        return self.run_query(f"SELECT * FROM [{schema}].[{table}]")

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
    def truncate_table(self, table: str, schema: str = "dbo") -> None:
        self.execute_script(f"TRUNCATE TABLE [{schema}].[{table}]")

    def bulk_insert(self, table: str, df: pd.DataFrame, schema: str = "dbo") -> int:
        """Inserta el DataFrame completo. Dentro de transaccion() no hace
        commit por lote: todo o nada."""
        if df.empty:
            logger.info("[%s].[%s]: 0 filas para insertar.", schema, table)
            return 0

        columnas = list(df.columns)
        columnas_sql = ", ".join(f"[{c}]" for c in columnas)
        placeholders = ", ".join("?" for _ in columnas)
        insert_sql = f"INSERT INTO [{schema}].[{table}] ({columnas_sql}) VALUES ({placeholders})"

        try:
            cursor = self._asegurar_conexion().cursor()
            try:
                cursor.fast_executemany = True
                total = 0
                for inicio in range(0, len(df), self._batch_size):
                    lote = df.iloc[inicio : inicio + self._batch_size]
                    params = [_fila_a_parametros(f) for f in lote.itertuples(index=False, name=None)]
                    cursor.executemany(insert_sql, params)
                    total += len(params)
            finally:
                cursor.close()
            self._commit()
        except Exception as exc:
            self._rollback()
            raise CargaError(f"No se pudieron insertar filas en [{schema}].[{table}]: {exc}") from exc

        logger.info("%s filas insertadas en [%s].[%s].", total, schema, table)
        return total

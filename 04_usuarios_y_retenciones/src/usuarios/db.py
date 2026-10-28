"""Acceso a SQL Server: fabrica de conexiones (pyodbc) y el gateway que usan
extractor.py/validator.py/transformer.py/loader.py para ejecutar scripts,
truncar, consultar e insertar.

Una instancia de DatabaseGateway equivale a un Connection Manager OLE DB de
los 5 paquetes originales. El proyecto usa uno solo: 'CL_USUARIOS'
(172.17.0.162, autenticacion SQL) -- 'Externos_Frac' ya no se usa (como
origen migro a SharePoint/Microsoft Graph, y su unico destino se dio de baja
por obsoleto, ver pipeline.py).
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

import numpy as np
import pandas as pd
import pyodbc

from config import DbSettings
from exceptions import CargaError

logger = logging.getLogger("usuarios")


def _fila_a_parametros(fila: tuple) -> tuple:
    """Sanea una fila (tupla de valores de un DataFrame) antes de bindear
    los parametros del INSERT contra pyodbc:

    - NaN/NaT/pd.NA -> None. Los origenes SQL (antes de la migracion a
      SharePoint) siempre devolvian NULL -> None nativo via pyodbc; los CSV
      via pandas (dtype=str, na_values=['']) representan una celda vacia
      como NaN (float) en vez de None -- pyodbc no puede bindear un NaN
      crudo contra SQL Server (el driver corta la conexion con un error de
      protocolo TDS/RPC en vez de tratarlo como NULL).
    - Escalares numpy (numpy.int64, numpy.float64, etc.) -> tipo nativo de
      Python. Las columnas 'Int64' nullable de pandas (ver
      extraccion/extractor.py: _cast_int_estricto/_cast_int_tolerante)
      entregan numpy.int64 al iterar con itertuples(), que pyodbc no sabe
      describir ('Unknown object type ... during describe'); antes de la
      migracion a SharePoint, todas las columnas numericas venian de
      cursor.fetchall() de otra consulta SQL, siempre como int nativo.
    """
    saneada = []
    for valor in fila:
        if pd.isna(valor):
            saneada.append(None)
        elif isinstance(valor, np.generic):
            saneada.append(valor.item())
        else:
            saneada.append(valor)
    return tuple(saneada)


def crear_conexion(settings: DbSettings) -> pyodbc.Connection:
    """Arma la cadena de conexion segun el modo de autenticacion del
    Connection Manager original: SQL Server (UID/PWD, p.ej. 'CL_USUARIOS') si
    'settings.user' esta definido, o Windows integrada (Trusted_Connection,
    p.ej. 'Externos_Frac') si no lo esta."""
    if settings.user:
        auth = f"UID={settings.user};PWD={settings.password};Persist Security Info=True;"
    else:
        auth = "Trusted_Connection=yes;"

    conn_str = (
        f"DRIVER={{{settings.driver}}};"
        f"SERVER={settings.server};"
        f"DATABASE={settings.database};"
        f"{auth}"
        f"Encrypt={settings.encrypt};"
        f"TrustServerCertificate={settings.trust_server_certificate}"
    )
    return pyodbc.connect(conn_str)


class DatabaseGateway:
    """Envuelve una conexion pyodbc con las operaciones que el pipeline
    necesita (equivalentes a las tareas Execute SQL / Data Flow del paquete
    original que corren sobre un Connection Manager)."""

    def __init__(self, conn: pyodbc.Connection, batch_size: int = 5000) -> None:
        self._conn = conn
        self._batch_size = batch_size

    def execute_script(self, sql: str, params: Sequence[Any] | None = None) -> None:
        """Ejecuta un script T-SQL completo (una o mas sentencias, sin 'GO')
        como un unico batch. Equivalente a un Execute SQL Task del paquete
        original (incluye los que llaman procedimientos/UDFs de otra base de
        datos del mismo servidor via nombre de 3 partes -- no se reimplementa
        esa logica en Python, se ejecuta tal cual)."""
        try:
            cursor = self._conn.cursor()
            try:
                if params:
                    cursor.execute(sql, tuple(params))
                else:
                    cursor.execute(sql)
                self._conn.commit()
            finally:
                cursor.close()
        except Exception as exc:
            self._conn.rollback()
            raise CargaError(f"Fallo la ejecucion del script T-SQL: {exc}") from exc

    def fetch_scalar(self, sql: str, params: Sequence[Any] | None = None) -> Any:
        """Ejecuta una consulta escalar y devuelve el primer valor de la
        primera fila (o None si no hay filas)."""
        try:
            cursor = self._conn.cursor()
            try:
                cursor.execute(sql, tuple(params) if params else ())
                fila = cursor.fetchone()
                return fila[0] if fila is not None else None
            finally:
                cursor.close()
        except Exception as exc:
            raise CargaError(f"Fallo la consulta escalar: {exc}") from exc

    def run_query(self, sql: str, params: Sequence[Any] | None = None) -> pd.DataFrame:
        """Ejecuta una consulta parametrizada y devuelve un DataFrame.
        Equivalente a un Origen OLE DB en modo 'SQL Command' con parametros
        posicionales ('?')."""
        try:
            cursor = self._conn.cursor()
            try:
                cursor.execute(sql, tuple(params) if params else ())
                columnas = [col[0] for col in cursor.description]
                filas = cursor.fetchall()
                return pd.DataFrame.from_records(filas, columns=columnas)
            finally:
                cursor.close()
        except Exception as exc:
            raise CargaError(f"Fallo la consulta parametrizada: {exc}") from exc

    def truncate_table(self, table: str, schema: str = "dbo") -> None:
        """Equivalente a un Execute SQL Task 'TRUNCATE TABLE [schema].[table]'."""
        self.execute_script(f"TRUNCATE TABLE [{schema}].[{table}]")
        logger.info("Tabla [%s].[%s] truncada.", schema, table)

    def bulk_insert(self, table: str, df: pd.DataFrame, schema: str = "dbo") -> int:
        """Equivalente a un OLE DB Destination en modo fast-load con
        disposicion de error 'FailComponent': cualquier fallo de insercion
        detiene el lote completo. Devuelve la cantidad de filas insertadas."""
        if df.empty:
            logger.warning("bulk_insert: DataFrame vacio para [%s].[%s], no se inserta nada", schema, table)
            return 0

        insert_sql = self._insert_sql(table, list(df.columns), schema)

        try:
            cursor = self._conn.cursor()
            try:
                try:
                    cursor.fast_executemany = True
                except Exception:
                    pass

                total_insertadas = 0
                for inicio in range(0, len(df), self._batch_size):
                    lote = df.iloc[inicio : inicio + self._batch_size]
                    params = [_fila_a_parametros(fila) for fila in lote.itertuples(index=False, name=None)]
                    cursor.executemany(insert_sql, params)
                    self._conn.commit()
                    total_insertadas += len(params)
            finally:
                cursor.close()

            logger.info("%s filas insertadas en [%s].[%s].", total_insertadas, schema, table)
            return total_insertadas
        except Exception as exc:
            self._conn.rollback()
            raise CargaError(f"No se pudieron insertar filas en [{schema}].[{table}]: {exc}") from exc

    def bulk_insert_ignorando_errores(self, table: str, df: pd.DataFrame, schema: str = "dbo") -> int:
        """Equivalente a un OLE DB Destination con disposicion de error
        'IgnoreFailure': intenta el fast-load completo y, si falla, reintenta
        fila por fila descartando (y logueando) las que no se puedan
        insertar, en vez de abortar todo el lote. Usado unicamente por el
        Destino 'INTENCIONES LOCAL' de TBL_INTENCIONES\\INTENCIONES -- el
        unico Data Flow de los 5 paquetes con esa disposicion (ver README,
        Notas de fidelidad)."""
        if df.empty:
            logger.warning("bulk_insert_ignorando_errores: DataFrame vacio para [%s].[%s]", schema, table)
            return 0

        try:
            return self.bulk_insert(table, df, schema)
        except CargaError:
            logger.warning(
                "bulk_insert_ignorando_errores: fallo el lote completo en [%s].[%s], "
                "reintentando fila por fila (IgnoreFailure).",
                schema,
                table,
            )

        insert_sql = self._insert_sql(table, list(df.columns), schema)
        insertadas = 0
        descartadas = 0
        cursor = self._conn.cursor()
        try:
            for fila in df.itertuples(index=False, name=None):
                try:
                    cursor.execute(insert_sql, _fila_a_parametros(fila))
                    self._conn.commit()
                    insertadas += 1
                except Exception as exc:
                    self._conn.rollback()
                    descartadas += 1
                    logger.warning("Fila descartada en [%s].[%s] (IgnoreFailure): %s", schema, table, exc)
        finally:
            cursor.close()

        logger.info(
            "%s filas insertadas, %s descartadas (IgnoreFailure) en [%s].[%s].",
            insertadas,
            descartadas,
            schema,
            table,
        )
        return insertadas

    def read_table(self, table: str, schema: str = "dbo") -> pd.DataFrame:
        """Lee una tabla completa. Equivalente a un OLE DB Source en modo
        tabla (AccessMode=0)."""
        try:
            cursor = self._conn.cursor()
            try:
                cursor.execute(f"SELECT * FROM [{schema}].[{table}]")
                columnas = [col[0] for col in cursor.description]
                filas = cursor.fetchall()
                return pd.DataFrame.from_records(filas, columns=columnas)
            finally:
                cursor.close()
        except Exception as exc:
            raise CargaError(f"No se pudo leer [{schema}].[{table}]: {exc}") from exc

    @staticmethod
    def _insert_sql(table: str, columnas: list[str], schema: str) -> str:
        columnas_sql = ", ".join(f"[{c}]" for c in columnas)
        placeholders = ", ".join("?" for _ in columnas)
        return f"INSERT INTO [{schema}].[{table}] ({columnas_sql}) VALUES ({placeholders})"

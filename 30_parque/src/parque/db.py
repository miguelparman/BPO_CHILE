"""Acceso a SQL Server: fabrica de conexiones (pyodbc) y el gateway que usan
extraccion/validacion/transformacion/carga para truncar, insertar y (si hace
falta) leer tablas de CL_PLANTA.

Una instancia de DatabaseGateway equivale al Connection Manager OLE DB
'CL_PLANTA' del paquete original -- el pipeline usa una sola, compartida por
las 2 ramas (FIJO, MOVIL), igual que en el .dtsx original.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

import pandas as pd
import pyodbc

from config import DbSettings
from exceptions import CargaError

logger = logging.getLogger("parque")


_DRIVERS_PREFERIDOS = ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server")


def _resolver_driver(configurado: str) -> str:
    """Devuelve el driver ODBC a usar: el configurado (DB_DRIVER) si esta
    instalado en esta maquina; si no, el mas nuevo de los instalados. Evita
    tener que fijar la version en el .env de cada equipo."""
    instalados = pyodbc.drivers()
    nombre = configurado.strip().strip("{}")
    if nombre in instalados:
        return nombre
    for candidato in _DRIVERS_PREFERIDOS:
        if candidato in instalados:
            import logging as _logging

            _logging.getLogger(__name__).warning(
                "Driver ODBC '%s' no instalado; se usa '%s'.", nombre, candidato
            )
            return candidato
    return nombre


def crear_conexion(settings: DbSettings) -> pyodbc.Connection:
    conn_str = (
        f"DRIVER={{{_resolver_driver(settings.driver)}}};"
        f"SERVER={settings.server};"
        f"DATABASE={settings.database};"
        f"UID={settings.user};"
        f"PWD={settings.password};"
        f"Encrypt={settings.encrypt};"
        f"TrustServerCertificate={settings.trust_server_certificate}"
    )
    return pyodbc.connect(conn_str)


class DatabaseGateway:
    """Envuelve una conexion pyodbc con las operaciones que el pipeline
    necesita (equivalentes a las tareas Execute SQL / Data Flow del paquete
    original que corren sobre el Connection Manager 'CL_PLANTA')."""

    def __init__(self, conn: pyodbc.Connection, batch_size: int = 5000) -> None:
        self._conn = conn
        self._batch_size = batch_size

    def execute_script(self, sql: str, params: Sequence[Any] | None = None) -> None:
        """Ejecuta un script T-SQL completo. Equivalente a un Execute SQL Task
        simple del paquete original."""
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

    def execute_script_rowcount(self, sql: str, params: Sequence[Any] | None = None) -> int:
        """Como execute_script, pero devuelve la cantidad de filas afectadas
        (cursor.rowcount). Equivalente a las tareas 'DELETE'/'INSERT ...
        SELECT' de la Fase 2 (HISTORICO), cuyo resultado se quiere reportar
        en ResultadoHistorico."""
        try:
            cursor = self._conn.cursor()
            try:
                if params:
                    cursor.execute(sql, tuple(params))
                else:
                    cursor.execute(sql)
                filas = cursor.rowcount
                self._conn.commit()
                return filas if filas is not None and filas >= 0 else 0
            finally:
                cursor.close()
        except Exception as exc:
            self._conn.rollback()
            raise CargaError(f"Fallo la ejecucion del script T-SQL: {exc}") from exc

    def fetch_scalar(self, sql: str, params: Sequence[Any] | None = None) -> Any:
        """Ejecuta una consulta escalar y devuelve el primer valor de la
        primera fila."""
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

    def truncate_table(self, table: str, schema: str = "dbo") -> None:
        """Equivalente a las tareas 'TRUNCATE' de 'PQ FIJO I' / 'PQ MOVIL I':
        Execute SQL Task 'TRUNCATE TABLE [schema].[table]'. Se ejecuta como
        tarea separada e incondicional, antes del Data Flow -- ver
        pipeline.py y README, seccion 'Notas de fidelidad'."""
        self.execute_script(f"TRUNCATE TABLE [{schema}].[{table}]")
        logger.info("Tabla [%s].[%s] truncada.", schema, table)

    def bulk_insert(self, table: str, df: pd.DataFrame, schema: str = "dbo") -> int:
        """Equivalente al Destino OLE DB en modo fast-load (TABLOCK,
        CHECK_CONSTRAINTS, ROWS_PER_BATCH=5000, KeepNulls=true) de cada Data
        Flow del paquete original. Devuelve la cantidad de filas insertadas."""
        if df.empty:
            logger.warning("bulk_insert: DataFrame vacio para [%s].[%s], no se inserta nada", schema, table)
            return 0

        columnas = list(df.columns)
        columnas_sql = ", ".join(f"[{c}]" for c in columnas)
        placeholders = ", ".join("?" for _ in columnas)
        insert_sql = f"INSERT INTO [{schema}].[{table}] ({columnas_sql}) VALUES ({placeholders})"

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
                    params = [
                        tuple(None if pd.isna(valor) else valor for valor in fila)
                        for fila in lote.itertuples(index=False, name=None)
                    ]
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

    def read_table(self, table: str, schema: str = "dbo") -> pd.DataFrame:
        """Lee una tabla completa. Reservado para la Fase 2 (HISTORICO leera
        desde las tablas _ACTUAL usando este metodo)."""
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

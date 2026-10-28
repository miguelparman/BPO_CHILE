"""Dobles de prueba (fakes) para DatabaseGateway (db.py) y SharePointCsvReader
(sharepoint/reader.py).

Permiten testear el pipeline sin una base de datos ni una conexion Graph/
SharePoint reales, registrando las llamadas para poder aseverar el orden/
contenido -- igual que en los demas proyectos migrados de este repositorio
(ver 30_parque/tests/unit/fakes.py). No heredan de las clases concretas:
Python no lo exige (duck typing) y evita acoplar los fakes a la
implementacion real.
"""

from __future__ import annotations

from typing import Any, Sequence

import pandas as pd


class FakeDatabaseGateway:
    def __init__(self) -> None:
        self.executed_scripts: list[tuple[str, tuple]] = []
        self.truncated_tables: list[str] = []
        self.inserted: dict[str, pd.DataFrame] = {}
        self.inserted_ignorando_errores: dict[str, pd.DataFrame] = {}
        self.tables: dict[str, pd.DataFrame] = {}
        # Config de test: texto exacto de la consulta -> valor devuelto por fetch_scalar.
        self.scalars: dict[str, Any] = {}
        # Config de test: texto exacto de la consulta -> DataFrame devuelto por run_query.
        self.query_results: dict[str, pd.DataFrame] = {}
        self.queries_ejecutadas: list[tuple[str, tuple]] = []

    def execute_script(self, sql: str, params: Sequence[Any] | None = None) -> None:
        self.executed_scripts.append((sql, tuple(params) if params else ()))

    def fetch_scalar(self, sql: str, params: Sequence[Any] | None = None) -> Any:
        return self.scalars.get(sql, 0)

    def run_query(self, sql: str, params: Sequence[Any] | None = None) -> pd.DataFrame:
        self.queries_ejecutadas.append((sql, tuple(params) if params else ()))
        return self.query_results[sql]

    def truncate_table(self, table: str, schema: str = "dbo") -> None:
        self.truncated_tables.append(table)

    def bulk_insert(self, table: str, df: pd.DataFrame, schema: str = "dbo") -> int:
        self.inserted[table] = df
        return len(df)

    def bulk_insert_ignorando_errores(self, table: str, df: pd.DataFrame, schema: str = "dbo") -> int:
        self.inserted_ignorando_errores[table] = df
        return len(df)

    def read_table(self, table: str, schema: str = "dbo") -> pd.DataFrame:
        return self.tables[table]


class FakeSharePointCsvReader:
    def __init__(self, archivos: dict[str, pd.DataFrame]) -> None:
        self._archivos = archivos

    def leer_csv(self, nombre_archivo: str) -> pd.DataFrame:
        return self._archivos[nombre_archivo]

"""Dobles de prueba (fakes) para DatabaseGateway (db.py) y
SharePointCsvReader/SharePointExcelReader (sharepoint/reader.py).

Permiten testear el pipeline sin una base de datos ni una conexion Graph/
SharePoint reales, registrando las llamadas para poder aseverar el orden/
contenido -- mismo patron que 30_parque/tests/unit/fakes.py y
04_usuarios_y_retenciones/tests/unit/fakes.py. No heredan de las clases concretas: Python
no lo exige (duck typing) y evita acoplar los fakes a la implementacion real.
"""

from __future__ import annotations

from typing import Any, Sequence

import pandas as pd


class FakeDatabaseGateway:
    def __init__(self) -> None:
        self.executed_scripts: list[tuple[str, tuple]] = []
        self.executed_rowcount_scripts: list[tuple[str, tuple]] = []
        self.truncated_tables: list[str] = []
        self.inserted: dict[str, pd.DataFrame] = {}
        self.tables: dict[str, pd.DataFrame] = {}
        self.scalars: dict[str, Any] = {}
        # Valores devueltos por execute_script_rowcount, en el orden en que
        # se llame (FIFO).
        self.rowcount_results: list[int] = []

    def execute_script(self, sql: str, params: Sequence[Any] | None = None) -> None:
        self.executed_scripts.append((sql, tuple(params) if params else ()))

    def execute_script_rowcount(self, sql: str, params: Sequence[Any] | None = None) -> int:
        self.executed_rowcount_scripts.append((sql, tuple(params) if params else ()))
        if self.rowcount_results:
            return self.rowcount_results.pop(0)
        return 0

    def fetch_scalar(self, sql: str, params: Sequence[Any] | None = None) -> Any:
        return self.scalars.get(sql, 0)

    def truncate_table(self, table: str, schema: str = "dbo") -> None:
        self.truncated_tables.append(table)

    def bulk_insert(self, table: str, df: pd.DataFrame, schema: str = "dbo") -> int:
        self.inserted[table] = df
        return len(df)

    def read_table(self, table: str, schema: str = "dbo") -> pd.DataFrame:
        return self.tables[table]


class FakeSharePointCsvReader:
    def __init__(self, archivos: dict[str, pd.DataFrame]) -> None:
        self._archivos = archivos

    def leer_csv(self, nombre_archivo: str) -> pd.DataFrame:
        return self._archivos[nombre_archivo]


class FakeSharePointExcelReader:
    def __init__(self, hojas: dict[tuple[str, str], pd.DataFrame]) -> None:
        self._hojas = hojas

    def leer_hoja(self, nombre_archivo: str, hoja: str) -> pd.DataFrame:
        return self._hojas[(nombre_archivo, hoja)]

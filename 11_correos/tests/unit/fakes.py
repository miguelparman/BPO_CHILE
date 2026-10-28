"""Dobles de prueba (fakes) para SharePointClient y DatabaseGateway. Permiten
testear ingesta/bronze/silver/gold sin una conexion Graph/SQL Server
real, registrando las llamadas para poder aseverar el orden/contenido --
mismo patron ya usado en 04_usuarios_y_retenciones/tests/unit/fakes.py y
30_parque/tests/unit/fakes.py. No heredan de las clases concretas: Python no
lo exige (duck typing)."""

from __future__ import annotations

import pandas as pd

from comun.exceptions import SharePointResolutionError, SharePointUploadError


class FakeSharePointClient:
    def __init__(self, archivos_origen: dict[str, bytes] | None = None) -> None:
        self._archivos_origen = archivos_origen or {}
        self.subidos: dict[str, bytes] = {}
        self.fallar_descarga: set[str] = set()
        self.fallar_subida: set[str] = set()

    def resolve_site(self, hostname: str, site_path: str) -> str:
        return f"site::{site_path}"

    def resolve_default_drive(self, site_id: str) -> str:
        return f"drive::{site_id}"

    def resolve_drive(self, site_id: str, drive_name: str) -> str:
        return f"drive::{site_id}::{drive_name}"

    def resolve_folder(self, drive_id: str, folder_path: str) -> str:
        return f"folder::{drive_id}::{folder_path}"

    def list_excel_files(self, drive_id: str, folder_path: str) -> list[str]:
        return sorted(self._archivos_origen)

    def download_file(self, drive_id: str, file_path: str) -> bytes:
        nombre = file_path.rsplit("/", 1)[-1]
        if nombre in self.fallar_descarga:
            raise SharePointResolutionError(f"descarga simulada fallida: {nombre}")
        if nombre not in self._archivos_origen:
            raise SharePointResolutionError(f"archivo no encontrado (fake): {nombre}")
        return self._archivos_origen[nombre]

    def upload_file(self, drive_id: str, folder_id: str, filename: str, content: bytes) -> None:
        if filename in self.fallar_subida:
            raise SharePointUploadError(f"subida simulada fallida: {filename}")
        self.subidos[filename] = content


class FakeDatabaseGateway:
    def __init__(self) -> None:
        self.deletes: list[tuple[str, tuple]] = []
        self.truncated_tables: list[str] = []
        self.inserted: dict[str, pd.DataFrame] = {}
        self.filas_a_eliminar = 0
        self.selects: list[tuple[str, tuple]] = []
        self.resultado_select = pd.DataFrame()
        # Si se cargan, cada SELECT consume el siguiente en orden (para flujos
        # con varias lecturas distintas, ej. gold/cargar.py); si no, resultado_select.
        self.resultados_select: list[pd.DataFrame] = []
        self.inserts_con_id: list[tuple[str, tuple]] = []
        self.siguiente_id = 1
        # Si se carga, execute_script_rowcount levanta esta excepcion.
        self.fallar_execute: Exception | None = None

    def insert_returning_id(self, sql: str, params: tuple | None = None) -> int:
        self.inserts_con_id.append((sql, tuple(params) if params else ()))
        return self.siguiente_id

    def fetch_dataframe(self, sql: str, params: tuple | None = None) -> pd.DataFrame:
        self.selects.append((sql, tuple(params) if params else ()))
        if self.resultados_select:
            return self.resultados_select.pop(0).copy()
        return self.resultado_select.copy()

    def execute_script_rowcount(self, sql: str, params: tuple | None = None) -> int:
        if self.fallar_execute is not None:
            raise self.fallar_execute
        self.deletes.append((sql, tuple(params) if params else ()))
        return self.filas_a_eliminar

    def truncate_table(self, table: str, schema: str = "dbo") -> None:
        self.truncated_tables.append(table)

    def bulk_insert(self, table: str, df: pd.DataFrame, schema: str = "dbo") -> int:
        self.inserted[table] = df
        return len(df)

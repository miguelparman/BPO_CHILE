"""Dobles de prueba (fakes) para DatabaseGateway (db.py) y CsvReader
(sharepoint/reader.py).

Permiten testear el pipeline sin base de datos ni SharePoint, registrando
cada operacion en una lista de eventos compartida para poder aseverar el
ORDEN del Control Flow. No heredan de las clases concretas (duck typing).
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Sequence

import pandas as pd

import mappings
import sql

# texto SQL -> nombre de la tarea del .dtsx (para eventos legibles)
_NOMBRE_SCRIPT = {
    sql.LOG_INICIO: "Log Inicio",
    sql.TEMPORALES_TRUNCA_TABLAS: "TRUNCA TABLAS",
    sql.TEMPORALES_UPDATE: "UPDATE",
    **{script: nombre for nombre, script in sql.LIMPIA_TEMPORALES},
    sql.CL_TRAFICO_DELETE_PERIODO: "DELETE PERIODO",
    sql.CL_TRAFICO_UPDATE_WSP: "UPDATE_WSP",
    sql.LOG_FIN: "Log Fin",
}


def esquema_ok(tabla: str) -> dict[str, tuple[str, int | None]]:
    """Esquema 'real' identico al que espera mappings.py."""
    if tabla in mappings.TIPOS_TEMPORALES:
        return dict(mappings.TIPOS_TEMPORALES[tabla])
    destino = next(d for d in mappings.DESTINOS if d.tabla == tabla)
    return {c.destino: (c.tipo_destino, c.largo_destino) for c in destino.columnas}


class FakeDatabaseGateway:
    def __init__(self, nombre: str, eventos: list | None = None) -> None:
        self.nombre = nombre
        self.eventos: list = eventos if eventos is not None else []
        self.inserted: dict[str, pd.DataFrame] = {}
        self.tables: dict[str, pd.DataFrame] = {}
        self.esquemas: dict[str, dict] = {}
        self.fallar_en: str | None = None  # nombre de tarea/tabla que debe fallar
        self.commits = 0
        self.rollbacks = 0

    @contextmanager
    def transaccion(self):
        self.eventos.append((self.nombre, "BEGIN"))
        try:
            yield
            self.commits += 1
            self.eventos.append((self.nombre, "COMMIT"))
        except Exception:
            self.rollbacks += 1
            self.eventos.append((self.nombre, "ROLLBACK"))
            raise

    def execute_script(self, sql_text: str, params: Sequence[Any] | None = None) -> None:
        nombre = _NOMBRE_SCRIPT.get(sql_text, sql_text[:40])
        self.eventos.append((self.nombre, nombre, tuple(params) if params else ()))
        if self.fallar_en == nombre:
            raise RuntimeError(f"fallo simulado en {nombre}")

    def bulk_insert(self, table: str, df: pd.DataFrame, schema: str = "dbo") -> int:
        self.eventos.append((self.nombre, f"INSERT {table}", len(df)))
        if self.fallar_en == table:
            raise RuntimeError(f"fallo simulado insertando {table}")
        self.inserted[table] = df
        return len(df)

    def read_table(self, table: str, schema: str = "dbo") -> pd.DataFrame:
        self.eventos.append((self.nombre, f"SELECT {table}"))
        return self.tables[table]

    def columnas_de_tabla(self, table: str, schema: str = "dbo") -> dict:
        return self.esquemas.get(table) or esquema_ok(table)


class FakeCsvReader:
    def __init__(self, archivos: dict[str, pd.DataFrame]) -> None:
        self._archivos = archivos
        self.leidos: list[str] = []

    def read_csv(self, nombre_archivo: str) -> pd.DataFrame:
        self.leidos.append(nombre_archivo)
        if nombre_archivo not in self._archivos:
            raise FileNotFoundError(nombre_archivo)
        return self._archivos[nombre_archivo]


def csv_minimo(origen: mappings.OrigenCsv, filas: list[dict] | None = None) -> pd.DataFrame:
    """CSV (todo texto) con las columnas del origen + la columna extra 'ID'."""
    base = {c: "" for c in origen.columnas}
    esquema = mappings.TIPOS_TEMPORALES[origen.tabla_temporal]
    for c in origen.columnas:
        tipo = esquema[c][0]
        base[c] = {"int": "1", "date": "2026-09-01", "datetime": "2026-09-01 10:15:00"}.get(tipo, "x")
        if c in origen.columnas_texto_datetime2:
            base[c] = "2026-09-01 10:20:00"
    if origen.periodo_desde_fecha:
        base[origen.columna_periodo] = "2026-09-02 08:00:00"
    else:
        base[origen.columna_periodo] = "202609"
    filas = filas if filas is not None else [{}]
    df = pd.DataFrame([{**base, **f} for f in filas], dtype=str)
    df["ID"] = [str(i) for i in range(len(df))]
    return df


def csvs_minimos() -> dict[str, pd.DataFrame]:
    return {o.archivo: csv_minimo(o) for o in mappings.ORIGENES}

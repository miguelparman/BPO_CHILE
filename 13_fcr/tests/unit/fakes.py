"""Doble de prueba (fake) de DatabaseGateway (db.py).

Permite testear el pipeline sin base de datos, registrando cada operacion en
una lista de eventos para poder aseverar el ORDEN del Control Flow. No hereda
de la clase concreta (duck typing).
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Any, Sequence

import pandas as pd

import mappings
import sql

_NOMBRE_SCRIPT = {
    sql.LOG_INICIO: "Log Inicio",
    sql.LIMPIA_TABLA: "Limpia Tabla",
    sql.LOG_FIN: "Log Fin",
}


def esquema_destino_ok() -> dict[str, tuple[str, int | None]]:
    return {c: (t, l) for c, t, l in mappings.COLUMNAS_DESTINO}


def origen(filas: list[tuple]) -> pd.DataFrame:
    """[(AGENT_START, ANI, SERVICIO, LOGINID), ...] -> DataFrame como run_query."""
    cols = list(mappings.COLUMNAS_ORIGEN)
    return pd.DataFrame({c: pd.Series([f[i] for f in filas], dtype=object) for i, c in enumerate(cols)}, columns=cols)


def bases_minimas() -> dict[str, pd.DataFrame]:
    """Dos atenciones del mismo ANI a 10 minutos en cada base."""
    return {
        b.tabla_temporal: origen(
            [
                (datetime(2026, 9, 1, 10, 0, 0), "56911111111", b.servicio, "u1"),
                (datetime(2026, 9, 1, 10, 10, 0), "56911111111", b.servicio, "u2"),
            ]
        )
        for b in mappings.BASES
    }


class FakeDatabaseGateway:
    def __init__(self, bases: dict[str, pd.DataFrame] | None = None, eventos: list | None = None) -> None:
        self.eventos: list = eventos if eventos is not None else []
        self.bases = bases if bases is not None else bases_minimas()
        self.inserted: dict[str, pd.DataFrame] = {}
        self.esquemas: dict[str, dict] = {}
        self.fallar_en: str | None = None
        self.filas_periodo = 7
        self.commits = 0
        self.rollbacks = 0

    @contextmanager
    def transaccion(self):
        self.eventos.append("BEGIN")
        try:
            yield
            self.commits += 1
            self.eventos.append("COMMIT")
        except Exception:
            self.rollbacks += 1
            self.eventos.append("ROLLBACK")
            raise

    def execute_script(self, sql_text: str, params: Sequence[Any] | None = None) -> None:
        nombre = _NOMBRE_SCRIPT.get(sql_text, sql_text[:40])
        self.eventos.append((nombre, tuple(params) if params else ()))
        if self.fallar_en == nombre:
            raise RuntimeError(f"fallo simulado en {nombre}")

    def fetch_scalar(self, sql_text: str, params: Sequence[Any] | None = None) -> Any:
        self.eventos.append(("COUNT", tuple(params) if params else ()))
        return self.filas_periodo

    def run_query(self, sql_text: str, params: Sequence[Any] | None = None) -> pd.DataFrame:
        base = next(b for b in mappings.BASES if sql_text == sql.extraccion_base(b))
        self.eventos.append((f"SELECT {base.tabla_temporal}", tuple(params) if params else ()))
        if self.fallar_en == base.tabla_temporal:
            raise RuntimeError("fallo simulado leyendo origen")
        return self.bases[base.tabla_temporal]

    def bulk_insert(self, table: str, df: pd.DataFrame, schema: str = "dbo") -> int:
        self.eventos.append((f"INSERT {table}", len(df)))
        if self.fallar_en == table:
            raise RuntimeError(f"fallo simulado insertando {table}")
        self.inserted[table] = df
        return len(df)

    def columnas_de_tabla(self, table: str, schema: str = "dbo") -> dict:
        if table in self.esquemas:
            return self.esquemas[table]
        if table == mappings.TABLA_DESTINO:
            return esquema_destino_ok()
        return dict(mappings.COLUMNAS_ORIGEN)

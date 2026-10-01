"""Carga: Execute SQL Tasks y el 'Destino de OLE DB' de Cl_Proc_Logueo.dtsx.

Todas las operaciones usan el Connection Manager 'CL_LOGUEO' (un solo
DatabaseGateway). Los T-SQL son literales del .dtsx (ver sql.py).
"""

from __future__ import annotations

import logging
from decimal import Decimal

import pandas as pd

import mappings
import sql
from db import DatabaseGateway

logger = logging.getLogger("logueo")


class LogueoLoader:
    def __init__(self, db: DatabaseGateway) -> None:
        self._db = db

    # Package\Log Inicio
    def log_inicio(self) -> None:
        self._db.execute_autocommit(sql.LOG_INICIO)

    # Lookup 'Busqueda' (Full Cache): lectura de la referencia
    def leer_referencia(self) -> pd.DataFrame:
        return self._db.run_query(sql.LOOKUP_REFERENCIA)

    def esquema_destino(self) -> dict[str, tuple[str, int | None]]:
        return self._db.columnas_de_tabla(mappings.TABLA_DESTINO, mappings.SCHEMA)

    # 'Destino de OLE DB' -> [dbo].[TBL_CONEXIONES]
    def insertar(self, df_destino: pd.DataFrame, esquema: dict[str, tuple[str, int | None]]) -> int:
        columnas = list(mappings.COLUMNAS_INSERT)
        filas = [tuple(f) for f in df_destino[columnas].itertuples(index=False, name=None)]
        anchos = [esquema[c][1] if esquema[c][1] not in (None, -1) else 0 for c in columnas]
        return self._db.insertar_todo_o_nada(sql.INSERT_DESTINO, filas, anchos)

    # Package\LOGUEO CHILE\AGREGA DNI  (? = User::Periodo, DataType 131 = numerico)
    def agregar_dni(self, periodo: int) -> int:
        return self._db.execute_autocommit(sql.AGREGA_DNI, (Decimal(periodo),))

    # Package\Log Fin
    def log_fin(self) -> None:
        self._db.execute_autocommit(sql.LOG_FIN)

    # Package\SP
    def sp_logueo(self) -> None:
        self._db.execute_autocommit(sql.SP_LOGUEO)

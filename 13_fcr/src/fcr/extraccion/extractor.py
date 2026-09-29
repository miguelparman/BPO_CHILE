"""Extraccion: lee de CL_TRAFICO las atenciones de cada base (bloque 'XA'
de Alimenta Tabla) desde el periodo indicado.

Origen: TBL_LLAMADAS_ATENDIDAS_INBOUND y TBL_CHAT, que carga 12_trafico
(CL_Proc_Trafico_01.dtsx). Por eso este proceso corre DESPUES de aquel.
"""

from __future__ import annotations

import logging

import pandas as pd

import mappings
import sql
from exceptions import ExtraccionError

logger = logging.getLogger("fcr")


def extraer_base(db, base: mappings.BaseFCR, periodo: int) -> pd.DataFrame:
    """Filas crudas de una base: AGENT_START, ANI, SERVICIO, LOGINID (dtype
    object, valores tal cual los entrega pyodbc)."""
    try:
        df = db.run_query(sql.extraccion_base(base), (periodo,))
    except Exception as exc:  # noqa: BLE001 - se re-lanza tipado
        raise ExtraccionError(f"No se pudo leer {base.tabla_origen} / {base.servicio}: {exc}") from exc
    logger.info("[FCR]   %s (%s, %s): %s filas", base.tabla_temporal, base.tabla_origen, base.servicio, len(df))
    return df


def extraer_bases(db, periodo: int) -> dict[str, pd.DataFrame]:
    """{tabla_temporal: DataFrame} para las 5 bases, en el orden de mappings.BASES."""
    return {base.tabla_temporal: extraer_base(db, base, periodo) for base in mappings.BASES}

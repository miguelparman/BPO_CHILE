"""
Reemplaza los componentes Microsoft.ExcelSource del Data Flow.
"""
import logging
from io import BytesIO

import pandas as pd

logger = logging.getLogger(__name__)


def read_excel_sheet(contenido: bytes, sheet_name: str, origen: str = "", dtype=None) -> pd.DataFrame:
    """
    Lee una hoja completa del Excel ya descargado (bytes).

    Nota: en el .dtsx los OpenRowset son 'DB$' y 'DB_DETRACTOR$' (el '$' es la
    convención interna de SSIS para nombrar hojas). Aquí se usa el nombre sin '$'.

    dtype: se pasa tal cual a pandas (p. ej. str para no perder ceros iniciales).
    """
    logger.info("Leyendo Excel: %s [hoja=%s]", origen, sheet_name)
    df = pd.read_excel(BytesIO(contenido), sheet_name=sheet_name, engine="openpyxl", dtype=dtype)
    logger.info("Filas leídas: %d, columnas: %s", len(df), list(df.columns))
    return df

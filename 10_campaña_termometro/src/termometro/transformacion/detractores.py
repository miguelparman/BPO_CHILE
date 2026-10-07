"""
Reemplaza el Data Flow 'TBL_CAMPAÑA_TERMOMETRO_DETRACTOR':
  Origen de Excel -> Conversión de datos -> OLE DB Destination

El Data Convert solo castea a texto (wstr) las columnas PERIODO y RUT_SIN_DV,
que ya vienen con esos nombres en la hoja 'DB_DETRACTOR$' del Excel.
"""
import logging
import pandas as pd

logger = logging.getLogger(__name__)

OUTPUT_COLUMNS = ["PERIODO", "RUT_SIN_DV"]


def transform_detractores(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    faltantes = set(OUTPUT_COLUMNS) - set(df.columns)
    if faltantes:
        raise ValueError(f"Faltan columnas esperadas en el Excel de detractores: {faltantes}")

    df["PERIODO"] = df["PERIODO"].astype("string").str.strip()
    df["RUT_SIN_DV"] = df["RUT_SIN_DV"].astype("string").str.strip()

    return df[OUTPUT_COLUMNS]

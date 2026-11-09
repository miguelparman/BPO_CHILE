"""
Reemplaza Microsoft.FlatFileSource "Reporte_isn_aux_cliente_v2" del Data Flow
"TBL_ISN_SF_AUX_CLIENTE 1\\TBL_ISN_SF_AUX_CLIENTE".
"""
from __future__ import annotations

import io
import logging

import pandas as pd

from config import settings
from sharepoint.descarga import descargar_archivo
from isn.columns import COLUMNAS_AUX_CLIENTE

logger = logging.getLogger(__name__)


def leer_aux_cliente(contenido: bytes | None = None) -> pd.DataFrame:
    """Lee el CSV desde SharePoint (Graph); `contenido` permite inyectar bytes en pruebas."""
    if contenido is None:
        contenido = descargar_archivo(settings.sp_aux_cliente_nombre)
    path = settings.sp_aux_cliente_nombre
    df = pd.read_csv(
        io.BytesIO(contenido),
        sep=",",
        encoding=settings.csv_isn_encoding,
        quotechar='"',
        header=0,
        dtype=str,
        keep_default_na=False,
        na_values=[""],
    )
    if len(df.columns) != len(COLUMNAS_AUX_CLIENTE):
        raise ValueError(
            f"Se esperaban {len(COLUMNAS_AUX_CLIENTE)} columnas en {path}, se encontraron {len(df.columns)}: "
            f"{list(df.columns)}"
        )
    df.columns = COLUMNAS_AUX_CLIENTE
    for col in COLUMNAS_AUX_CLIENTE:
        df[col] = df[col].astype("string").str.strip()
    logger.info("Filas leídas (aux cliente): %d", len(df))
    return df

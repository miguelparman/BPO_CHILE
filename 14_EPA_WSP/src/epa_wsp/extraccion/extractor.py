"""Extraccion.

1) ENCUESTA.csv y WS_MEDALLIA_2.csv de SharePoint (Microsoft Graph).
   Reemplazan el 'SELECT ... FROM [Externos_Frac].[dbo].[ENCUESTA|WS_MEDALLIA_2]'
   de Traslado_Calidad_Servidor_55_EPA_ISN.py / _EPA_WSP_MEDALLIA.py. Los
   publica 01_servidor_chile (los 2 ultimos meses de cada tabla) y se leen
   TODO como texto: la tipificacion la hace transformacion/transformer.py
   segun el esquema de la tabla destino.

2) Encuestas_Medallia.csv (lo deja la descarga del portal Medallia en la
   carpeta de SharePoint '16 MEDALLIA'; antes era un archivo local). Se lee
   EXACTAMENTE como CL_Carga_de_encuestas_MEDALLIA.py:
   pd.read_csv(csv_file, encoding='latin1', dtype=str), con el manejo de NA
   por defecto de pandas (una celda vacia o 'NA' -> NaN).
"""

from __future__ import annotations

import io
import logging

import pandas as pd

from exceptions import ExtraccionError, ValidacionError
from mappings import Traslado

logger = logging.getLogger("epa_wsp")


def extraer_csv_sharepoint(reader, traslado: Traslado) -> pd.DataFrame:
    """CSV de SharePoint -> DataFrame de strings (celda vacia = '')."""
    try:
        df = reader.read_csv(traslado.archivo)
    except Exception as exc:  # noqa: BLE001 - se re-lanza tipado
        raise ExtraccionError(f"No se pudo leer '{traslado.archivo}' de SharePoint: {exc}") from exc
    faltantes = [c for c in traslado.columnas if c not in df.columns]
    if faltantes:
        raise ValidacionError(f"{traslado.archivo}: faltan columnas obligatorias {faltantes}")
    logger.info("%s: %s filas leidas de SharePoint.", traslado.archivo, len(df))
    return df


def leer_csv_medallia(origen) -> pd.DataFrame:
    """Lectura identica al script original: pd.read_csv(latin1, dtype=str).
    'origen' es una ruta o un buffer de bytes."""
    return pd.read_csv(origen, encoding="latin1", dtype=str)


def extraer_csv_medallia(carpeta, nombre: str) -> pd.DataFrame:
    """Encuestas_Medallia.csv de la carpeta de SharePoint -> DataFrame."""
    try:
        contenido = carpeta.leer(nombre)
    except Exception as exc:  # noqa: BLE001
        raise ExtraccionError(f"No se pudo leer '{nombre}' de SharePoint ({carpeta.url(nombre)}): {exc}") from exc
    try:
        df = leer_csv_medallia(io.BytesIO(contenido))
    except Exception as exc:  # noqa: BLE001
        raise ExtraccionError(f"No se pudo parsear el CSV de Medallia '{nombre}': {exc}") from exc
    logger.info("%s: %s filas leidas de SharePoint (%s columnas).", nombre, len(df), len(df.columns))
    return df

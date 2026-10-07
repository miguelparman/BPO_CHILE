"""
Reemplaza el componente Microsoft.FlatFileSource (Connection Manager 'Reporte_termometro_v2').

Configuración original en el .dtsx:
- Delimitado, con encabezado en la primera fila
- TextQualifier: comillas dobles
- CodePage declarado: 1252 (Windows-1252)

OJO: al probar con el archivo real, 'cp1252' estricto falla (UnicodeDecodeError,
byte 0x8d inválido para esa tabla de códigos) — el archivo tiene algún byte fuera
de rango, probablemente por un copy-paste desde otra fuente en alguna celda de
comentarios. 'latin-1' (ISO-8859-1) sí lo lee completo porque mapea 1:1 todos los
256 valores de byte, así que se usa como default. Es una diferencia real de
comportamiento frente a SSIS: si SSIS también encontraba ese byte, probablemente
lo estaba reemplazando silenciosamente por el carácter cp1252 más cercano o
fallando esa fila puntual. Vale la pena revisar con quien genera el reporte de
Salesforce si pueden exportarlo en UTF-8 para evitar esta ambigüedad a futuro.
"""
import logging
from io import BytesIO

import pandas as pd

from config import settings

logger = logging.getLogger(__name__)


def read_salesforce_csv(contenido: bytes, origen: str = "") -> pd.DataFrame:
    """Parsea el CSV ya descargado (bytes)."""
    logger.info("Leyendo CSV Salesforce: %s", origen)
    df = pd.read_csv(
        BytesIO(contenido),
        sep=settings.csv_salesforce_delimiter,
        encoding=settings.csv_salesforce_encoding,  # default ahora es latin-1, ver nota arriba
        quotechar='"',
        dtype=str,  # se castea explícitamente en el transformer, igual que el Data Convert de SSIS
        keep_default_na=False,
        na_values=[""],
    )
    logger.info("Filas leídas: %d, columnas: %s", len(df), list(df.columns))
    return df

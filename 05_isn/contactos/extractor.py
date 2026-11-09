"""
Reemplaza los componentes Microsoft.FlatFileSource / Microsoft.OLEDBSource
del paquete SSIS_CL_ISN_Contactos.dtsx.

Configuración original de la conexión FLATFILE "Reporte_Contactos_Salesforce_BI":
delimitado por coma, calificador de texto '"', CodePage 1252, encabezado en
la primera fila (se descarta, ver contactos/columns.py sobre por qué el
mapeo es posicional y no por nombre de cabecera).
"""
from __future__ import annotations

import io
import logging
from pathlib import Path

import pandas as pd

from config import settings
from contactos.columns import COLUMNAS_ORIGEN, TABLA_DESTINO
from db import get_engine
from sharepoint.descarga import descargar_archivo

logger = logging.getLogger(__name__)


def leer_csv_contactos(contenido: bytes | None = None) -> pd.DataFrame:
    """Lee el CSV desde SharePoint (Graph); `contenido` permite inyectar bytes en pruebas."""
    path = settings.sp_contactos_nombre
    if contenido is None:
        if settings.contactos_csv_muestra:  # solo ambiente de pruebas (infra/.env.test)
            logger.info("Leyendo CSV de muestra local (modo prueba): %s", settings.contactos_csv_muestra)
            contenido = Path(settings.contactos_csv_muestra).read_bytes()
        else:
            contenido = descargar_archivo(path, settings.sp_contactos_folder_path)
    df = pd.read_csv(
        io.BytesIO(contenido),
        sep=settings.csv_contactos_delimiter,
        encoding=settings.csv_contactos_encoding,
        quotechar='"',
        header=0,  # se descarta la cabecera real del archivo (ver columns.py)
        dtype=str,  # se castea explícitamente en el transformer, igual que el Data Convert de SSIS
        keep_default_na=False,
        na_values=[""],
    )
    if len(df.columns) != len(COLUMNAS_ORIGEN):
        raise ValueError(
            f"Se esperaban {len(COLUMNAS_ORIGEN)} columnas en {path}, se encontraron {len(df.columns)}: "
            f"{list(df.columns)}"
        )
    df.columns = COLUMNAS_ORIGEN
    logger.info("Filas leídas: %d", len(df))
    return df


def extraer_numeros_distintos() -> pd.DataFrame:
    """Reemplaza el OLE DB Source del Data Flow 'Números (Local)':
    UNION de TELÉFONO/MÓVIL no nulos de TBL_CONTACTOS_AUTORIZADOS_CHILE, sin repetidos.
    """
    sql_path = Path(__file__).resolve().parent / "sql" / "select_numeros_distintos.sql"
    sql = sql_path.read_text(encoding="utf-8")
    logger.info("Extrayendo números distintos desde %s", TABLA_DESTINO)
    engine = get_engine(settings.db_database_analisis)
    df = pd.read_sql(sql, engine)
    logger.info("Números distintos extraídos: %d", len(df))
    return df

"""
Reemplaza los componentes Microsoft.OLEDBDestination (con FastLoad/TABLOCK)
usando pandas.to_sql + fast_executemany de pyodbc.
"""
import logging
import pandas as pd
from sqlalchemy import text

from db import get_engine, get_connection

logger = logging.getLogger(__name__)


def truncate_table(table: str, schema: str = "dbo") -> None:
    logger.info("TRUNCATE %s.%s", schema, table)
    with get_connection() as conn:
        conn.execute(text(f"TRUNCATE TABLE [{schema}].[{table}]"))


def load_dataframe(df: pd.DataFrame, table: str, schema: str = "dbo", if_exists: str = "append") -> None:
    logger.info("Cargando %d filas en %s.%s", len(df), schema, table)
    engine = get_engine()
    df.to_sql(
        table,
        con=engine,
        schema=schema,
        if_exists=if_exists,
        index=False,
        chunksize=5000,  # equivalente aproximado a ROWS_PER_BATCH = 5000 del FastLoad
        # NO usar method="multi": arma un solo INSERT con chunksize * n_columnas
        # parámetros, lo que supera el límite de 2100 parámetros de SQL Server
        # (con tablas anchas incluso revienta un contador interno del driver).
        # El modo por defecto usa executemany, que sí es compatible con
        # fast_executemany=True configurado en db.py.
    )
    logger.info("Carga completada en %s.%s", schema, table)

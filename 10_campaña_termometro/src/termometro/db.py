"""
Manejo de conexión y ejecución SQL contra SQL Server.
"""
import logging
from contextlib import contextmanager
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from config import settings

logger = logging.getLogger(__name__)

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(settings.sqlalchemy_url, fast_executemany=True)
    return _engine


@contextmanager
def get_connection():
    engine = get_engine()
    conn = engine.connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def run_sql_file(path: str | Path, params: dict | None = None) -> None:
    """Ejecuta un archivo .sql con parámetros nombrados (:param), dentro de una transacción."""
    with open(path, "r", encoding="utf-8") as f:
        sql = f.read()
    logger.info("Ejecutando %s con params=%s", path, params)
    with get_connection() as conn:
        conn.execute(text(sql), params or {})


def run_sql(sql: str, params: dict | None = None) -> None:
    logger.info("Ejecutando SQL inline con params=%s", params)
    with get_connection() as conn:
        conn.execute(text(sql), params or {})

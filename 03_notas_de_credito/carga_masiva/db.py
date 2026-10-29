"""Conexión a SQL Server y truncado de la tabla destino."""

from __future__ import annotations

import logging

import pyodbc

from config import Settings

logger = logging.getLogger("carga_masiva")


_DRIVERS_PREFERIDOS = ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server")


def _resolver_driver(configurado: str) -> str:
    """Devuelve el driver ODBC a usar: el configurado (DB_DRIVER) si esta
    instalado en esta maquina; si no, el mas nuevo de los instalados. Evita
    tener que fijar la version en el .env de cada equipo."""
    instalados = pyodbc.drivers()
    nombre = configurado.strip().strip("{}")
    if nombre in instalados:
        return nombre
    for candidato in _DRIVERS_PREFERIDOS:
        if candidato in instalados:
            import logging as _logging

            _logging.getLogger(__name__).warning(
                "Driver ODBC '%s' no instalado; se usa '%s'.", nombre, candidato
            )
            return candidato
    return nombre


def crear_conexion(settings: Settings) -> pyodbc.Connection:
    conn_str = (
        f"DRIVER={{{_resolver_driver(settings.db_driver)}}};"
        f"SERVER={settings.db_server};"
        f"DATABASE={settings.db_database};"
        f"UID={settings.db_uid};"
        f"PWD={settings.db_pwd};"
        f"Encrypt={settings.db_encrypt};"
        f"TrustServerCertificate={settings.db_trust_server_certificate}"
    )
    return pyodbc.connect(conn_str)


def truncar_tabla(conn: pyodbc.Connection, tabla: str) -> None:
    cursor = conn.cursor()
    try:
        cursor.execute(f"TRUNCATE TABLE {tabla}")
        conn.commit()
        logger.info("Tabla %s truncada.", tabla)
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()

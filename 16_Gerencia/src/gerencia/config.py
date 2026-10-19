"""Arma la configuracion a partir de variables de entorno (archivo '.env').
Ninguna credencial vive en el codigo ni en este repositorio.

Equivalencias con CL_Proc_Volumetria_Gerencia.dtsx:
  - OLE DB Connection Manager '162.CL_MOVIL' (172.17.0.162, catalogo
    CL_MOVIL, usuario mparedes, MSOLEDBSQL.1): su password estaba encriptada
    por usuario/maquina (DPAPI) y no es reutilizable -> DB_* en '.env'.
  - 4 Excel Connection Managers (archivos locales en '...\\BPO - Insumos\\
    Chile\\Especializados\\...') -> se copian del sitio 'BPO' al sitio
    'ReportingFractalia' (02 ESPECIALIZADOS) via Microsoft Graph y se leen
    desde ahi. Las rutas viven en mappings.py.

'BPO' y 'ReportingFractalia' son tenants de Microsoft Entra DISTINTOS: cada
uno tiene su App Registration (SOURCE_* para BPO, sin prefijo para Reporting),
los mismos que usan 02_ventas y 11_correos.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from exceptions import ConfiguracionError


@dataclass(frozen=True)
class DbSettings:
    """Equivalente al Connection Manager OLE DB '162.CL_MOVIL'."""

    server: str
    database: str
    user: str
    password: str
    driver: str = "ODBC Driver 18 for SQL Server"
    encrypt: str = "no"
    trust_server_certificate: str = "yes"


@dataclass(frozen=True)
class GraphSettings:
    """App Registration (client credentials) + sitio de SharePoint.
    drive_name vacio = drive por defecto del sitio ('BPO' tiene uno solo)."""

    tenant_id: str
    client_id: str
    client_secret: str
    hostname: str
    site_path: str
    drive_name: str | None = None
    timeout_ms: int = 120000


@dataclass(frozen=True)
class Settings:
    db: DbSettings
    origen: GraphSettings  # sitio 'BPO'
    destino: GraphSettings  # sitio 'ReportingFractalia'
    batch_size: int = 5000
    reintentos_conexion: int = 3
    espera_reintento_s: int = 300
    log_dir: Path = Path("logs")


def _require_env(nombre: str) -> str:
    valor = os.getenv(nombre)
    if not valor:
        raise ConfiguracionError(f"La variable de entorno '{nombre}' es obligatoria. Ver .env.example.")
    return valor


def _env_int(nombre: str, default: int) -> int:
    valor = os.getenv(nombre)
    if valor is None or not valor.strip():
        return default
    try:
        return int(valor)
    except ValueError as exc:
        raise ConfiguracionError(f"La variable de entorno '{nombre}' debe ser un numero entero: {valor!r}") from exc


def cargar_configuracion(base_dir: Path) -> Settings:
    """Carga '.env' (junto a main.py) y arma la configuracion."""
    load_dotenv(base_dir / ".env")
    hostname = os.getenv("SHAREPOINT_HOSTNAME") or "fractaliagroup.sharepoint.com"

    return Settings(
        db=DbSettings(
            server=_require_env("DB_SERVER"),
            database=os.getenv("DB_NAME") or "CL_MOVIL",
            user=_require_env("DB_USER"),
            password=_require_env("DB_PASSWORD"),
            driver=os.getenv("DB_DRIVER") or "ODBC Driver 18 for SQL Server",
            encrypt=os.getenv("DB_ENCRYPT") or "no",
            trust_server_certificate=os.getenv("DB_TRUST_SERVER_CERTIFICATE") or "yes",
        ),
        origen=GraphSettings(
            tenant_id=_require_env("SOURCE_TENANT_ID"),
            client_id=_require_env("SOURCE_CLIENT_ID"),
            client_secret=_require_env("SOURCE_CLIENT_SECRET"),
            hostname=os.getenv("SOURCE_SHAREPOINT_HOSTNAME") or hostname,
            site_path=os.getenv("SOURCE_SHAREPOINT_SITE_PATH") or "/sites/BPO",
            drive_name=os.getenv("SOURCE_SHAREPOINT_DRIVE_NAME") or None,
            timeout_ms=_env_int("SOURCE_GRAPH_TIMEOUT", 120000),
        ),
        destino=GraphSettings(
            tenant_id=_require_env("TENANT_ID"),
            client_id=_require_env("CLIENT_ID"),
            client_secret=_require_env("CLIENT_SECRET"),
            hostname=hostname,
            site_path=os.getenv("SHAREPOINT_SITE_PATH") or "/sites/ReportingFractalia",
            drive_name=os.getenv("SHAREPOINT_DRIVE_NAME") or "Data Reporting",
            timeout_ms=_env_int("GRAPH_TIMEOUT", 120000),
        ),
        batch_size=_env_int("BATCH_SIZE", 5000),
        reintentos_conexion=_env_int("REINTENTOS_CONEXION", 3),
        espera_reintento_s=_env_int("ESPERA_REINTENTO_S", 300),
        log_dir=base_dir / "logs",
    )

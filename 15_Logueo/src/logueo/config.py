"""Arma la configuracion a partir de variables de entorno (archivo '.env').
Ninguna credencial vive en el codigo ni en este repositorio.

Equivalencias con Cl_Proc_Logueo.dtsx:
  - OLE DB Connection Manager 'CL_LOGUEO' (172.17.0.162, catalogo CL_LOGUEO,
    usuario mparedes, Provider MSOLEDBSQL.1): su password estaba encriptada por
    usuario/maquina (DPAPI) y no es reutilizable -> DB_* en '.env'.
  - Flat File Connection Manager 'Logueo' (archivo local
    ...\\15 PORTAL COMERCIAL\\REPORTE_AGENTES_FRACTALIA_SEM.csv) -> la misma
    carpeta en SharePoint via Microsoft Graph (SharePointSettings).
  - Variable User::Periodo -> PERIODO (opcional; ver periodo.py).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

import mappings
from exceptions import ConfiguracionError

FOLDER_DEFAULT = "REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/15 PORTAL COMERCIAL"


@dataclass(frozen=True)
class DbSettings:
    """Equivalente al Connection Manager OLE DB 'CL_LOGUEO'."""

    server: str
    database: str
    user: str
    password: str
    driver: str = "ODBC Driver 18 for SQL Server"
    encrypt: str = "no"
    trust_server_certificate: str = "yes"


@dataclass(frozen=True)
class SharePointSettings:
    """App Registration de Microsoft Graph (Sites.Selected sobre
    ReportingFractalia) y carpeta donde 203_bot_portal_comercial publica el CSV."""

    tenant_id: str
    client_id: str
    client_secret: str
    hostname: str
    site_path: str
    drive_name: str
    folder_path: str = FOLDER_DEFAULT
    archivo: str = mappings.ARCHIVO
    timeout_ms: int = 120000

    @property
    def web_drive(self) -> str:
        """URL web de la biblioteca (para los logs)."""
        return f"https://{self.hostname}{self.site_path}/{quote(self.drive_name)}"


@dataclass(frozen=True)
class Settings:
    db: DbSettings
    sharepoint: SharePointSettings
    periodo_env: str | None  # PERIODO del .env (vacio = regla del .dtsx)
    batch_size: int = 5000
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

    return Settings(
        db=DbSettings(
            server=_require_env("DB_SERVER"),
            database=os.getenv("DB_NAME") or "CL_LOGUEO",
            user=_require_env("DB_USER"),
            password=_require_env("DB_PASSWORD"),
            driver=os.getenv("DB_DRIVER") or "ODBC Driver 18 for SQL Server",
            encrypt=os.getenv("DB_ENCRYPT") or "no",
            trust_server_certificate=os.getenv("DB_TRUST_SERVER_CERTIFICATE") or "yes",
        ),
        sharepoint=SharePointSettings(
            tenant_id=_require_env("TENANT_ID"),
            client_id=_require_env("CLIENT_ID"),
            client_secret=_require_env("CLIENT_SECRET"),
            hostname=os.getenv("SHAREPOINT_HOSTNAME") or "fractaliagroup.sharepoint.com",
            site_path=_require_env("SHAREPOINT_SITE_PATH"),
            drive_name=_require_env("SHAREPOINT_DRIVE_NAME"),
            folder_path=os.getenv("SHAREPOINT_FOLDER_PATH") or FOLDER_DEFAULT,
            archivo=os.getenv("LOGUEO_ARCHIVO") or mappings.ARCHIVO,
            timeout_ms=_env_int("GRAPH_TIMEOUT", 120000),
        ),
        periodo_env=os.getenv("PERIODO"),
        batch_size=_env_int("BATCH_SIZE", 5000),
        log_dir=base_dir / "logs",
    )

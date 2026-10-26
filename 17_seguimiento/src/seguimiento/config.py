"""Arma la configuracion a partir de variables de entorno (archivo '.env').
Ninguna credencial vive en el codigo ni en este repositorio.

Equivalencias con los paquetes CL_Seguimiento_0x.dtsx:
  - OLE DB Connection Managers 'PEOPEDESK0328.CL_TEMPORALES',
    '162.CL_TEMPORALES', 'PEOPEDESK0328.BBDD_GENERAL' y '162.BBDD_GENERAL'
    (172.17.0.162, usuario mparedes, SQLOLEDB.1): todos apuntan al mismo
    servidor y todo el T-SQL usa nombres de 3 partes, asi que basta UNA
    configuracion (DB_*). Las passwords estaban encriptadas por
    usuario/maquina (DPAPI) y no son reutilizables -> '.env'.
  - Flat File Connection Managers (...\\BPO - Insumos\\Chile\\SEGUIMIENTO\\
    Nuevo\\*.csv) -> los CSV que publica 201_bot_salesforce en SharePoint
    (SharePointSettings): carpeta '01 SEGUIMIENTO', salvo los dos que el bot
    publica en '12 AUXILIARES' (ver mappings.CARPETA_*).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

import mappings
from exceptions import ConfiguracionError


@dataclass(frozen=True)
class DbSettings:
    """Equivalente a los Connection Managers OLE DB de los paquetes."""

    server: str
    database: str
    user: str
    password: str
    driver: str = "ODBC Driver 18 for SQL Server"
    encrypt: str = "no"
    trust_server_certificate: str = "yes"
    # Idioma de la sesion. El login 'mparedes' tiene idioma por defecto
    # 'Espanol', pero las sesiones de SSIS (SQLOLEDB.1) corren en us_english:
    # TBL_SEGUIMIENTO_FECHA_BASE guarda FORMAT(..., 'hh:mm tt') = '05:30 PM'
    # (en espanol 'tt' sale vacio). Se fija el mismo idioma para que todo el
    # T-SQL (y los SP del paquete 07) se ejecute igual que en SSIS.
    language: str = "us_english"


@dataclass(frozen=True)
class SharePointSettings:
    """App Registration de Microsoft Graph (Sites.Selected sobre
    ReportingFractalia) y carpetas donde 201_bot_salesforce publica los CSV."""

    tenant_id: str
    client_id: str
    client_secret: str
    hostname: str
    site_path: str
    drive_name: str
    carpetas: dict[str, str]  # clave logica (mappings.CARPETA_*) -> ruta dentro del drive
    timeout_ms: int = 120000

    @property
    def web_drive(self) -> str:
        """URL web de la biblioteca (para los logs)."""
        return f"https://{self.hostname}{self.site_path}/{quote(self.drive_name)}"


@dataclass(frozen=True)
class Settings:
    db: DbSettings
    sharepoint: SharePointSettings
    batch_size: int = 5000
    reintentos_conexion: int = 3
    espera_reintento_s: float = 300
    log_dir: Path = Path("logs")
    # Frescura de los CSV (frescura.py): antiguedad maxima en minutos.
    frescura_max_min: int = 150


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
            database=os.getenv("DB_NAME") or mappings.BD_STAGING,
            user=_require_env("DB_USER"),
            password=_require_env("DB_PASSWORD"),
            driver=os.getenv("DB_DRIVER") or "ODBC Driver 18 for SQL Server",
            encrypt=os.getenv("DB_ENCRYPT") or "no",
            trust_server_certificate=os.getenv("DB_TRUST_SERVER_CERTIFICATE") or "yes",
            language=os.getenv("DB_LANGUAGE") or "us_english",
        ),
        sharepoint=SharePointSettings(
            tenant_id=_require_env("TENANT_ID"),
            client_id=_require_env("CLIENT_ID"),
            client_secret=_require_env("CLIENT_SECRET"),
            hostname=os.getenv("SHAREPOINT_HOSTNAME") or "fractaliagroup.sharepoint.com",
            site_path=_require_env("SHAREPOINT_SITE_PATH"),
            drive_name=_require_env("SHAREPOINT_DRIVE_NAME"),
            carpetas={
                mappings.CARPETA_SEGUIMIENTO: os.getenv("SHAREPOINT_FOLDER_SEGUIMIENTO")
                or mappings.CARPETAS_DEFAULT[mappings.CARPETA_SEGUIMIENTO],
                mappings.CARPETA_AUXILIARES: os.getenv("SHAREPOINT_FOLDER_AUXILIARES")
                or mappings.CARPETAS_DEFAULT[mappings.CARPETA_AUXILIARES],
            },
            timeout_ms=_env_int("GRAPH_TIMEOUT", 120000),
        ),
        batch_size=_env_int("BATCH_SIZE", 5000),
        reintentos_conexion=_env_int("REINTENTOS_CONEXION", 3),
        espera_reintento_s=_env_int("ESPERA_REINTENTO_S", 300),
        log_dir=base_dir / "logs",
        frescura_max_min=_env_int("FRESCURA_MAX_MIN", 150),
    )

"""Arma la configuracion a partir de variables de entorno (archivo '.env').
Ninguna credencial vive en el codigo ni en este repositorio.

Equivalencias con SSIS_CL_Puntualidad.dtsx:
  - OLE DB Connection Managers '162.CL_MOVIL.mparedes' y '162_CL_ANALISIS'
    (172.17.0.162, usuario mparedes, MSOLEDBSQL.1): apuntan al mismo servidor y
    todo el T-SQL usa nombres de 3 partes, asi que basta UNA configuracion
    (DB_*). Las passwords estaban encriptadas por usuario/maquina (DPAPI) y no
    son reutilizables -> '.env'.
  - Excel Connection Manager 'SLA' (...\\BPO - Insumos\\Chile\\INDICADORES CHILE\\
    SLA Puntualidad\\DB.xlsx, ACE.OLEDB.12.0) -> el mismo DB.xlsx en SharePoint
    (SharePointSettings), carpeta '08 PUNTUALIDAD'.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

import mappings
from exceptions import ConfiguracionError


@dataclass(frozen=True)
class DbSettings:
    """Equivalente a los Connection Managers OLE DB del paquete."""

    server: str
    database: str
    user: str
    password: str
    driver: str = "ODBC Driver 18 for SQL Server"
    encrypt: str = "no"
    trust_server_certificate: str = "yes"
    # Idioma de la sesion. Los 3 .dtsx anteriores corren en us_english; las
    # funciones de SERVICIOS_GENERALES no dependen del idioma (verificado), pero
    # se fija el mismo de los demas proyectos para que el T-SQL se comporte igual.
    language: str = "us_english"


@dataclass(frozen=True)
class SharePointSettings:
    """App Registration de Microsoft Graph (Sites.Selected sobre
    ReportingFractalia) y ubicacion del Excel DB.xlsx."""

    tenant_id: str
    client_id: str
    client_secret: str
    hostname: str
    site_path: str
    drive_name: str
    carpeta: str
    archivo: str
    hoja: str
    timeout_ms: int = 120000

    @property
    def ruta_archivo(self) -> str:
        """Ruta del Excel dentro del drive (carpeta + nombre)."""
        return f"{self.carpeta.strip('/')}/{self.archivo}"

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
    evidencias_dir: Path = Path("evidencias")
    # Casos con apertura desde esta fecha (FECHA_DESDE en .env), 'YYYY-MM-DD'.
    fecha_desde: str = mappings.FECHA_DESDE_DEFAULT


def _require_env(nombre: str) -> str:
    valor = os.getenv(nombre)
    if not valor:
        raise ConfiguracionError(f"La variable de entorno '{nombre}' es obligatoria. Ver .env.example.")
    return valor


def _env_fecha(nombre: str, default: str) -> str:
    """Fecha 'YYYY-MM-DD' (se escribe como literal en el T-SQL, asi que se valida el formato) y dentro
    del calendario laboral de scripts_sql/puntualidad/10_calendario.sql."""
    valor = (os.getenv(nombre) or default).strip()
    try:
        fecha = datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ConfiguracionError(f"La variable de entorno '{nombre}' debe ser una fecha YYYY-MM-DD: {valor!r}") from exc
    if fecha < datetime.strptime(mappings.FECHA_DESDE_MINIMA, "%Y-%m-%d").date():
        raise ConfiguracionError(
            f"'{nombre}' ({valor}) es anterior al inicio del calendario laboral ({mappings.FECHA_DESDE_MINIMA})."
        )
    return fecha.isoformat()


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
            database=os.getenv("DB_NAME") or mappings.BD_PUNTUALIDAD,
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
            carpeta=os.getenv("SHAREPOINT_FOLDER_PUNTUALIDAD") or mappings.CARPETA_DEFAULT,
            archivo=os.getenv("SHAREPOINT_FILE_SLA") or mappings.ARCHIVO_DEFAULT,
            hoja=os.getenv("SHEET_SLA") or mappings.HOJA_DEFAULT,
            timeout_ms=_env_int("GRAPH_TIMEOUT", 120000),
        ),
        batch_size=_env_int("BATCH_SIZE", 5000),
        reintentos_conexion=_env_int("REINTENTOS_CONEXION", 3),
        espera_reintento_s=_env_int("ESPERA_REINTENTO_S", 300),
        log_dir=base_dir / "logs",
        evidencias_dir=base_dir / "evidencias",
        fecha_desde=_env_fecha("FECHA_DESDE", mappings.FECHA_DESDE_DEFAULT),
    )

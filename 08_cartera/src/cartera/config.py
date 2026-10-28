"""Arma la configuracion a partir de variables de entorno (archivo '.env'),
con valores por defecto no sensibles si no estan definidas. Ninguna
credencial vive en el codigo ni en este repositorio.

Equivalente a los 3 Connection Managers y a la variable User::Fecha_Inicio de
CL_Proc_Carga_Cartera.dtsx. El Connection Manager Excel 'CARTERA' (antes una
ruta local/de red) se reemplazo por Microsoft Graph / SharePoint: ver
SharePointSettings.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from exceptions import CarteraError


@dataclass(frozen=True)
class DbSettings:
    """Equivalente a un Connection Manager OLE DB (Provider MSOLEDBSQL.1)."""

    server: str
    database: str
    user: str
    password: str
    driver: str = "ODBC Driver 18 for SQL Server"
    encrypt: str = "no"
    trust_server_certificate: str = "yes"


@dataclass(frozen=True)
class SharePointSettings:
    """Reemplaza al Connection Manager Excel 'CARTERA': App Registration de
    Microsoft Graph con permiso Sites.Selected sobre el sitio
    ReportingFractalia. Identico al patron de 04_usuarios_y_retenciones/config.py."""

    tenant_id: str
    client_id: str
    client_secret: str
    hostname: str
    site_path: str
    drive_name: str
    folder_path: str
    excel_file_name: str
    timeout_ms: int = 120000

    @property
    def excel_path(self) -> str:
        """Ruta del Excel de origen dentro del drive (carpeta + archivo)."""
        return f"{self.folder_path.strip('/')}/{self.excel_file_name}"


@dataclass(frozen=True)
class Settings:
    db_cartera: DbSettings  # Connection Manager 'PEOPEDESK0328.CL_CARTERA'
    db_temporales: DbSettings  # Connection Manager 'PEOPEDESK0328.CL_TEMPORALES'
    sharepoint: SharePointSettings  # Connection Manager 'CARTERA' (Excel, ahora en SharePoint)
    fecha_inicio: int | None  # User::Fecha_Inicio (valor de diseno original: literal fijo)
    batch_size: int = 5000
    log_file: Path = Path("cartera.log")


def _require_env(nombre: str) -> str:
    valor = os.getenv(nombre)
    if not valor:
        raise CarteraError(f"La variable de entorno '{nombre}' es obligatoria. Ver .env.example.")
    return valor


def _env_int_opcional(nombre: str) -> int | None:
    valor = os.getenv(nombre)
    if valor is None or not valor.strip():
        return None
    return int(valor)


def _env_int(nombre: str, default: int) -> int:
    valor = os.getenv(nombre)
    if valor is None or not valor.strip():
        return default
    return int(valor)


def cargar_configuracion(base_dir: Path, fecha_inicio: int | None = None) -> Settings:
    """Carga '.env' (si existe, junto a main.py) y arma la configuracion.

    'fecha_inicio' permite sobrescribir por linea de comandos el valor de
    VAR_FECHA_INICIO de '.env' -- igual que en SSIS se editaba a mano la
    expresion de la variable User::Fecha_Inicio antes de cada corrida.
    """
    load_dotenv(base_dir / ".env")

    servidor = _require_env("DB_SERVER")
    usuario = _require_env("DB_USER")
    password = _require_env("DB_PASSWORD")
    driver = os.getenv("DB_DRIVER", "ODBC Driver 18 for SQL Server")
    encrypt = os.getenv("DB_ENCRYPT", "no")
    trust_cert = os.getenv("DB_TRUST_SERVER_CERTIFICATE", "yes")

    return Settings(
        db_cartera=DbSettings(
            server=servidor,
            database=os.getenv("DB_NAME_CARTERA", "CL_CARTERA"),
            user=usuario,
            password=password,
            driver=driver,
            encrypt=encrypt,
            trust_server_certificate=trust_cert,
        ),
        db_temporales=DbSettings(
            server=servidor,
            database=os.getenv("DB_NAME_TEMPORALES", "CL_TEMPORALES"),
            user=usuario,
            password=password,
            driver=driver,
            encrypt=encrypt,
            trust_server_certificate=trust_cert,
        ),
        sharepoint=SharePointSettings(
            tenant_id=_require_env("TENANT_ID"),
            client_id=_require_env("CLIENT_ID"),
            client_secret=_require_env("CLIENT_SECRET"),
            hostname=os.getenv("SHAREPOINT_HOSTNAME", "fractaliagroup.sharepoint.com"),
            site_path=_require_env("SHAREPOINT_SITE_PATH"),
            drive_name=_require_env("SHAREPOINT_DRIVE_NAME"),
            folder_path=_require_env("SHAREPOINT_FOLDER_PATH"),
            excel_file_name=os.getenv("EXCEL_FILE_NAME", "CARTERA_FRACTALIA.xlsx"),
            timeout_ms=_env_int("GRAPH_TIMEOUT", 120000),
        ),
        fecha_inicio=fecha_inicio if fecha_inicio is not None else _env_int_opcional("VAR_FECHA_INICIO"),
        batch_size=_env_int("BATCH_SIZE", 5000),
        log_file=base_dir / "cartera.log",
    )

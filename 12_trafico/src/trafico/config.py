"""Arma la configuracion a partir de variables de entorno (archivo '.env').
Ninguna credencial vive en el codigo ni en este repositorio.

Equivalente a los 2 Connection Managers de CL_Proc_Trafico_01.dtsx
('PEOPEDESK0328.CL_TEMPORALES' y 'PEOPEDESK0328.CL_TRAFICO'). El origen
[Externos_Frac] (antes embebido, con usuario y password en texto plano, en
los 7 scripts Traslado_Trafico_Servidor_55_*.py) se reemplazo por CSV en
SharePoint via Microsoft Graph: ver SharePointSettings.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from exceptions import TraficoError

ALERTA_TXT_PATH_DEFAULT = (
    r"D:\IRISCENE ENGINEERING CORPORATION SLU\Gestión Indicadores MDS - CL_trafico\resultado.txt"
)


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
    """App Registration de Microsoft Graph (Sites.Selected sobre
    ReportingFractalia) y carpeta donde 01_servidor_chile publica los CSV."""

    tenant_id: str
    client_id: str
    client_secret: str
    hostname: str
    site_path: str
    drive_name: str
    folder_path: str
    timeout_ms: int = 120000

    def ruta_archivo(self, nombre_archivo: str) -> str:
        """Ruta de un archivo dentro del drive (carpeta + archivo)."""
        return f"{self.folder_path.strip('/')}/{nombre_archivo}"


@dataclass(frozen=True)
class AlertaSettings:
    """Parametros de enviar_alerta_trafico.py (antes constantes en el script)."""

    txt_path: Path
    segundos_espera: int = 30


@dataclass(frozen=True)
class Settings:
    db_temporales: DbSettings  # Connection Manager 'PEOPEDESK0328.CL_TEMPORALES'
    db_trafico: DbSettings  # Connection Manager 'PEOPEDESK0328.CL_TRAFICO'
    sharepoint: SharePointSettings  # reemplaza a [Externos_Frac]
    alerta: AlertaSettings
    periodo: int | None = None  # PERIODO: fija User::Periodo (None = calculo automatico)
    dia_cierre_mes: int = 4  # DIA_CIERRE_MES: hasta que dia se recarga el mes anterior
    batch_size: int = 5000
    log_dir: Path = Path("logs")


def _require_env(nombre: str) -> str:
    valor = os.getenv(nombre)
    if not valor:
        raise TraficoError(f"La variable de entorno '{nombre}' es obligatoria. Ver .env.example.")
    return valor


def _env_int(nombre: str, default: int) -> int:
    valor = os.getenv(nombre)
    if valor is None or not valor.strip():
        return default
    return int(valor)


def _env_int_opcional(nombre: str) -> int | None:
    valor = os.getenv(nombre)
    if valor is None or not valor.strip():
        return None
    try:
        return int(valor)
    except ValueError as exc:
        raise TraficoError(f"La variable de entorno '{nombre}' debe ser un numero entero: {valor!r}") from exc


def cargar_configuracion(base_dir: Path) -> Settings:
    """Carga '.env' (junto a main.py) y arma la configuracion."""
    load_dotenv(base_dir / ".env")

    servidor = _require_env("DB_SERVER")
    usuario = _require_env("DB_USER")
    password = _require_env("DB_PASSWORD")
    driver = os.getenv("DB_DRIVER", "ODBC Driver 18 for SQL Server")
    encrypt = os.getenv("DB_ENCRYPT", "no")
    trust_cert = os.getenv("DB_TRUST_SERVER_CERTIFICATE", "yes")

    def _db(nombre_env: str, default: str) -> DbSettings:
        return DbSettings(
            server=servidor,
            database=os.getenv(nombre_env, default),
            user=usuario,
            password=password,
            driver=driver,
            encrypt=encrypt,
            trust_server_certificate=trust_cert,
        )

    return Settings(
        db_temporales=_db("DB_NAME_TEMPORALES", "CL_TEMPORALES"),
        db_trafico=_db("DB_NAME_TRAFICO", "CL_TRAFICO"),
        sharepoint=SharePointSettings(
            tenant_id=_require_env("TENANT_ID"),
            client_id=_require_env("CLIENT_ID"),
            client_secret=_require_env("CLIENT_SECRET"),
            hostname=os.getenv("SHAREPOINT_HOSTNAME", "fractaliagroup.sharepoint.com"),
            site_path=_require_env("SHAREPOINT_SITE_PATH"),
            drive_name=_require_env("SHAREPOINT_DRIVE_NAME"),
            folder_path=_require_env("SHAREPOINT_FOLDER_PATH"),
            timeout_ms=_env_int("GRAPH_TIMEOUT", 120000),
        ),
        alerta=AlertaSettings(
            txt_path=Path(os.getenv("ALERTA_TXT_PATH") or ALERTA_TXT_PATH_DEFAULT),
            segundos_espera=_env_int("ALERTA_SEGUNDOS_ESPERA", 30),
        ),
        periodo=_env_int_opcional("PERIODO"),
        dia_cierre_mes=_env_int_opcional("DIA_CIERRE_MES") or 4,
        batch_size=_env_int("BATCH_SIZE", 5000),
        log_dir=base_dir / "logs",
    )

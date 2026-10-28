"""Arma la configuracion a partir de variables de entorno (archivo '.env').
Ninguna credencial vive en el codigo ni en este repositorio.

Equivalente al Connection Manager OLE DB 'CL_USUARIOS' (unico destino
restante de los 5 .dtsx originales) y a la variable de paquete
User::Periodo / User::Periodo01 -- mas la configuracion de Microsoft Graph
que reemplaza a 'Externos_Frac' como ORIGEN (ver sharepoint/, extraccion/
extractor.py). 'Externos_Frac' ya no se usa para nada: como origen migro a
SharePoint, y su unico destino (TBL_FRACTALIA_USER_RETENCIONES) se dio de
baja por obsoleto -- no queda ninguna conexion SQL Server hacia esa base.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from exceptions import UsuariosError
from models import Periodo


@dataclass(frozen=True)
class DbSettings:
    """Equivalente a un Connection Manager OLE DB (Provider MSOLEDBSQL.1).

    'user'/'password' quedan en None para un Connection Manager con
    autenticacion de Windows integrada (SSPI) -- ver db.crear_conexion."""

    server: str
    database: str
    driver: str = "ODBC Driver 18 for SQL Server"
    user: str | None = None
    password: str | None = None
    encrypt: str = "no"
    trust_server_certificate: str = "yes"


@dataclass(frozen=True)
class SharePointSettings:
    """Reemplaza, como ORIGEN, al Connection Manager OLE DB 'Externos_Frac':
    App Registration de Microsoft Graph con permiso Sites.Selected sobre el
    sitio ReportingFractalia. Identico al patron de 30_parque/config.py."""

    tenant_id: str
    client_id: str
    client_secret: str
    hostname: str
    site_path: str
    drive_name: str
    folder_path: str
    timeout_ms: int = 120000


@dataclass(frozen=True)
class Settings:
    db_cl_usuarios: DbSettings  # Connection Manager 'LocalHost.CL_USUARIOS' / '162.CL_USUARIOS' (auth SQL)
    sharepoint: SharePointSettings  # ORIGEN: reemplaza las lecturas que antes iban contra Externos_Frac
    periodo: Periodo | None  # User::Periodo / User::Periodo01
    batch_size: int = 5000
    log_file: Path = Path("usuarios.log")


def _require_env(nombre: str) -> str:
    valor = os.getenv(nombre)
    if not valor:
        raise UsuariosError(f"La variable de entorno '{nombre}' es obligatoria. Ver .env.example.")
    return valor


def _env_int(nombre: str, default: int) -> int:
    valor = os.getenv(nombre)
    if valor is None or not valor.strip():
        return default
    return int(valor)


def cargar_configuracion(base_dir: Path, periodo: str | None = None) -> Settings:
    """Carga '.env' (si existe, junto a main.py) y arma la configuracion.

    'periodo' permite sobrescribir por linea de comandos el valor de
    PERIODO de '.env' -- igual que en SSIS se editaba a mano la expresion de
    la variable User::Periodo / User::Periodo01 antes de cada corrida.
    """
    load_dotenv(base_dir / ".env")

    driver = os.getenv("DB_DRIVER", "ODBC Driver 18 for SQL Server")
    encrypt = os.getenv("DB_ENCRYPT", "no")
    trust_cert = os.getenv("DB_TRUST_SERVER_CERTIFICATE", "yes")

    db_cl_usuarios = DbSettings(
        server=_require_env("CL_USUARIOS_DB_SERVER"),
        database=os.getenv("CL_USUARIOS_DB_NAME", "CL_USUARIOS"),
        driver=driver,
        user=_require_env("CL_USUARIOS_DB_USER"),
        password=_require_env("CL_USUARIOS_DB_PASSWORD"),
        encrypt=encrypt,
        trust_server_certificate=trust_cert,
    )
    sharepoint = SharePointSettings(
        tenant_id=_require_env("TENANT_ID"),
        client_id=_require_env("CLIENT_ID"),
        client_secret=_require_env("CLIENT_SECRET"),
        hostname=os.getenv("SHAREPOINT_HOSTNAME", "fractaliagroup.sharepoint.com"),
        site_path=_require_env("SHAREPOINT_SITE_PATH"),
        drive_name=_require_env("SHAREPOINT_DRIVE_NAME"),
        folder_path=_require_env("SHAREPOINT_FOLDER_PATH"),
        timeout_ms=_env_int("GRAPH_TIMEOUT", 120000),
    )

    valor_periodo = periodo if periodo is not None else os.getenv("PERIODO")

    return Settings(
        db_cl_usuarios=db_cl_usuarios,
        sharepoint=sharepoint,
        periodo=Periodo(valor_periodo) if valor_periodo else None,
        batch_size=_env_int("BATCH_SIZE", 5000),
        log_file=base_dir / "usuarios.log",
    )

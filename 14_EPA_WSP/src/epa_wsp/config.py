"""Arma la configuracion a partir de variables de entorno (archivo '.env').
Ninguna credencial vive en el codigo ni en este repositorio.

Equivalente a los 3 Connection Managers de CL_Proc_EPA_WSP.dtsx
('162.BBDD_GENERAL', '162.CL_CALIDAD' y '162.CL_TEMPORALES_INDICADORES').
Sus passwords estaban encriptadas por usuario/maquina (DPAPI) y no son
reutilizables: se declaran en '.env'.

Los scripts .py que ejecutaba el paquete (102_calidad/) tenian ademas
credenciales en TEXTO PLANO: SQL Server (UID/PWD) y la cuenta del portal
Medallia. Aqui todas salen de '.env' (ver .env.example).

El origen [Externos_Frac] (sqlclu01lis01.tchile.local) se reemplazo por los
CSV de SharePoint (Microsoft Graph): ver SharePointSettings. Tambien las 2
carpetas locales de los scripts (Encuestas_Medallia.csv y resultado.txt) se
reemplazaron por la carpeta de SharePoint '16 MEDALLIA' (folder_medallia).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

from exceptions import EpaWspError

FOLDER_MEDALLIA_DEFAULT = "REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/16 MEDALLIA"
MEDALLIA_URL_LOGIN_DEFAULT = "https://telefonicacl.medallia.com/telefonicacl/"
MEDALLIA_URL_REGISTROS_DEFAULT = (
    "https://telefonicacl.medallia.com/telefonicacl/applications/ex_WEB-9/pages/208?roleId=646"
    "&f.pfe_tf_tipo_encuesta_enum=543_9&f.timeperiod=490&fi.pfe_tf_tipo_encuesta_enum=543_9&fi.timeperiod=490"
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
    ReportingFractalia), carpeta donde 01_servidor_chile publica los CSV
    (folder_path, solo lectura) y carpeta donde este proceso deja
    Encuestas_Medallia.csv y resultado.txt (folder_medallia, lectura/escritura)."""

    tenant_id: str
    client_id: str
    client_secret: str
    hostname: str
    site_path: str
    drive_name: str
    folder_path: str
    folder_medallia: str = FOLDER_MEDALLIA_DEFAULT
    timeout_ms: int = 120000

    @property
    def web_drive(self) -> str:
        """URL web de la biblioteca (para los logs)."""
        return f"https://{self.hostname}{self.site_path}/{quote(self.drive_name)}"


@dataclass(frozen=True)
class AlertaSettings:
    """Parametros de enviar_alerta_encuesta.py (antes constantes en el script).
    resultado.txt se guarda en SharePoint (SHAREPOINT_FOLDER_MEDALLIA); antes en
    la carpeta local sincronizada '...\\Gestion Indicadores MDS - Cl_encuesta'."""

    archivo: str = "resultado.txt"
    segundos_espera: int = 30


@dataclass(frozen=True)
class MedalliaSettings:
    """Parametros de CL_Descarga_encuestas_Medallia.py y
    CL_Carga_de_encuestas_MEDALLIA.py (antes constantes en los scripts)."""

    usuario: str
    password: str
    # ruta_destino (descarga) = csv_file (carga): ahora en SharePoint
    # (SHAREPOINT_FOLDER_MEDALLIA); antes '...\\Data Analytics Reporting Fractalia - Medallia'.
    archivo: str = "Encuestas_Medallia.csv"
    url_login: str = MEDALLIA_URL_LOGIN_DEFAULT
    url_registros: str = MEDALLIA_URL_REGISTROS_DEFAULT
    prefijo_archivo: str = "Telefonica Moviles Chile SA_export_"
    segundos_espera_descarga: int = 60
    headless: bool = True
    navegador: str = "firefox"  # navegador de Playwright: firefox (como el original), chromium o webkit
    carpeta_capturas: Path = Path("logs")  # captura de pantalla si la descarga falla


@dataclass(frozen=True)
class Settings:
    db_bbdd_general: DbSettings  # Connection Manager '162.BBDD_GENERAL'
    db_calidad: DbSettings  # Connection Manager '162.CL_CALIDAD'
    db_indicadores: DbSettings  # Connection Manager '162.CL_TEMPORALES_INDICADORES'
    sharepoint: SharePointSettings  # reemplaza a [Externos_Frac]
    alerta: AlertaSettings
    medallia: MedalliaSettings
    periodo_desde_encuesta: int = 202601  # filtro 'periodo_evento >= 202601' del traslado EPA_ISN
    batch_size: int = 5000
    log_dir: Path = Path("logs")


def _require_env(nombre: str) -> str:
    valor = os.getenv(nombre)
    if not valor:
        raise EpaWspError(f"La variable de entorno '{nombre}' es obligatoria. Ver .env.example.")
    return valor


def _env_int(nombre: str, default: int) -> int:
    valor = os.getenv(nombre)
    if valor is None or not valor.strip():
        return default
    try:
        return int(valor)
    except ValueError as exc:
        raise EpaWspError(f"La variable de entorno '{nombre}' debe ser un numero entero: {valor!r}") from exc


def _env_bool(nombre: str, default: bool) -> bool:
    valor = os.getenv(nombre)
    if valor is None or not valor.strip():
        return default
    return valor.strip().lower() in ("1", "true", "si", "sí", "yes")


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
        db_bbdd_general=_db("DB_NAME_BBDD_GENERAL", "BBDD_GENERAL"),
        db_calidad=_db("DB_NAME_CALIDAD", "CL_CALIDAD"),
        db_indicadores=_db("DB_NAME_INDICADORES", "CL_TEMPORALES_INDICADORES"),
        sharepoint=SharePointSettings(
            tenant_id=_require_env("TENANT_ID"),
            client_id=_require_env("CLIENT_ID"),
            client_secret=_require_env("CLIENT_SECRET"),
            hostname=os.getenv("SHAREPOINT_HOSTNAME", "fractaliagroup.sharepoint.com"),
            site_path=_require_env("SHAREPOINT_SITE_PATH"),
            drive_name=_require_env("SHAREPOINT_DRIVE_NAME"),
            folder_path=_require_env("SHAREPOINT_FOLDER_PATH"),
            folder_medallia=os.getenv("SHAREPOINT_FOLDER_MEDALLIA") or FOLDER_MEDALLIA_DEFAULT,
            timeout_ms=_env_int("GRAPH_TIMEOUT", 120000),
        ),
        alerta=AlertaSettings(
            archivo=os.getenv("ALERTA_ARCHIVO") or "resultado.txt",
            segundos_espera=_env_int("ALERTA_SEGUNDOS_ESPERA", 30),
        ),
        medallia=MedalliaSettings(
            usuario=_require_env("MEDALLIA_USER"),
            password=_require_env("MEDALLIA_PASSWORD"),
            archivo=os.getenv("MEDALLIA_ARCHIVO") or "Encuestas_Medallia.csv",
            url_login=os.getenv("MEDALLIA_URL_LOGIN") or MEDALLIA_URL_LOGIN_DEFAULT,
            url_registros=os.getenv("MEDALLIA_URL_REGISTROS") or MEDALLIA_URL_REGISTROS_DEFAULT,
            prefijo_archivo=os.getenv("MEDALLIA_PREFIJO_ARCHIVO") or "Telefonica Moviles Chile SA_export_",
            segundos_espera_descarga=_env_int("MEDALLIA_SEGUNDOS_ESPERA_DESCARGA", 60),
            headless=_env_bool("MEDALLIA_HEADLESS", True),
            navegador=(os.getenv("MEDALLIA_NAVEGADOR") or "firefox").strip().lower(),
            carpeta_capturas=base_dir / "logs",
        ),
        periodo_desde_encuesta=_env_int("PERIODO_DESDE_ENCUESTA", 202601),
        batch_size=_env_int("BATCH_SIZE", 5000),
        log_dir=base_dir / "logs",
    )

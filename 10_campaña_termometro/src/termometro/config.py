"""
Configuración del pipeline, leída desde variables de entorno (.env).

Reemplaza:
- Los Connection Managers del .dtsx (OLEDB "162", EXCEL "ACTUAL_", FLATFILE "Reporte_termometro_v2").
  Los dos archivos se leen de SharePoint vía Microsoft Graph (carpeta
  .../04 CAMPAÑAS/Termometro del site ReportingFractalia), no de disco.
- Las variables User::Fecha_inicio, User::Fecha_fin, User::Periodo
"""
import os
from datetime import date
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")  # .env en la raiz del proyecto, junto a main.py
except ImportError:
    pass  # python-dotenv es opcional; si no está, se usan variables de entorno del sistema


_DRIVERS_PREFERIDOS = ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server")


def _resolver_driver(configurado: str) -> str:
    """Devuelve el driver ODBC a usar: el configurado (DB_DRIVER) si esta
    instalado en esta maquina; si no, el mas nuevo de los instalados. Evita
    tener que fijar la version en el .env de cada equipo."""
    import pyodbc

    instalados = pyodbc.drivers()
    nombre = configurado.strip().strip("{}")
    if nombre in instalados:
        return nombre
    for candidato in _DRIVERS_PREFERIDOS:
        if candidato in instalados:
            return candidato
    return nombre


@dataclass(frozen=True)
class Settings:
    # --- Conexión SQL Server (reemplaza Connection Manager "162") ---
    db_server: str = os.getenv("DB_SERVER", "172.17.0.162")
    db_database: str = os.getenv("DB_DATABASE", "CL_CAMPAÑAS")
    db_user: str = os.getenv("DB_USER", "")
    db_password: str = os.getenv("DB_PASSWORD", "")
    db_driver: str = os.getenv("DB_DRIVER", "ODBC Driver 18 for SQL Server")

    # --- Base de datos de cartera (usada en el JOIN final) ---
    db_cartera_database: str = os.getenv("DB_CARTERA_DATABASE", "CL_CARTERA")

    # --- Microsoft Graph: App Registration con acceso al site ReportingFractalia ---
    tenant_id: str = os.getenv("TENANT_ID", "")
    client_id: str = os.getenv("CLIENT_ID", "")
    client_secret: str = os.getenv("CLIENT_SECRET", "")
    graph_timeout_ms: int = int(os.getenv("GRAPH_TIMEOUT") or 120000)

    # --- Origen de los archivos en SharePoint (reemplaza Connection Manager "ACTUAL_" y "Reporte_termometro_v2") ---
    sharepoint_hostname: str = os.getenv("SHAREPOINT_HOSTNAME") or "fractaliagroup.sharepoint.com"
    sharepoint_site_path: str = os.getenv("SHAREPOINT_SITE_PATH") or "/sites/ReportingFractalia"
    sharepoint_drive_name: str = os.getenv("SHAREPOINT_DRIVE_NAME") or "Data Reporting"
    sharepoint_folder_path: str = (
        os.getenv("SHAREPOINT_FOLDER_PATH") or "REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/04 CAMPAÑAS/Termometro"
    )
    # Rutas relativas a SHAREPOINT_FOLDER_PATH
    excel_clientes_archivo: str = os.getenv("EXCEL_CLIENTES_ARCHIVO") or "SOURCE/ACTUAL_.xlsx"
    csv_salesforce_archivo: str = os.getenv("CSV_SALESFORCE_ARCHIVO") or "SF/Reporte_termometros.csv"

    excel_clientes_sheet: str = os.getenv("EXCEL_CLIENTES_SHEET", "DB")
    excel_detractores_sheet: str = os.getenv("EXCEL_DETRACTORES_SHEET", "DB_DETRACTOR")

    csv_salesforce_encoding: str = os.getenv("CSV_SALESFORCE_ENCODING", "latin-1")
    csv_salesforce_delimiter: str = os.getenv("CSV_SALESFORCE_DELIMITER", ",")

    # --- Validación de conexiones antes de ejecutar (conexiones.py) ---
    reintentos_conexion: int = int(os.getenv("REINTENTOS_CONEXION") or 3)
    espera_reintento_s: int = int(os.getenv("ESPERA_REINTENTO_S") or 300)

    # --- Parámetros del proceso (reemplaza User::Periodo, User::Fecha_inicio, User::Fecha_fin) ---
    periodo: int = int(os.getenv("PERIODO", date.today().strftime("%Y%m")))
    fecha_inicio: str = os.getenv("FECHA_INICIO", date.today().replace(day=1).isoformat())
    fecha_fin: str = os.getenv("FECHA_FIN", date.today().isoformat())

    @property
    def sqlalchemy_url(self) -> str:
        from urllib.parse import quote_plus

        odbc_str = (
            f"DRIVER={{{_resolver_driver(self.db_driver)}}};"
            f"SERVER={self.db_server};"
            f"DATABASE={self.db_database};"
            f"UID={self.db_user};PWD={self.db_password};"
            f"TrustServerCertificate=yes;"
        )
        return f"mssql+pyodbc:///?odbc_connect={quote_plus(odbc_str)}"


settings = Settings()

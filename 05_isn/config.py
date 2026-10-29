"""
Configuración del pipeline, leída desde variables de entorno (.env).

Reemplaza:
- Los Connection Managers OLEDB de ambos .dtsx: "162.CL_ANALISIS.mparedes"
  (SSIS_CL_ISN_Contactos), "162.CL_ISN" y "162.CL_CALIDAD" (SSIS_CL_ISN).
  Los tres apuntan al mismo servidor (172.17.0.162), solo cambia la base.
- Los Connection Managers FLATFILE: "Reporte_Contactos_Salesforce_BI", "CSV"
  (isn.csv), "Reporte_isn_aux_cliente", "Reporte_isn_aux_contacto".
- Las variables User::Fecha_inicio / User::Fecha_fin / User::New_name de
  SSIS_CL_ISN.dtsx.

Ningún valor sensible tiene default embebido salvo el usuario de BD (que ya
figuraba en texto plano en los .dtsx originales); la contraseña siempre se
lee de entorno y por defecto es "" para forzar a completarla en .env.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # python-dotenv es opcional; si no está, se usan variables de entorno del sistema

BASE_DIR = Path(__file__).resolve().parent


def _default_fecha(offset_dias: int = 1) -> str:
    return (date.today() - timedelta(days=offset_dias)).isoformat()


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
    # --- Conexión SQL Server (mismo servidor, 3 bases) ---
    db_server: str = os.getenv("DB_SERVER", "172.17.0.162")
    db_user: str = os.getenv("DB_USER", "mparedes")
    db_password: str = os.getenv("DB_PASSWORD", "")
    db_driver: str = os.getenv("DB_DRIVER", "ODBC Driver 18 for SQL Server")

    db_database_analisis: str = os.getenv("DB_DATABASE_ANALISIS", "CL_ANALISIS")
    db_database_isn: str = os.getenv("DB_DATABASE_ISN", "CL_ISN")
    db_database_calidad: str = os.getenv("DB_DATABASE_CALIDAD", "CL_CALIDAD")

    # --- Contactos: Connection Manager FLATFILE "Reporte_Contactos_Salesforce_BI" ---
    csv_contactos_path: Path = field(
        default_factory=lambda: Path(
            os.getenv(
                "CSV_CONTACTOS_PATH",
                r"D:\IRISCENE ENGINEERING CORPORATION SLU\BPO - Insumos\Chile\Reporte Contactos Salesforce BI\Reporte_Contactos_Salesforce_BI.csv",
            )
        )
    )
    # El .dtsx declara CodePage=1252, pero el archivo real (verificado) trae
    # al menos un byte fuera de rango para cp1252 estricto (0x8d, en algún
    # campo de texto libre) -- igual que el hallazgo ya documentado en
    # 10_campaña_termometro/. "latin-1" (ISO-8859-1) mapea los 256 valores de
    # byte 1:1 y sí lee el archivo completo. Ver README para el detalle.
    csv_contactos_encoding: str = os.getenv("CSV_CONTACTOS_ENCODING", "latin-1")
    csv_contactos_delimiter: str = os.getenv("CSV_CONTACTOS_DELIMITER", ",")

    # --- ISN: Connection Managers FLATFILE "CSV", "Reporte_isn_aux_cliente", "Reporte_isn_aux_contacto" ---
    csv_isn_path: Path = field(
        default_factory=lambda: Path(
            os.getenv(
                "CSV_ISN_PATH",
                r"D:\OneDrive - IRISCENE ENGINEERING CORPORATION SLU\ISN\Automatizado\Source\isn.csv",
            )
        )
    )
    csv_isn_aux_cliente_path: Path = field(
        default_factory=lambda: Path(
            os.getenv(
                "CSV_ISN_AUX_CLIENTE_PATH",
                r"D:\IRISCENE ENGINEERING CORPORATION SLU\BPO - Insumos\Chile\ISN\Aux_cliente\Reporte_isn_aux_cliente.csv",
            )
        )
    )
    csv_isn_aux_contacto_path: Path = field(
        default_factory=lambda: Path(
            os.getenv(
                "CSV_ISN_AUX_CONTACTO_PATH",
                r"D:\IRISCENE ENGINEERING CORPORATION SLU\BPO - Insumos\Chile\ISN\Aux_contacto\Reporte_isn_aux_contacto.csv",
            )
        )
    )
    # Mismo hallazgo que en csv_contactos_encoding: cp1252 estricto puede
    # fallar con bytes fuera de rango en estos reportes; latin-1 es más
    # tolerante y se usa como default (confirmar si aparecen tildes mal
    # decodificadas en algún campo puntual).
    csv_isn_encoding: str = os.getenv("CSV_ISN_ENCODING", "latin-1")

    # --- ISN: variable User::New_name (carpeta donde se archiva el export con fecha) ---
    isn_archive_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv(
                "ISN_ARCHIVE_DIR",
                r"D:\OneDrive - IRISCENE ENGINEERING CORPORATION SLU\ISN\Automatizado",
            )
        )
    )
    # El .dtsx original no trae un "Operation" explícito en el FileSystemTask
    # "Cambiar nombre archivo" (se verificó en el XML); el default de SSIS es
    # CopyFile, así que por defecto no se destruye el isn.csv fuente. Se deja
    # configurable por si en producción el comportamiento real era mover el
    # archivo (confirmar contra SSDT si hace falta).
    isn_archive_operation: str = os.getenv("ISN_ARCHIVE_OPERATION", "copy")  # "copy" | "move"

    # --- ISN: variables User::Fecha_inicio / User::Fecha_fin (rango a evaluar en TBL_ISN_SF) ---
    fecha_inicio: str = os.getenv("FECHA_INICIO", _default_fecha())
    fecha_fin: str = os.getenv("FECHA_FIN", _default_fecha())

    log_dir: Path = field(default_factory=lambda: BASE_DIR / "logs")

    def _odbc_string(self, database: str) -> str:
        return (
            f"DRIVER={{{_resolver_driver(self.db_driver)}}};"
            f"SERVER={self.db_server};"
            f"DATABASE={database};"
            f"UID={self.db_user};PWD={self.db_password};"
            f"TrustServerCertificate=yes;"
        )

    def sqlalchemy_url(self, database: str) -> str:
        from urllib.parse import quote_plus

        return f"mssql+pyodbc:///?odbc_connect={quote_plus(self._odbc_string(database))}"


settings = Settings()

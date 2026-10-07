"""
Punto de entrada. Reemplaza la ejecución manual/por SQL Server Agent del
paquete SSIS_CL_Campaña_Termometro.dtsx.

Arquitectura (src layout, modular por componentes):
    extraccion/fuentes.py            Origen de los archivos: SharePoint vía Graph (o disco, contingencia).
    extraccion/excel_extractor.py    Origen de Excel (hojas DB y DB_DETRACTOR de ACTUAL_.xlsx).
    extraccion/csv_extractor.py      Flat File Source (Reporte_termometros.csv de Salesforce).
    transformacion/clientes.py       Data Flow 'BASE TERMOMETRO'.
    transformacion/detractores.py    Data Flow 'TBL_CAMPAÑA_TERMOMETRO_DETRACTOR'.
    transformacion/encuestas.py      Data Flow 'TBL_CAMPAÑA_TERMOMETRO_SF_TEMP_2'.
    carga/loader.py                  OLE DB Destination (TRUNCATE + carga por lotes).
    pipeline.py                      Orquestador: el Control Flow del .dtsx.
    sql.py, scripts_sql/             Execute SQL Task (T-SQL parametrizado).
    db.py, config.py                 Conexión SQL Server y configuración vía '.env'.
    sharepoint/                      Cliente Microsoft Graph (mismo de 15_Logueo).
    main.py (este archivo)           Composition root.

Archivos crudos (SharePoint, site ReportingFractalia / Data Reporting):
    REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/04 CAMPAÑAS/Termometro/SOURCE/ACTUAL_.xlsx
    REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/04 CAMPAÑAS/Termometro/SF/Reporte_termometros.csv

Uso:
    python main.py --periodo 202607 --fecha-inicio 2026-07-01 --fecha-fin 2026-07-31
    python main.py --excel-local RUTA --csv-local RUTA   # contingencia: lee de disco en vez de SharePoint
"""
import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "src" / "termometro"))  # permite 'import config', 'import pipeline', etc.

from config import settings  # noqa: E402
import pipeline  # noqa: E402
from extraccion.fuentes import Fuente, FuenteLocal, FuenteSharePoint  # noqa: E402
from sharepoint.auth import get_graph_token  # noqa: E402
from sharepoint.client import SharePointClient  # noqa: E402


def setup_logging() -> None:
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_dir / f"termometro_{datetime.now():%Y%m%d_%H%M%S}.log", encoding="utf-8"),
        ],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ETL Campaña Termómetro (migrado desde SSIS)")
    parser.add_argument("--periodo", type=int, default=settings.periodo, help="Periodo AAAAMM, ej. 202607")
    parser.add_argument("--fecha-inicio", type=str, default=settings.fecha_inicio, help="YYYY-MM-DD")
    parser.add_argument("--fecha-fin", type=str, default=settings.fecha_fin, help="YYYY-MM-DD")
    parser.add_argument("--excel-local", type=Path, help="Lee ACTUAL_.xlsx desde disco en vez de SharePoint.")
    parser.add_argument("--csv-local", type=Path, help="Lee Reporte_termometros.csv desde disco en vez de SharePoint.")
    return parser.parse_args()


def crear_fuentes(args: argparse.Namespace) -> tuple[Fuente, Fuente]:
    """Fuentes de los dos archivos crudos. Solo se conecta a Graph si alguno se lee de SharePoint."""
    if args.excel_local and args.csv_local:
        return FuenteLocal(args.excel_local), FuenteLocal(args.csv_local)

    for nombre in ("tenant_id", "client_id", "client_secret"):
        if not getattr(settings, nombre):
            raise RuntimeError(f"Falta {nombre.upper()} en el .env (App Registration de Microsoft Graph).")
    token = get_graph_token(settings.tenant_id, settings.client_id, settings.client_secret, settings.graph_timeout_ms)
    client = SharePointClient(token, settings.graph_timeout_ms)
    site_id = client.resolve_site(settings.sharepoint_hostname, settings.sharepoint_site_path)
    drive_id = client.resolve_drive(site_id, settings.sharepoint_drive_name)
    web_drive = f"https://{settings.sharepoint_hostname}{settings.sharepoint_site_path}/{quote(settings.sharepoint_drive_name)}"

    def sharepoint(archivo: str) -> FuenteSharePoint:
        return FuenteSharePoint(client, drive_id, f"{settings.sharepoint_folder_path}/{archivo}", web_drive)

    excel = FuenteLocal(args.excel_local) if args.excel_local else sharepoint(settings.excel_clientes_archivo)
    csv = FuenteLocal(args.csv_local) if args.csv_local else sharepoint(settings.csv_salesforce_archivo)
    return excel, csv


def main() -> int:
    setup_logging()
    logger = logging.getLogger("main")

    args = parse_args()
    logger.info("Iniciando ETL Termómetro | periodo=%s rango=%s..%s", args.periodo, args.fecha_inicio, args.fecha_fin)

    try:
        fuente_excel, fuente_csv = crear_fuentes(args)
        pipeline.run(args.periodo, args.fecha_inicio, args.fecha_fin, fuente_excel, fuente_csv)
    except Exception:
        logger.exception("El pipeline terminó con errores")
        return 1

    logger.info("ETL Termómetro finalizado correctamente")
    return 0


def _mostrar_proyecto():
    """Muestra el nombre del proyecto en la consola y en el titulo de la ventana."""
    import ctypes

    nombre = BASE_DIR.name
    print("=" * 60, f" PROYECTO: {nombre}", "=" * 60, sep="\n", flush=True)
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetConsoleTitleW(nombre)


if __name__ == "__main__":
    _mostrar_proyecto()
    sys.exit(main())

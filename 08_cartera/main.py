"""Migracion a Python del paquete SSIS 'CL_Proc_Carga_Cartera.dtsx': carga de
la cartera de clientes vigente (Chile) desde un Excel mantenido manualmente
hacia SQL Server, con reclasificacion de estado (NUEVO/SE MANTIENE/REINGRESO)
contra el historico.

Flujo (equivalente a los 3 Sequence Containers del .dtsx -- ver pipeline.py
para el detalle completo):

    CARGA CARTERA TEMPORAL -> CARGA CARTERA ACTUAL -> HISTORICO CARTERA

Arquitectura ("src layout": codigo en src/cartera/, modular, dividida en
las 4 capas del proceso original, una carpeta por capa):
    extraccion/extractor.py       Extraccion: Excel (SharePoint) -> DataFrame saneado.
    validacion/validator.py       Validacion: los 4 controles de la tarea 'VALIDA'.
    transformacion/transformer.py Transformacion: CARGA DNI, ACTUALIZA STATUS,
                                   LIMITA CLIENTES, LIMPIA TEMPORAL.
    carga/loader.py               Carga: truncados, inserts y copia entre bases.
    pipeline.py                   Orquestador: llama a las 4 capas anteriores en
                                   el orden del Control Flow original.
    models.py, exceptions.py      Value objects (Periodo, ResultadoPipeline) y
                                   excepciones. Sin dependencias externas.
    mappings.py, sql.py           Constantes de negocio: columnas/tablas/anchos
                                   de truncamiento, y las sentencias T-SQL
                                   migradas literalmente de cada Execute SQL Task.
    db.py, spreadsheet.py         Adaptadores concretos: pyodbc (SQL Server) y
                                   pandas/openpyxl (Excel descargado de SharePoint).
    sharepoint/                   Adaptadores Microsoft Graph: auth.py (token
                                   client credentials) y client.py (site/drive/descarga).
    config.py, logging_setup.py   Configuracion via '.env' y logging.
    main.py (este archivo)        Composition root: arma db.py/spreadsheet.py (con
                                   el cliente Graph) y los pasa a CarteraPipeline.

Configuracion:
    Los valores se leen del archivo '.env' (junto a este script; ver
    '.env.example' para la lista completa). Ninguna credencial esta
    embebida en el codigo -- las 2 conexiones OLE DB del paquete original
    tenian password DPAPI-encriptado por usuario/maquina, imposible de
    reutilizar fuera de esa maquina; aqui se declaran en '.env' (no
    versionado). El Excel de origen (CARTERA_FRACTALIA.xlsx) se descarga de
    SharePoint (sitio ReportingFractalia) via Microsoft Graph con un App
    Registration (Sites.Selected), en vez de leerse de una ruta local/de red.

Uso:
    python main.py --fecha-inicio 20260827   # equivalente a editar a mano
                                              # User::Fecha_Inicio en el .dtsx
    python main.py                           # usa VAR_FECHA_INICIO de .env
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "src" / "cartera"))  # permite 'import mappings', 'import sql', etc. al correr como script suelto

from config import cargar_configuracion
from db import DatabaseGateway, crear_conexion
from exceptions import CarteraError, PipelineError, ValidacionError
from logging_setup import NOMBRE_LOGGER, configurar_logging
from models import Periodo, hoy_yyyymmdd
from pipeline import CarteraPipeline
from sharepoint.auth import GraphAuthError, get_graph_token
from sharepoint.client import SharePointClient, SharePointResolutionError
from spreadsheet import SpreadsheetReader

logger = logging.getLogger(NOMBRE_LOGGER)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--fecha-inicio",
        type=int,
        default=None,
        help="Inicio del periodo de cartera vigente, formato YYYYMMDD "
        "(equivalente a User::Fecha_Inicio). Por defecto: VAR_FECHA_INICIO de .env.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    settings = cargar_configuracion(BASE_DIR, fecha_inicio=args.fecha_inicio)
    configurar_logging(settings.log_file)

    if settings.fecha_inicio is None:
        logger.error(
            "No hay fecha de inicio de periodo disponible: defina VAR_FECHA_INICIO "
            "en .env (equivalente a User::Fecha_Inicio) o pase --fecha-inicio YYYYMMDD."
        )
        return 1

    periodo = Periodo(fecha_inicio=settings.fecha_inicio, fecha_fin=hoy_yyyymmdd())
    logger.info("Iniciando carga de Cartera para el periodo %s.", periodo)

    conn_cartera = None
    conn_temporales = None
    try:
        sp = settings.sharepoint
        token = get_graph_token(sp.tenant_id, sp.client_id, sp.client_secret, sp.timeout_ms)
        client = SharePointClient(token, sp.timeout_ms)
        site_id = client.resolve_site(sp.hostname, sp.site_path)
        drive_id = client.resolve_drive(site_id, sp.drive_name)

        conn_cartera = crear_conexion(settings.db_cartera)
        conn_temporales = crear_conexion(settings.db_temporales)

        pipeline = CarteraPipeline(
            db_cartera=DatabaseGateway(conn_cartera, settings.batch_size),
            db_temporales=DatabaseGateway(conn_temporales, settings.batch_size),
            spreadsheet_reader=SpreadsheetReader(client, drive_id),
            excel_path=sp.excel_path,
        )
        resultado = pipeline.run(periodo)

        logger.info(
            "Proceso finalizado correctamente: %s filas extraidas, %s en staging, "
            "%s copiadas a TBL_CARTERA_ACTUAL.",
            resultado.filas_extraidas,
            resultado.filas_staging,
            resultado.filas_actual,
        )
        return 0

    except PipelineError as exc:
        if isinstance(exc.causa, ValidacionError):
            logger.error("Validacion de calidad de datos fallida: %s", exc.causa)
        else:
            logger.error("Error durante la carga de Cartera: %s", exc)
        logger.exception("Detalle del error:")
        return 1

    except (GraphAuthError, SharePointResolutionError) as exc:
        logger.error("Error conectando con SharePoint (Microsoft Graph): %s", exc)
        return 1

    except CarteraError as exc:
        logger.error("Error de configuracion: %s", exc)
        return 1

    finally:
        if conn_temporales is not None:
            conn_temporales.close()
        if conn_cartera is not None:
            conn_cartera.close()


def _mostrar_proyecto():
    """Muestra el nombre del proyecto en la consola y en el titulo de la ventana."""
    import ctypes
    import sys
    from pathlib import Path

    carpeta = Path(__file__).resolve().parent
    nombre = carpeta.name
    print("=" * 60, f" PROYECTO: {nombre}", "=" * 60, sep="\n", flush=True)
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetConsoleTitleW(nombre)


if __name__ == "__main__":
    _mostrar_proyecto()
    sys.exit(main())

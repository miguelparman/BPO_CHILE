"""Migracion a Python del paquete SSIS 'CL_Proc_Trafico_01.dtsx': carga diaria
del trafico de llamadas/chat de Chile (atendidas, abandonadas, transferidas,
outbound, cleared, callback y cross inbound) en CL_TEMPORALES y CL_TRAFICO.

Flujo (ver src/trafico/pipeline.py para el detalle y la equivalencia con
cada tarea del .dtsx):

    Log Inicio -> alerta -> TEMPORALES -> LIMPIA TEMPORALES -> CL_TRAFICO -> Log Fin

Arquitectura (src layout, modular por componentes, una carpeta por capa):
    extraccion/extractor.py        CSV de SharePoint -> DataFrames tipados; lectura de temporales.
    validacion/validator.py        Esquema real vs mappings.py; anchos de los datos de origen.
    transformacion/transformer.py  Tareas SQL de enriquecimiento + Data Flow 'CARGA'.
    carga/loader.py                LOGS_PROCESOS, temporales y CL_TRAFICO (transaccionales).
    alerta.py                      enviar_alerta_trafico.py (resultado.txt para Power Automate).
    pipeline.py                    Orquestador: llama a las capas en el orden del Control Flow.
    mappings.py, sql.py            Constantes de negocio y T-SQL literal del .dtsx (scripts_sql/).
    db.py, sharepoint/             Adaptadores: pyodbc (SQL Server) y Microsoft Graph.
    config.py, logging_setup.py    Configuracion via '.env' y logging.
    main.py (este archivo)         Composition root: arma los adaptadores y corre el pipeline.

Configuracion: archivo '.env' junto a este script (ver '.env.example').
Ninguna credencial esta embebida en el codigo.

Uso:
    python main.py                    # periodo: PERIODO de .env, o automatico (mes anterior si hoy es dia <= DIA_CIERRE_MES)
    python main.py --periodo 202609   # fuerza el periodo (YYYYMM); tiene prioridad sobre .env
    python main.py --solo-validar     # descarga y valida los CSV + esquema, sin escribir nada
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "src" / "trafico"))  # permite 'import mappings', 'import sql', etc.

from config import cargar_configuracion  # noqa: E402
from db import DatabaseGateway, crear_conexion  # noqa: E402
from exceptions import PipelineError, TraficoError  # noqa: E402
from logging_setup import NOMBRE_LOGGER, configurar_logging  # noqa: E402
from models import resolver_periodo  # noqa: E402
from pipeline import TraficoPipeline  # noqa: E402
from sharepoint.auth import GraphAuthError, get_graph_token  # noqa: E402
from sharepoint.client import SharePointClient, SharePointResolutionError  # noqa: E402
from sharepoint.reader import CsvReader  # noqa: E402

logger = logging.getLogger(NOMBRE_LOGGER)


def _periodo(texto: str) -> int:
    if len(texto) != 6 or not texto.isdigit() or not 1 <= int(texto[4:]) <= 12:
        raise argparse.ArgumentTypeError("formato esperado YYYYMM, p.ej. 202609")
    return int(texto)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--periodo", type=_periodo, default=None, help="Periodo YYYYMM; prioridad sobre PERIODO de .env (por defecto: User::Periodo).")
    parser.add_argument(
        "--solo-validar", action="store_true", help="Solo extrae y valida (CSV + esquema); no escribe en la base."
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        settings = cargar_configuracion(BASE_DIR)
    except TraficoError as exc:
        print(f"Error de configuracion: {exc}", file=sys.stderr)
        return 1
    log_file = configurar_logging(settings.log_dir)
    logger.info("Log de esta corrida: %s", log_file)
    try:
        periodo, fuente = resolver_periodo(date.today(), args.periodo, settings.periodo, settings.dia_cierre_mes)
    except ValueError as exc:
        logger.error("PERIODO invalido: %s", exc)
        return 1
    logger.info("Periodo a procesar: %s (origen: %s)", periodo, fuente)

    db_temporales = DatabaseGateway(lambda: crear_conexion(settings.db_temporales), settings.batch_size, "CL_TEMPORALES")
    db_trafico = DatabaseGateway(lambda: crear_conexion(settings.db_trafico), settings.batch_size, "CL_TRAFICO")
    try:
        sp = settings.sharepoint
        token = get_graph_token(sp.tenant_id, sp.client_id, sp.client_secret, sp.timeout_ms)
        client = SharePointClient(token, sp.timeout_ms)
        drive_id = client.resolve_drive(client.resolve_site(sp.hostname, sp.site_path), sp.drive_name)

        pipeline = TraficoPipeline(
            db_temporales=db_temporales,
            db_trafico=db_trafico,
            csv_reader=CsvReader(client, drive_id, sp.folder_path),
            alerta_txt_path=settings.alerta.txt_path,
            alerta_segundos_espera=settings.alerta.segundos_espera,
        )
        pipeline.run(periodo, solo_validar=args.solo_validar)
        return 0

    except PipelineError as exc:
        logger.error("Error durante el proceso de Trafico: %s", exc)
        logger.exception("Detalle del error:")
        return 1
    except (GraphAuthError, SharePointResolutionError) as exc:
        logger.error("Error conectando con SharePoint (Microsoft Graph): %s", exc)
        return 1
    except TraficoError as exc:
        logger.error("Error: %s", exc)
        return 1
    except Exception:  # noqa: BLE001 - p.ej. pyodbc.Error al conectar a SQL Server
        logger.exception("Error inesperado:")
        return 1
    finally:
        db_trafico.cerrar()
        db_temporales.cerrar()


if __name__ == "__main__":
    sys.exit(main())

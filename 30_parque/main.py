"""Migracion a Python del paquete SSIS 'SSIS_Chile_parque.dtsx': carga de las
tablas de parque fijo y movil (vigente y historico) hacia CL_PLANTA, ahora
desde CSV publicados en SharePoint (Microsoft Graph) en vez de la tabla SQL
Server 'Externos_Frac' del paquete original.

Flujo (equivalente a las 2 ramas independientes 'PQ FIJO I+II'/'PQ MOVIL
I+II' del .dtsx original -- ver pipeline.py para el detalle completo):

    TRUNCATE -> Origen SharePoint/CSV -> filtro por periodo -> Destino _ACTUAL (CL_PLANTA)
      -> DELETE WHERE PERIODO=? -> INSERT ... SELECT _ACTUAL -> Destino _HISTORICO (CL_PLANTA)

Arquitectura ("src layout": codigo en src/parque/, modular, una carpeta
por capa):
    sharepoint/                    Adaptadores: auth.py (token Graph),
                                   client.py (resolver site/drive, descargar
                                   archivo), reader.py (CSV -> DataFrame).
    extraccion/extractor.py        Extraccion: descarga el CSV del flujo.
    validacion/validator.py        Validacion: columnas esperadas, filtro por
                                   periodo, largos maximos (FailComponent).
    transformacion/transformer.py  Transformacion: reordena columnas al
                                   orden del Destino OLE DB.
    carga/loader.py                Carga: TRUNCATE + insercion masiva.
    pipeline.py                    Orquestador: corre ambas ramas (FIJO,
                                   MOVIL) de forma independiente; dentro de
                                   cada rama, _HISTORICO depende de que
                                   _ACTUAL haya cargado sin error.
    models.py, exceptions.py       Value objects y excepciones.
    mappings.py, sql.py             Constantes de negocio (columnas/anchos/
                                   tablas) y SQL literal migrado.
    db.py                           Adaptador SQL Server (pyodbc).
    config.py, logging_setup.py    Configuracion via '.env' y logging.
    main.py (este archivo)          Composition root.

Configuracion:
    Los valores se leen del archivo '.env' (junto a este script; ver
    '.env.example' para la lista completa). Ninguna credencial esta
    embebida en el codigo: la password del Connection Manager 'CL_PLANTA'
    y el App Registration de Microsoft Graph (que reemplaza al Connection
    Manager 'srv_chile') se declaran en '.env' (no versionado).

Uso:
    python main.py --periodo 202607   # equivalente a editar a mano
                                       # User::Periodo en el .dtsx
    python main.py                    # usa VAR_PERIODO de .env
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "src" / "parque"))  # permite 'import mappings', 'import sql', etc. al correr como script suelto

import mappings
from config import cargar_configuracion
from db import DatabaseGateway, crear_conexion
from exceptions import ParqueError, PipelineError, ValidacionError
from logging_setup import NOMBRE_LOGGER, configurar_logging
from pipeline import ParquePipeline
from sharepoint.auth import get_graph_token
from sharepoint.client import SharePointClient
from sharepoint.reader import SharePointCsvReader

logger = logging.getLogger(NOMBRE_LOGGER)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--periodo",
        type=str,
        default=None,
        help="Periodo a cargar, tal como aparece en la columna 'periodo' del "
        "CSV (equivalente a User::Periodo). Por defecto: VAR_PERIODO de .env.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    settings = cargar_configuracion(BASE_DIR, periodo=args.periodo)
    configurar_logging(settings.log_file)

    if not settings.periodo:
        logger.error(
            "No hay periodo disponible: defina VAR_PERIODO en .env (equivalente "
            "a User::Periodo) o pase --periodo <valor>."
        )
        return 1

    logger.info("Iniciando carga de Parque para el periodo %s.", settings.periodo)

    conn = None
    try:
        token = get_graph_token(
            settings.sharepoint.tenant_id,
            settings.sharepoint.client_id,
            settings.sharepoint.client_secret,
            settings.sharepoint.timeout_ms,
        )
        client = SharePointClient(token, settings.sharepoint.timeout_ms)
        site_id = client.resolve_site(settings.sharepoint.hostname, settings.sharepoint.site_path)
        drive_id = client.resolve_drive(site_id, settings.sharepoint.drive_name)
        reader = SharePointCsvReader(
            client, drive_id, settings.sharepoint.folder_path, delimiter=mappings.CSV_DELIMITER
        )

        conn = crear_conexion(settings.db)

        pipeline = ParquePipeline(
            db=DatabaseGateway(conn, settings.batch_size),
            sharepoint_reader=reader,
            fijo_spec=mappings.FIJO_SPEC,
            movil_spec=mappings.MOVIL_SPEC,
        )
        resultado = pipeline.run(settings.periodo)

        logger.info(
            "Proceso finalizado correctamente: "
            "%s=%s filas, %s=%s filas, %s=%s filas, %s=%s filas.",
            mappings.FIJO_SPEC.tabla_destino,
            resultado.fijo.actual.filas_cargadas,
            mappings.FIJO_SPEC.tabla_historico,
            resultado.fijo.historico.filas_insertadas,
            mappings.MOVIL_SPEC.tabla_destino,
            resultado.movil.actual.filas_cargadas,
            mappings.MOVIL_SPEC.tabla_historico,
            resultado.movil.historico.filas_insertadas,
        )
        return 0

    except PipelineError as exc:
        if isinstance(exc.causa, ValidacionError):
            logger.error("Validacion de calidad de datos fallida: %s", exc.causa)
        else:
            logger.error("Error durante la carga de Parque: %s", exc)
        logger.exception("Detalle del error:")
        return 1

    except ParqueError as exc:
        logger.error("Error de configuracion: %s", exc)
        return 1

    finally:
        if conn is not None:
            conn.close()


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

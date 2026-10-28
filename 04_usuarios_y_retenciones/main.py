"""Migracion a Python de 5 paquetes SSIS 'USUARIOS_*.dtsx' (Chile): parque de
clientes, retenciones, intenciones de baja, items Amdocs y base SAIP.

Arquitectura ("src layout": codigo en src/usuarios/, modular, dividida en
las 4 capas del proceso original, una carpeta por capa):
    sharepoint/                   Adaptadores Microsoft Graph: auth.py
                                   (token), client.py (resolver site/drive,
                                   descargar archivo), reader.py (CSV ->
                                   DataFrame). Reemplaza, como ORIGEN, al
                                   Connection Manager OLE DB 'Externos_Frac'.
    extraccion/extractor.py       Extraccion: CSV SharePoint -> DataFrame,
                                   un extraer_xxx por Origen.
    validacion/validator.py       Validacion: controles de calidad de datos.
    transformacion/transformer.py Transformacion: 'Data Conversion' emulado
                                   + tareas SQL que corren en el mismo servidor.
    carga/loader.py               Carga: deletes/truncados y Destinos OLE DB
                                   (todos en CL_USUARIOS).
    pipeline.py                   Orquestador: llama a las 4 capas anteriores,
                                   una funcion 'ejecutar_xxx' por paquete .dtsx.
    models.py, exceptions.py      Value objects (Periodo, ResultadoPipeline) y
                                   excepciones. Sin dependencias externas.
    mappings.py, sql.py           Constantes de negocio: columnas/tablas/anchos
                                   de truncamiento, nombres de archivo CSV, y
                                   las sentencias T-SQL migradas literalmente
                                   de cada Execute SQL Task / Origen OLE DB
                                   (los SELECT que leian Externos_Frac quedan
                                   solo como referencia, ya no se ejecutan).
    db.py                         Adaptador concreto: pyodbc (SQL Server).
    config.py, logging_setup.py   Configuracion via '.env' y logging.
    main.py (este archivo)        Composition root: arma db.py + el cliente
                                   de SharePoint y los pasa a UsuariosPipeline.

Configuracion:
    Los valores se leen del archivo '.env' (junto a este script; ver
    '.env.example'). Ninguna credencial esta embebida en el codigo -- la
    conexion 'CL_USUARIOS' de los 5 .dtsx originales tenia password
    DPAPI-encriptado por usuario/maquina, imposible de reutilizar fuera de
    esa maquina; aqui se declara en '.env' (no versionado). La conexion
    'Externos_Frac' ya no se usa para nada: como ORIGEN fue reemplazada por
    un App Registration de Microsoft Graph (Sites.Selected sobre el sitio
    ReportingFractalia) que lee los CSV publicados en SharePoint, y su unico
    destino (TBL_FRACTALIA_USER_RETENCIONES) se dio de baja por obsoleto.

Uso:
    python main.py --periodo 202608                 # equivalente a editar a
                                                      # mano User::Periodo en
                                                      # el .dtsx; corre los 5
                                                      # paquetes en orden
    python main.py --periodo 202608 --paquete parque # corre solo un paquete
    python main.py --paquete saip                    # SAIP no usa periodo
    python main.py                                   # usa PERIODO de .env
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "src" / "usuarios"))  # permite 'import mappings', 'import sql', etc. al correr como script suelto

import mappings
from config import cargar_configuracion
from db import DatabaseGateway, crear_conexion
from exceptions import PipelineError, UsuariosError
from logging_setup import NOMBRE_LOGGER, configurar_logging
from pipeline import UsuariosPipeline
from sharepoint.auth import get_graph_token
from sharepoint.client import SharePointClient
from sharepoint.reader import SharePointCsvReader

logger = logging.getLogger(NOMBRE_LOGGER)

PAQUETES_DISPONIBLES = ("parque", "retenciones", "intenciones", "item_amdocs", "saip", "todos")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--periodo",
        type=str,
        default=None,
        help="Periodo a procesar, formato YYYYMM (equivalente a User::Periodo / "
        "User::Periodo01). Por defecto: PERIODO de .env.",
    )
    parser.add_argument(
        "--paquete",
        choices=PAQUETES_DISPONIBLES,
        default="todos",
        help="Que paquete .dtsx migrado correr. Por defecto: todos, en el orden original.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    settings = cargar_configuracion(BASE_DIR, periodo=args.periodo)
    configurar_logging(settings.log_file)

    if settings.periodo is None and args.paquete != "saip":
        logger.error(
            "No hay periodo disponible: defina PERIODO en .env (equivalente a "
            "User::Periodo / User::Periodo01) o pase --periodo YYYYMM."
        )
        return 1

    logger.info("Iniciando USUARIOS (paquete=%s) para el periodo %s.", args.paquete, settings.periodo)

    conn_cl_usuarios = None
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
        sharepoint_reader = SharePointCsvReader(
            client, drive_id, settings.sharepoint.folder_path, delimiter=mappings.CSV_DELIMITER
        )

        conn_cl_usuarios = crear_conexion(settings.db_cl_usuarios)

        pipeline = UsuariosPipeline(
            db_cl_usuarios=DatabaseGateway(conn_cl_usuarios, settings.batch_size),
            sharepoint_reader=sharepoint_reader,
        )

        if args.paquete == "parque":
            resultado = pipeline.ejecutar_parque(settings.periodo)
            logger.info("Proceso finalizado correctamente: %s", resultado)
        elif args.paquete == "retenciones":
            resultado = pipeline.ejecutar_retenciones(settings.periodo)
            logger.info("Proceso finalizado correctamente: %s", resultado)
        elif args.paquete == "intenciones":
            resultado = pipeline.ejecutar_intenciones(settings.periodo)
            logger.info("Proceso finalizado correctamente: %s", resultado)
        elif args.paquete == "item_amdocs":
            resultado = pipeline.ejecutar_item_amdocs(settings.periodo)
            logger.info("Proceso finalizado correctamente: %s", resultado)
        elif args.paquete == "saip":
            resultado = pipeline.ejecutar_saip()
            logger.info("Proceso finalizado correctamente: %s", resultado)
        else:
            resultado = pipeline.ejecutar_todo(settings.periodo)
            logger.info("Proceso finalizado correctamente: %s sub-pipelines completados.", len(resultado.resultados))
        return 0

    except PipelineError as exc:
        logger.error("Error durante la carga de USUARIOS: %s", exc)
        logger.exception("Detalle del error:")
        return 1

    except UsuariosError as exc:
        logger.error("Error de configuracion: %s", exc)
        return 1

    finally:
        if conn_cl_usuarios is not None:
            conn_cl_usuarios.close()


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

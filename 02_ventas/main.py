"""Migracion a Python de 2 paquetes SSIS 'CROSS 01*.dtsx' (Chile): funnel de
señalizaciones y funnel de ventas cross-selling.

Arquitectura ("src layout": en la raiz solo quedan README/config/puntos de
entrada; el codigo vive en src/ventas/, modular y plano -- dividido en las
4 capas del proceso original, una carpeta por capa):
    sharepoint/                   Adaptadores Microsoft Graph: auth.py
                                   (token), client.py (resolver site/drive,
                                   descargar/copiar archivo), reader.py (CSV/
                                   Excel -> DataFrame). Reemplaza, como
                                   ORIGEN, a los archivos de red local y a la
                                   descarga de Google Drive de los .dtsx
                                   originales -- ver README, "Alcance de origenes".
    extraccion/extractor.py       Extraccion: SharePoint -> DataFrame, un
                                   extraer_xxx por Origen.
    validacion/validator.py       Validacion: columnas esperadas, anchos
                                   (FailComponent/IgnoreFailure).
    transformacion/transformer.py Transformacion: 'Conversión de datos'
                                   emulada + tareas SQL que corren en el
                                   mismo servidor.
    carga/loader.py               Carga: truncados/deletes y Destinos OLE DB
                                   (todos en CL_USUARIOS).
    pipeline.py                   Orquestador: llama a las 4 capas anteriores,
                                   una funcion 'ejecutar_xxx' por paquete .dtsx.
    models.py, exceptions.py      Value objects (ColumnaSpec, ResultadoPipeline)
                                   y excepciones. Sin dependencias externas.
    mappings.py, sql.py           Constantes de negocio: columnas/tablas/anchos,
                                   nombres de archivo/hoja SharePoint, y las
                                   sentencias T-SQL migradas literalmente de
                                   cada Execute SQL Task.
    db.py                         Adaptador concreto: pyodbc (SQL Server).
    config.py, logging_setup.py   Configuracion via '.env' y logging.
    copiar_funnel_ventas.py       Paso 0a: copia 'FUNNEL VENTAS V2.xlsx' del
                                   sitio BPO a '07 CROSS' via Microsoft Graph.
                                   main.py llama a copiar_funnel_ventas() antes
                                   de correr el paquete 'ventas'/'todos' -- ver
                                   ese archivo para correrlo suelto.
    exportar_senhalizaciones_csv.py Paso 0b: sube 'Señalizaciones.csv' (Google
                                   Sheets) a '07 CROSS'. main.py llama a
                                   subir_senhalizaciones_csv() antes de correr
                                   el paquete 'senalizaciones'/'todos'.
    main.py (este archivo)        Composition root: arma db.py + el cliente
                                   de SharePoint, corre el Paso 0 que
                                   corresponda segun --paquete, y pasa el
                                   cliente a VentasPipeline.

Configuracion:
    Los valores se leen del archivo '.env' (junto a este script; ver
    '.env.example'). Ninguna credencial esta embebida en el codigo.

Uso:
    python main.py --fecha 2026-08-01                 # corre los 2 paquetes en orden
    python main.py --fecha 2026-08-01 --paquete ventas # corre solo un paquete
    python main.py --paquete senalizaciones            # no usa fecha
    python main.py                                     # usa VAR_FECHA de .env
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "src" / "ventas"))  # permite 'import mappings', 'import sql', etc. al correr como script suelto

from config import cargar_configuracion, cargar_configuracion_origen
from copiar_funnel_ventas import copiar_funnel_ventas
from db import DatabaseGateway, crear_conexion
from exceptions import PipelineError, VentasError
from exportar_senhalizaciones_csv import subir_senhalizaciones_csv
from logging_setup import CONSOLA, NOMBRE_LOGGER, configurar_logging, resumen_avisos
from mappings import ARCHIVO_FUNNEL_VENTAS_XLSX, ARCHIVO_SENHALIZACIONES_CSV, CSV_DELIMITER
from pipeline import VentasPipeline
from sharepoint.auth import get_graph_token
from sharepoint.client import SharePointClient
from sharepoint.reader import SharePointCsvReader, SharePointExcelReader

logger = logging.getLogger(NOMBRE_LOGGER)

PAQUETES_DISPONIBLES = ("senalizaciones", "ventas", "todos")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--fecha",
        type=str,
        default=None,
        help="Fecha watermark (User::Fecha, YYYY-MM-DD) para el ciclo LOCAL de Ventas. "
        "Por defecto: VAR_FECHA de .env. No se usa para --paquete senalizaciones.",
    )
    parser.add_argument(
        "--paquete",
        choices=PAQUETES_DISPONIBLES,
        default="todos",
        help="Que paquete .dtsx migrado correr. Por defecto: todos, en el orden original (0101 -> 0102).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    settings = cargar_configuracion(BASE_DIR, fecha=args.fecha)
    configurar_logging(settings.log_file)

    if settings.fecha is None and args.paquete != "senalizaciones":
        logger.error(
            "No hay fecha disponible: defina VAR_FECHA en .env (equivalente a "
            "User::Fecha, formato YYYY-MM-DD) o pase --fecha YYYY-MM-DD."
        )
        return 1

    logger.info("Iniciando VENTAS (paquete=%s) con fecha=%s.", args.paquete, settings.fecha, extra=CONSOLA)

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
        csv_reader = SharePointCsvReader(client, drive_id, settings.sharepoint.folder_path, delimiter=CSV_DELIMITER)
        excel_reader = SharePointExcelReader(client, drive_id, settings.sharepoint.folder_path)

        # Paso 0: refresca en '07 CROSS' los origenes que antes solo se
        # actualizaban a mano (ver copiar_funnel_ventas.py/
        # exportar_senhalizaciones_csv.py) -- el .dtsx original si bajaba el
        # formulario de señalizaciones como parte del propio Control Flow
        # (Execute Process Task), asi que esto replica ese comportamiento en
        # vez de depender de que alguien corra los scripts sueltos antes.
        if args.paquete in ("senalizaciones", "todos"):
            logger.info("Paso 0b: actualizando '%s' desde Google Sheets...", ARCHIVO_SENHALIZACIONES_CSV, extra=CONSOLA)
            subir_senhalizaciones_csv(client, drive_id, settings.sharepoint.folder_path)
        if args.paquete in ("ventas", "todos"):
            origen = cargar_configuracion_origen(BASE_DIR)
            logger.info("Paso 0a: actualizando '%s' desde el sitio BPO...", ARCHIVO_FUNNEL_VENTAS_XLSX, extra=CONSOLA)
            copiar_funnel_ventas(origen, client, drive_id, settings.sharepoint.folder_path)

        conn = crear_conexion(settings.db)

        pipeline = VentasPipeline(
            db=DatabaseGateway(conn, settings.batch_size),
            csv_reader=csv_reader,
            excel_reader=excel_reader,
        )

        if args.paquete == "senalizaciones":
            pipeline.ejecutar_senalizaciones()
        elif args.paquete == "ventas":
            pipeline.ejecutar_ventas(settings.fecha)
        else:
            pipeline.ejecutar_todo(settings.fecha)
        avisos = resumen_avisos()
        if avisos:
            logger.info(avisos, extra=CONSOLA)
        logger.info("Proceso finalizado correctamente.", extra=CONSOLA)
        return 0

    except PipelineError as exc:
        logger.error("Error durante la carga de VENTAS: %s", exc)
        logger.exception("Detalle del error:")
        return 1

    except VentasError as exc:
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

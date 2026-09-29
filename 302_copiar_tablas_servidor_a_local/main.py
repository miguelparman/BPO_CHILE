"""Copia el esquema y los datos de tablas del servidor SQL Server origen
(172.17.0.162) hacia el servidor SQL Server local, tabla por tabla.

Por defecto copia las tablas listadas en mappings.py, pero se puede indicar
otra lista en el momento con una o mas opciones '--tabla', p.ej.:

    python main.py --tabla "[CL_CARTERA].[dbo].[TBL_CARTERA_ACTUAL]" \\
                    --tabla "[CL_USUARIOS].[dbo].[TBL_USUARIOS]"

Cada tabla puede pertenecer a una base de datos distinta del mismo servidor
origen. Si una tabla ya existe en el destino, se pide confirmacion por
consola antes de eliminarla y volver a crearla con el esquema (columnas,
tipos, longitudes, identity) leido directamente del origen via sys.columns.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from config import cargar_configuracion
from db import DatabaseGateway, crear_conexion, parsear_ruta_tabla
from exceptions import CopiaTablaError
from mappings import TABLAS_A_COPIAR

BASE_DIR = Path(__file__).resolve().parent

logger = logging.getLogger("copiar_tablas")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Copia tablas del servidor origen al servidor local.")
    parser.add_argument(
        "--tabla",
        action="append",
        dest="tablas",
        metavar="[BASE].[schema].[tabla]",
        help="Ruta completa de una tabla a copiar. Puede repetirse. "
        "Si no se indica ninguna, se usa la lista de mappings.py.",
    )
    return parser.parse_args(argv)


def configurar_logging(log_file: Path) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )


def confirmar_eliminacion(base: str, schema: str, tabla: str) -> bool:
    respuesta = input(
        f"La tabla [{base}].[{schema}].[{tabla}] ya existe en el servidor destino. "
        f"¿Eliminarla y reemplazarla por la copia del origen? [s/N]: "
    ).strip().lower()
    return respuesta in ("s", "si", "sí", "y", "yes")


def copiar_tabla(origen: DatabaseGateway, destino: DatabaseGateway, ruta: str) -> None:
    base, schema, tabla = parsear_ruta_tabla(ruta)
    logger.info("Copiando [%s].[%s].[%s]...", base, schema, tabla)

    if not destino.base_existe(base):
        raise CopiaTablaError(
            f"La base de datos '{base}' no existe en el servidor destino. "
            "Creala manualmente antes de copiar esta tabla."
        )

    columnas = origen.obtener_definicion_columnas(base, schema, tabla)

    if destino.tabla_existe(base, schema, tabla):
        if not confirmar_eliminacion(base, schema, tabla):
            logger.info("Se omite [%s].[%s].[%s]: el usuario no confirmo el reemplazo.", base, schema, tabla)
            return
        destino.eliminar_tabla(base, schema, tabla)
        logger.info("Tabla [%s].[%s].[%s] eliminada en el destino.", base, schema, tabla)

    destino.crear_tabla(base, schema, tabla, columnas)
    logger.info("Tabla [%s].[%s].[%s] creada en el destino.", base, schema, tabla)

    df = origen.leer_tabla(base, schema, tabla)
    filas_insertadas = destino.insertar_datos(base, schema, tabla, df, columnas)
    logger.info("%s filas copiadas en [%s].[%s].[%s].", filas_insertadas, base, schema, tabla)


def main() -> None:
    args = parse_args()
    settings = cargar_configuracion(BASE_DIR)
    configurar_logging(settings.log_file)

    tablas = args.tablas if args.tablas else TABLAS_A_COPIAR

    conn_origen = crear_conexion(settings.db_origen)
    conn_destino = crear_conexion(settings.db_destino)
    try:
        origen = DatabaseGateway(conn_origen, batch_size=settings.batch_size)
        destino = DatabaseGateway(conn_destino, batch_size=settings.batch_size)

        for ruta in tablas:
            try:
                copiar_tabla(origen, destino, ruta)
            except Exception as exc:
                logger.error("Fallo al copiar %s: %s", ruta, exc)
    finally:
        # pyodbc.Connection usado como context manager haria commit/rollback
        # al salir, no close(): se cierra aqui de forma explicita, e ignorando
        # errores porque la conexion ya pudo haberse caido (p.ej. corte de red).
        for conn in (conn_origen, conn_destino):
            try:
                conn.close()
            except Exception:
                pass

    logger.info("Proceso finalizado.")


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
    main()

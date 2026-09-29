"""
Carga masiva de Notas de Crédito: trunca [CL_FACTURACION].[dbo].[TBL_NC_DB] y
la recarga por completo con el contenido de NC_.xlsx.

A diferencia de 'etl_carga' (que recarga solo el período en curso, vía tabla
de staging + limpieza de filas fuera de período/inválidas), esta herramienta
reemplaza TODO el contenido de la tabla de una sola vez -- pensada para un
reinicio completo desde cero, no para la recarga mensual incremental.

Pasos:
    1. TRUNCATE de la tabla destino.
    2. Carga masiva del Excel completo (ya depurado del pie de página que
       agrega Power BI) hacia esa misma tabla.

Configuración: variables de entorno en '.env' (ver '.env.example'), junto a
este script.

Uso:
    python main.py            # pide confirmación antes de truncar
    python main.py --si       # no pide confirmación (uso no interactivo)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from carga import cargar_tabla
from config import cargar_configuracion
from db import crear_conexion, truncar_tabla
from excel_reader import leer_excel

logger = logging.getLogger("carga_masiva")


def _configurar_logging(log_file: Path) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler()],
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--si", action="store_true", help="No pedir confirmación antes de truncar la tabla.")
    return parser.parse_args()


def _confirmar(tabla: str, excel_path: Path) -> bool:
    respuesta = input(
        f"Esto BORRA todo el contenido de {tabla} y lo reemplaza por el "
        f"contenido de '{excel_path}'. ¿Continuar? (si/no): "
    )
    return respuesta.strip().lower() in ("si", "sí", "s", "yes", "y")


def main() -> int:
    args = _parse_args()
    settings = cargar_configuracion(BASE_DIR)
    _configurar_logging(settings.log_file)

    logger.info("Carga masiva: '%s' -> %s", settings.excel_path, settings.tabla_destino)

    if not args.si and not _confirmar(settings.tabla_destino, settings.excel_path):
        logger.info("Operación cancelada por el usuario.")
        print("Operación cancelada.")
        return 1

    conn = None
    try:
        df = leer_excel(settings.excel_path)
        logger.info("Archivo leído y depurado: %s filas.", len(df))

        conn = crear_conexion(settings)
        truncar_tabla(conn, settings.tabla_destino)

        filas_cargadas = cargar_tabla(conn, df, settings.tabla_destino, settings.batch_size)
        logger.info("Carga masiva finalizada: %s filas cargadas en %s.", filas_cargadas, settings.tabla_destino)
        print(f"\nCarga masiva completada: {filas_cargadas} filas cargadas en {settings.tabla_destino}.\n")
        return 0

    except Exception as exc:
        logger.error("Error durante la carga masiva: %s", exc)
        logger.exception("Detalle del error:")
        print(f"\nOcurrió un error: {exc}\nRevisa '{settings.log_file.name}'.\n")
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
    nombre = f"{carpeta.parent.name} / {carpeta.name}"
    print("=" * 60, f" PROYECTO: {nombre}", "=" * 60, sep="\n", flush=True)
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetConsoleTitleW(nombre)


if __name__ == "__main__":
    _mostrar_proyecto()
    sys.exit(main())

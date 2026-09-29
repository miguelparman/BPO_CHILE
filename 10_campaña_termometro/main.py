"""
Punto de entrada. Reemplaza la ejecución manual/por SQL Server Agent del .dtsx.

Uso:
    python main.py --periodo 202607 --fecha-inicio 2026-07-01 --fecha-fin 2026-07-31
"""
import argparse
import logging
import sys
from datetime import datetime

from config import settings
import pipeline


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(f"logs/termometro_{datetime.now():%Y%m%d_%H%M%S}.log", encoding="utf-8"),
        ],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ETL Campaña Termómetro (migrado desde SSIS)")
    parser.add_argument("--periodo", type=int, default=settings.periodo, help="Periodo AAAAMM, ej. 202607")
    parser.add_argument("--fecha-inicio", type=str, default=settings.fecha_inicio, help="YYYY-MM-DD")
    parser.add_argument("--fecha-fin", type=str, default=settings.fecha_fin, help="YYYY-MM-DD")
    return parser.parse_args()


def main() -> int:
    import os
    os.makedirs("logs", exist_ok=True)
    setup_logging()
    logger = logging.getLogger("main")

    args = parse_args()
    logger.info("Iniciando ETL Termómetro | periodo=%s rango=%s..%s", args.periodo, args.fecha_inicio, args.fecha_fin)

    try:
        pipeline.run(args.periodo, args.fecha_inicio, args.fecha_fin)
    except Exception:
        logger.exception("El pipeline terminó con errores")
        return 1

    logger.info("ETL Termómetro finalizado correctamente")
    return 0


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

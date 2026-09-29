"""
Punto de entrada. Reemplaza la ejecución manual/por SQL Server Agent de
SSIS_CL_ISN_Contactos.dtsx + SSIS_CL_ISN.dtsx (en ese orden).

Uso:
    python main.py
    python main.py --fecha-inicio 2026-09-06 --fecha-fin 2026-09-06
    python main.py --saltar contactos      # solo corre ISN
    python main.py --saltar isn            # solo corre Contactos
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime

from config import settings
import pipeline


def setup_logging() -> None:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(settings.log_dir / f"isn_{datetime.now():%Y%m%d_%H%M%S}.log", encoding="utf-8"),
        ],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ETL Contactos + ISN (migrado desde SSIS)")
    parser.add_argument("--fecha-inicio", type=str, default=None, help="YYYY-MM-DD (rango evaluado en TBL_ISN_SF)")
    parser.add_argument("--fecha-fin", type=str, default=None, help="YYYY-MM-DD (rango evaluado en TBL_ISN_SF)")
    parser.add_argument(
        "--saltar",
        action="append",
        choices=["contactos", "isn"],
        default=[],
        help="Omite una etapa (se puede repetir). Ej: --saltar contactos",
    )
    return parser.parse_args()


def main() -> int:
    setup_logging()
    logger = logging.getLogger("main")

    args = parse_args()
    logger.info("Iniciando pipeline Contactos + ISN | saltar=%s", args.saltar)

    try:
        pipeline.run(fecha_inicio=args.fecha_inicio, fecha_fin=args.fecha_fin, saltar=set(args.saltar))
    except Exception:
        logger.exception("El pipeline terminó con errores")
        return 1

    logger.info("Pipeline finalizado correctamente")
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

"""Configuracion de logging (archivo + consola)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

NOMBRE_LOGGER = "usuarios"


def configurar_logging(log_file: Path) -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger(NOMBRE_LOGGER)

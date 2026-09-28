"""Configuracion de logging (un archivo por corrida en logs/ + consola)."""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

NOMBRE_LOGGER = "trafico"


def configurar_logging(log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    # La consola de Windows (cp1252) no puede mostrar los emojis del mensaje de
    # la alerta (✅ ⚠️ ❌): se reemplazan en pantalla; el archivo .log es UTF-8.
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    log_file = log_dir / f"trafico_{datetime.now():%Y%m%d_%H%M%S}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return log_file

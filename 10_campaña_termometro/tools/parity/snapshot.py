"""
Saca una "foto" del resultado actual de TBL_CAMPAÑA_TERMOMETRO para un periodo
dado, y la guarda en disco. Se usa dos veces:

  1) Después de correr el paquete SSIS original       -> --etiqueta ssis
  2) Después de correr el pipeline Python (este repo)  -> --etiqueta python

Cada corrida sobrescribe la tabla, por eso hay que capturar el resultado en un
archivo antes de correr la otra versión.

Uso:
    python -m tools.parity.snapshot --periodo 202607 --etiqueta ssis
    python -m tools.parity.snapshot --periodo 202607 --etiqueta python
"""
import argparse
import logging
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "src", "termometro"))

import pandas as pd
from sqlalchemy import text

import sql
from db import get_engine

logger = logging.getLogger(__name__)

SNAPSHOT_DIR = os.path.join(_ROOT, "tools", "parity", "snapshots")


def snapshot(periodo: int, etiqueta: str) -> str:
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    with open(sql.SELECT_PERIODO_FINAL, "r", encoding="utf-8") as f:
        query = f.read()

    engine = get_engine()
    df = pd.read_sql(text(query), engine, params={"periodo": periodo})

    out_path = os.path.join(SNAPSHOT_DIR, f"{periodo}_{etiqueta}.parquet")
    df.to_parquet(out_path, index=False)
    logger.info("Snapshot guardado: %s (%d filas, %d columnas)", out_path, len(df), len(df.columns))
    print(f"OK: {len(df)} filas guardadas en {out_path}")
    return out_path


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
    parser = argparse.ArgumentParser(description="Guarda una foto de TBL_CAMPAÑA_TERMOMETRO para un periodo")
    parser.add_argument("--periodo", type=int, required=True, help="Periodo AAAAMM, ej. 202607")
    parser.add_argument("--etiqueta", type=str, required=True, help="Nombre para identificar la corrida, ej. 'ssis' o 'python'")
    args = parser.parse_args()

    snapshot(args.periodo, args.etiqueta)
    return 0


if __name__ == "__main__":
    sys.exit(main())

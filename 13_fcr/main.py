"""Migracion a Python del paquete SSIS 'CL_Proc_Trafico_FCR_02.dtsx': calculo
del FCR (First Contact Resolution) de Chile. Para cada atencion de llamadas
(TRIADAS, CARTERIZADOS, USUARIOS) y WhatsApp (TRIADAS, CARTERIZADOS) busca la
siguiente atencion del mismo ANI y marca si hubo re-contacto dentro de 30 min,
1 h, ... 15 dias; el resultado va a CL_TRAFICO.dbo.TBL_FCR.

Flujo (ver src/fcr/pipeline.py):

    Log Inicio -> Proceso Carga Tabla (Limpia Tabla -> Alimenta Tabla) -> Log Fin

Arquitectura (src layout, modular por componentes, una carpeta por capa):
    extraccion/extractor.py        SELECT de las 5 bases desde el periodo.
    validacion/validator.py        Esquema real vs mappings.py; datos y anchos.
    transformacion/transformer.py  LEAD por ANI+SERVICIO, 14 FCR, TRAMO_QUIEBRE.
    carga/loader.py                LOGS_PROCESOS + DELETE periodo + INSERT (transaccional).
    pipeline.py                    Orquestador: llama a las capas en el orden del Control Flow.
    mappings.py, sql.py            Constantes de negocio y T-SQL literal del .dtsx (scripts_sql/).
    db.py                          Adaptador pyodbc (reutilizado de 12_trafico).
    config.py, logging_setup.py    Configuracion via '.env' y logging.
    main.py (este archivo)         Composition root: arma el adaptador y corre el pipeline.

Orden de ejecucion: DESPUES de 12_trafico (CL_Proc_Trafico_01), que carga
TBL_LLAMADAS_ATENDIDAS_INBOUND y TBL_CHAT.

Configuracion: archivo '.env' junto a este script (ver '.env.example').
Ninguna credencial esta embebida en el codigo.

Uso:
    python main.py                    # periodo: PERIODO de .env, o automatico (mes anterior si hoy es dia <= DIA_CIERRE_MES)
    python main.py --periodo 202608   # fuerza el periodo (YYYYMM); tiene prioridad sobre .env
    python main.py --solo-validar     # extrae, transforma y valida, sin escribir nada
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "src" / "fcr"))  # permite 'import mappings', 'import sql', etc.

from config import cargar_configuracion  # noqa: E402
from db import DatabaseGateway, crear_conexion  # noqa: E402
from exceptions import FcrError, PipelineError  # noqa: E402
from logging_setup import NOMBRE_LOGGER, configurar_logging  # noqa: E402
from models import resolver_periodo  # noqa: E402
from pipeline import FcrPipeline  # noqa: E402

logger = logging.getLogger(NOMBRE_LOGGER)


def _periodo(texto: str) -> int:
    if len(texto) != 6 or not texto.isdigit() or not 1 <= int(texto[4:]) <= 12:
        raise argparse.ArgumentTypeError("formato esperado YYYYMM, p.ej. 202609")
    return int(texto)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--periodo", type=_periodo, default=None, help="Periodo YYYYMM; prioridad sobre PERIODO de .env.")
    parser.add_argument(
        "--solo-validar", action="store_true", help="Solo extrae, transforma y valida; no escribe en la base."
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        settings = cargar_configuracion(BASE_DIR)
    except FcrError as exc:
        print(f"Error de configuracion: {exc}", file=sys.stderr)
        return 1
    log_file = configurar_logging(settings.log_dir)
    logger.info("Log de esta corrida: %s", log_file)
    try:
        periodo, fuente = resolver_periodo(date.today(), args.periodo, settings.periodo, settings.dia_cierre_mes)
    except ValueError as exc:
        logger.error("PERIODO invalido: %s", exc)
        return 1
    logger.info("Periodo a procesar: %s (origen: %s)", periodo, fuente)

    db = DatabaseGateway(lambda: crear_conexion(settings.db_trafico), settings.batch_size, "CL_TRAFICO")
    try:
        FcrPipeline(db=db).run(periodo, solo_validar=args.solo_validar)
        return 0
    except PipelineError as exc:
        logger.error("Error durante el proceso FCR: %s", exc)
        logger.exception("Detalle del error:")
        return 1
    except FcrError as exc:
        logger.error("Error: %s", exc)
        return 1
    except Exception:  # noqa: BLE001 - p.ej. pyodbc.Error al conectar a SQL Server
        logger.exception("Error inesperado:")
        return 1
    finally:
        db.cerrar()


def _mostrar_proyecto():
    """Muestra el nombre del proyecto en la consola y en el titulo de la ventana."""
    import ctypes

    nombre = BASE_DIR.name
    print("=" * 60, f" PROYECTO: {nombre}", "=" * 60, sep="\n", flush=True)
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetConsoleTitleW(nombre)


if __name__ == "__main__":
    _mostrar_proyecto()
    sys.exit(main())

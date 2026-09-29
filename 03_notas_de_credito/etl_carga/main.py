"""
Migración a Python del paquete SSIS 'SSIS_CL_NC.dtsx' (Contenedor de
secuencias): recarga mensual de Notas de Crédito desde el Excel exportado de
Power BI hacia SQL Server.

Flujo (equivalente a las PrecedenceConstraints del .dtsx):
    Extract+Load a staging (antes: 'Tarea Ejecutar proceso' -> ETL_NC_polars.py)
        -> DELETE (fuera de período) -> DELETE 2 (filas inválidas)
        -> DELETE NC (limpia destino) -> CARGA NC (staging -> destino)
        -> UPDATE (homologación de EJECUTIVO)

Arquitectura (Clean/Layered):
    app/domain/          Entidades (PeriodoCarga, ETLSettings, ResultadoETL) y
                          excepciones. Sin dependencias externas.
    app/application/     Puertos (interfaces) y el caso de uso que orquesta
                          el pipeline. Solo conoce domain/ y los puertos.
    app/infrastructure/  Implementaciones concretas: Excel (polars), SQL
                          Server (pyodbc), .env, logging.
    main.py (este archivo) Composition root: arma las piezas concretas de
                          infrastructure/ y las inyecta en el caso de uso.
                          Es el único punto que conoce ambas capas a la vez.

Configuración:
    Los valores se leen del archivo '.env' (junto a este script; ver
    '.env.example' para la lista completa). Si una variable no está
    definida en '.env', se usa el valor por defecto indicado en
    app/infrastructure/config.py.

Uso:
    python main.py                  # usa ANIO/MES de .env, o el mes actual
    python main.py --anio 2026 --mes 9
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))  # permite 'import app.xxx' al correr como script suelto

from app.application.use_cases import CargarNotasDeCreditoUseCase
from app.infrastructure.config import cargar_configuracion
from app.infrastructure.db import crear_conexion
from app.infrastructure.excel_extractor import ExcelNotasCreditoExtractor
from app.infrastructure.logging_setup import NOMBRE_LOGGER, configurar_logging
from app.infrastructure.sqlserver_destino_repository import SqlServerDestinoRepository
from app.infrastructure.sqlserver_staging_repository import SqlServerStagingRepository

logger = logging.getLogger(NOMBRE_LOGGER)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--anio", type=int, default=None, help="Año a recargar (por defecto: .env o el actual).")
    parser.add_argument("--mes", type=int, default=None, help="Mes a recargar, 1-12 (por defecto: .env o el actual).")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    settings = cargar_configuracion(BASE_DIR, anio=args.anio, mes=args.mes)
    configurar_logging(settings.log_file)

    logger.info("Iniciando recarga de Notas de Crédito para %04d-%02d.", settings.periodo.anio, settings.periodo.mes)

    conn = None
    try:
        conn = crear_conexion(settings)

        extractor = ExcelNotasCreditoExtractor(settings.excel_path, settings.columnas)
        staging = SqlServerStagingRepository(conn, settings.tabla_staging, settings.columnas, settings.batch_size)
        destino = SqlServerDestinoRepository(conn, settings.tabla_destino, settings.columnas, settings.batch_size)

        caso_de_uso = CargarNotasDeCreditoUseCase(
            extractor=extractor,
            staging=staging,
            destino=destino,
            periodo=settings.periodo,
        )
        resultado = caso_de_uso.ejecutar()

        logger.info(
            "Proceso finalizado correctamente: %s filas extraídas, %s en staging tras limpieza, "
            "%s eliminadas en destino, %s cargadas en destino, %s con EJECUTIVO homologado.",
            resultado.filas_extraidas,
            resultado.filas_staging_tras_limpieza,
            resultado.filas_eliminadas_destino,
            resultado.filas_cargadas_destino,
            resultado.filas_ejecutivo_normalizadas,
        )
        return 0

    except Exception as exc:
        logger.error("Error durante la recarga de Notas de Crédito: %s", exc)
        logger.exception("Detalle del error:")
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

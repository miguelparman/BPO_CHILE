"""401_BI_Service: historial de actualizaciones (refresh) de los datasets de
Power BI Service, via la API REST con el App Registration de
Repositorio.bi@fractaliasystems.es (client credentials).

Flujo (ver src/bi_service/pipeline.py):

    validar conexiones -> workspaces (PBI_WORKSPACES) -> datasets / informes
    -> historial y programacion de cada dataset -> CSV historico
    -> analisis de cruces de horarios -> Excel

Arquitectura (src layout, modular por componentes):
    conexiones.py        Validacion previa con reintento automatico (5 min x 3).
    powerbi/auth.py      Token OAuth2 client credentials (scope Power BI).
    powerbi/client.py    API REST de Power BI (reintentos 429/5xx, paginado).
    extractor.py         Recorre workspaces -> datasets / informes -> refreshes.
    transformer.py       Tablas: Datasets, Actualizaciones, Programacion, Informes, Workspaces, Errores.
    zonas.py             Zonas de Windows de las programaciones -> ZONA_HORARIA.
    analisis.py          Duracion por horario, mapa de cruces, concurrencia real, fallos.
    salida.py            CSV historico acumulado + Excel de la corrida.
    pipeline.py          Orquestador.
    config.py, logging_setup.py, exceptions.py
    main.py (este archivo)  Composition root.

Configuracion: archivo '.env' junto a este script (ver '.env.example').

Uso:
    python main.py                            # corrida normal (todos los workspaces visibles)
    python main.py --workspace "Chile"        # solo ese workspace, por nombre o id (repetible)
    python main.py --solo-leer                # consulta la API y muestra el resumen; no escribe archivos
    python main.py --sin-validar-conexiones   # emergencia: omite la validacion previa
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "src" / "bi_service"))  # permite 'import config', 'import extractor', etc.

from config import cargar_configuracion  # noqa: E402
from conexiones import validar_conexiones, verificaciones_para  # noqa: E402
from exceptions import BIServiceError, ConexionError  # noqa: E402
from extractor import Extractor  # noqa: E402
from logging_setup import NOMBRE_LOGGER, configurar_logging  # noqa: E402
from pipeline import BIServicePipeline, ResultadoPipeline  # noqa: E402
from powerbi.client import PowerBIClient  # noqa: E402

logger = logging.getLogger(NOMBRE_LOGGER)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workspace", action="append", help="Solo ese workspace, por nombre o id (repetible).")
    parser.add_argument("--solo-leer", action="store_true", help="No escribe el Excel ni el CSV historico.")
    parser.add_argument("--sin-validar-conexiones", action="store_true", help="Omite la validacion previa (emergencias).")
    return parser.parse_args(argv)


def _resumen(resultado: ResultadoPipeline) -> None:
    logger.info(
        "Workspaces=%s datasets=%s informes=%s horarios_programados=%s actualizaciones_leidas=%s errores=%s",
        resultado.workspaces, resultado.datasets, resultado.informes, resultado.horarios, resultado.actualizaciones,
        len(resultado.errores),
    )
    cruces = resultado.hojas.get("Cruces")
    if cruces is not None and len(cruces):
        logger.info("Bloques de 15 min con 2+ datasets actualizandose a la vez: %s (hoja 'Cruces')", len(cruces))
    if resultado.excel:
        logger.info("Historico: %s filas (%s nuevas) -> %s", resultado.total_historico, resultado.nuevas_historico,
                    resultado.csv)
        logger.info("Excel: %s", resultado.excel)
    for e in resultado.errores:
        logger.warning("Sin acceso: [%s] %s / %s (HTTP %s)", e["NIVEL"], e["WORKSPACE"], e["OBJETO"], e["HTTP"])


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        settings = cargar_configuracion(BASE_DIR)
    except BIServiceError as exc:
        print(f"Error de configuracion: {exc}", file=sys.stderr)
        return 1
    log_file = configurar_logging(settings.log_dir)
    logger.info("Log de esta corrida: %s", log_file)

    salida_dir = None if args.solo_leer else settings.salida_dir
    try:
        validar = None
        if not args.sin_validar_conexiones:
            verificaciones = verificaciones_para(settings.powerbi, salida_dir)
            validar = lambda: validar_conexiones(  # noqa: E731
                verificaciones, settings.reintentos_conexion, settings.espera_reintento_s
            )
        else:
            logger.warning("--sin-validar-conexiones: se omite la validacion previa.")

        extractor = Extractor(PowerBIClient(settings.powerbi), settings.top_actualizaciones)
        pipeline = BIServicePipeline(validar, extractor, settings.zona_horaria, salida_dir, settings.dias_analisis)
        filtro = args.workspace or list(settings.workspaces)
        logger.info("Workspaces: %s", ", ".join(filtro) if filtro else "todos los visibles para la app")
        resultado = pipeline.run(filtro)
        _resumen(resultado)
        logger.info("Corrida finalizada correctamente.")
        return 0
    except ConexionError as exc:
        logger.error("Proceso terminado: %s", exc)
        return 1
    except BIServiceError as exc:
        logger.error("Error: %s", exc)
        return 1
    except Exception:  # noqa: BLE001
        logger.exception("Error inesperado:")
        return 1


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

"""Migracion a Python del paquete SSIS 'CL_Proc_Carga_Places.dtsx':
recarga completa de [CL_DATA].[dbo].[TBL_PLACES] desde el Excel
'Place utilizados.xlsx' y foto diaria en [TBL_HISTORICO_PLACES].

Flujo (ver src/places/pipeline.py):

    validar conexiones -> Log Inicio ->
    CARGA PLACES: leer Excel -> validar -> convertir -> TRUNCATE + INSERT + LIMPIA TABLA ->
    CARGA PLACES HISTORICO: DELETE fecha actual + INSERT -> Log Fin

Arquitectura (src layout, modular por componentes):
    conexiones.py                  Validacion previa con reintento automatico (5 min x 3).
    extraccion/extractor.py        Excel Source (ACE, Hoja1$, HDR=YES) via Microsoft Graph.
    validacion/validator.py        Puntos FailComponent de la Conversion de datos.
    transformacion/transformer.py  Conversion de datos (DT_WSTR -> DT_STR 1252).
    carga/loader.py                TRUNCA TABLA -> CARGA TABLA -> LIMPIA TABLA.
    carga/historico.py             CARGA PLACES HISTORICO.
    logs_proceso.py                Log Inicio / Log Fin.
    pipeline.py                    Orquestador.
    mappings.py                    Constantes del .dtsx (columnas, anchos, T-SQL literal).
    db.py, sharepoint/             Adaptadores: pyodbc y Microsoft Graph.
    config.py, logging_setup.py    Configuracion via '.env' y logging.
    main.py (este archivo)         Composition root.

Configuracion: archivo '.env' junto a este script (ver '.env.example').
Ninguna credencial esta embebida en el codigo.

Uso:
    python main.py                          # corrida normal
    python main.py --solo-validar           # lee, valida y convierte; no escribe en SQL
    python main.py --archivo RUTA.xlsx      # contingencia: lee el Excel de disco (sin SharePoint)
    python main.py --sin-validar-conexiones # emergencia: omite la validacion previa
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "src" / "places"))  # permite 'import mappings', 'import db', etc.

from carga.historico import HistoricoLoader  # noqa: E402
from carga.loader import PlacesLoader  # noqa: E402
from conexiones import validar_conexiones, verificaciones_para  # noqa: E402
from config import cargar_configuracion  # noqa: E402
from db import DatabaseGateway, crear_conexion  # noqa: E402
from exceptions import ConexionError, PlacesError  # noqa: E402
from extraccion.extractor import Extractor, FuenteArchivo, FuenteLocal, FuenteSharePoint  # noqa: E402
from logging_setup import NOMBRE_LOGGER, configurar_logging  # noqa: E402
from logs_proceso import LogsProceso  # noqa: E402
from pipeline import PlacesPipeline, ResultadoPipeline  # noqa: E402
from sharepoint.client import ConexionGraph  # noqa: E402
from transformacion.transformer import Transformer  # noqa: E402
from validacion.validator import Validator  # noqa: E402

logger = logging.getLogger(NOMBRE_LOGGER)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--solo-validar", action="store_true", help="No escribe en SQL Server.")
    parser.add_argument("--archivo", type=Path, help="Lee este .xlsx de disco en vez de SharePoint (contingencia).")
    parser.add_argument("--sin-validar-conexiones", action="store_true", help="Omite la validacion previa (emergencias).")
    return parser.parse_args(argv)


def _resumen(resultado: ResultadoPipeline) -> None:
    if resultado.carga is None:
        logger.info("Filas leidas=%s (sin escribir)", resultado.filas_leidas)
        return
    logger.info(
        "TBL_PLACES OK  leidas=%s insertadas=%s borradas_id_nulo=%s finales=%s",
        resultado.filas_leidas,
        resultado.carga.insertadas,
        resultado.carga.borradas_nulos,
        resultado.carga.finales,
    )
    if resultado.historico is not None:
        logger.info(
            "TBL_HISTORICO_PLACES OK  fecha=%s eliminadas=%s insertadas=%s",
            resultado.historico.fecha.isoformat(),
            resultado.historico.eliminadas,
            resultado.historico.insertadas,
        )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        settings = cargar_configuracion(BASE_DIR)
    except PlacesError as exc:
        print(f"Error de configuracion: {exc}", file=sys.stderr)
        return 1
    log_file = configurar_logging(settings.log_dir)
    logger.info("Log de esta corrida: %s", log_file)

    cargar = not args.solo_validar
    leer_sharepoint = args.archivo is None
    logger.info("lectura=%s carga=%s", "SharePoint" if leer_sharepoint else args.archivo, cargar)

    db = DatabaseGateway(lambda: crear_conexion(settings.db), settings.batch_size, settings.db.database)
    try:
        validar = None
        if not args.sin_validar_conexiones:
            verificaciones = verificaciones_para(leer_sharepoint, cargar, settings.db, settings.sharepoint)
            validar = lambda: validar_conexiones(  # noqa: E731
                verificaciones, settings.reintentos_conexion, settings.espera_reintento_s
            )
        else:
            logger.warning("--sin-validar-conexiones: se omite la validacion previa.")

        # Graph autentica al primer uso (despues de validar las conexiones).
        fuente: FuenteArchivo = FuenteLocal(args.archivo) if args.archivo else FuenteSharePoint(
            ConexionGraph(settings.sharepoint)
        )
        pipeline = PlacesPipeline(
            validar,
            Extractor(fuente),
            Validator(),
            Transformer(),
            PlacesLoader(db) if cargar else None,
            HistoricoLoader(db) if cargar else None,
            LogsProceso(db) if cargar else None,
        )
        resultado = pipeline.run()
        _resumen(resultado)
        logger.info("Corrida finalizada correctamente.")
        return 0
    except ConexionError as exc:
        logger.error("Proceso terminado: %s", exc)
        return 1
    except PlacesError as exc:
        logger.error("Error: %s", exc)
        return 1
    except Exception:  # noqa: BLE001 - p.ej. pyodbc.Error inesperado
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

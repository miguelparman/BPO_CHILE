"""Migracion a Python del paquete SSIS 'CL_Proc_Volumetria_Gerencia.dtsx':
recarga completa de las 4 tablas de volumetria de casos especializados de
Chile en [CL_MOVIL].[dbo]:

    GERENCIA        ALTA GERENCIA_NVO ARCHIVO.xlsx          -> TBL_VOLUMETRIA_GERENCIA
    ESCALAMIENTO    Escalamiento.xlsx                       -> TBL_VOLUMETRIA_ESCALAMIENTO
    CLOSE THE LOOP  CASOS SALESFORCE - CLOSE THE LOOP.xlsx  -> TBL_VOLUMETRIA_CLOSE_THE_LOOP
    T-ATIENDO       CASOS SALESFORCE - T-ATIENDO.xlsx       -> TBL_VOLUMETRIA_T_ATIENDO

Flujo (ver src/gerencia/pipeline.py):

    validar conexiones -> copia BPO -> ReportingFractalia ->
    por flujo: extraer -> validar -> transformar -> TRUNCATE + INSERT + DELETE IS NULL

Arquitectura (src layout, modular por componentes):
    conexiones.py                  Validacion previa con reintento automatico (5 min x 3).
    ingesta/copiar.py              Copia de los 4 Excel entre sitios/tenants (Graph).
    extraccion/extractor.py        Excel Source (ACE, Hoja1$, HDR=YES).
    validacion/validator.py        Puntos FailComponent de la Conversion de datos.
    transformacion/transformer.py  Conversion de datos (DT_R8/DT_DATE/DT_WSTR -> DT_STR/DT_DBDATE).
    carga/loader.py                TRUNCATE -> OLE DB Destination -> DELETE.
    pipeline.py                    Orquestador.
    mappings.py                    Especificacion de los 4 flujos (constantes del .dtsx).
    db.py, sharepoint/             Adaptadores: pyodbc y Microsoft Graph.
    config.py, logging_setup.py    Configuracion via '.env' y logging.
    main.py (este archivo)         Composition root.

Configuracion: archivo '.env' junto a este script (ver '.env.example').
Ninguna credencial esta embebida en el codigo.

Uso:
    python main.py                          # corrida normal (copia + carga de los 4 flujos)
    python main.py --flujo GERENCIA         # solo ese flujo (repetible)
    python main.py --solo-copia             # solo copia BPO -> ReportingFractalia
    python main.py --sin-copia              # carga desde ReportingFractalia sin copiar antes
    python main.py --solo-validar           # copia, lee, valida y transforma; no escribe en SQL
    python main.py --archivo-dir RUTA       # contingencia: lee los Excel de disco (sin SharePoint)
    python main.py --sin-validar-conexiones # emergencia: omite la validacion previa
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "src" / "gerencia"))  # permite 'import mappings', 'import db', etc.

import mappings  # noqa: E402
from carga.loader import VolumetriaLoader  # noqa: E402
from conexiones import validar_conexiones, verificaciones_para  # noqa: E402
from config import cargar_configuracion  # noqa: E402
from db import DatabaseGateway, crear_conexion  # noqa: E402
from exceptions import ConexionError, GerenciaError  # noqa: E402
from extraccion.extractor import Extractor, FuenteArchivo, FuenteLocal, FuenteSharePoint  # noqa: E402
from ingesta.copiar import CopiadorSharePoint  # noqa: E402
from logging_setup import NOMBRE_LOGGER, configurar_logging  # noqa: E402
from pipeline import GerenciaPipeline, ResultadoPipeline  # noqa: E402
from sharepoint.client import ConexionGraph  # noqa: E402
from transformacion.transformer import Transformer  # noqa: E402
from validacion.validator import Validator  # noqa: E402

logger = logging.getLogger(NOMBRE_LOGGER)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--flujo", action="append", choices=list(mappings.FLUJOS_POR_NOMBRE), help="Ejecuta solo ese flujo (repetible)."
    )
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--solo-copia", action="store_true", help="Solo copia BPO -> ReportingFractalia.")
    modo.add_argument("--sin-copia", action="store_true", help="No copia; lee lo que ya esta en ReportingFractalia.")
    modo.add_argument("--archivo-dir", type=Path, help="Lee los Excel desde <dir>/<subcarpeta>/<archivo> (contingencia).")
    parser.add_argument("--solo-validar", action="store_true", help="No escribe en SQL Server.")
    parser.add_argument("--sin-validar-conexiones", action="store_true", help="Omite la validacion previa (emergencias).")
    args = parser.parse_args(argv)
    if args.solo_copia and args.solo_validar:
        parser.error("--solo-validar no aplica con --solo-copia.")
    return args


def _resumen(resultado: ResultadoPipeline) -> None:
    for c in resultado.copias:
        logger.info("Copia %-15s %s", c.flujo, "OK" if c.ok else f"FALLO: {c.error}")
    for f in resultado.flujos:
        if f.ok and f.carga:
            logger.info(
                "Flujo %-15s OK  leidas=%s insertadas=%s borradas_nulos=%s finales=%s",
                f.flujo, f.filas_leidas, f.carga.insertadas, f.carga.borradas_nulos, f.carga.finales,
            )
        elif f.ok:
            logger.info("Flujo %-15s OK  leidas=%s (sin escribir)", f.flujo, f.filas_leidas)
        else:
            logger.info("Flujo %-15s FALLO: %s", f.flujo, f.error)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        settings = cargar_configuracion(BASE_DIR)
    except GerenciaError as exc:
        print(f"Error de configuracion: {exc}", file=sys.stderr)
        return 1
    log_file = configurar_logging(settings.log_dir)
    logger.info("Log de esta corrida: %s", log_file)

    flujos = [mappings.FLUJOS_POR_NOMBRE[n] for n in args.flujo] if args.flujo else list(mappings.FLUJOS)
    copiar = not (args.sin_copia or args.archivo_dir)
    leer = not args.solo_copia
    leer_sharepoint = leer and not args.archivo_dir
    cargar = leer and not args.solo_validar
    logger.info("Flujos: %s | copia=%s lectura=%s carga=%s", [f.nombre for f in flujos], copiar,
                "local" if args.archivo_dir else ("SharePoint" if leer else "no"), cargar)

    db = DatabaseGateway(lambda: crear_conexion(settings.db), settings.batch_size, settings.db.database)
    try:
        validar = None
        if not args.sin_validar_conexiones:
            verificaciones = verificaciones_para(
                flujos, copiar, leer_sharepoint, cargar, settings.db, settings.origen, settings.destino
            )
            validar = lambda: validar_conexiones(  # noqa: E731
                verificaciones, settings.reintentos_conexion, settings.espera_reintento_s
            )
        else:
            logger.warning("--sin-validar-conexiones: se omite la validacion previa.")

        # Graph autentica al primer uso (despues de validar las conexiones).
        destino = ConexionGraph(settings.destino)
        copiador = CopiadorSharePoint(ConexionGraph(settings.origen), destino) if copiar else None
        extractor = None
        if leer:
            fuente: FuenteArchivo = FuenteLocal(args.archivo_dir) if args.archivo_dir else FuenteSharePoint(destino)
            extractor = Extractor(fuente)

        pipeline = GerenciaPipeline(
            flujos, validar, copiador, extractor, Validator(), Transformer(), VolumetriaLoader(db) if cargar else None
        )
        resultado = pipeline.run()
        _resumen(resultado)
        if not resultado.ok:
            logger.error("La corrida termino con errores (ver arriba).")
            return 1
        logger.info("Corrida finalizada correctamente.")
        return 0
    except ConexionError as exc:
        logger.error("Proceso terminado: %s", exc)
        return 1
    except GerenciaError as exc:
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

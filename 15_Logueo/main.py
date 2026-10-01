"""Migracion a Python del paquete SSIS 'Cl_Proc_Logueo.dtsx': carga
incremental del logueo de agentes de Chile (REPORTE_AGENTES_FRACTALIA_SEM.csv
del portal comercial) en [CL_LOGUEO].[dbo].[TBL_CONEXIONES], completa el DNI y
ejecuta SP_LOGUEO.

Flujo (ver src/logueo/pipeline.py), en serie:

    Log Inicio -> CARGA TABLA -> AGREGA DNI -> Log Fin -> SP      (BK deshabilitada)

Arquitectura (src layout, modular por componentes):
    extraccion/extractor.py        Flat File Source (CSV desde SharePoint via Graph).
    validacion/validator.py        Puntos FailComponent del Data Flow + controles previos.
    transformacion/transformer.py  Derived Columns 'Dia_mes' y 'FechaAnsi' + Conversion de datos.
    transformacion/lookup.py       Lookup 'Busqueda' (Full Cache, salida no coincidentes).
    carga/loader.py                LOGS_PROCESOS, INSERT, AGREGA DNI, SP_LOGUEO.
    pipeline.py                    Orquestador: el Control Flow del .dtsx.
    periodo.py                     Variable User::Periodo.
    mappings.py, sql.py            Constantes del .dtsx y T-SQL literal (scripts_sql/).
    db.py, sharepoint/             Adaptadores: pyodbc y Microsoft Graph.
    config.py, logging_setup.py    Configuracion via '.env' y logging.
    main.py (este archivo)         Composition root.

Configuracion: archivo '.env' junto a este script (ver '.env.example').
Ninguna credencial esta embebida en el codigo.

Uso:
    python main.py                        # corrida normal
    python main.py --periodo 202609       # fuerza User::Periodo (prioridad sobre PERIODO del .env)
    python main.py --solo-validar         # extrae, valida, transforma y cruza; no escribe nada
    python main.py --archivo-local RUTA   # contingencia: lee el CSV de disco en vez de SharePoint
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "src" / "logueo"))  # permite 'import mappings', 'import sql', etc.

from carga.loader import LogueoLoader  # noqa: E402
from config import cargar_configuracion  # noqa: E402
from db import DatabaseGateway, crear_conexion  # noqa: E402
from exceptions import LogueoError, PipelineError  # noqa: E402
from extraccion.extractor import FuenteArchivo, FuenteLocal, FuenteSharePoint  # noqa: E402
from logging_setup import NOMBRE_LOGGER, configurar_logging  # noqa: E402
from periodo import resolver_periodo  # noqa: E402
from pipeline import LogueoPipeline  # noqa: E402
from sharepoint.auth import GraphAuthError, get_graph_token  # noqa: E402
from sharepoint.client import SharePointClient, SharePointResolutionError  # noqa: E402

logger = logging.getLogger(NOMBRE_LOGGER)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--solo-validar", action="store_true", help="Solo extrae, valida, transforma y cruza; no escribe.")
    parser.add_argument("--periodo", help="User::Periodo YYYYMM (prioridad sobre PERIODO del .env).")
    parser.add_argument("--archivo-local", type=Path, help="Lee el CSV desde disco en vez de SharePoint (contingencia).")
    return parser.parse_args()


def crear_fuente_sharepoint(settings) -> FuenteSharePoint:
    sp = settings.sharepoint
    token = get_graph_token(sp.tenant_id, sp.client_id, sp.client_secret, sp.timeout_ms)
    client = SharePointClient(token, sp.timeout_ms)
    drive_id = client.resolve_drive(client.resolve_site(sp.hostname, sp.site_path), sp.drive_name)
    return FuenteSharePoint(client, drive_id, sp.folder_path, sp.archivo, sp.web_drive)


def main() -> int:
    args = _parse_args()
    try:
        settings = cargar_configuracion(BASE_DIR)
        periodo = resolver_periodo(args.periodo, settings.periodo_env, date.today())
    except LogueoError as exc:
        print(f"Error de configuracion: {exc}", file=sys.stderr)
        return 1
    log_file = configurar_logging(settings.log_dir)
    logger.info("Log de esta corrida: %s", log_file)

    db = DatabaseGateway(lambda: crear_conexion(settings.db), settings.batch_size, settings.db.database)
    try:
        fuente: FuenteArchivo = FuenteLocal(args.archivo_local) if args.archivo_local else crear_fuente_sharepoint(settings)
        resultado = LogueoPipeline(LogueoLoader(db), fuente, periodo).run(solo_validar=args.solo_validar)
        logger.info(
            "Resumen: archivo=%s, coincidentes=%s, no coincidentes=%s, insertadas=%s, DNI=%s, pasos=%s",
            resultado.filas_archivo,
            resultado.filas_coincidentes,
            resultado.filas_no_coincidentes,
            resultado.filas_insertadas,
            resultado.filas_dni,
            " -> ".join(resultado.pasos_ejecutados),
        )
        return 0
    except PipelineError as exc:
        logger.error("Proceso detenido (como el .dtsx, Log Fin no se ejecuta): %s", exc)
        logger.debug("Detalle", exc_info=True)
        return 1
    except (GraphAuthError, SharePointResolutionError) as exc:
        logger.error("Error conectando con SharePoint (Microsoft Graph): %s", exc)
        return 1
    except LogueoError as exc:
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

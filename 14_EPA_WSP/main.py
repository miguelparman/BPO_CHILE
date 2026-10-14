"""Migracion a Python del paquete SSIS 'CL_Proc_EPA_WSP.dtsx': carga diaria
de las encuestas de calidad de Chile (EPA/ISN, WhatsApp Medallia y portal
Medallia) en CL_TEMPORALES_INDICADORES y su proceso en CL_CALIDAD.

Flujo (ver src/epa_wsp/pipeline.py para el detalle y la equivalencia con
cada tarea del .dtsx), en serie:

    Log_Inicio -> alerta -> WSP -> EPA_ISN -> SP_EPA_ISN_CHILE
               -> MEDALIA (descarga -> carga -> SP_PROCESO_ENCUESTAS_MEDALLIA) -> Log_Fin

Arquitectura (src layout, modular por componentes, una carpeta por capa):
    extraccion/extractor.py          CSV de SharePoint y CSV local de Medallia.
    extraccion/medallia_descarga.py  Descarga del export del portal Medallia (Playwright).
    validacion/validator.py          Esquema real vs mappings.py; anchos; periodos.
    transformacion/transformer.py    Reglas de los 3 scripts de carga (tipos, clean_row, Medallia).
    carga/loader.py                  LOGS_PROCESOS, DELETE por periodo + INSERT, SPs.
    alerta.py                        enviar_alerta_encuesta.py (resultado.txt para Power Automate).
    pipeline.py                      Orquestador: llama a las capas en el orden del Control Flow.
    mappings.py, sql.py              Constantes de negocio y T-SQL literal del .dtsx (scripts_sql/).
    db.py, sharepoint/               Adaptadores: pyodbc (SQL Server) y Microsoft Graph.
    config.py, logging_setup.py      Configuracion via '.env' y logging.
    main.py (este archivo)           Composition root: arma los adaptadores y corre el pipeline.

Configuracion: archivo '.env' junto a este script (ver '.env.example').
Ninguna credencial esta embebida en el codigo.

Uso:
    python main.py                  # corrida normal
    python main.py --solo-validar   # descarga y valida los CSV + esquema, sin escribir nada
    python main.py --estricto       # se detiene en el primer paso que falle
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "src" / "epa_wsp"))  # permite 'import mappings', 'import sql', etc.

from config import cargar_configuracion  # noqa: E402
from db import DatabaseGateway, crear_conexion  # noqa: E402
from exceptions import ContrasenaMedalliaCaducadaError, EpaWspError, PipelineError  # noqa: E402
from logging_setup import NOMBRE_LOGGER, configurar_logging  # noqa: E402
from pipeline import EpaWspPipeline  # noqa: E402
from sharepoint.auth import GraphAuthError, get_graph_token  # noqa: E402
from sharepoint.carpeta import CarpetaSharePoint  # noqa: E402
from sharepoint.client import SharePointClient, SharePointResolutionError  # noqa: E402
from sharepoint.reader import CsvReader  # noqa: E402

logger = logging.getLogger(NOMBRE_LOGGER)


def _avisar_contrasena_medallia_caducada(usuario: str, url_login: str) -> None:
    """Aviso destacado al final de la consola (y en el log): sin cambio de
    contrasena en la web, la carga Medallia sigue usando el CSV anterior."""
    linea = "!" * 78
    logger.warning(
        "\n%s\n"
        "  ATENCION: MEDALLIA PIDE CAMBIO DE CONTRASENA\n"
        "  La contrasena del usuario '%s' caduco en el portal Medallia.\n"
        "  Hoy NO se descargaron encuestas nuevas: se cargo el CSV anterior.\n"
        "  1) Entrar a %s con ese usuario y crear la contrasena nueva.\n"
        "  2) Actualizar MEDALLIA_PASSWORD en el archivo .env de este proyecto.\n"
        "  3) Volver a ejecutar: python main.py\n"
        "%s",
        linea, usuario, url_login, linea,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--solo-validar", action="store_true", help="Solo extrae, transforma y valida; no escribe en la base."
    )
    parser.add_argument(
        "--estricto", action="store_true", help="Detiene el proceso en el primer paso que falle (por defecto sigue, como el .dtsx)."
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        settings = cargar_configuracion(BASE_DIR)
    except EpaWspError as exc:
        print(f"Error de configuracion: {exc}", file=sys.stderr)
        return 1
    log_file = configurar_logging(settings.log_dir)
    logger.info("Log de esta corrida: %s", log_file)

    db_general = DatabaseGateway(lambda: crear_conexion(settings.db_bbdd_general), settings.batch_size, "BBDD_GENERAL")
    db_calidad = DatabaseGateway(lambda: crear_conexion(settings.db_calidad), settings.batch_size, "CL_CALIDAD")
    db_indicadores = DatabaseGateway(
        lambda: crear_conexion(settings.db_indicadores), settings.batch_size, "CL_TEMPORALES_INDICADORES"
    )
    try:
        sp = settings.sharepoint
        token = get_graph_token(sp.tenant_id, sp.client_id, sp.client_secret, sp.timeout_ms)
        client = SharePointClient(token, sp.timeout_ms)
        drive_id = client.resolve_drive(client.resolve_site(sp.hostname, sp.site_path), sp.drive_name)

        pipeline = EpaWspPipeline(
            db_general=db_general,
            db_calidad=db_calidad,
            db_indicadores=db_indicadores,
            csv_reader=CsvReader(client, drive_id, sp.folder_path),
            medallia=settings.medallia,
            carpeta_medallia=CarpetaSharePoint(client, drive_id, sp.folder_medallia, sp.web_drive),
            alerta_archivo=settings.alerta.archivo,
            alerta_segundos_espera=settings.alerta.segundos_espera,
            periodo_desde_encuesta=settings.periodo_desde_encuesta,
            estricto=args.estricto,
        )
        resultado = pipeline.run(solo_validar=args.solo_validar)
        for paso, error in resultado.pasos_fallidos:
            logger.error("Paso fallido: %s -> %s", paso, error)
        if resultado.medallia_contrasena_caducada:
            _avisar_contrasena_medallia_caducada(settings.medallia.usuario, settings.medallia.url_login)
        return 0 if resultado.exitoso else 1

    except PipelineError as exc:
        logger.error("Error durante el proceso EPA/WSP: %s", exc)
        logger.exception("Detalle del error:")
        if isinstance(exc.causa, ContrasenaMedalliaCaducadaError):  # --estricto
            _avisar_contrasena_medallia_caducada(exc.causa.usuario, exc.causa.url_login)
        return 1
    except (GraphAuthError, SharePointResolutionError) as exc:
        logger.error("Error conectando con SharePoint (Microsoft Graph): %s", exc)
        return 1
    except EpaWspError as exc:
        logger.error("Error: %s", exc)
        return 1
    except Exception:  # noqa: BLE001 - p.ej. pyodbc.Error al conectar a SQL Server
        logger.exception("Error inesperado:")
        return 1
    finally:
        db_indicadores.cerrar()
        db_calidad.cerrar()
        db_general.cerrar()


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

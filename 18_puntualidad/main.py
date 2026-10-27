r"""Migracion a Python del paquete SSIS SSIS_CL_Puntualidad.dtsx (Chile):

    SLA PRUEBA (TRUNCA TABLA -> TBL_SLA_CHILE -> UPDATE)  ->  PUNTUALIDAD

  1. SLA: el Excel DB.xlsx (hoja 'SLA - Carterizado') -> [CL_ANALISIS].[dbo].[TBL_SLA].
  2. PUNTUALIDAD: [CL_MOVIL].[dbo].[TBL_PUNTUALIDAD], desde la vista de seguimiento
     cruzada con las vistas SLA, con sus fechas de vencimiento y tiempos de atencion.

Origen: el mismo DB.xlsx, ahora en SharePoint (ReportingFractalia / Data Reporting /
REPOSITORIOS DE CRUDOS / CHILE / BPOCHIPE / 08 PUNTUALIDAD), leido via Microsoft Graph.
Antes era ...\BPO - Insumos\Chile\INDICADORES CHILE\SLA Puntualidad\DB.xlsx.

Arquitectura (src layout, modular por componentes):
    extraccion/extractor.py         SharePoint/local; lectura del Excel (Excel Source).
    validacion/validator.py         Encabezados, esquema y anchos reales de la tabla destino.
    transformacion/transformer.py   Data Conversion (tipos, anchos, cp1252, numeric -> int).
    carga/loader.py                 TRUNCATE + carga + UPDATE de TBL_SLA y generacion de PUNTUALIDAD.
    pipeline.py                     Orquestador.
    equivalencia/comparador.py      Prueba de equivalencia contra el T-SQL original (en el servidor).
    mappings.py, sql.py             Constantes del .dtsx y T-SQL (scripts_sql/).
    db.py, sharepoint/              Adaptadores: pyodbc y Microsoft Graph.
    conexiones.py                   Validacion previa de conexiones (5 min x 3).
    config.py, logging_setup.py     Configuracion via '.env' y logging.
    main.py (este archivo)          Composition root.

Configuracion: archivo '.env' junto a este script (ver '.env.example').
Ninguna credencial esta embebida en el codigo.

Destino: por defecto --destino prueba (TBL_SLA_PY y TBL_PUNTUALIDAD_PY; no toca
produccion). --destino produccion escribe las tablas reales.

Uso:
    python main.py                          # corrida completa, en modo prueba
    python main.py --destino produccion     # corrida completa sobre las tablas reales
    python main.py --solo sla               # solo la carga de TBL_SLA
    python main.py --solo puntualidad       # solo TBL_PUNTUALIDAD
    python main.py --solo-validar           # lee, valida y transforma el Excel; no escribe nada
    python main.py --verificar              # solo conexiones; no carga nada
    python main.py --origen-local RUTA.xlsx # contingencia: Excel desde una ruta local
    python main.py --equivalencia           # compara contra el T-SQL original (escribe solo tablas _EQ_/_PY)

Codigo de salida: 0 OK; 1 error (conexion, configuracion o una tarea fallo);
--equivalencia: 2 si el resultado no es equivalente.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "src" / "puntualidad"))  # permite 'import mappings', 'import sql', etc.

from carga.loader import PuntualidadLoader  # noqa: E402
from conexiones import validar_conexiones, verificaciones_para  # noqa: E402
from config import cargar_configuracion  # noqa: E402
from db import DatabaseGateway, crear_conexion  # noqa: E402
from equivalencia.comparador import ejecutar_equivalencia, veredicto  # noqa: E402
from exceptions import ConexionError, PipelineError, PuntualidadError  # noqa: E402
from extraccion.extractor import FuenteExcel, FuenteLocal, FuenteSharePoint  # noqa: E402
from logging_setup import NOMBRE_LOGGER, configurar_logging  # noqa: E402
from mappings import MODO_PRODUCCION, MODO_PRUEBA, MODOS, destino_para  # noqa: E402
from pipeline import TAREA_PUNTUALIDAD, TAREA_SLA, PuntualidadPipeline  # noqa: E402
from sharepoint.client import conectar  # noqa: E402

logger = logging.getLogger(NOMBRE_LOGGER)

_SOLO = {"sla": TAREA_SLA, "puntualidad": TAREA_PUNTUALIDAD}
RUTA_ORIGINAL = BASE_DIR / "docs" / "referencia_sql" / "p2_PUNTUALIDAD.sql"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--destino", choices=MODOS, default=MODO_PRUEBA, help="prueba (TBL_*_PY, por defecto) o produccion (TBL_SLA y TBL_PUNTUALIDAD)."
    )
    parser.add_argument("--solo", nargs="+", choices=sorted(_SOLO), help="Ejecuta solo estas tareas (en orden).")
    parser.add_argument("--solo-validar", action="store_true", help="Lee, valida y transforma el Excel; no escribe.")
    parser.add_argument("--verificar", action="store_true", help="Solo conexiones; no carga nada.")
    parser.add_argument("--origen-local", type=Path, help="Lee el Excel desde una ruta local en vez de SharePoint.")
    parser.add_argument("--equivalencia", action="store_true", help="Compara contra el T-SQL original (ver docs/EQUIVALENCIA.md).")
    parser.add_argument("--sin-referencia", action="store_true", help="Con --equivalencia: no corre el T-SQL original (lento).")
    parser.add_argument("--conservar-tablas", action="store_true", help="Con --equivalencia: no borra las tablas TBL_PUNTUALIDAD_EQ_*.")
    return parser.parse_args()


def crear_fuente_sharepoint(settings) -> FuenteSharePoint:
    sp = settings.sharepoint
    cliente, drive_id = conectar(sp)
    return FuenteSharePoint(cliente, drive_id, sp.ruta_archivo, sp.web_drive)


def main() -> int:
    args = _parse_args()
    try:
        settings = cargar_configuracion(BASE_DIR)
    except PuntualidadError as exc:
        print(f"Error de configuracion: {exc}", file=sys.stderr)
        return 1
    log_file = configurar_logging(settings.log_dir)
    logger.info("Log de esta corrida: %s", log_file)
    destino = destino_para(args.destino, settings.fecha_desde)
    tareas = [_SOLO[s] for s in sorted(args.solo, key=list(_SOLO).index)] if args.solo else [TAREA_SLA, TAREA_PUNTUALIDAD]
    if destino.modo == MODO_PRODUCCION and not (args.solo_validar or args.verificar):
        logger.warning("MODO PRODUCCION: se escribiran %s y %s.", destino.tbl_sla, destino.tbl_puntualidad)

    db = DatabaseGateway(lambda: crear_conexion(settings.db), settings.batch_size, settings.db.server)
    try:
        validar_conexiones(
            verificaciones_para(
                settings.db,
                settings.sharepoint,
                leer_sharepoint=not args.origen_local and not args.equivalencia and TAREA_SLA in tareas,
            ),
            reintentos=settings.reintentos_conexion,
            espera_s=settings.espera_reintento_s,
        )
        if args.verificar:
            logger.info("Verificacion: conexiones OK. Listo para correr.")
            return 0
        if args.equivalencia:
            resultado = ejecutar_equivalencia(
                db,
                RUTA_ORIGINAL,
                settings.evidencias_dir,
                con_referencia=not args.sin_referencia,
                conservar=args.conservar_tablas,
                destino_sla=destino_para(MODO_PRUEBA),
            )
            logger.info("Equivalencia: %s", veredicto(resultado))
            return 0 if resultado.equivalente or resultado.equivalente_salvo_empates or args.sin_referencia else 2
        if args.origen_local:
            fuente: FuenteExcel | None = FuenteLocal(args.origen_local)
        else:
            fuente = crear_fuente_sharepoint(settings) if TAREA_SLA in tareas else None
        resultado = PuntualidadPipeline(PuntualidadLoader(db, destino), fuente, settings.sharepoint.hoja).run(
            tareas, solo_validar=args.solo_validar
        )
        logger.info("=" * 70)
        logger.info("Proceso terminado: %s tarea(s).", len(resultado.tareas))
        return 0
    except ConexionError as exc:
        logger.error("%s", exc)
        return 1
    except PipelineError as exc:
        logger.error("Proceso detenido (no se ejecutan las tareas siguientes): %s", exc)
        logger.debug("Detalle", exc_info=True)
        return 1
    except PuntualidadError as exc:
        logger.error("Error: %s", exc)
        return 1
    except Exception:  # noqa: BLE001 - p.ej. error de Graph al resolver el drive
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

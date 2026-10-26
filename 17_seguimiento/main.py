"""Migracion a Python de los paquetes SSIS CL_Seguimiento (Chile):

    02 CL_Seguimiento_02_Proc_Carga_Casos.dtsx
    03 CL_Seguimiento_03_Proc_Carga_Correos.dtsx
    04 CL_Seguimiento_04_Proc_Carga_Historial_Casos.dtsx
    06 CL_Seguimiento_06_Proc_Carga_Historial_Comentarios.dtsx
    07 CL_Seguimiento_07_Proc_Seguimiento.dtsx
    (05 Historial Asignaciones: fuera de alcance)

Se ejecutan en ese orden; un paquete empieza solo si el anterior termino OK
y ante cualquier fallo se detiene todo (ver src/seguimiento/pipeline.py).

Origen: los CSV CRUDOS que 201_bot_salesforce publica en SharePoint
(ReportingFractalia / Data Reporting / REPOSITORIOS DE CRUDOS / CHILE /
BPOCHIPE / 01 SEGUIMIENTO y 12 AUXILIARES), leidos tal cual (sin el paso
intermedio del paquete 01 a ...\\SEGUIMIENTO\\Nuevo) y descargados en
paralelo. Las staging van a #temporales de la sesion de cada paquete y se
quitaron los pasos redundantes (ver docs/EQUIVALENCIA.md).

Arquitectura (src layout, modular por componentes):
    extraccion/extractor.py         SharePoint/local, descarga en paralelo, lectura del CSV crudo (Flat File Source).
    validacion/validator.py         Columnas por fila, esquema y anchos reales de la staging.
    transformacion/transformer.py   Derived Column + Data Conversion (tipos, anchos, disposiciones) + saltos CRLF.
    transformacion/cruce.py         Casos x Nombre Contacto (reemplaza staging + 'Agrega Nombre de Contacto').
    transformacion/descripciones_nc.py  Carga_Reporte_Descripciones_NC_Chile.py migrado.
    carga/loader.py                 Sesion por paquete, #temporales, Execute SQL Tasks y transacciones.
    paquetes/pXX_*.py               Control Flow de cada .dtsx declarado como datos.
    pipeline.py                     Orquestador.
    mappings.py, sql.py             Constantes del .dtsx y T-SQL literal (scripts_sql/).
    db.py, sharepoint/              Adaptadores: pyodbc y Microsoft Graph.
    conexiones.py                   Validacion previa de conexiones (5 min x 3).
    config.py, logging_setup.py     Configuracion via '.env' y logging.
    main.py (este archivo)          Composition root.

Configuracion: archivo '.env' junto a este script (ver '.env.example').
Ninguna credencial esta embebida en el codigo.

Uso:
    python main.py                         # corrida completa 02 -> 07
    python main.py --desde 04              # retoma desde un paquete (04, 06, 07)
    python main.py --solo 03 04            # solo esos paquetes (en orden)
    python main.py --solo-validar          # extrae, valida y transforma; no escribe nada
    python main.py --origen-local RUTA     # contingencia: CSV crudos del bot desde una carpeta local
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "src" / "seguimiento"))  # permite 'import mappings', 'import sql', etc.

from carga.loader import SeguimientoLoader  # noqa: E402
from conexiones import validar_conexiones, verificaciones_para  # noqa: E402
from config import cargar_configuracion  # noqa: E402
from db import DatabaseGateway, crear_conexion  # noqa: E402
from exceptions import ConexionError, PipelineError, SeguimientoError  # noqa: E402
from extraccion.extractor import FuenteArchivo, FuenteLocal, FuenteSharePoint  # noqa: E402
from logging_setup import NOMBRE_LOGGER, configurar_logging  # noqa: E402
from paquetes import CODIGOS, seleccionar  # noqa: E402
from pipeline import SeguimientoPipeline  # noqa: E402
from sharepoint.client import conectar  # noqa: E402

logger = logging.getLogger(NOMBRE_LOGGER)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--desde", choices=CODIGOS, help="Ejecuta desde este paquete en adelante.")
    parser.add_argument("--solo", nargs="+", choices=CODIGOS, help="Ejecuta solo estos paquetes (en orden).")
    parser.add_argument("--solo-validar", action="store_true", help="Extrae, valida y transforma; no escribe.")
    parser.add_argument("--origen-local", type=Path, help="Lee los CSV crudos desde una carpeta local en vez de SharePoint.")
    return parser.parse_args()


def crear_fuente_sharepoint(settings) -> FuenteSharePoint:
    sp = settings.sharepoint
    cliente, drive_id = conectar(sp)
    return FuenteSharePoint(cliente, drive_id, sp.carpetas, sp.web_drive)


def main() -> int:
    args = _parse_args()
    try:
        settings = cargar_configuracion(BASE_DIR)
        paquetes = seleccionar(args.desde, args.solo)
    except SeguimientoError as exc:
        print(f"Error de configuracion: {exc}", file=sys.stderr)
        return 1
    log_file = configurar_logging(settings.log_dir)
    logger.info("Log de esta corrida: %s", log_file)
    logger.info("Paquetes: %s%s", " -> ".join(p.codigo for p in paquetes), " (solo validar)" if args.solo_validar else "")

    db = DatabaseGateway(lambda: crear_conexion(settings.db), settings.batch_size, settings.db.server)
    try:
        validar_conexiones(
            verificaciones_para(paquetes, settings.db, settings.sharepoint, leer_sharepoint=not args.origen_local),
            reintentos=settings.reintentos_conexion,
            espera_s=settings.espera_reintento_s,
        )
        fuente: FuenteArchivo = FuenteLocal(args.origen_local) if args.origen_local else crear_fuente_sharepoint(settings)
        resultado = SeguimientoPipeline(SeguimientoLoader(db), fuente, paquetes).run(solo_validar=args.solo_validar)
        logger.info("=" * 70)
        logger.info("Proceso terminado: %s tareas, %s advertencia(s).", len(resultado.tareas), len(resultado.advertencias))
        for t in resultado.advertencias:
            logger.warning("  [%s] %s: %s", t.paquete, t.tarea, t.detalle)
        return 0
    except ConexionError as exc:
        logger.error("%s", exc)
        return 1
    except PipelineError as exc:
        logger.error("Proceso detenido (no se ejecutan las tareas ni los paquetes siguientes): %s", exc)
        logger.debug("Detalle", exc_info=True)
        return 1
    except SeguimientoError as exc:
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

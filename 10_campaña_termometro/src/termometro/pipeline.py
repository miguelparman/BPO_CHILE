"""
Orquestación del pipeline. Reemplaza el Control Flow del .dtsx:

  SOURCE (clientes)             \\
  Contenedor de secuencias       |-> convergen en -> Contenedor "162" (paso final)
  (detractores)                  |
  SALESFORCE 1 (encuestas)      /

Las tres primeras ramas corren en paralelo (igual que en SSIS, donde no
dependen entre sí), y el paso final solo arranca cuando las tres terminan
exitosamente -- igual que las Precedence Constraints originales.

Antes de las ramas se descargan los dos archivos crudos (SharePoint vía
Graph). Si alguna descarga falla, el proceso se detiene sin haber hecho
ningún TRUNCATE/DELETE: las tablas quedan como estaban.
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import sql
from db import run_sql_file
from carga.loader import truncate_table, load_dataframe
from extraccion.excel_extractor import read_excel_sheet
from extraccion.csv_extractor import read_salesforce_csv
from extraccion.fuentes import Fuente
from transformacion.clientes import transform_clientes
from transformacion.detractores import transform_detractores
from transformacion.encuestas import transform_encuestas
from config import settings

logger = logging.getLogger(__name__)


def descargar(nombre: str, fuente: Fuente) -> bytes:
    logger.info("[descarga] %s: %s", nombre, fuente.descripcion)
    contenido = fuente.leer()
    logger.info("[descarga] %s: %d bytes", nombre, len(contenido))
    return contenido


def rama_clientes(excel: bytes, origen: str, periodo: int) -> None:
    """Reemplaza el contenedor 'SOURCE': TRUNCATE + Data Flow 'BASE TERMOMETRO'."""
    logger.info("[clientes] inicio")
    truncate_table("TBL_CAMPAÑA_TERMOMETRO_SOURCE")
    df = read_excel_sheet(excel, settings.excel_clientes_sheet, origen)
    df = transform_clientes(df, periodo)
    load_dataframe(df, "TBL_CAMPAÑA_TERMOMETRO_SOURCE")
    logger.info("[clientes] fin (%d filas)", len(df))


def rama_detractores(excel: bytes, origen: str) -> None:
    """Reemplaza 'Contenedor de secuencias': TRUNCATE + Data Flow detractores."""
    logger.info("[detractores] inicio")
    truncate_table("TBL_CAMPAÑA_TERMOMETRO_DETRACTOR")
    df = read_excel_sheet(excel, settings.excel_detractores_sheet, origen)
    df = transform_detractores(df)
    load_dataframe(df, "TBL_CAMPAÑA_TERMOMETRO_DETRACTOR")
    logger.info("[detractores] fin (%d filas)", len(df))


def rama_salesforce(csv: bytes, origen: str, periodo: int, fecha_inicio: str, fecha_fin: str) -> None:
    """Reemplaza 'SALESFORCE 1': DELETE PERIODO -> carga CSV -> limpieza -> ESTADO -> PESO."""
    logger.info("[salesforce] inicio")
    run_sql_file(sql.DELETE_PERIODO_SF, {"periodo": periodo})

    df = read_salesforce_csv(csv, origen)
    df = transform_encuestas(df, periodo)
    load_dataframe(df, "TBL_CAMPAÑA_TERMOMETRO_SF_TEMP")

    run_sql_file(sql.DELETE_FUERA_RANGO, {"fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin})
    run_sql_file(sql.UPDATE_ESTADO, {"periodo": periodo})
    run_sql_file(sql.UPDATE_PESO, {"periodo": periodo})
    logger.info("[salesforce] fin (%d filas)", len(df))


def paso_final(periodo: int, fecha_evaluacion: str, fecha_fin_evaluacion: str) -> None:
    """Reemplaza el contenedor '162': DELETE PERIODO EN EVALUACION + INSERT final."""
    logger.info("[final] inicio")
    run_sql_file(sql.DELETE_PERIODO_EVALUACION, {"periodo": periodo})
    run_sql_file(
        sql.INSERT_FINAL,
        {
            "periodo": periodo,
            "fecha_evaluacion": fecha_evaluacion,
            "fecha_fin_evaluacion": fecha_fin_evaluacion,
        },
    )
    logger.info("[final] fin")


def run(periodo: int, fecha_inicio: str, fecha_fin: str, fuente_excel: Fuente, fuente_csv: Fuente) -> None:
    excel = descargar("Excel clientes/detractores", fuente_excel)
    csv = descargar("CSV Salesforce", fuente_csv)

    ramas = {
        "clientes": lambda: rama_clientes(excel, fuente_excel.descripcion, periodo),
        "detractores": lambda: rama_detractores(excel, fuente_excel.descripcion),
        "salesforce": lambda: rama_salesforce(csv, fuente_csv.descripcion, periodo, fecha_inicio, fecha_fin),
    }

    logger.info("Ejecutando las 3 ramas en paralelo: %s", list(ramas))
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(fn): name for name, fn in ramas.items()}
        errores = []
        for future in as_completed(futures):
            name = futures[future]
            try:
                future.result()
            except Exception as exc:
                logger.exception("La rama '%s' falló", name)
                errores.append((name, exc))

    if errores:
        raise RuntimeError(
            f"El pipeline se detuvo: fallaron las ramas {[n for n, _ in errores]}. "
            "El paso final no se ejecuta (igual que las Precedence Constraints originales)."
        )

    paso_final(periodo, fecha_inicio, fecha_fin)

"""Carga.

- Log Inicio / Log Fin: [BBDD_GENERAL].[dbo].[LOGS_PROCESOS] (Nombre='Chile_Trafico').
- TEMPORALES: TRUNCA TABLAS + INSERT de cada origen, en UNA transaccion.
  (Los scripts originales ademas hacian 'DELETE ... WHERE DATE_YYYYMM >= ?'
  sobre la temporal recien truncada: era un no-op y no se replica.)
- CL_TRAFICO: DELETE PERIODO + los 8 OLE DB Destination del Data Flow
  CARGA, en UNA transaccion. En SSIS eran tareas separadas: si CARGA
  fallaba, el periodo quedaba borrado; aqui un fallo deja la tabla como estaba.
"""

from __future__ import annotations

import logging

import pandas as pd

import mappings
import previsto
import sql

logger = logging.getLogger("trafico")


def registrar_inicio(db_trafico) -> None:
    """Package\\Log Inicio."""
    db_trafico.execute_script(sql.LOG_INICIO)


def registrar_fin(db_trafico) -> None:
    """Package\\Log Fin."""
    db_trafico.execute_script(sql.LOG_FIN)


def cargar_temporales(db_temporales, extraidos: dict[str, pd.DataFrame]) -> dict[str, int]:
    """Package\\TEMPORALES: TRUNCA TABLAS -> Atendidas -> Abandono -> Transfer ->
    Outbound -> Cleared -> Callback -> Cross_In."""
    filas: dict[str, int] = {}
    with db_temporales.transaccion():
        db_temporales.execute_script(sql.TEMPORALES_TRUNCA_TABLAS)
        logger.info("[Trafico]   TEMPORALES / TRUNCA TABLAS (7 tablas)")
        for origen in mappings.ORIGENES:
            logger.info("[Trafico]   TEMPORALES / %s -> %s", origen.paso, origen.tabla_temporal)
            filas[origen.tabla_temporal] = db_temporales.bulk_insert(
                origen.tabla_temporal, extraidos[origen.tabla_temporal], mappings.SCHEMA
            )
    return filas


def cargar_cl_trafico(db_trafico, periodo: int, transformados: dict[str, pd.DataFrame]) -> dict[str, int]:
    """Package\\CL_TRAFICO: DELETE PERIODO (? = User::Periodo) -> CARGA."""
    filas: dict[str, int] = {}
    with db_trafico.transaccion():
        db_trafico.execute_script(sql.CL_TRAFICO_DELETE_PERIODO, (periodo,))
        logger.info("[Trafico]   CL_TRAFICO / DELETE PERIODO >= %s (8 tablas)", periodo)
        for destino in mappings.DESTINOS:
            filas[destino.tabla] = db_trafico.bulk_insert(destino.tabla, transformados[destino.tabla], mappings.SCHEMA)
    return filas


def leer_previsto_existente(db_data, desde, hoy) -> tuple[pd.DataFrame, int]:
    """Lee de TBL_PREVISTO_CL (solo lectura) las filas con Fecha entre 'desde' y 'hoy' (para saber que
    llaves ya existen) y cuenta cuantas filas futuras (Fecha > hoy) hay hoy en la tabla."""
    existente = db_data.run_query(
        f"SELECT Servicio, Fecha, Tramo, Prev_Voz FROM [{previsto.ESQUEMA}].[{previsto.TABLA}] "
        "WHERE Fecha >= ? AND Fecha <= ?",
        (desde, hoy),
    )
    futuras = db_data.fetch_scalar(
        f"SELECT COUNT(*) FROM [{previsto.ESQUEMA}].[{previsto.TABLA}] WHERE Fecha > ?", (hoy,)
    )
    return existente, int(futuras or 0)


def cargar_previsto(db_data, plan: previsto.PlanPrevisto) -> dict[str, int]:
    """[CL_DATA].[dbo].[TBL_PREVISTO_CL], en UNA transaccion (todo o nada): borra las fechas FUTURAS
    (> hoy) solo si el archivo trae fechas futuras con que reemplazarlas, inserta las llaves faltantes
    del pasado/hoy y las fechas futuras del archivo. Nunca actualiza ni borra filas con Fecha <= hoy."""
    resultado = {"borradas": 0, "insertadas_pasado": 0, "insertadas_futuro": 0}
    with db_data.transaccion():
        if len(plan.reemplazar_futuro):
            db_data.execute_script(
                f"DELETE FROM [{previsto.ESQUEMA}].[{previsto.TABLA}] WHERE Fecha > ?", (plan.hoy,)
            )
            resultado["borradas"] = plan.futuro_en_tabla
        resultado["insertadas_pasado"] = db_data.bulk_insert(previsto.TABLA, plan.insertar_pasado, previsto.ESQUEMA)
        resultado["insertadas_futuro"] = db_data.bulk_insert(previsto.TABLA, plan.reemplazar_futuro, previsto.ESQUEMA)
    return resultado

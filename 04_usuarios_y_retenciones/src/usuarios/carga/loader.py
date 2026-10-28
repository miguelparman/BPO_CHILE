"""Carga: deletes/truncados y Destinos OLE DB de los 5 paquetes
USUARIOS_*.dtsx. Todos los destinos viven en CL_USUARIOS -- la carga de
'CARGA DE USUARIOS RETENCIONES SERVIDOR CHILE' (Externos_Frac,
TBL_FRACTALIA_USER_RETENCIONES) se dio de baja por ser un trabajo obsoleto,
ver pipeline.py."""

from __future__ import annotations

import logging

import pandas as pd

import mappings
import sql
from db import DatabaseGateway
from exceptions import CargaError
from models import Periodo

logger = logging.getLogger("usuarios")


def eliminar_parque(db_cl_usuarios: DatabaseGateway, periodo: Periodo) -> None:
    """Tarea 'DELETE' (USUARIOS_0101 Parque.dtsx)."""
    try:
        db_cl_usuarios.execute_script(sql.PARQUE_DELETE, params=(periodo.valor,))
    except Exception as exc:
        raise CargaError(f"Fallo la tarea 'DELETE' de Parque: {exc}") from exc
    logger.info("Parque: filas de ParqueTCH con periodo >= (periodo-1 mes) eliminadas.")


def cargar_parque(db_cl_usuarios: DatabaseGateway, df: pd.DataFrame) -> int:
    """Destino OLE DB 'ParqueTCH' del Data Flow 'PARQUE'."""
    return db_cl_usuarios.bulk_insert(mappings.PARQUE_TABLE, df)


def eliminar_bajas_fraude(db_cl_usuarios: DatabaseGateway, periodo: Periodo) -> None:
    """Tarea 'DELETE' de "BAJAS FRAUDE" (USUARIOS_0201 SSIS_CL_Retenciones.dtsx)."""
    try:
        db_cl_usuarios.execute_script(sql.RETENCIONES_BAJAS_FRAUDE_DELETE, params=(periodo.valor,))
    except Exception as exc:
        raise CargaError(f"Fallo la tarea 'DELETE' de BAJAS FRAUDE: {exc}") from exc


def cargar_bajas_fraude(db_cl_usuarios: DatabaseGateway, df: pd.DataFrame) -> int:
    """Destino OLE DB 'TBL_SERVCH_BAJAS_FRAUDE' del Data Flow homonimo."""
    return db_cl_usuarios.bulk_insert(mappings.RETENCIONES_BAJAS_FRAUDE_TABLE, df)


def eliminar_bajas_por_alta(db_cl_usuarios: DatabaseGateway, periodo: Periodo) -> None:
    """Tarea 'DELETE LOCAL' de "BAJAS POR ALTA" (USUARIOS_0201 SSIS_CL_Retenciones.dtsx)."""
    try:
        db_cl_usuarios.execute_script(sql.RETENCIONES_BAJAS_POR_ALTA_DELETE, params=(periodo.valor,))
    except Exception as exc:
        raise CargaError(f"Fallo la tarea 'DELETE LOCAL' de BAJAS POR ALTA: {exc}") from exc


def cargar_bajas_por_alta(db_cl_usuarios: DatabaseGateway, df: pd.DataFrame) -> int:
    """Destino OLE DB 'TBL_SERVCH_BAJAS_POR_ALTA_FO' del Data Flow homonimo."""
    return db_cl_usuarios.bulk_insert(mappings.RETENCIONES_BAJAS_POR_ALTA_TABLE, df)


def eliminar_bd_reten(db_cl_usuarios: DatabaseGateway, periodo: Periodo) -> None:
    """Tarea 'DELETE BD_RETEN' de "Find new records or for updating"
    (USUARIOS_0201 SSIS_CL_Retenciones.dtsx)."""
    try:
        db_cl_usuarios.execute_script(sql.RETENCIONES_BD_RETEN_DELETE, params=(periodo.valor,))
    except Exception as exc:
        raise CargaError(f"Fallo la tarea 'DELETE BD_RETEN': {exc}") from exc


def cargar_bd_reten(db_cl_usuarios: DatabaseGateway, df: pd.DataFrame) -> int:
    """Destino OLE DB 'BD_RETEN (Local)' del Data Flow 'BD_RETEN'."""
    return db_cl_usuarios.bulk_insert(mappings.RETENCIONES_BD_RETEN_TABLE, df)


def eliminar_bajas_fijo(db_cl_usuarios: DatabaseGateway, periodo: Periodo) -> None:
    """Tarea 'DELETE FIJO' de "CARGA BAJAS" (USUARIOS_0300 ETL_INTENCIONES.dtsx)."""
    try:
        db_cl_usuarios.execute_script(sql.INTENCIONES_DELETE_BAJAS_FIJO, params=(periodo.valor,))
    except Exception as exc:
        raise CargaError(f"Fallo la tarea 'DELETE FIJO': {exc}") from exc


def cargar_bajas_fijo(db_cl_usuarios: DatabaseGateway, df: pd.DataFrame) -> int:
    """Destino OLE DB del pipe 'BAJAS_FIJO' del Data Flow 'TBL_CH_BAJAS'."""
    return db_cl_usuarios.bulk_insert(mappings.INTENCIONES_BAJAS_FIJO_TABLE, df)


def eliminar_bajas_movil(db_cl_usuarios: DatabaseGateway, periodo: Periodo) -> None:
    """Tarea 'DELETE MOVIL' de "CARGA BAJAS" (USUARIOS_0300 ETL_INTENCIONES.dtsx)."""
    try:
        db_cl_usuarios.execute_script(sql.INTENCIONES_DELETE_BAJAS_MOVIL, params=(periodo.valor,))
    except Exception as exc:
        raise CargaError(f"Fallo la tarea 'DELETE MOVIL': {exc}") from exc


def cargar_bajas_movil(db_cl_usuarios: DatabaseGateway, df: pd.DataFrame) -> int:
    """Destino OLE DB del pipe 'BAJAS_MOVIL' del Data Flow 'TBL_CH_BAJAS'."""
    return db_cl_usuarios.bulk_insert(mappings.INTENCIONES_BAJAS_MOVIL_TABLE, df)


def eliminar_intenciones(db_cl_usuarios: DatabaseGateway, periodo: Periodo) -> None:
    """Tarea 'DELETE' de "TBL_INTENCIONES" (USUARIOS_0300 ETL_INTENCIONES.dtsx)."""
    try:
        db_cl_usuarios.execute_script(sql.INTENCIONES_TBL_DELETE, params=(periodo.valor,))
    except Exception as exc:
        raise CargaError(f"Fallo la tarea 'DELETE' de TBL_INTENCIONES: {exc}") from exc


def cargar_intenciones_local(db_cl_usuarios: DatabaseGateway, df: pd.DataFrame) -> int:
    """Destino OLE DB 'INTENCIONES LOCAL' del Data Flow 'INTENCIONES'. Unico
    destino de los 5 paquetes con disposicion de error IgnoreFailure."""
    return db_cl_usuarios.bulk_insert_ignorando_errores(mappings.INTENCIONES_TABLE, df)


def truncar_temp01(db_cl_usuarios: DatabaseGateway) -> None:
    """Tarea 'TRUNCATE TEMP_01' de "TABULANDO INTENCIONES"."""
    db_cl_usuarios.truncate_table(mappings.INTENCIONES_TEMP01_TABLE)


def truncar_temp02(db_cl_usuarios: DatabaseGateway) -> None:
    """Tarea 'TRUNCATE TABLE TEMP_02' de "TABULANDO INTENCIONES"."""
    db_cl_usuarios.truncate_table(mappings.INTENCIONES_TEMP02_TABLE)


def truncar_temp03(db_cl_usuarios: DatabaseGateway) -> None:
    """Tarea 'TRUNCATE TABLE TEMP_03' de "TABULANDO INTENCIONES"."""
    db_cl_usuarios.truncate_table(mappings.INTENCIONES_TEMP03_TABLE)


def truncar_temp04(db_cl_usuarios: DatabaseGateway) -> None:
    """Tarea 'TRUNCATE TABLE TEMP_04' de "TABULANDO INTENCIONES"."""
    db_cl_usuarios.truncate_table(mappings.INTENCIONES_TEMP04_TABLE)


def eliminar_intenciones_tab(db_cl_usuarios: DatabaseGateway, periodo: Periodo) -> None:
    """Tarea 'DELETE INTENCIONES_TAB' de "TABULANDO INTENCIONES"."""
    try:
        db_cl_usuarios.execute_script(sql.INTENCIONES_TAB_DELETE, params=(periodo.valor,))
    except Exception as exc:
        raise CargaError(f"Fallo la tarea 'DELETE INTENCIONES_TAB': {exc}") from exc


def eliminar_item_amdocs(db_cl_usuarios: DatabaseGateway, periodo: Periodo) -> None:
    """Tarea 'DELETE' de "Loading to the Staging"
    (USUARIOS_0301 SSIS_CL_Item_amdocs.dtsx)."""
    try:
        db_cl_usuarios.execute_script(sql.ITEM_AMDOCS_DELETE, params=(periodo.valor,))
    except Exception as exc:
        raise CargaError(f"Fallo la tarea 'DELETE' de Item_amdocs: {exc}") from exc


def cargar_item_amdocs(db_cl_usuarios: DatabaseGateway, df: pd.DataFrame) -> int:
    """Destino OLE DB del Data Flow 'INTEN_AMDOCS'."""
    return db_cl_usuarios.bulk_insert(mappings.ITEM_AMDOCS_TABLE, df)


def truncar_saip(db_cl_usuarios: DatabaseGateway) -> None:
    """Tarea 'TRUNCATE SAIP' (USUARIOS_0302 ETL_BASE_SAIP.dtsx)."""
    db_cl_usuarios.truncate_table(mappings.SAIP_TABLE)


def cargar_saip(db_cl_usuarios: DatabaseGateway, df: pd.DataFrame) -> int:
    """Destino OLE DB 'Local SAIP' del Data Flow 'SAIP'."""
    return db_cl_usuarios.bulk_insert(mappings.SAIP_TABLE, df)

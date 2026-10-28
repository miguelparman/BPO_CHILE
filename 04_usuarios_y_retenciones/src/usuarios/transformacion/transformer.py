"""Transformacion: emulacion de los componentes 'Data Conversion' de cada
Data Flow (sobre DataFrame, para copias entre instancias SQL distintas) y
las tareas Execute SQL / Data Flow que corren enteramente dentro del mismo
servidor -- estas ultimas se preservan como scripts T-SQL en sql.py y se
ejecutan tal cual (no se reimplementa su logica en pandas): son las mismas
sentencias que corria el paquete original contra el mismo servidor, sobre
las mismas tablas, incluyendo llamadas a UDFs/vistas de otras bases de datos
(SERVICIOS_GENERALES, CL_DATA) que no forman parte del .dtsx y cuya logica
interna no es necesario conocer para preservar el comportamiento -- ver
README, seccion "Notas de fidelidad".
"""

from __future__ import annotations

import logging

import sql
from db import DatabaseGateway
from exceptions import CargaError
from models import Periodo

logger = logging.getLogger("usuarios")


def corregir_acento_submotivo(db_cl_usuarios: DatabaseGateway) -> None:
    """Tarea 'UPDATE' de "Find new records or for updating"
    (USUARIOS_0201 SSIS_CL_Retenciones.dtsx): corrige, en 'submotivo' y
    'submotivo2', el defecto preexistente 'BAJA SIN RETENCION' (sin tilde) ->
    'BAJA SIN RETENCIÓN'. En el .dtsx original eran 2 sentencias separadas
    por 'GO' dentro del mismo Execute SQL Task; se ejecutan aqui como 2
    scripts independientes (ver sql.py)."""
    try:
        db_cl_usuarios.execute_script(sql.RETENCIONES_CORRIGE_ACENTO_SUBMOTIVO)
        db_cl_usuarios.execute_script(sql.RETENCIONES_CORRIGE_ACENTO_SUBMOTIVO2)
    except Exception as exc:
        raise CargaError(f"Fallo la tarea 'UPDATE' (corregir_acento_submotivo): {exc}") from exc
    logger.info("BD_RETEN: tilde de 'BAJA SIN RETENCIÓN' corregida en submotivo/submotivo2.")


# ---------------------------------------------------------------------------
# USUARIOS_0300 ETL_INTENCIONES.dtsx -- Sequence "TABULANDO INTENCIONES".
#
# TEMP_01..TEMP_04 e INTENCIONES_TAB tienen origen y destino en la misma
# instancia SQL Server (CL_USUARIOS): se ejecutan como 'INSERT INTO ...
# SELECT ...' literales (sql.py), no como Origen+Destino OLE DB en pandas
# (ver README, "Notas de fidelidad").
# ---------------------------------------------------------------------------


def poblar_temp01_notas_limpias(db_cl_usuarios: DatabaseGateway, periodo: Periodo) -> None:
    """Data Flow 'TEMP_01': limpia CASE_NOTE via
    SERVICIOS_GENERALES.dbo.FUNC_CH_limpiacaracteresXML."""
    try:
        db_cl_usuarios.execute_script(sql.INTENCIONES_TEMP01_INSERT, params=(periodo.valor,))
    except Exception as exc:
        raise CargaError(f"Fallo el Data Flow 'TEMP_01': {exc}") from exc


def poblar_temp02_notas_divididas(db_cl_usuarios: DatabaseGateway) -> None:
    """Data Flow 'TEMP_02': envuelve cada nota separada por '*' en un
    elemento XML '<nota>'."""
    try:
        db_cl_usuarios.execute_script(sql.INTENCIONES_TEMP02_INSERT)
    except Exception as exc:
        raise CargaError(f"Fallo el Data Flow 'TEMP_02': {exc}") from exc


def poblar_temp03_notas_separadas(db_cl_usuarios: DatabaseGateway) -> None:
    """Data Flow 'TEMP_03': separa el XML de TEMP_02 en una fila por nota
    ('CROSS APPLY .nodes(''/nota'')')."""
    try:
        db_cl_usuarios.execute_script(sql.INTENCIONES_TEMP03_INSERT)
    except Exception as exc:
        raise CargaError(f"Fallo el Data Flow 'TEMP_03': {exc}") from exc


def poblar_temp04_notas_con_fecha_usuario(db_cl_usuarios: DatabaseGateway) -> None:
    """Data Flow 'TEMP_04': extrae fecha y usuario de cada nota via
    PATINDEX/SUBSTRING."""
    try:
        db_cl_usuarios.execute_script(sql.INTENCIONES_TEMP04_INSERT)
    except Exception as exc:
        raise CargaError(f"Fallo el Data Flow 'TEMP_04': {exc}") from exc


def poblar_intenciones_tab(db_cl_usuarios: DatabaseGateway) -> None:
    """Data Flow 'INTENCIONES_TAB': limpia 'Usuario' y calcula 'PERIODO'."""
    try:
        db_cl_usuarios.execute_script(sql.INTENCIONES_TAB_INSERT)
    except Exception as exc:
        raise CargaError(f"Fallo el Data Flow 'INTENCIONES_TAB': {exc}") from exc


# ---------------------------------------------------------------------------
# USUARIOS_0301 SSIS_CL_Item_amdocs.dtsx -- las 9 tareas 'UPDATE' que corren
# despues de la carga (todas contra CL_USUARIOS, en el orden exacto de las
# Precedence Constraints originales; 3 de ellas llaman UDFs de
# SERVICIOS_GENERALES no incluidas en el .dtsx, ejecutadas tal cual).
# ---------------------------------------------------------------------------


def actualizar_primer_usuario(db_cl_usuarios: DatabaseGateway, periodo: Periodo) -> None:
    """Tareas 'UPDATE - PRIMER USUARIO POR BASE INTENCION' (limpia a NULL) y
    'UPDATE - PRIMER USUARIO POR BASE INTENCION_' (join contra
    VIEW_INTENCIONES_TAB_PRIMER_USUARIO_RETENCIONES)."""
    try:
        db_cl_usuarios.execute_script(sql.ITEM_AMDOCS_UPDATE_PRIMER_USUARIO_NULL, params=(periodo.valor,))
        db_cl_usuarios.execute_script(sql.ITEM_AMDOCS_UPDATE_PRIMER_USUARIO_JOIN, params=(periodo.valor,))
    except Exception as exc:
        raise CargaError(f"Fallo 'UPDATE - PRIMER USUARIO POR BASE INTENCION': {exc}") from exc


def actualizar_fecha_inicio_calendario(db_cl_usuarios: DatabaseGateway, periodo: Periodo) -> None:
    """Tarea 'UPDATE - FECHA INICIO CALENDARIO'
    (SERVICIOS_GENERALES.dbo.FUNC_CH_FECHA_INICIO)."""
    try:
        db_cl_usuarios.execute_script(sql.ITEM_AMDOCS_UPDATE_FECHA_INICIO_CALENDARIO, params=(periodo.valor,))
    except Exception as exc:
        raise CargaError(f"Fallo 'UPDATE - FECHA INICIO CALENDARIO': {exc}") from exc


def actualizar_tiempo_atencion_habil(db_cl_usuarios: DatabaseGateway, periodo: Periodo) -> None:
    """Tareas 'UPDATE - TIEMPO DE ATENCION HABIL (MINUTOS)'
    (SERVICIOS_GENERALES.dbo.FUNC_CH_MINUTOS_VALIDOS_ENTRE_FECHAS), '...
    seteo' (pisa negativos a 0) y '... (dias horas)' (deriva horas/dias)."""
    try:
        db_cl_usuarios.execute_script(sql.ITEM_AMDOCS_UPDATE_TIEMPO_ATENCION_MINUTOS, params=(periodo.valor,))
        db_cl_usuarios.execute_script(sql.ITEM_AMDOCS_UPDATE_TIEMPO_ATENCION_MINUTOS_SETEO, params=(periodo.valor,))
        db_cl_usuarios.execute_script(sql.ITEM_AMDOCS_UPDATE_TIEMPO_ATENCION_DIAS_HORAS, params=(periodo.valor,))
    except Exception as exc:
        raise CargaError(f"Fallo 'UPDATE - TIEMPO DE ATENCION HABIL': {exc}") from exc


def actualizar_tiempo_atencion_calendario(db_cl_usuarios: DatabaseGateway, periodo: Periodo) -> None:
    """Tarea 'UPDATE - TIEMPO DE ATENCION CALENDARIO (DIAS)'
    (SERVICIOS_GENERALES.dbo.FUNC_CH_DIAS_LABORABLES)."""
    try:
        db_cl_usuarios.execute_script(sql.ITEM_AMDOCS_UPDATE_TIEMPO_ATENCION_CALENDARIO_DIAS, params=(periodo.valor,))
    except Exception as exc:
        raise CargaError(f"Fallo 'UPDATE - TIEMPO DE ATENCION CALENDARIO (DIAS)': {exc}") from exc


def actualizar_estado_atendido(db_cl_usuarios: DatabaseGateway, periodo: Periodo) -> None:
    """Tareas 'UPDATE - ESTADO ATENDIDO 2 DIAS' y '... 15 DIAS' (finales de
    USUARIOS_0301 SSIS_CL_Item_amdocs.dtsx)."""
    try:
        db_cl_usuarios.execute_script(sql.ITEM_AMDOCS_UPDATE_ESTADO_ATENDIDO_2_DIAS, params=(periodo.valor,))
        db_cl_usuarios.execute_script(sql.ITEM_AMDOCS_UPDATE_ESTADO_ATENDIDO_15_DIAS, params=(periodo.valor,))
    except Exception as exc:
        raise CargaError(f"Fallo 'UPDATE - ESTADO ATENDIDO': {exc}") from exc


def ejecutar_sp_retenciones_efectividad_asesor(db_cl_usuarios: DatabaseGateway) -> None:
    """Tarea 'SP_RETENCIONES_EFECTIVIDAD_ASESOR' (final de
    USUARIOS_0302 ETL_BASE_SAIP.dtsx). El procedimiento no forma parte del
    .dtsx; se ejecuta tal cual (ver README, "Notas de fidelidad")."""
    try:
        db_cl_usuarios.execute_script(sql.SAIP_EXEC_SP)
    except Exception as exc:
        raise CargaError(f"Fallo 'SP_RETENCIONES_EFECTIVIDAD_ASESOR': {exc}") from exc

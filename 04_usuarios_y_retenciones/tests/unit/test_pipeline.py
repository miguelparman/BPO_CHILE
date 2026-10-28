import pandas as pd
import pytest

import mappings
import sql
from exceptions import CargaError, PipelineError
from models import Periodo
from pipeline import UsuariosPipeline
from tests.unit.fakes import FakeDatabaseGateway, FakeSharePointCsvReader


def _build_pipeline(archivos_sharepoint: dict[str, pd.DataFrame] | None = None):
    db_cl_usuarios = FakeDatabaseGateway()
    sharepoint_reader = FakeSharePointCsvReader(archivos_sharepoint or {})
    pipeline = UsuariosPipeline(db_cl_usuarios=db_cl_usuarios, sharepoint_reader=sharepoint_reader)
    return pipeline, db_cl_usuarios


def _fila_bd_reten(**overrides) -> dict:
    fila = {
        "periodo": "202608",
        "rut": "123456785",
        "nomcli": "CLIENTE X",
        "segme": "MEDIANA",
        "nom_sm": "ASESOR X",
        "nom_sup": "SUPERVISOR X",
        "sub_segme": "SUB X",
        "tpo_serv": "FIJO",
        "tpo_prod": "BAF",
        "tpo_tecno": "FO",
        "q_parque": "1",
        "q_riesgo": "0",
        "q_baja_v": "0",
        "q_baja_p": "0",
        "q_baja_m": "0",
        "motivo": "MOTIVO SIN USO",
        "submotivo": "BAJA SIN RETENCION",
        "submotivo2": "",
        "canal_ing": "CALL",
        "subcan_ing": "IN",
        "canal_res": "CALL",
        "subcan_res": "OUT",
        "cargo_res": "AGENTE",
        "canal_hres": "CALL",
        "fecha_ultima_actualizacion": "2026-08-01 10:00:00",
        "cons_estados": '{"estado":"OK"}',
    }
    fila.update(overrides)
    return fila


def _fila_item_amdocs(**overrides) -> dict:
    fila = {
        "rut": "123456785",
        "case_idnum": "36110065",
        "type1": "TIPO1",
        "type2": "TIPO2",
        "sub_motivo": "SUBMOTIVO",
        "case_desc": "DESCRIPCION",
        "case_resol": "RESOLUCION",
        "case_optim": "2026-08-01 10:00:00",
        "agent_orig": "111",
        "agent_reso": "222",
        "canal_ing": "CALL",
        "subcan_ing": "IN",
        "case_cltim": "01-AUG-26:10.00.00.000 AM",
        "segmento": "MASIVO",
        "subtype": "SUBTIPO",
        "line_buss": "FIJA",
        "motivo": "MOTIVO",
        "servicio": "BAF",
        "cantidad": "1",
        "prod_type": "BAF",
        "ser_stat_r": "OK",
        "periodo": "202608",
        "tpo_serv": "FIJO",
        "rutcli": "12345678",
        "pqe_stb": "0",
        "pqe_baf": "1",
        "pqe_tv": "0",
        "pqe_voz": "0",
        "pqe_bam": "0",
        "tecno_stb": "",
        "tecno_baf": "FO",
        "tecno_tv": "",
        "tpo_t_stb": "",
        "tpo_t_baf": "CO",
        "tpo_t_tv": "",
        "origen": "WEB",
        "canal_res": "CALL",
        "subcan_res": "OUT",
        "cargo_res": "AGENTE",
        "canal_hres": "CALL",
    }
    fila.update(overrides)
    return fila


def _fila_generica(columnas, **overrides) -> dict:
    fila = {col: f"v_{col}" for col in columnas}
    fila.update(overrides)
    return fila


def _archivos_parque() -> dict[str, pd.DataFrame]:
    fijo = pd.DataFrame(
        [{"periodo": "202608", "segme": "Micro", "q_casos": "1", "tpo_prod": "BAF", "tecnologia": "FIBER", "rut": "123456785"}]
    )
    movil = pd.DataFrame(columns=["periodo", "segme", "tpo_prod", "rutcli"])
    marca = pd.DataFrame([{"rutcli": "12345678", "marca": "3"}])
    return {
        mappings.PARQUE_FIJO_ARCHIVO: fijo,
        mappings.PARQUE_MOVIL_ARCHIVO: movil,
        mappings.RUT_MARCA_CARTERA_ARCHIVO: marca,
    }


def _archivos_retenciones() -> dict[str, pd.DataFrame]:
    from extraccion import extractor

    return {
        mappings.RETENCIONES_BAJAS_FRAUDE_ARCHIVO: pd.DataFrame(
            [_fila_generica(extractor._BAJAS_FRAUDE_COLUMNAS, PERIODO="202608")]
        ),
        mappings.RETENCIONES_BAJAS_POR_ALTA_ARCHIVO: pd.DataFrame(
            [_fila_generica(extractor._BAJAS_POR_ALTA_COLUMNAS, PERIODO="202608")]
        ),
        mappings.RETENCIONES_BD_RETEN_ARCHIVO: pd.DataFrame([_fila_bd_reten()]),
    }


def _archivos_intenciones() -> dict[str, pd.DataFrame]:
    from extraccion import extractor

    return {
        mappings.INTENCIONES_BAJAS_FIJO_ARCHIVO: pd.DataFrame(
            [_fila_generica(extractor._BAJAS_FIJO_COLUMNAS, YEAR_MONTH="202608")]
        ),
        mappings.INTENCIONES_BAJAS_MOVIL_ARCHIVO: pd.DataFrame(
            [_fila_generica(extractor._BAJAS_MOVIL_COLUMNAS, PERIODO="202608")]
        ),
        mappings.INTENCIONES_V2_ARCHIVO: pd.DataFrame(
            [{"CASE_ID_NUMBER": "12345", "CASE_OPEN_TIME": "2026-08-01", "CASE_NOTE": "nota"}]
        ),
    }


def _archivos_item_amdocs() -> dict[str, pd.DataFrame]:
    return {mappings.ITEM_AMDOCS_ARCHIVO: pd.DataFrame([_fila_item_amdocs()])}


def _archivos_saip() -> dict[str, pd.DataFrame]:
    from extraccion import extractor

    # fec_saip_a posterior a 2022-01-01 -> pasa el filtro (ver
    # extractor.extraer_saip, comparacion de fechas real).
    fila = _fila_generica(extractor._SAIP_COLUMNAS_ORIGEN, fec_ingr="2020-01-15", fec_saip_a="25/01/2022", fec_saip_b="26/01/2022")
    return {mappings.SAIP_ARCHIVO: pd.DataFrame([fila])}


def test_ejecutar_parque_borra_luego_extrae_y_carga_en_ese_orden():
    pipeline, db_cl_usuarios = _build_pipeline(_archivos_parque())
    periodo = Periodo("202608")

    resultado = pipeline.ejecutar_parque(periodo)

    assert db_cl_usuarios.executed_scripts[0][0] == sql.PARQUE_DELETE
    assert mappings.PARQUE_TABLE in db_cl_usuarios.inserted
    assert resultado.nombre == "parque"
    # 202608 (dato real) + 202609 (proyeccion 'ultimo_parque').
    assert resultado.filas_por_paso == {"PARQUE": 2}


def test_ejecutar_parque_propaga_fallo_del_delete_como_pipelineerror():
    pipeline, db_cl_usuarios = _build_pipeline(_archivos_parque())

    def _falla(*args, **kwargs):
        raise CargaError("fallo simulado")

    db_cl_usuarios.execute_script = _falla  # type: ignore[method-assign]

    with pytest.raises(PipelineError) as exc_info:
        pipeline.ejecutar_parque(Periodo("202608"))

    assert exc_info.value.pipeline == "parque"
    assert isinstance(exc_info.value.causa, CargaError)
    # No debe haber llegado a cargar.
    assert mappings.PARQUE_TABLE not in db_cl_usuarios.inserted


def test_ejecutar_retenciones_corre_las_3_sequences_en_orden_y_corrige_acento_al_final():
    pipeline, db_cl_usuarios = _build_pipeline(_archivos_retenciones())

    resultado = pipeline.ejecutar_retenciones(Periodo("202608"))

    scripts_cl_usuarios = [s for s, _ in db_cl_usuarios.executed_scripts]
    assert scripts_cl_usuarios == [
        sql.RETENCIONES_BAJAS_FRAUDE_DELETE,
        sql.RETENCIONES_BAJAS_POR_ALTA_DELETE,
        sql.RETENCIONES_BD_RETEN_DELETE,
        sql.RETENCIONES_CORRIGE_ACENTO_SUBMOTIVO,
        sql.RETENCIONES_CORRIGE_ACENTO_SUBMOTIVO2,
    ]
    assert mappings.RETENCIONES_BAJAS_FRAUDE_TABLE in db_cl_usuarios.inserted
    assert mappings.RETENCIONES_BAJAS_POR_ALTA_TABLE in db_cl_usuarios.inserted
    assert mappings.RETENCIONES_BD_RETEN_TABLE in db_cl_usuarios.inserted
    assert resultado.nombre == "retenciones"
    assert resultado.filas_por_paso == {
        "TBL_SERVCH_BAJAS_FRAUDE": 1,
        "TBL_SERVCH_BAJAS_POR_ALTA_FO": 1,
        "BD_RETEN": 1,
    }


def test_ejecutar_intenciones_corre_los_3_contenedores_en_orden():
    pipeline, db_cl_usuarios = _build_pipeline(_archivos_intenciones())

    resultado = pipeline.ejecutar_intenciones(Periodo("202608"))

    assert db_cl_usuarios.executed_scripts == [
        (sql.INTENCIONES_DELETE_BAJAS_FIJO, ("202608",)),
        (sql.INTENCIONES_DELETE_BAJAS_MOVIL, ("202608",)),
        (sql.INTENCIONES_TBL_DELETE, ("202608",)),
        (sql.INTENCIONES_TEMP01_INSERT, ("202608",)),
        (sql.INTENCIONES_TEMP02_INSERT, ()),
        (sql.INTENCIONES_TEMP03_INSERT, ()),
        (sql.INTENCIONES_TEMP04_INSERT, ()),
        (sql.INTENCIONES_TAB_DELETE, ("202608",)),
        (sql.INTENCIONES_TAB_INSERT, ()),
    ]
    assert db_cl_usuarios.truncated_tables == [
        mappings.INTENCIONES_TEMP01_TABLE,
        mappings.INTENCIONES_TEMP02_TABLE,
        mappings.INTENCIONES_TEMP03_TABLE,
        mappings.INTENCIONES_TEMP04_TABLE,
    ]
    assert mappings.INTENCIONES_BAJAS_FIJO_TABLE in db_cl_usuarios.inserted
    assert mappings.INTENCIONES_BAJAS_MOVIL_TABLE in db_cl_usuarios.inserted
    assert mappings.INTENCIONES_TABLE in db_cl_usuarios.inserted_ignorando_errores
    assert resultado.nombre == "intenciones"
    assert resultado.filas_por_paso == {
        "TBL_CH_BAJAS_FIJO": 1,
        "TBL_CH_BAJAS_MOVIL": 1,
        "INTENCIONES": 1,
    }


def test_ejecutar_item_amdocs_carga_y_luego_corre_los_9_update_en_orden():
    pipeline, db_cl_usuarios = _build_pipeline(_archivos_item_amdocs())

    resultado = pipeline.ejecutar_item_amdocs(Periodo("202608"))

    assert db_cl_usuarios.executed_scripts == [
        (sql.ITEM_AMDOCS_DELETE, ("202608",)),
        (sql.ITEM_AMDOCS_UPDATE_PRIMER_USUARIO_NULL, ("202608",)),
        (sql.ITEM_AMDOCS_UPDATE_PRIMER_USUARIO_JOIN, ("202608",)),
        (sql.ITEM_AMDOCS_UPDATE_FECHA_INICIO_CALENDARIO, ("202608",)),
        (sql.ITEM_AMDOCS_UPDATE_TIEMPO_ATENCION_MINUTOS, ("202608",)),
        (sql.ITEM_AMDOCS_UPDATE_TIEMPO_ATENCION_MINUTOS_SETEO, ("202608",)),
        (sql.ITEM_AMDOCS_UPDATE_TIEMPO_ATENCION_DIAS_HORAS, ("202608",)),
        (sql.ITEM_AMDOCS_UPDATE_TIEMPO_ATENCION_CALENDARIO_DIAS, ("202608",)),
        (sql.ITEM_AMDOCS_UPDATE_ESTADO_ATENDIDO_2_DIAS, ("202608",)),
        (sql.ITEM_AMDOCS_UPDATE_ESTADO_ATENDIDO_15_DIAS, ("202608",)),
    ]
    assert mappings.ITEM_AMDOCS_TABLE in db_cl_usuarios.inserted
    assert resultado.nombre == "item_amdocs"
    assert resultado.filas_por_paso == {"INTEN_AMDOCS": 1}


def test_ejecutar_saip_trunca_luego_extrae_carga_y_ejecuta_el_sp():
    pipeline, db_cl_usuarios = _build_pipeline(_archivos_saip())

    resultado = pipeline.ejecutar_saip()

    assert db_cl_usuarios.truncated_tables == [mappings.SAIP_TABLE]
    assert mappings.SAIP_TABLE in db_cl_usuarios.inserted
    assert db_cl_usuarios.executed_scripts == [(sql.SAIP_EXEC_SP, ())]
    assert resultado.nombre == "saip"
    assert resultado.filas_por_paso == {"BASE_SAIP": 1}


def test_ejecutar_todo_corre_los_5_paquetes_en_orden():
    archivos = {
        **_archivos_parque(),
        **_archivos_retenciones(),
        **_archivos_intenciones(),
        **_archivos_item_amdocs(),
        **_archivos_saip(),
    }
    pipeline, db_cl_usuarios = _build_pipeline(archivos)
    periodo = Periodo("202608")

    resultado = pipeline.ejecutar_todo(periodo)

    assert resultado.periodo == periodo
    assert [r.nombre for r in resultado.resultados] == [
        "parque",
        "retenciones",
        "intenciones",
        "item_amdocs",
        "saip",
    ]

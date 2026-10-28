import sql
from models import Periodo
from tests.unit.fakes import FakeDatabaseGateway
from transformacion import transformer


def test_corregir_acento_submotivo_ejecuta_las_2_sentencias_en_orden():
    db = FakeDatabaseGateway()

    transformer.corregir_acento_submotivo(db)

    scripts = [s for s, _ in db.executed_scripts]
    assert scripts == [
        sql.RETENCIONES_CORRIGE_ACENTO_SUBMOTIVO,
        sql.RETENCIONES_CORRIGE_ACENTO_SUBMOTIVO2,
    ]


def test_poblar_temp01_notas_limpias_ejecuta_el_insert_con_periodo():
    db = FakeDatabaseGateway()
    transformer.poblar_temp01_notas_limpias(db, Periodo("202608"))
    assert db.executed_scripts[0] == (sql.INTENCIONES_TEMP01_INSERT, ("202608",))


def test_poblar_temp02_a_temp04_y_tab_ejecutan_su_insert_sin_parametros():
    db = FakeDatabaseGateway()
    transformer.poblar_temp02_notas_divididas(db)
    transformer.poblar_temp03_notas_separadas(db)
    transformer.poblar_temp04_notas_con_fecha_usuario(db)
    transformer.poblar_intenciones_tab(db)

    assert db.executed_scripts == [
        (sql.INTENCIONES_TEMP02_INSERT, ()),
        (sql.INTENCIONES_TEMP03_INSERT, ()),
        (sql.INTENCIONES_TEMP04_INSERT, ()),
        (sql.INTENCIONES_TAB_INSERT, ()),
    ]


def test_actualizar_primer_usuario_ejecuta_las_2_sentencias_con_periodo():
    db = FakeDatabaseGateway()
    transformer.actualizar_primer_usuario(db, Periodo("202608"))
    assert db.executed_scripts == [
        (sql.ITEM_AMDOCS_UPDATE_PRIMER_USUARIO_NULL, ("202608",)),
        (sql.ITEM_AMDOCS_UPDATE_PRIMER_USUARIO_JOIN, ("202608",)),
    ]


def test_actualizar_fecha_inicio_calendario_ejecuta_el_update_con_periodo():
    db = FakeDatabaseGateway()
    transformer.actualizar_fecha_inicio_calendario(db, Periodo("202608"))
    assert db.executed_scripts == [(sql.ITEM_AMDOCS_UPDATE_FECHA_INICIO_CALENDARIO, ("202608",))]


def test_actualizar_tiempo_atencion_habil_ejecuta_las_3_sentencias_en_orden():
    db = FakeDatabaseGateway()
    transformer.actualizar_tiempo_atencion_habil(db, Periodo("202608"))
    assert db.executed_scripts == [
        (sql.ITEM_AMDOCS_UPDATE_TIEMPO_ATENCION_MINUTOS, ("202608",)),
        (sql.ITEM_AMDOCS_UPDATE_TIEMPO_ATENCION_MINUTOS_SETEO, ("202608",)),
        (sql.ITEM_AMDOCS_UPDATE_TIEMPO_ATENCION_DIAS_HORAS, ("202608",)),
    ]


def test_actualizar_tiempo_atencion_calendario_ejecuta_el_update_con_periodo():
    db = FakeDatabaseGateway()
    transformer.actualizar_tiempo_atencion_calendario(db, Periodo("202608"))
    assert db.executed_scripts == [(sql.ITEM_AMDOCS_UPDATE_TIEMPO_ATENCION_CALENDARIO_DIAS, ("202608",))]


def test_actualizar_estado_atendido_ejecuta_las_2_sentencias_en_orden():
    db = FakeDatabaseGateway()
    transformer.actualizar_estado_atendido(db, Periodo("202608"))
    assert db.executed_scripts == [
        (sql.ITEM_AMDOCS_UPDATE_ESTADO_ATENDIDO_2_DIAS, ("202608",)),
        (sql.ITEM_AMDOCS_UPDATE_ESTADO_ATENDIDO_15_DIAS, ("202608",)),
    ]


def test_ejecutar_sp_retenciones_efectividad_asesor_ejecuta_el_exec():
    db = FakeDatabaseGateway()
    transformer.ejecutar_sp_retenciones_efectividad_asesor(db)
    assert db.executed_scripts == [(sql.SAIP_EXEC_SP, ())]

import pandas as pd

import mappings
import sql
from carga import loader
from models import Periodo
from tests.unit.fakes import FakeDatabaseGateway


def test_eliminar_parque_ejecuta_el_delete_con_periodo_como_parametro():
    db = FakeDatabaseGateway()
    loader.eliminar_parque(db, Periodo("202608"))

    consulta, params = db.executed_scripts[0]
    assert consulta == sql.PARQUE_DELETE
    assert params == ("202608",)


def test_cargar_parque_inserta_en_parquetch():
    db = FakeDatabaseGateway()
    df = pd.DataFrame([{"periodo": 202608, "segme": "MICRO", "pqe": 1}])

    filas = loader.cargar_parque(db, df)

    assert filas == 1
    pd.testing.assert_frame_equal(db.inserted[mappings.PARQUE_TABLE], df)


def test_eliminar_bajas_fraude_ejecuta_el_delete_con_periodo():
    db = FakeDatabaseGateway()
    loader.eliminar_bajas_fraude(db, Periodo("202608"))
    assert db.executed_scripts[0] == (sql.RETENCIONES_BAJAS_FRAUDE_DELETE, ("202608",))


def test_cargar_bajas_fraude_inserta_en_tbl_servch_bajas_fraude():
    db = FakeDatabaseGateway()
    df = pd.DataFrame([{"PERIODO": 202608}])
    assert loader.cargar_bajas_fraude(db, df) == 1
    pd.testing.assert_frame_equal(db.inserted[mappings.RETENCIONES_BAJAS_FRAUDE_TABLE], df)


def test_eliminar_bajas_por_alta_ejecuta_el_delete_local_con_periodo():
    db = FakeDatabaseGateway()
    loader.eliminar_bajas_por_alta(db, Periodo("202608"))
    assert db.executed_scripts[0] == (sql.RETENCIONES_BAJAS_POR_ALTA_DELETE, ("202608",))


def test_cargar_bajas_por_alta_inserta_en_tbl_servch_bajas_por_alta_fo():
    db = FakeDatabaseGateway()
    df = pd.DataFrame([{"PERIODO": 202608}])
    assert loader.cargar_bajas_por_alta(db, df) == 1
    pd.testing.assert_frame_equal(db.inserted[mappings.RETENCIONES_BAJAS_POR_ALTA_TABLE], df)


def test_eliminar_bd_reten_ejecuta_el_delete_bd_reten_con_periodo():
    db = FakeDatabaseGateway()
    loader.eliminar_bd_reten(db, Periodo("202608"))
    assert db.executed_scripts[0] == (sql.RETENCIONES_BD_RETEN_DELETE, ("202608",))


def test_cargar_bd_reten_inserta_en_bd_reten():
    db = FakeDatabaseGateway()
    df = pd.DataFrame([{"periodo": 202608}])
    assert loader.cargar_bd_reten(db, df) == 1
    pd.testing.assert_frame_equal(db.inserted[mappings.RETENCIONES_BD_RETEN_TABLE], df)


def test_eliminar_bajas_fijo_ejecuta_el_delete_fijo_con_periodo():
    db = FakeDatabaseGateway()
    loader.eliminar_bajas_fijo(db, Periodo("202608"))
    assert db.executed_scripts[0] == (sql.INTENCIONES_DELETE_BAJAS_FIJO, ("202608",))


def test_cargar_bajas_fijo_inserta_en_tbl_ch_bajas_fijo():
    db = FakeDatabaseGateway()
    df = pd.DataFrame([{"YEAR_MONTH": 202608}])
    assert loader.cargar_bajas_fijo(db, df) == 1
    pd.testing.assert_frame_equal(db.inserted[mappings.INTENCIONES_BAJAS_FIJO_TABLE], df)


def test_eliminar_bajas_movil_ejecuta_el_delete_movil_con_periodo():
    db = FakeDatabaseGateway()
    loader.eliminar_bajas_movil(db, Periodo("202608"))
    assert db.executed_scripts[0] == (sql.INTENCIONES_DELETE_BAJAS_MOVIL, ("202608",))


def test_cargar_bajas_movil_inserta_en_tbl_ch_bajas_movil():
    db = FakeDatabaseGateway()
    df = pd.DataFrame([{"PERIODO": 202608}])
    assert loader.cargar_bajas_movil(db, df) == 1
    pd.testing.assert_frame_equal(db.inserted[mappings.INTENCIONES_BAJAS_MOVIL_TABLE], df)


def test_eliminar_intenciones_ejecuta_el_delete_con_periodo():
    db = FakeDatabaseGateway()
    loader.eliminar_intenciones(db, Periodo("202608"))
    assert db.executed_scripts[0] == (sql.INTENCIONES_TBL_DELETE, ("202608",))


def test_cargar_intenciones_local_usa_bulk_insert_ignorando_errores():
    db = FakeDatabaseGateway()
    df = pd.DataFrame([{"CASE_ID_NUMBER": "12345"}])
    assert loader.cargar_intenciones_local(db, df) == 1
    pd.testing.assert_frame_equal(db.inserted_ignorando_errores[mappings.INTENCIONES_TABLE], df)
    assert mappings.INTENCIONES_TABLE not in db.inserted


def test_truncar_temp01_a_temp04():
    db = FakeDatabaseGateway()
    loader.truncar_temp01(db)
    loader.truncar_temp02(db)
    loader.truncar_temp03(db)
    loader.truncar_temp04(db)
    assert db.truncated_tables == [
        mappings.INTENCIONES_TEMP01_TABLE,
        mappings.INTENCIONES_TEMP02_TABLE,
        mappings.INTENCIONES_TEMP03_TABLE,
        mappings.INTENCIONES_TEMP04_TABLE,
    ]


def test_eliminar_intenciones_tab_ejecuta_el_delete_con_periodo():
    db = FakeDatabaseGateway()
    loader.eliminar_intenciones_tab(db, Periodo("202608"))
    assert db.executed_scripts[0] == (sql.INTENCIONES_TAB_DELETE, ("202608",))


def test_eliminar_item_amdocs_ejecuta_el_delete_con_periodo():
    db = FakeDatabaseGateway()
    loader.eliminar_item_amdocs(db, Periodo("202608"))
    assert db.executed_scripts[0] == (sql.ITEM_AMDOCS_DELETE, ("202608",))


def test_cargar_item_amdocs_inserta_en_inten_amdocs():
    db = FakeDatabaseGateway()
    df = pd.DataFrame([{"periodo": 202608, "case_idnum": 36110065}])
    assert loader.cargar_item_amdocs(db, df) == 1
    pd.testing.assert_frame_equal(db.inserted[mappings.ITEM_AMDOCS_TABLE], df)


def test_truncar_saip_trunca_base_saip():
    db = FakeDatabaseGateway()
    loader.truncar_saip(db)
    assert db.truncated_tables == [mappings.SAIP_TABLE]


def test_cargar_saip_inserta_en_base_saip():
    db = FakeDatabaseGateway()
    df = pd.DataFrame([{"rut_ej": "1"}])
    assert loader.cargar_saip(db, df) == 1
    pd.testing.assert_frame_equal(db.inserted[mappings.SAIP_TABLE], df)

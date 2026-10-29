from datetime import date

import pytest

import mappings
from carga.historico import HistoricoLoader
from carga.loader import PlacesLoader, anchos_parametros, insert_sql
from exceptions import CargaError
from logs_proceso import LogsProceso
from tests.unit.fakes import FakeDb


def test_insert_usa_columnas_destino_en_orden():
    assert insert_sql() == (
        "INSERT INTO [dbo].[TBL_PLACES] ([ID], [Etiqueta], [Plataforma], [Rut], [Asesor], [DNI]) "
        "VALUES (?, ?, ?, ?, ?, ?)"
    )
    assert anchos_parametros() == [8, 30, 30, 50, 100, 15]


def test_carga_usa_sql_literal_y_cuenta_filas():
    db = FakeDb()
    filas = [("1", "e", "p", "r", "a", "d"), (None, None, None, None, None, None)]
    r = PlacesLoader(db).cargar(filas)
    llamada = db.recargas[0]
    assert llamada["truncate"] == mappings.SQL_TRUNCATE and llamada["limpia"] == mappings.SQL_LIMPIA
    assert (r.insertadas, r.borradas_nulos, r.finales) == (2, 1, 1)


def test_carga_propaga_carga_error():
    with pytest.raises(CargaError):
        PlacesLoader(FakeDb(falla=CargaError("boom"))).cargar([])


def test_historico_elimina_e_inserta_con_la_fecha_actual_en_una_transaccion():
    db = FakeDb()
    r = HistoricoLoader(db, hoy=lambda: date(2026, 10, 29)).cargar()
    assert db.transacciones == [
        [(mappings.SQL_HISTORICO_ELIMINA, (date(2026, 10, 29),)), (mappings.SQL_HISTORICO_INSERTA, (date(2026, 10, 29),))]
    ]
    assert r.fecha == date(2026, 10, 29)


def test_logs_inicio_y_fin():
    db = FakeDb()
    logs = LogsProceso(db)
    logs.inicio()
    logs.fin()
    assert [t[0][0] for t in db.transacciones] == [mappings.SQL_LOG_INICIO, mappings.SQL_LOG_FIN]

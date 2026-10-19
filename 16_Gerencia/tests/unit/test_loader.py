from datetime import date

import pytest

import mappings
from carga.loader import VolumetriaLoader, insert_sql, tipos_parametros
from db import PARAM_FECHA, PARAM_TEXTO, DatabaseGateway, _input_size
from exceptions import CargaError
from tests.unit.fakes import FakeDb


def test_insert_sql():
    assert insert_sql(mappings.T_ATIENDO) == (
        "INSERT INTO [dbo].[TBL_VOLUMETRIA_T_ATIENDO] ([Número del caso], [Fecha], [Causa Raiz], [Motivo C/R], "
        "[Derivado por], [Cargo], [SM Quiebre], [Coordinador Quiebre]) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    )


def test_tipos_parametros():
    assert tipos_parametros(mappings.ESCALAMIENTO) == [
        (PARAM_TEXTO, 15), (PARAM_FECHA, None), (PARAM_TEXTO, 30), (PARAM_TEXTO, 100),
        (PARAM_TEXTO, 50), (PARAM_TEXTO, 255), (PARAM_TEXTO, 50), (PARAM_TEXTO, 50),
    ]


def test_cargar_truncate_insert_delete_literal():
    db = FakeDb()
    filas = [("1", date(2026, 1, 1), "c", "m", "d", "g", "s", "k"), (None,) * 8]
    resultado = VolumetriaLoader(db).cargar(mappings.GERENCIA, filas)
    llamada = db.llamadas[0]
    assert llamada["truncate"] == mappings.GERENCIA.sql_truncate
    assert llamada["delete"] == mappings.GERENCIA.sql_delete
    assert llamada["filas"] == filas  # se insertan todas; el DELETE borra las de caso NULL
    assert (resultado.insertadas, resultado.borradas_nulos, resultado.finales) == (2, 1, 1)


def test_error_de_carga_se_propaga():
    with pytest.raises(CargaError):
        VolumetriaLoader(FakeDb(falla=CargaError("x"))).cargar(mappings.GERENCIA, [])


class _Cursor:
    def __init__(self, log, falla_en=None):
        self.log, self.falla_en, self.rowcount = log, falla_en, 0
        self.fast_executemany = False

    def execute(self, sql, *a):
        self.log.append(("execute", sql))
        if self.falla_en and self.falla_en in sql:
            raise RuntimeError("boom")
        self.rowcount = 3
        return self

    def fetchall(self):
        return [(1,)]

    def setinputsizes(self, tamanos):
        self.log.append(("sizes", tamanos))

    def executemany(self, sql, lote):
        self.log.append(("executemany", len(lote)))

    def close(self):
        pass


class _Conn:
    def __init__(self, falla_en=None):
        self.log, self.falla_en = [], falla_en

    def cursor(self):
        return _Cursor(self.log, self.falla_en)

    def commit(self):
        self.log.append(("commit",))

    def rollback(self):
        self.log.append(("rollback",))

    def close(self):
        pass


def test_gateway_una_transaccion_y_lotes():
    conn = _Conn()
    gw = DatabaseGateway(lambda: conn, batch_size=2)
    insertadas, borradas = gw.recargar_tabla("TRUNCATE T", "INSERT ?", [(1,)] * 5, [(PARAM_TEXTO, 15)], "DELETE T")
    pasos = [p[0] if p[0] != "execute" else p[1] for p in conn.log]
    assert pasos == ["TRUNCATE T", "sizes", "executemany", "executemany", "executemany", "DELETE T", "commit"]
    assert (insertadas, borradas) == (5, 3)


def test_gateway_rollback_si_falla_el_delete():
    conn = _Conn(falla_en="DELETE")
    with pytest.raises(CargaError, match="rollback"):
        DatabaseGateway(lambda: conn).recargar_tabla("TRUNCATE T", "INSERT ?", [(1,)], [(PARAM_TEXTO, 1)], "DELETE T")
    assert ("rollback",) in conn.log and ("commit",) not in conn.log


def test_input_sizes():
    import pyodbc

    assert _input_size(PARAM_FECHA, None) == (pyodbc.SQL_TYPE_DATE, 0, 0)
    assert _input_size(PARAM_TEXTO, 30) == (pyodbc.SQL_WVARCHAR, 30, 0)

"""db.py (batches GO, buffers, reintento de conexion) y sql.py."""

import pyodbc
import pytest

import mappings
import sql
from config import DbSettings
from db import crear_conexion, dividir_en_batches, tamanos_parametros


def test_dividir_en_batches_por_go():
    assert dividir_en_batches("SELECT 1\nGO\nSELECT 2\n  go  -- fin\n") == ["SELECT 1", "SELECT 2"]
    assert dividir_en_batches("SELECT 'GOOD'") == ["SELECT 'GOOD'"]


def test_scripts_del_dtsx_no_tienen_go():
    for script in (sql.LOG_INICIO, sql.SP_EPA_ISN_CHILE, sql.SP_PROCESO_ENCUESTAS_MEDALLIA, sql.LOG_FIN):
        assert len(dividir_en_batches(script)) == 1


def test_tamanos_parametros_por_esquema():
    tam = tamanos_parametros(["SurveyID", "loginid", "verbatim"], mappings.WSP.esquema)
    assert tam[0] is None
    assert tam[1] == (pyodbc.SQL_WVARCHAR, 15, 0)
    assert tam[2] == (pyodbc.SQL_WVARCHAR, 0, 0)  # nvarchar(max)


def test_delete_ventana_y_anteriores():
    assert sql.delete_ventana(mappings.WSP, 2) == (
        "DELETE FROM [dbo].[TBL_ENCUESTAS_WSP_MEDALLIA] WHERE [Periodo] IN (?, ?)"
    )
    assert "TRY_CAST([periodo_evento] AS int) < ?" in sql.delete_anteriores(mappings.ENCUESTA)


def _settings():
    return DbSettings(server="s", database="d", user="u", password="p")


def test_crear_conexion_reintenta_una_vez_como_el_connection_manager():
    intentos, esperas = [], []

    class Conn:
        timeout = None

    def conectar(cs, autocommit):
        intentos.append(cs)
        if len(intentos) == 1:
            raise pyodbc.InterfaceError("28000", "login fallido")
        return Conn()

    conn = crear_conexion(_settings(), dormir=esperas.append, conectar=conectar)
    assert len(intentos) == 2 and esperas == [5] and conn.timeout == 0
    assert "PWD=p" in intentos[0] and "DATABASE=d" in intentos[0]


def test_crear_conexion_falla_tras_el_reintento():
    def conectar(cs, autocommit):
        raise pyodbc.InterfaceError("28000", "login fallido")

    with pytest.raises(pyodbc.InterfaceError):
        crear_conexion(_settings(), dormir=lambda s: None, conectar=conectar)

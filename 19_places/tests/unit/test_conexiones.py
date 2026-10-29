import pytest

from conexiones import Verificacion, validar_conexiones, verificaciones_para
from config import DbSettings, GraphSettings
from exceptions import ConexionError

DB = DbSettings("srv", "CL_DATA", "u", "p")
SP = GraphSettings("t", "c", "s", "h", "/sites/R", "Data Reporting")


def test_todas_ok_no_espera():
    esperas = []
    validar_conexiones([Verificacion("a", lambda: None)], 3, 300, esperar=esperas.append)
    assert esperas == []


def test_reintenta_solo_las_fallidas_y_se_recupera():
    intentos = {"b": 0, "a": 0}

    def a():
        intentos["a"] += 1

    def b():
        intentos["b"] += 1
        if intentos["b"] < 3:
            raise RuntimeError("caido")

    esperas = []
    validar_conexiones([Verificacion("a", a), Verificacion("b", b)], 3, 300, esperar=esperas.append)
    assert intentos == {"a": 1, "b": 3} and esperas == [300, 300]


def test_sin_conexion_tras_reintentos_levanta_error_y_no_ejecuta_nada():
    esperas = []

    def cae():
        raise RuntimeError("sin red")

    with pytest.raises(ConexionError, match="No se ejecuto ninguna etapa"):
        validar_conexiones([Verificacion("SQL", cae)], 3, 300, esperar=esperas.append)
    assert len(esperas) == 3


def test_verificaciones_segun_modo():
    assert len(verificaciones_para(True, True, DB, SP)) == 2  # SQL + Graph
    assert [v.nombre for v in verificaciones_para(True, False, DB, SP)][0].startswith("Microsoft Graph")
    assert verificaciones_para(False, False, DB, SP) == []
    assert verificaciones_para(False, True, DB, SP)[0].nombre.startswith("SQL Server CL_DATA")

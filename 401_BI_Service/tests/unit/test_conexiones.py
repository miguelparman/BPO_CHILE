import pytest

from conexiones import Verificacion, validar_conexiones
from exceptions import ConexionError


def test_reintenta_solo_las_fallidas_y_luego_pasa():
    intentos = {"a": 0, "b": 0}

    def falla_una_vez():
        intentos["b"] += 1
        if intentos["b"] == 1:
            raise RuntimeError("caida")

    def ok():
        intentos["a"] += 1

    esperas = []
    validar_conexiones([Verificacion("a", ok), Verificacion("b", falla_una_vez)], 3, 300, esperas.append)
    assert intentos == {"a": 1, "b": 2}
    assert esperas == [300]


def test_agota_reintentos_y_levanta_conexionerror():
    def falla():
        raise RuntimeError("caida")

    esperas = []
    with pytest.raises(ConexionError):
        validar_conexiones([Verificacion("pbi", falla)], 3, 300, esperas.append)
    assert esperas == [300, 300, 300]

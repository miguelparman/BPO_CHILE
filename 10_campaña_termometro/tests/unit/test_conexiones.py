import pytest

from conexiones import ConexionError, Verificacion, validar_conexiones


def _falla_n_veces(n: int):
    llamadas = {"n": 0}

    def probar():
        llamadas["n"] += 1
        if llamadas["n"] <= n:
            raise OSError("Login timeout expired")

    return probar, llamadas


def test_todo_ok_no_espera():
    esperas = []
    validar_conexiones([Verificacion("sql", lambda: None)], reintentos=3, espera_s=300, esperar=esperas.append)
    assert esperas == []


def test_reintenta_solo_las_fallidas_y_se_recupera():
    sql, llamadas_sql = _falla_n_veces(2)
    ok, llamadas_ok = _falla_n_veces(0)
    esperas = []
    validar_conexiones(
        [Verificacion("sql", sql), Verificacion("sharepoint", ok)], reintentos=3, espera_s=300, esperar=esperas.append
    )
    assert esperas == [300, 300]
    assert llamadas_sql["n"] == 3
    assert llamadas_ok["n"] == 1


def test_termina_tras_el_ultimo_reintento():
    sql, llamadas = _falla_n_veces(99)
    esperas = []
    with pytest.raises(ConexionError, match="sql"):
        validar_conexiones([Verificacion("sql", sql)], reintentos=3, espera_s=300, esperar=esperas.append)
    assert llamadas["n"] == 4  # intento inicial + 3 reintentos
    assert esperas == [300, 300, 300]  # no espera después del último

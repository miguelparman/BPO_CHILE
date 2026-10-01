import pandas as pd
import pytest

import mappings
from exceptions import ValidacionError
from extraccion.extractor import parsear_archivo_plano
from tests.unit.fakes import csv_bytes, fila_csv
from transformacion.transformer import transformar
from validacion import validator


def _validar_archivo(*filas):
    a = parsear_archivo_plano(csv_bytes(*filas))
    validator.validar_archivo(a.cabecera, a.filas)
    return a


def test_archivo_valido():
    _validar_archivo(fila_csv())


def test_cabecera_distinta():
    a = parsear_archivo_plano(csv_bytes(fila_csv()))
    cabecera = list(a.cabecera)
    cabecera[1], cabecera[2] = cabecera[2], cabecera[1]
    with pytest.raises(ValidacionError, match="cabecera"):
        validator.validar_archivo(cabecera, a.filas)


def test_sin_filas():
    with pytest.raises(ValidacionError, match="no tiene filas"):
        _validar_archivo()


def test_fila_corta():
    with pytest.raises(ValidacionError, match="menos de 45"):
        _validar_archivo(fila_csv(), "2026;9;23")


def test_valor_de_mas_de_100_caracteres():
    with pytest.raises(ValidacionError, match="DT_STR\\(100\\)"):
        _validar_archivo(fila_csv(nombre="x" * 101))
    _validar_archivo(fila_csv(nombre="x" * 100))


@pytest.mark.parametrize("valor, ok", [("9", True), (" 9 ", True), ("-1", True), ("32767", True), ("32768", False), ("9a", False), ("", False)])
def test_cast_dt_i2(valor, ok):
    if ok:
        validator.cast_dt_i2(valor)
    else:
        with pytest.raises(ValueError):
            validator.cast_dt_i2(valor)


def test_validar_casts_mes_no_numerico():
    df = parsear_archivo_plano(csv_bytes(fila_csv(mes="SEP"))).a_dataframe()
    with pytest.raises(ValidacionError, match="DT_I2"):
        validator.validar_casts(df)


def test_validar_casts_acepta_null():
    df = parsear_archivo_plano(csv_bytes(fila_csv(mes=""))).a_dataframe()
    validator.validar_casts(df)


def test_conversion_a_dt_str_50():
    df = parsear_archivo_plano(csv_bytes(fila_csv(nombre="x" * 51))).a_dataframe()
    with pytest.raises(ValidacionError, match="DT_STR\\(50\\)"):
        validator.validar_conversion(transformar(df))
    df_ok = parsear_archivo_plano(csv_bytes(fila_csv(nombre="x" * 50))).a_dataframe()
    validator.validar_conversion(transformar(df_ok))


def test_fecha_ansi_de_mas_de_50_caracteres_falla():
    df = parsear_archivo_plano(csv_bytes(fila_csv(anio="2" * 48))).a_dataframe()
    with pytest.raises(ValidacionError, match="FECHA ANSI"):
        validator.validar_conversion(transformar(df))


def test_esquema_destino_ok_y_columna_ampliada():
    esquema = dict(mappings.ESQUEMA_DESTINO)
    validator.validar_esquema_destino(esquema)
    esquema["AGENT_NOMBRE"] = ("varchar", 100)  # ampliar la columna es valido
    validator.validar_esquema_destino(esquema)


@pytest.mark.parametrize(
    "cambio, mensaje",
    [
        (lambda e: e.pop("HORA"), "falta \\[HORA\\]"),
        (lambda e: e.__setitem__("TMO", ("int", None)), "es int"),
        (lambda e: e.__setitem__("PCRC", ("varchar", 30)), "varchar\\(30\\)"),
        (lambda e: e.pop("DNI"), "falta \\[DNI\\]"),
    ],
)
def test_esquema_destino_invalido(cambio, mensaje):
    esquema = dict(mappings.ESQUEMA_DESTINO)
    cambio(esquema)
    with pytest.raises(ValidacionError, match=mensaje):
        validator.validar_esquema_destino(esquema)


def test_tabla_inexistente():
    with pytest.raises(ValidacionError, match="No existe"):
        validator.validar_esquema_destino({})

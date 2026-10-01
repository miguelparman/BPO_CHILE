import pytest

import mappings
from extraccion.extractor import parsear_archivo_plano
from tests.unit.fakes import csv_bytes, fila_csv
from transformacion.transformer import fecha_ansi, rellenar_dia_mes, rellenar_intervalo, transformar


@pytest.mark.parametrize(
    "valor, esperado",
    [
        ("9", "09"),
        ("1", "01"),
        ("10", "10"),
        ("31", "31"),
        ("09", "009"),  # literal SSIS: (DT_I2)"09" = 9 < 10 -> "0" + "09"
        ("0", "00"),
        (" 9", "0 9"),  # el cast tolera espacios, la concatenacion usa el texto original
        (None, None),  # NULL se propaga
    ],
)
def test_dia_mes(valor, esperado):
    assert rellenar_dia_mes(valor) == esperado


@pytest.mark.parametrize(
    "valor, esperado",
    [
        ("08:30", "08:30"),
        ("8:30", "08:30"),
        (" 8:30 ", "08:30"),  # TRIM quita espacios
        ("\t8:30", "\t8:30"),  # TRIM de SSIS no quita tabs (len 5)
        ("12:00", "12:00"),
        ("830", "830"),
        ("", ""),
        (None, None),
    ],
)
def test_intervalo(valor, esperado):
    assert rellenar_intervalo(valor) == esperado


def test_fecha_ansi_concatena_y_propaga_null():
    assert fecha_ansi("2026", "09", "23") == "20260923"
    assert fecha_ansi("2026", None, "23") is None


def test_transformar_columnas_nombres_y_orden_del_destino():
    df = parsear_archivo_plano(csv_bytes(fila_csv(mes="9", dia="3", intervalo="8:00", login="51030001"))).a_dataframe()
    out = transformar(df)
    assert list(out.columns) == list(mappings.COLUMNAS_INSERT)
    fila = out.iloc[0]
    assert fila["FECHA ANSI"] == "20260903"  # FechaAnsi usa MES/DIA ya rellenados
    assert fila["MES"] == "09" and fila["DIA"] == "03"
    assert fila["HORA"] == "08:00"
    assert fila["ID CONEXION"] == "51030001"
    assert fila["AÑO"] == "2026"


def test_transformar_null_y_texto_sin_cambios():
    df = parsear_archivo_plano(csv_bytes(fila_csv(nombre="", resto=" 7 "))).a_dataframe()
    fila = transformar(df).iloc[0]
    assert fila["AGENT_NOMBRE"] is None
    assert fila["TMO"] == " 7 "  # la conversion a DT_STR no recorta

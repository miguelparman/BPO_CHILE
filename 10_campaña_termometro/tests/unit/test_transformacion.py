import pandas as pd
import pytest

from transformacion.clientes import OUTPUT_COLUMNS as COLS_CLIENTES, transform_clientes
from transformacion.detractores import transform_detractores
from transformacion.encuestas import OUTPUT_COLUMNS as COLS_ENCUESTAS, transform_encuestas


def _excel_clientes(**overrides):
    fila = {"RUT_DV": "12345678-9", "NOMCLI": None, "SEGME": "PYME", "NOM_SM": " Ana ", "NOM_SUP": "Luis", "TENTA_FO": "SI"}
    fila.update(overrides)
    return pd.DataFrame([fila])


def test_clientes_deriva_rut_y_periodo():
    df = transform_clientes(_excel_clientes(), 202609)
    fila = df.iloc[0]
    assert list(df.columns) == COLS_CLIENTES
    assert fila["RUT_SIN_DV"] == "123456789"
    assert fila["RUT"] == "0012345678"  # sin DV, relleno a 10
    assert fila["PERIODO"] == 202609
    assert fila["TENTA FO"] == "SI"
    assert fila["NOM_SM"] == "Ana"


def test_clientes_vacio_queda_nulo_no_texto_nan():
    df = transform_clientes(_excel_clientes(), 202609)
    assert pd.isna(df.iloc[0]["NOMCLI"])


def test_clientes_falta_columna():
    with pytest.raises(KeyError):
        transform_clientes(_excel_clientes().drop(columns=["TENTA_FO"]), 202609)


def test_detractores_castea_a_texto():
    df = transform_detractores(pd.DataFrame({"PERIODO": [202609], "RUT_SIN_DV": [123456789], "OTRA": ["x"]}))
    assert list(df.columns) == ["PERIODO", "RUT_SIN_DV"]
    assert df.iloc[0]["RUT_SIN_DV"] == "123456789"


def test_detractores_falta_columna():
    with pytest.raises(ValueError):
        transform_detractores(pd.DataFrame({"PERIODO": [202609]}))


def _csv_encuestas(**overrides):
    fila = {c: None for c in COLS_ENCUESTAS if c != "PERIODO"}
    fila.pop("No  identificación fiscal")
    fila.pop("Plan de acción  Caso")
    fila.update(
        {
            "No. identificación fiscal": "123456789",
            "Plan de acción: Caso": "C-1",
            "Nombre del cliente": "no se carga",
            "Fecha de la encuesta": "05-09-2026",
            "Promedio del termómetro": "6,77",
            "11. Satisfacción general": "7",
            "14. Probabilidad de recomendación": "No evaluado",
        }
    )
    fila.update(overrides)
    return pd.DataFrame([fila], dtype=object)


def test_encuestas_renombra_y_descarta_columnas():
    df = transform_encuestas(_csv_encuestas(), 202609)
    assert list(df.columns) == COLS_ENCUESTAS
    assert df.iloc[0]["No  identificación fiscal"] == "123456789"
    assert df.iloc[0]["Plan de acción  Caso"] == "C-1"
    assert df.iloc[0]["PERIODO"] == 202609


def test_encuestas_fecha_dia_primero():
    df = transform_encuestas(_csv_encuestas(), 202609)
    assert df.iloc[0]["Fecha de la encuesta"] == pd.Timestamp(2026, 9, 5)


def test_encuestas_coma_decimal_y_enteros():
    fila = transform_encuestas(_csv_encuestas(), 202609).iloc[0]
    assert fila["Promedio del termómetro"] == pytest.approx(6.77)
    assert fila["11. Satisfacción general"] == 7
    assert pd.isna(fila["14. Probabilidad de recomendación"])  # "No evaluado" -> NULL

"""Reglas de transformacion de los 3 scripts de carga, comparadas contra los
oraculos literales de tools/oraculos.py cuando aplica."""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

import mappings
from exceptions import ValidacionError
from tests.unit.fakes import csv_de, fila_encuesta, fila_wsp
from tools import oraculos
from transformacion import transformer


# --------------------------------------------------------------------------- #
# Conversores
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "texto, esperado",
    [("5", 5), ("-1", -1), ("10.00", 10), ("-1.00", -1), (" 7 ", 7), ("5.70", 5), ("-1.50", -1)],
)
def test_a_int_trunca_hacia_cero_como_sql_server(texto, esperado):
    assert transformer.a_int(texto) == esperado


def test_a_int_rechaza_texto():
    with pytest.raises(ValueError):
        transformer.a_int("abc")


def test_a_datetime_formato_csv_writer():
    assert transformer.a_datetime("2026-08-19 10:56:00") == datetime(2026, 8, 19, 10, 56)
    assert transformer.a_datetime("2026-08-19 10:56:00.1234567") == datetime(2026, 8, 19, 10, 56, 0, 123456)


# --------------------------------------------------------------------------- #
# EPA_ISN
# --------------------------------------------------------------------------- #
def test_encuestas_chile_filtra_periodo_desde_y_descarta_nulos():
    crudo = csv_de([
        fila_encuesta(id_encuesta_registro="1", periodo_evento="202512"),
        fila_encuesta(id_encuesta_registro="2", periodo_evento="202601"),
        fila_encuesta(id_encuesta_registro="3", periodo_evento="202609"),
        fila_encuesta(id_encuesta_registro="4", periodo_evento=""),
    ])
    df = transformer.encuestas_chile(crudo, 202601)
    assert df["id_encuesta_registro"].tolist() == ["2", "3"]


def test_encuestas_chile_tipos_y_vacios():
    crudo = csv_de([fila_encuesta(r1="-1", r4="", NEGOCIO="", **{"año_evento": "2026"})])
    df = transformer.encuestas_chile(crudo, 202601)
    fila = df.iloc[0]
    assert fila["r1"] == -1 and isinstance(fila["r1"], int)
    assert fila["r4"] is None  # int vacio -> NULL
    assert fila["NEGOCIO"] is None  # texto vacio -> NULL
    assert fila["año_evento"] == "2026"
    assert fila["periodo_evento"] == "202609"  # nvarchar(10): texto
    assert list(df.columns) == list(mappings.ENCUESTA.esquema)  # orden de column_list


def test_encuestas_chile_int_invalido_es_error_de_validacion():
    with pytest.raises(ValidacionError, match="r1"):
        transformer.encuestas_chile(csv_de([fila_encuesta(r1="x")]), 202601)


# --------------------------------------------------------------------------- #
# WSP: clean_row
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "valor, largo, sufijo",
    [
        (None, None, False), (float("nan"), None, False), ("nan", None, False), ("NaN", 5, True),
        ("77960408.0", 20, True), ("-5.0", 20, True), ("77960408.0", 20, False), ("77960408.00", 20, True),
        ("abcdefghij", 5, False), ("abc", 5, False), ("123456789012.0", 5, True), ("", 5, False),
    ],
)
def test_clean_value_equivale_a_clean_row_original(valor, largo, sufijo):
    esperado = oraculos.clean_row((valor,), [largo], {0} if sufijo else None)[0]
    obtenido = transformer.clean_value(valor, largo, sufijo)
    if isinstance(esperado, float):
        assert obtenido is None or (isinstance(obtenido, float) and np.isnan(obtenido))
    else:
        assert obtenido == esperado


def test_wsp_tipos_y_limpieza():
    df = transformer.wsp_medallia(csv_de([fila_wsp(rutcli="nan"), fila_wsp(SurveyID="2")]))
    f0, f1 = df.iloc[0], df.iloc[1]
    assert f0["SurveyID"] == 36068939
    assert f0["NPS"] == 10 and f0["Facilidad"] == 5 and f0["ISN"] == -1
    assert f0["Periodo"] == 202609 and f0["cnps"] == 1
    assert f0["Responsedate"] == datetime(2026, 9, 19, 10, 56)
    assert f0["rutcli"] is None  # 'nan' -> NULL
    assert f1["rutcli"] == "77220662"  # sufijo .0 quitado
    assert f0["Subtype"] is None  # '' -> NULL
    assert f0["CONNID"] == "0009QaN8BE5S07B7"  # 'connid' del CSV -> [CONNID]
    assert "HoraRespuesta" not in df.columns  # no esta en column_list
    assert list(df.columns) == list(mappings.WSP.columnas.values())


def test_wsp_tipificacion_vacia_es_texto_si_la_encuesta_cruzo_y_null_si_no():
    df = transformer.wsp_medallia(csv_de([
        fila_wsp(tipificacion=""),  # cruzo (pcrc_eac informado) -> ''
        fila_wsp(tipificacion="", pcrc_eac="", loginid="", vq=""),  # no cruzo -> NULL
    ]))
    assert df.iloc[0]["tipificacion"] == ""
    assert df.iloc[1]["tipificacion"] is None
    assert df.iloc[1]["pcrc_eac"] is None and df.iloc[1]["loginid"] is None


def test_wsp_trunca_texto_al_ancho_destino():
    df = transformer.wsp_medallia(csv_de([fila_wsp(loginid="1234567890123456789")]))
    assert df.iloc[0]["loginid"] == "123456789012345"  # nvarchar(15)


def test_wsp_verbatim_max_no_se_trunca():
    largo = "x" * 5000
    assert transformer.wsp_medallia(csv_de([fila_wsp(verbatim=largo)])).iloc[0]["verbatim"] == largo


# --------------------------------------------------------------------------- #
# MEDALLIA (contra el oraculo literal, sobre un CSV latin1 real)
# --------------------------------------------------------------------------- #
def _escribir_csv_medallia(tmp_path, filas):
    columnas = list(mappings.MEDALLIA.columnas) + ["Otra", mappings.MEDALLIA_COLUMNA_DUPLICADA]
    df = pd.DataFrame(filas, columns=columnas)
    ruta = tmp_path / "Encuestas_Medallia.csv"
    df.to_csv(ruta, index=False, encoding="latin1")  # pandas renombra el duplicado a '.1' al leer
    return ruta


def test_medallia_equivale_al_script_original(tmp_path):
    n = len(mappings.MEDALLIA.columnas)
    filas = [
        ["1", "B2B", "569", "28-09-2026", "2026-09-23", "10", "Sí", "5", "4", "5", "OK", "bien", "C1", "PLAT", "CAT", "EMP", "o", ""],
        ["2", "B2B", "", "27-09-2026", "23-09-2026", "NULL", "No", "nan", "", "None", "OK", "", "C2", "PLAT", "", "EMP", "o", "razon dup"],
        ["3", "B2B", "569", "fecha mala", "2026-09-23", "1", "", "", "", "", "", "", "", "", "", "", "", ""],
        ["4", "B2B", "569", "", "2026-09-23", "1", "", "", "", "", "", "", "", "", "", "", "", ""],
    ]
    assert all(len(f) == n + 2 for f in filas)
    ruta = _escribir_csv_medallia(tmp_path, filas)

    original = oraculos.medallia_datos(ruta)
    # En el original las filas con Responsedate NaT fallaban al insertar.
    insertables = [f for f in original if not pd.isna(f[3])]

    from extraccion.extractor import extraer_csv_medallia
    from tests.unit.fakes import FakeCarpeta

    carpeta = FakeCarpeta({"Encuestas_Medallia.csv": ruta.read_bytes()})  # mismo archivo, leido desde SharePoint
    df, rechazadas = transformer.medallia(extraer_csv_medallia(carpeta, "Encuestas_Medallia.csv"))
    assert rechazadas == [3, 4]
    obtenidas = [tuple(f) for f in df.itertuples(index=False, name=None)]
    assert len(obtenidas) == len(insertables) == 2
    for a, b in zip(insertables, obtenidas):
        assert tuple(None if (isinstance(v, float) and np.isnan(v)) else (v.to_pydatetime() if isinstance(v, pd.Timestamp) else v) for v in a) == b
    # columna duplicada fusionada
    razones = mappings.MEDALLIA_COLUMNA_DUPLICADA
    assert df.iloc[1][razones] == "razon dup"
    assert df.iloc[1]["NPS"] is None and df.iloc[1]["SAT - Asesor"] is None


def test_medallia_falta_columna():
    crudo = pd.DataFrame({"ID de encuesta": ["1"], "Responsedate": ["28-09-2026"]}, dtype=str)
    with pytest.raises(ValidacionError, match="faltan columnas"):
        transformer.medallia(crudo)

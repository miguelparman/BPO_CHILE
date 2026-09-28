from datetime import date, datetime

import pytest

import mappings
from exceptions import ExtraccionError, ValidacionError
from extraccion import extractor
from tests.unit.fakes import FakeCsvReader, csv_minimo

ATENDIDA = next(o for o in mappings.ORIGENES if o.archivo == "ATENDIDA.csv")
CALLBACK = next(o for o in mappings.ORIGENES if o.archivo == "CALLBACK.csv")
CROSS = next(o for o in mappings.ORIGENES if o.archivo == "cross_inbound.csv")


def test_filtro_periodo_int_yyyymm_es_mayor_o_igual():
    df = csv_minimo(ATENDIDA, [{"DATE_YYYYMM": "202608"}, {"DATE_YYYYMM": "202609"}, {"DATE_YYYYMM": "202610"}, {"DATE_YYYYMM": ""}])
    assert extractor.filtrar_periodo(df, ATENDIDA, 202609)["DATE_YYYYMM"].tolist() == ["202609", "202610"]


def test_filtro_periodo_callback_usa_el_mes_de_fecha():
    df = csv_minimo(
        CALLBACK,
        [{"FECHA": "2026-08-31 23:59:59"}, {"FECHA": "2026-09-01 00:00:00"}, {"FECHA": ""}, {"FECHA": "2027-01-02 10:00:00"}],
    )
    assert extractor.filtrar_periodo(df, CALLBACK, 202609)["FECHA"].tolist() == ["2026-09-01 00:00:00", "2027-01-02 10:00:00"]


def test_tipifica_segun_el_esquema_de_la_temporal():
    df = csv_minimo(ATENDIDA, [{"INTERACTION_ID": "23787897", "START_YYYYMMDD_HHMMSS": "2026-08-01 01:49:52",
                                 "DATE_YYYYMMDD": "2026-08-01", "T_QUEUE": "0", "MEDIA": "VOICE"}])
    fila = extractor.tipificar(df, ATENDIDA).iloc[0]
    assert fila["INTERACTION_ID"] == 23787897 and type(fila["INTERACTION_ID"]) is int
    assert fila["START_YYYYMMDD_HHMMSS"] == datetime(2026, 8, 1, 1, 49, 52)
    assert fila["DATE_YYYYMMDD"] == date(2026, 8, 1)
    assert fila["T_QUEUE"] == 0
    assert fila["MEDIA"] == "VOICE"


def test_proyecta_solo_las_columnas_del_insert_original():
    df = csv_minimo(CROSS)
    df["rutcli"] = "123"
    salida = extractor.tipificar(df, CROSS)
    assert list(salida.columns) == list(mappings.COLUMNAS_TRAFICO)  # sin ID, rutcli, etc.


def test_celda_vacia_es_null_salvo_texto_de_cross_inbound():
    vacias = {"DNIS": "", "AGENT_GROUP": "", "T_RING": "", "QUEUE_START_YYYYMMDD_HHMMSS": ""}
    a = extractor.tipificar(csv_minimo(ATENDIDA, [vacias]), ATENDIDA).iloc[0]
    c = extractor.tipificar(csv_minimo(CROSS, [vacias]), CROSS).iloc[0]
    assert a["DNIS"] is None and a["AGENT_GROUP"] is None
    assert c["DNIS"] == "" and c["AGENT_GROUP"] == ""  # [cross_inbound] guardaba ''
    for fila in (a, c):  # no-texto vacio: siempre NULL
        assert fila["T_RING"] is None and fila["QUEUE_START_YYYYMMDD_HHMMSS"] is None


def test_texto_con_espacios_se_conserva_tal_cual():
    fila = extractor.tipificar(csv_minimo(ATENDIDA, [{"AGENT_NAME": " Perez, Juan "}]), ATENDIDA).iloc[0]
    assert fila["AGENT_NAME"] == " Perez, Juan "


def test_fecha_1900_se_mantiene_como_datetime():
    fila = extractor.tipificar(csv_minimo(CROSS, [{"QUEUE_START_YYYYMMDD_HHMMSS": "1900-01-01 00:00:00"}]), CROSS).iloc[0]
    assert fila["QUEUE_START_YYYYMMDD_HHMMSS"] == datetime(1900, 1, 1)


def test_callback_hora_inicio_fin_toman_el_formato_de_datetime2():
    df = csv_minimo(CALLBACK, [{"HORA_INICIO_LLAMADA": "2026-08-05 14:50:00", "HORA_FIN_LLAMADA": "",
                                "FECHA_EXTRACCION": "2026-09-01 22:03:22.000"}])
    fila = extractor.tipificar(df, CALLBACK).iloc[0]
    assert fila["HORA_INICIO_LLAMADA"] == "2026-08-05 14:50:00.0000000"
    assert fila["HORA_FIN_LLAMADA"] is None
    assert fila["FECHA_EXTRACCION"] == "2026-09-01 22:03:22.000"  # era texto: se copia literal


def test_valor_no_convertible_detiene_con_validacion_error():
    with pytest.raises(ValidacionError, match="T_TALK"):
        extractor.tipificar(csv_minimo(ATENDIDA, [{"T_TALK": "12s"}]), ATENDIDA)


def test_falta_una_columna_obligatoria():
    df = csv_minimo(ATENDIDA).drop(columns=["SKILL"])
    with pytest.raises(ValidacionError, match="SKILL"):
        extractor.tipificar(df, ATENDIDA)


def test_archivo_inexistente_en_sharepoint_es_extraccion_error():
    with pytest.raises(ExtraccionError, match="ATENDIDA.csv"):
        extractor.extraer_origen(FakeCsvReader({}), ATENDIDA, 202609)


def test_parsear_datetime_recorta_fraccion_de_7_digitos():
    assert extractor.parsear_datetime("2026-09-04 14:24:21.1234567") == datetime(2026, 9, 4, 14, 24, 21, 123456)

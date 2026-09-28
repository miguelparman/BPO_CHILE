from datetime import date, datetime

import pandas as pd
import pytest

import mappings
from exceptions import ConversionError
from mappings import ColumnaCarga
from transformacion import transformer
from transformacion.transformer import _FalloConversion, convertir_destino, convertir_ssis


def _df(filas):
    return pd.DataFrame({k: pd.Series([f[k] for f in filas], dtype=object) for k in filas[0]})


# --- Conditional Split ------------------------------------------------------ #
def test_split_envia_a_inbound_chat_o_descarta():
    df = _df([
        {"MEDIA": "VOICE", "INTERACTION_TYPE": "INBOUND"},
        {"MEDIA": "CHAT", "INTERACTION_TYPE": "INBOUND_WSP"},
        {"MEDIA": "VOICE", "INTERACTION_TYPE": "OUTBOUND"},  # salida predeterminada: se descarta
        {"MEDIA": "voice", "INTERACTION_TYPE": "INBOUND"},  # '==' de SSIS distingue mayusculas
    ])
    salidas = transformer.dividir_atendida(df)
    assert len(salidas["Inbound"]) == 1 and len(salidas["Chat"]) == 1


def test_split_con_condicion_null_falla_como_failcomponent():
    df = _df([{"MEDIA": None, "INTERACTION_TYPE": "INBOUND"}])
    with pytest.raises(ConversionError, match="NULL"):
        transformer.dividir_atendida(df)


def test_split_null_pero_otra_parte_false_no_falla():
    # FALSE && NULL = FALSE en SSIS: la fila no llega a evaluar a NULL
    df = _df([{"MEDIA": "SMS", "INTERACTION_TYPE": None}])
    salidas = transformer.dividir_atendida(df)
    assert all(len(v) == 0 for v in salidas.values())


# --- Derived Column (CALLBACK) ---------------------------------------------- #
def test_columnas_derivadas_de_callback():
    df = transformer.derivar_callback(_df([{"FECHA": datetime(2026, 9, 2, 15, 7, 5)}, {"FECHA": None}]))
    assert df["FECHA_DATE"].tolist() == [date(2026, 9, 2), None]
    assert df["FECHA_HORA"].tolist() == ["15:07:05", None]


# --- Data Conversion -------------------------------------------------------- #
def test_dt_str_trunca_falla():
    assert convertir_ssis("A" * 25, "DT_STR", 25) == "A" * 25
    with pytest.raises(_FalloConversion, match="truncamiento"):
        convertir_ssis("A" * 26, "DT_STR", 25)


def test_dt_str_exige_code_page_1252():
    assert convertir_ssis("Sánchez Ñuñez", "DT_STR", 60) == "Sánchez Ñuñez"
    with pytest.raises(_FalloConversion, match="1252"):
        convertir_ssis("Chat 💬", "DT_STR", 60)
    assert convertir_ssis("Chat 💬", "DT_WSTR", 60) == "Chat 💬"


def test_dt_i4_a_varchar_5_del_destino():
    assert convertir_destino(convertir_ssis(290, "DT_I4", None), "varchar", 5) == "290"
    with pytest.raises(_FalloConversion, match="varchar\\(5\\)"):
        convertir_destino(convertir_ssis(123456, "DT_I4", None), "varchar", 5)


def test_null_se_mantiene_null_en_toda_conversion():
    for conv in ("DT_STR", "DT_WSTR", "DT_I4", "DT_DBTIMESTAMP", "DT_DBDATE", None):
        assert convertir_ssis(None, conv, 10) is None
    assert convertir_destino(None, "varchar", 5) is None


def test_texto_a_datetime_del_destino():
    # FECHA_EXTRACCION: DT_WSTR(50) -> datetime (conversion del OLE DB Destination)
    assert convertir_destino("2026-09-28 08:00:42.000", "datetime", None) == datetime(2026, 9, 28, 8, 0, 42)


def _destino_con(col: ColumnaCarga):
    return mappings.DestinoCarga("TEST", "TBL_TEST", "TBL_TRAFICO_CALLBACK", None, (col,))


def test_ignore_failure_deja_null_y_failcomponent_aborta():
    df = _df([{"HORA_INICIO_LLAMADA": "no es fecha"}, {"HORA_INICIO_LLAMADA": "2026-09-04 14:24:21.0000000"}])
    ignora = ColumnaCarga("HORA_INICIO_LLAMADA", "HORA_INICIO_LLAMADA", "DT_DBTIMESTAMP", None, "datetime", None, ignorar_fallo=True)
    salida = transformer.mapear_destino(df, _destino_con(ignora))
    assert salida["HORA_INICIO_LLAMADA"].tolist() == [None, datetime(2026, 9, 4, 14, 24, 21)]

    falla = ColumnaCarga("HORA_INICIO_LLAMADA", "HORA_INICIO_LLAMADA", "DT_DBTIMESTAMP", None, "datetime", None)
    with pytest.raises(ConversionError, match="FailComponent"):
        transformer.mapear_destino(df, _destino_con(falla))


def test_los_ignore_failure_del_dtsx_son_solo_hora_inicio_y_fin_de_callback():
    ignorados = [(d.tabla, c.destino) for d in mappings.DESTINOS for c in d.columnas if c.ignorar_fallo]
    assert sorted(ignorados) == [("TBL_CALLBACK", "HORA_FIN_LLAMADA"), ("TBL_CALLBACK", "HORA_INICIO_LLAMADA")]


# --- Data Flow completo ----------------------------------------------------- #
def _temporales_minimas():
    esquema_valor = {"int": 1, "date": date(2026, 9, 1), "datetime": datetime(2026, 9, 1, 10, 15)}
    temporales = {}
    for o in mappings.ORIGENES:
        cols = mappings.TIPOS_TEMPORALES[o.tabla_temporal]
        fila = {c: esquema_valor.get(t, "x") for c, (t, _) in cols.items()}
        if "FECHA_EXTRACCION" in fila:  # nvarchar en la temporal, datetime en TBL_CALLBACK
            fila["FECHA_EXTRACCION"] = "2026-09-28 08:00:42.000"
        if o.tabla_temporal == "TBL_TRAFICO_ATENDIDA":
            filas = [dict(fila, MEDIA="VOICE", INTERACTION_TYPE="INBOUND", VIRTUAL_QUEUE="VQ_1"),
                     dict(fila, MEDIA="CHAT", INTERACTION_TYPE="INBOUND_WSP")]
        else:
            filas = [fila]
        temporales[o.tabla_temporal] = _df(filas)
    return temporales


def test_transformar_carga_produce_las_8_tablas_con_sus_columnas():
    salida = transformer.transformar_carga(_temporales_minimas())
    assert set(salida) == set(mappings.TABLAS_CL_TRAFICO)
    for d in mappings.DESTINOS:
        assert list(salida[d.tabla].columns) == [c.destino for c in d.columnas]
    assert len(salida["TBL_LLAMADAS_ATENDIDAS_INBOUND"]) == 1
    assert len(salida["TBL_CHAT"]) == 1
    inbound = salida["TBL_LLAMADAS_ATENDIDAS_INBOUND"].iloc[0]
    assert inbound["COLA"] == "VQ_1"  # VIRTUAL_QUEUE -> COLA
    assert inbound["TIEMPO_COLA"] == "1"  # T_QUEUE (int) -> varchar(5)
    assert salida["TBL_CALLBACK"].iloc[0]["HORA"] == "10:15:00"  # derivada de FECHA


def test_transformar_carga_falla_antes_de_devolver_nada_si_un_valor_no_cabe():
    temporales = _temporales_minimas()
    temporales["TBL_TRAFICO_OUTBOUND"].loc[0, "CONNID"] = "X" * 26  # DT_STR(25)
    with pytest.raises(ConversionError, match=r"TBL_LLAMADAS_ATENDIDAS_OUTBOUND\.\[CONNID\]"):
        transformer.transformar_carga(temporales)

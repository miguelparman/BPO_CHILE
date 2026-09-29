"""Transformacion: reproduce la semantica de SQL Server de Alimenta Tabla."""

from datetime import date, datetime, timedelta

import pandas as pd
import pytest

import mappings
from tests.unit.fakes import bases_minimas, origen
from transformacion import transformer

T0 = datetime(2026, 9, 1, 10, 0, 0)
LLAMADAS_TRIADAS = mappings.BASES[0]


def _fcr(filas):
    return transformer.calcular_fcr(transformer.preparar_base(origen(filas), LLAMADAS_TRIADAS))


def _con_bases(**por_base):
    """Todas las bases vacias salvo las indicadas."""
    datos = {b.tabla_temporal: origen([]) for b in mappings.BASES}
    datos.update(por_base)
    return datos


# --------------------------------------------------------------------------- #
# Bloque XA
# --------------------------------------------------------------------------- #
def test_columnas_derivadas_de_agent_start():
    df = transformer.preparar_base(origen([(datetime(2026, 9, 3, 23, 59, 59, 997000), "1", "TRIADAS", "u")]), LLAMADAS_TRIADAS)
    fila = df.iloc[0]
    assert fila["FECHA"] == date(2026, 9, 3)
    assert fila["HORA"] == "23:59:59"  # CAST(... AS TIME) -> VARCHAR(8) trunca, no redondea
    assert fila["BASE"] == "LLAMADAS"
    assert fila["FECHA/HORA"] == pd.Timestamp("2026-09-03 23:59:59.997")


# --------------------------------------------------------------------------- #
# LEAD + DATEDIFF(SECOND) + umbrales
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("umbral", mappings.UMBRALES, ids=lambda u: u.columna)
def test_limite_exacto_de_cada_umbral(umbral):
    en_limite = _fcr([(T0, "1", "TRIADAS", "a"), (T0 + timedelta(seconds=umbral.segundos), "1", "TRIADAS", "b")])
    fuera = _fcr([(T0, "1", "TRIADAS", "a"), (T0 + timedelta(seconds=umbral.segundos + 1), "1", "TRIADAS", "b")])
    assert en_limite[umbral.columna].iloc[0] == 0  # <= umbral -> 0
    assert fuera[umbral.columna].iloc[0] == 1


def test_datediff_cuenta_limites_de_segundo_no_tiempo_transcurrido():
    # 1799,2 s transcurridos, pero DATEDIFF(SECOND) = 1800 -> FCR_30min = 0
    df = _fcr([(T0.replace(microsecond=900000), "1", "TRIADAS", "a"), (T0 + timedelta(minutes=30, microseconds=100000), "1", "TRIADAS", "b")])
    assert transformer.diferencia_segundos(df["FECHA/HORA"], df["FECHA/HORA-PROXIMO"]).iloc[0] == 1800
    assert df["FCR_30min"].iloc[0] == 0


def test_ultima_atencion_sin_proximo_tiene_todos_los_fcr_en_1():
    df = _fcr([(T0, "1", "TRIADAS", "a")])
    assert pd.isna(df["FECHA/HORA-PROXIMO"].iloc[0])
    assert all(df[u.columna].iloc[0] == 1 for u in mappings.UMBRALES)


def test_lead_se_ordena_por_fecha_hora_y_no_por_orden_de_lectura():
    df = _fcr([(T0 + timedelta(hours=2), "1", "TRIADAS", "tarde"), (T0, "1", "TRIADAS", "temprano")])
    temprano = df[df.LOGINID == "temprano"].iloc[0]
    assert temprano["FECHA/HORA-PROXIMO"] == pd.Timestamp(T0 + timedelta(hours=2))
    assert pd.isna(df[df.LOGINID == "tarde"].iloc[0]["FECHA/HORA-PROXIMO"])


def test_particion_por_ani():
    df = _fcr([(T0, "1", "TRIADAS", "a"), (T0 + timedelta(minutes=1), "2", "TRIADAS", "b")])
    assert df["FECHA/HORA-PROXIMO"].isna().all()


def test_ani_null_forman_una_sola_particion():
    df = _fcr([(T0, None, "TRIADAS", "a"), (T0 + timedelta(minutes=1), None, "TRIADAS", "b")])
    assert df["FECHA/HORA-PROXIMO"].iloc[0] == pd.Timestamp(T0 + timedelta(minutes=1))
    assert df["FCR_30min"].iloc[0] == 0


def test_ani_vacio_y_ani_null_son_particiones_distintas():
    # Caso real (TBL_CHAT, 2025-03-20 ANI='' y 2026-06-04 ANI NULL): SQL no los encadena.
    df = _fcr([(T0, "", "TRIADAS", "a"), (T0 + timedelta(minutes=1), None, "TRIADAS", "b")])
    assert df["FECHA/HORA-PROXIMO"].isna().all()


def test_particion_con_collation_ci_y_sin_espacios_finales():
    # Modern_Spanish_CI_AS: 'abc' = 'ABC  ' en PARTITION BY
    df = _fcr([(T0, "abc", "TRIADAS", "a"), (T0 + timedelta(minutes=1), "ABC  ", "triadas", "b")])
    assert df["FECHA/HORA-PROXIMO"].iloc[0] == pd.Timestamp(T0 + timedelta(minutes=1))


# --------------------------------------------------------------------------- #
# UNION ALL + TRAMO_QUIEBRE
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("i", range(len(mappings.UMBRALES)))
def test_tramo_es_el_primer_umbral_en_0(i):
    umbral = mappings.UMBRALES[i]
    anterior = mappings.UMBRALES[i - 1].segundos if i else 0
    df = transformer.transformar(
        _con_bases(**{LLAMADAS_TRIADAS.tabla_temporal: origen(
            [(T0, "1", "TRIADAS", "a"), (T0 + timedelta(seconds=anterior + 1), "1", "TRIADAS", "b")]
        )})
    )
    assert df["TRAMO_QUIEBRE"].iloc[0] == umbral.tramo
    assert df["TRAMO_QUIEBRE"].iloc[1] == mappings.SIN_QUIEBRE


def test_mas_de_15_dias_es_sin_quiebre():
    df = transformer.transformar(
        _con_bases(**{LLAMADAS_TRIADAS.tabla_temporal: origen(
            [(T0, "1", "TRIADAS", "a"), (T0 + timedelta(days=15, seconds=1), "1", "TRIADAS", "b")]
        )})
    )
    assert list(df["TRAMO_QUIEBRE"]) == [mappings.SIN_QUIEBRE, mappings.SIN_QUIEBRE]


def test_llamadas_y_whatsapp_no_se_encadenan_aunque_sea_el_mismo_ani():
    chat = mappings.BASES[3]
    df = transformer.transformar(
        _con_bases(
            **{
                LLAMADAS_TRIADAS.tabla_temporal: origen([(T0, "1", "TRIADAS", "a")]),
                chat.tabla_temporal: origen([(T0 + timedelta(minutes=5), "1", "TRIADAS", "b")]),
            }
        )
    )
    assert df["FECHA/HORA-PROXIMO"].isna().all()
    assert list(df["BASE"]) == ["LLAMADAS", "WHATSAPP"]


def test_union_all_en_orden_de_bases_y_columnas_en_orden_de_posicion():
    df = transformer.transformar(bases_minimas())
    assert list(df.columns) == list(mappings.NOMBRES_DESTINO)
    assert len(df) == 2 * len(mappings.BASES)
    assert list(df["SERVICIO"][::2]) == [b.servicio for b in mappings.BASES]
    assert list(df["BASE"][::2]) == [b.base for b in mappings.BASES]


def test_bases_vacias_producen_resultado_vacio_con_todas_las_columnas():
    df = transformer.transformar(_con_bases())
    assert df.empty and list(df.columns) == list(mappings.NOMBRES_DESTINO)

from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from db import _fila_a_parametros, dividir_en_batches
from models import calcular_periodo, resolver_periodo


# --- User::Periodo --------------------------------------------------------- #
@pytest.mark.parametrize(
    "hoy, esperado",
    [
        (date(2026, 9, 28), 202609),
        (date(2026, 9, 5), 202609),  # dia 5: mes actual
        (date(2026, 9, 4), 202608),  # dia 4: todavia el mes anterior (cierre)
        (date(2026, 9, 1), 202608),
        (date(2026, 1, 3), 202512),  # enero: cruza de anio
        (date(2026, 1, 5), 202601),
        (date(2024, 3, 4), 202402),
    ],
)
def test_periodo_replica_la_expresion_de_user_periodo(hoy, esperado):
    assert calcular_periodo(hoy) == esperado


def test_dia_cierre_mes_configurable():
    assert calcular_periodo(date(2026, 10, 6), dia_cierre_mes=6) == 202609
    assert calcular_periodo(date(2026, 10, 7), dia_cierre_mes=6) == 202610


def test_prioridad_cli_sobre_env_sobre_automatico():
    hoy = date(2026, 9, 28)
    assert resolver_periodo(hoy, 202607, 202608) == (202607, "--periodo")
    assert resolver_periodo(hoy, None, 202608) == (202608, "PERIODO (.env)")
    assert resolver_periodo(hoy, None, None)[0] == 202609


@pytest.mark.parametrize("malo", [20269, 202613, 202600, 2026090])
def test_periodo_invalido_se_rechaza(malo):
    with pytest.raises(ValueError, match="YYYYMM"):
        resolver_periodo(date(2026, 9, 28), None, malo)


# --- separador GO ---------------------------------------------------------- #
def test_divide_por_go_en_su_propia_linea_y_descarta_batches_vacios():
    script = "UPDATE a SET x=1\r\nGO\r\n\r\nUPDATE b SET y=2\n  go  \nSELECT 'GO' AS texto\nGO -- fin\n"
    assert dividir_en_batches(script) == ["UPDATE a SET x=1", "UPDATE b SET y=2", "SELECT 'GO' AS texto"]


def test_no_parte_identificadores_que_contienen_go():
    script = "UPDATE [CL_TEMPORALES].[dbo].[TBL_GO] SET CATEGORY = 'GOLD'"
    assert dividir_en_batches(script) == [script]


def test_script_update_rut_del_dtsx_tiene_sus_batches():
    import sql

    # 16 'GO' en el script; OUTBOUND, CLEARED y CALLBACK van en el ultimo batch.
    batches = dividir_en_batches(sql.LIMPIA_UPDATE_RUT)
    assert len(batches) == 17
    assert not any(b.upper().strip() == "GO" for b in batches)


# --- saneo de parametros --------------------------------------------------- #
def test_fila_a_parametros_convierte_nan_y_numpy_a_nativos():
    ts = pd.Timestamp("2026-09-01 10:00:00")
    fila = (np.nan, pd.NA, pd.NaT, np.int64(5), np.float64(1.5), "", "x", ts, None, date(2026, 9, 1))
    assert _fila_a_parametros(fila) == (None, None, None, 5, 1.5, "", "x", datetime(2026, 9, 1, 10), None, date(2026, 9, 1))
    assert type(_fila_a_parametros((np.int64(5),))[0]) is int

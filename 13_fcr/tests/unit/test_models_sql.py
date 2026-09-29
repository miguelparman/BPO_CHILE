from datetime import date

import pytest

import mappings
import sql
from models import calcular_periodo, resolver_periodo


@pytest.mark.parametrize(
    "hoy, esperado",
    [(date(2026, 9, 4), 202608), (date(2026, 9, 5), 202609), (date(2026, 1, 2), 202512), (date(2026, 9, 29), 202609)],
)
def test_periodo_automatico_igual_que_12_trafico(hoy, esperado):
    assert calcular_periodo(hoy) == esperado


def test_prioridad_del_periodo():
    assert resolver_periodo(date(2026, 9, 29), 202601, 202602)[0] == 202601
    assert resolver_periodo(date(2026, 9, 29), None, 202602)[0] == 202602
    assert resolver_periodo(date(2026, 9, 29), None, None)[0] == 202609


def test_periodo_invalido():
    with pytest.raises(ValueError):
        resolver_periodo(date(2026, 9, 29), 202613, None)


@pytest.mark.parametrize("base", mappings.BASES, ids=lambda b: b.tabla_temporal)
def test_extraccion_usa_el_mismo_filtro_que_el_original(base):
    texto = sql.extraccion_base(base)
    assert f"FROM [CL_TRAFICO].[dbo].[{base.tabla_origen}]" in texto
    assert "WHERE CONVERT(VARCHAR(6),[AGENT_START_YYYYMMDD_HHMMSS],112)>=CAST(? AS INT)" in texto
    assert texto.endswith(f"SERVICIO IN ('{base.servicio}')")
    assert texto.count("?") == 1


def test_oraculo_solo_cambia_el_destino_del_insert():
    oraculo = sql.alimenta_tabla_oraculo()
    # TBL_FCR solo aparece como molde de la #temp (SELECT TOP 0 * INTO): nunca se escribe
    assert oraculo.count("[CL_TRAFICO].[dbo].[TBL_FCR]") == 1
    assert "SELECT TOP 0 * INTO #TBL_FCR_ORACULO FROM [CL_TRAFICO].[dbo].[TBL_FCR]" in oraculo
    assert "INSERT INTO #TBL_FCR_ORACULO" in oraculo
    assert "##TBL_TMP_FCR" not in oraculo
    assert not any(p in oraculo.upper() for p in ("DELETE", "UPDATE", "TRUNCATE"))
    # el resto del script es el literal del .dtsx
    assert oraculo.endswith(sql.ALIMENTA_TABLA.replace("INSERT INTO [CL_TRAFICO].[dbo].[TBL_FCR]", "INSERT INTO #TBL_FCR_ORACULO").replace("DROP TABLE IF EXISTS  ##TBL_TMP_FCR;", ""))

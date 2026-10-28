import pytest

from models import Periodo


def test_periodo_acepta_formato_yyyymm():
    periodo = Periodo("202608")
    assert str(periodo) == "202608"
    assert periodo.como_int == 202608


@pytest.mark.parametrize("valor", ["2026", "20260801", "abcdef", ""])
def test_periodo_rechaza_formato_invalido(valor):
    with pytest.raises(ValueError):
        Periodo(valor)

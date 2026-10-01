from datetime import date

import pytest

from exceptions import ConfiguracionError
from periodo import calcular_periodo, resolver_periodo


@pytest.mark.parametrize(
    "hoy, esperado",
    [
        (date(2026, 10, 1), 202609),
        (date(2026, 10, 4), 202609),  # dia 4 inclusive -> mes anterior
        (date(2026, 10, 5), 202610),
        (date(2026, 10, 31), 202610),
        (date(2027, 1, 1), 202612),  # enero -> diciembre del anio anterior
        (date(2027, 1, 4), 202612),
        (date(2027, 1, 5), 202701),
        (date(2024, 3, 2), 202402),  # anio bisiesto, sin efecto
    ],
)
def test_regla_del_dtsx(hoy, esperado):
    assert calcular_periodo(hoy) == esperado


def test_prioridad_cli_sobre_env_sobre_regla():
    hoy = date(2026, 10, 1)
    assert resolver_periodo("202512", "202601", hoy).valor == 202512
    assert resolver_periodo("202512", "202601", hoy).origen == "linea de comandos"
    assert resolver_periodo(None, "202601", hoy).valor == 202601
    assert resolver_periodo(None, "202601", hoy).origen == ".env"
    assert resolver_periodo(None, "", hoy).valor == 202609
    assert resolver_periodo("  ", None, hoy).origen == "regla dia<=4"


@pytest.mark.parametrize("invalido", ["2026", "202613", "202600", "2026-09", "abcdef", "2026091"])
def test_periodo_invalido(invalido):
    with pytest.raises(ConfiguracionError):
        resolver_periodo(None, invalido, date(2026, 10, 1))
    with pytest.raises(ConfiguracionError):
        resolver_periodo(invalido, None, date(2026, 10, 1))

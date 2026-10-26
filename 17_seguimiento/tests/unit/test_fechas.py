from __future__ import annotations

from datetime import datetime

import pytest

from transformacion.fechas import fecha_a_texto, parsear_fecha


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("23-10-2026 9:08", datetime(2026, 10, 23, 9, 8)),
        ("23-10-2026 14:31", datetime(2026, 10, 23, 14, 31)),
        ("01-02-2026 14:31:05", datetime(2026, 2, 1, 14, 31, 5)),  # dia primero (es-CL)
        ("01/02/2026", datetime(2026, 2, 1)),
        ("23-10-2026 2:31 p.\xa0m.", datetime(2026, 10, 23, 14, 31)),
        ("23-10-2026 2:31 pM", datetime(2026, 10, 23, 14, 31)),  # tras REPLACE(".\xa0m.","M")
        ("23-10-2026 12:05 a. m.", datetime(2026, 10, 23, 0, 5)),
        ("23-10-2026 12:05 p. m.", datetime(2026, 10, 23, 12, 5)),
        ("2026-10-23 09:08:00", datetime(2026, 10, 23, 9, 8)),
        ("2026-10-23T09:08:00.123", datetime(2026, 10, 23, 9, 8, 0, 123000)),
    ],
)
def test_formatos_aceptados(texto, esperado):
    assert parsear_fecha(texto) == esperado


@pytest.mark.parametrize("texto", ["", "abc", "32-10-2026 9:08", "23-13-2026", "23-10-2026 13:00 pM", "10/23/26"])
def test_textos_que_no_son_fecha(texto):
    with pytest.raises(ValueError):
        parsear_fecha(texto)


def test_fecha_a_texto_iso():
    assert fecha_a_texto(datetime(2026, 10, 16, 9, 8)) == "2026-10-16 09:08:00"

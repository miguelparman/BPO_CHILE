from datetime import date, datetime

import pytest

import mappings
from transformacion.transformer import Transformer, aplicar_ancho, convertir, r8_a_texto


@pytest.mark.parametrize(
    "valor,esperado",
    [(12239535.0, "12239535"), (0.0, "0"), (-5.0, "-5"), (1.5, "1.5"), (0.1, "0.1"), (1e16, "1E+16")],
)
def test_r8_a_texto(valor, esperado):
    assert r8_a_texto(valor) == esperado


def _col(tipo=mappings.TEXTO, ancho=5, disp=mappings.IGNORE):
    return mappings.ColumnaSpec("x", "x", tipo, ancho, disp)


def test_fecha_dbdate_descarta_hora():
    assert convertir(_col(mappings.FECHA, None), datetime(2026, 10, 5, 23, 59)) == date(2026, 10, 5)


def test_nulos_se_mantienen():
    for tipo in (mappings.CASO, mappings.FECHA, mappings.TEXTO):
        assert convertir(_col(tipo), None) is None


def test_ignore_trunca_no_anula():
    assert aplicar_ancho(_col(ancho=5), "ABCDEFGH") == "ABCDE"


def test_ignore_reemplaza_caracteres_fuera_de_1252():
    assert aplicar_ancho(_col(ancho=10), "a✓b") == "a?b"
    assert aplicar_ancho(_col(ancho=10), "ñÁ\xa0€") == "ñÁ\xa0€"  # existen en 1252


def test_fail_no_se_toca_aqui():
    assert aplicar_ancho(_col(disp=mappings.FAIL, ancho=3), "ABCDEF") == "ABCDEF"


def test_transformar_ordena_como_el_insert():
    flujo = mappings.CLOSE_THE_LOOP
    fila = {"Caso SF": 13213008.0, "Fecha": datetime(2024, 3, 18), "Causa Raiz": "X" * 33, "Motivo C/R": "m",
            "Derivado": "D" * 120, "cargo": None, "SM Quiebre": "s", "Coordinador de Quiebre": "k"}
    assert Transformer().transformar(flujo, [fila]) == [
        ("13213008", date(2024, 3, 18), "X" * 33, "m", "D" * 100, None, "s", "k")  # Causa Raiz ampliada a 255
    ]


def test_caso_nulo_queda_nulo_para_el_delete():
    flujo = mappings.GERENCIA
    fila = dict.fromkeys(flujo.columnas_origen)
    assert Transformer().transformar(flujo, [fila])[0][0] is None

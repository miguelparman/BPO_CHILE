from decimal import Decimal

import pytest

from exceptions import ValidacionError
from mappings import COLUMNAS
from transformacion.transformer import convertir_numero, convertir_texto, transformar

TIPO = next(c for c in COLUMNAS if c.origen == "Tipología")  # str(100)
SLA = next(c for c in COLUMNAS if c.origen == "SLA Real")


def test_texto_none_sigue_none_y_no_se_recorta():
    assert convertir_texto(None, TIPO, 2) is None
    assert convertir_texto("Solicitud Comercial ", TIPO, 2) == "Solicitud Comercial "


def test_texto_mas_ancho_que_la_columna_convertida_falla():
    convertir_texto("x" * 100, TIPO, 2)
    with pytest.raises(ValidacionError, match="str\\(100\\)"):
        convertir_texto("x" * 101, TIPO, 2)


def test_texto_fuera_de_cp1252_pasa_a_interrogacion():
    assert convertir_texto("a→b", TIPO, 2) == "a?b"
    assert convertir_texto("Atención de Averías", TIPO, 2) == "Atención de Averías"


@pytest.mark.parametrize(
    "valor, esperado",
    [
        (1, Decimal("1.00")), (30, Decimal("30.00")), (13.5, Decimal("13.50")), (2.5, Decimal("2.50")),
        (12.494, Decimal("12.49")), (12.495, Decimal("12.50")), (12.499, Decimal("12.50")), (None, None), ("7", Decimal("7.00")),
    ],
)
def test_numero_se_conserva_como_numeric_10_2(valor, esperado):
    # Decision del usuario: el valor real del SLA se conserva (13,5 y no 14). Solo el Data Conversion
    # (r8 -> numeric(10,2)) redondea, half-up, a 2 decimales.
    resultado = convertir_numero(valor, SLA, 2)
    assert resultado == esperado
    assert resultado is None or isinstance(resultado, Decimal)


def test_numero_no_convertible_o_fuera_de_rango_falla():
    with pytest.raises(ValidacionError):
        convertir_numero("abc", SLA, 2)
    with pytest.raises(ValidacionError, match="excede"):
        convertir_numero(1e8, SLA, 2)


def test_transformar_ordena_las_columnas_como_el_destino():
    posiciones = {
        "Estado": 0, "Línea de Negocio": 1, "Motivo de contacto": 2, "Tipología": 3,
        "Subtipología": 4, "SLA Real": 5, "Dia/Hora": 6, "Condicion": 7,
    }
    fila = ("Vigente", None, "Motivo", "Tip", "Sub", 13.5, "Horas", "Laboral")
    # orden de mappings.COLUMNAS: Tipología, Día/Hora, SLA, Calendario/Laboral, Estado, Línea, Motivo, Subtipología
    assert transformar([fila], posiciones) == [("Tip", "Horas", Decimal("13.50"), "Laboral", "Vigente", None, "Motivo", "Sub")]

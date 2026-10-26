from __future__ import annotations

import logging

import mappings as m
from transformacion.cruce import aplicar_cruce
from transformacion.transformer import saltos_crlf

FLUJO = m.FLUJO_TEMP_REPORTE_CASOS
I_CASO = [c.destino for c in FLUJO.columnas].index("Número del caso")


def caso(numero: str) -> tuple:
    fila = [""] * len(FLUJO.columnas)
    fila[I_CASO] = numero
    return tuple(fila)


def test_left_join_vacio_a_null_y_sin_contacto_null():
    contactos = [("19412328", "Ana", "", "912345678", ""), ("19412330", "", "b@x.cl", "", "")]
    salida = aplicar_cruce(FLUJO, [caso("19412328"), caso("19412329"), caso("19412330")], contactos)
    assert [f[-4:] for f in salida] == [
        ("Ana", None, "912345678", None),  # '' -> NULL
        (None, None, None, None),  # LEFT JOIN sin coincidencia
        (None, "b@x.cl", None, None),
    ]
    assert FLUJO.columnas_insert[-4:] == ("Nombre de contacto", "Correo Electrónico Contacto", "Teléfono Contacto", "Móvil Contacto")


def test_igualdad_como_sql_server_ci_y_sin_espacios_finales():
    contactos = [("ab123  ", "Ana", "", "", "")]
    (fila,) = aplicar_cruce(FLUJO, [caso("AB123")], contactos)
    assert fila[-4] == "Ana"


def test_casos_repetidos_usa_el_primero_y_avisa(caplog):
    contactos = [("1", "Primero", "", "", ""), ("1", "Segundo", "", "", "")]
    with caplog.at_level(logging.WARNING):
        (fila,) = aplicar_cruce(FLUJO, [caso("1")], contactos)
    assert fila[-4] == "Primero"
    assert "repetidos" in caplog.text


def test_saltos_crlf_como_el_archivo_nuevo():
    assert saltos_crlf("a\nb\r\nc\rd") == "a\r\nb\r\nc\r\nd"
    assert saltos_crlf("sin saltos") == "sin saltos"

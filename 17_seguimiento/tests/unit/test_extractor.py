from __future__ import annotations

import pytest

import mappings as m
from exceptions import ExtraccionError
from extraccion.extractor import FuenteLocal, FuentePrecargada, leer_csv
from tests.unit.fakes import FuenteFalsa


def test_lee_el_crudo_cp1252_tal_cual_sin_encabezado():
    crudo = '"Número","Descripción"\n"1","acción"\n"2",""\n'.encode("cp1252")
    assert leer_csv(crudo, m.ARCHIVO_DESCRIPCIONES_NC) == [["1", "acción"], ["2", ""]]


def test_conserva_saltos_de_linea_dentro_de_comillas_tal_cual():
    crudo = b'"a","b"\n"1","linea1\nlinea2"\n'
    assert leer_csv(crudo, m.ARCHIVO_DESCRIPCIONES_NC) == [["1", "linea1\nlinea2"]]


def test_comillas_escapadas_y_comas_dentro_del_valor():
    crudo = b'"a","b"\n"di ""hola""","x,y"\n'
    assert leer_csv(crudo, m.ARCHIVO_DESCRIPCIONES_NC) == [['di "hola"', "x,y"]]


def test_byte_no_definido_en_cp1252_se_conserva_para_repararlo():
    # SSIS lo convertia en U+FFFD y se perdia cual byte era (0x81 = A, 0x8D = I con tilde...)
    assert leer_csv(b'"a"\n"\x8d"\n', m.ARCHIVO_DESCRIPCIONES_NC) == [["\x8d"]]


def test_archivo_vacio_falla_y_lineas_en_blanco_se_ignoran():
    with pytest.raises(ExtraccionError):
        leer_csv(b"", m.ARCHIVO_DESCRIPCIONES_NC)
    assert leer_csv(b'"a","b"\n"1","2"\n\n', m.ARCHIVO_DESCRIPCIONES_NC) == [["1", "2"]]


def test_formato_antiguo_con_punto_y_coma_no_se_parte_y_lo_detecta_la_validacion():
    # Si el bot volviera a ';', cada fila queda en una sola columna -> validar_estructura falla.
    assert leer_csv(b'"a";"b"\n"1";"2"\n', m.ARCHIVO_DESCRIPCIONES_NC) == [['1;"2"']]


def test_fuente_local_lee_bytes_y_falla_si_no_existe(tmp_path):
    (tmp_path / m.ARCHIVO_CORREOS.nombre).write_bytes(b"abc")
    fuente = FuenteLocal(tmp_path)
    assert fuente.leer(m.ARCHIVO_CORREOS) == b"abc"
    with pytest.raises(ExtraccionError):
        fuente.leer(m.ARCHIVO_HISTORIAL)


def test_fuente_precargada_descarga_una_vez_y_difiere_el_error():
    base = FuenteFalsa({m.ARCHIVO_CORREOS.nombre: b"x"}, falla={m.ARCHIVO_HISTORIAL.nombre})
    fuente = FuentePrecargada(base, [m.ARCHIVO_CORREOS, m.ARCHIVO_HISTORIAL])
    assert sorted(base.leidos) == sorted([m.ARCHIVO_CORREOS.nombre, m.ARCHIVO_HISTORIAL.nombre])
    assert fuente.leer(m.ARCHIVO_CORREOS) == b"x"
    assert fuente.leer(m.ARCHIVO_CORREOS) == b"x"
    assert base.leidos.count(m.ARCHIVO_CORREOS.nombre) == 1
    with pytest.raises(RuntimeError, match="no se pudo leer"):
        fuente.leer(m.ARCHIVO_HISTORIAL)

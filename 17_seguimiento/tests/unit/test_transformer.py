from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import Decimal

import pytest

import mappings as m
from exceptions import ValidacionError
from transformacion.transformer import transformar


def fila_correos(**valores):
    base = ["de@x.cl", "para@x.cl", "18-10-2026 10:31", "19426116", "765939593", "1", "Asunto", "Email2Case CHI", "Admin", "Enviado"]
    for i, v in valores.items():
        base[int(i[1:])] = v
    return base


def test_correos_convierte_fecha_numerico_y_texto():
    (fila,) = transformar(m.FLUJO_TEMP_CORREOS, [fila_correos()])
    columnas = [c.destino for c in m.FLUJO_TEMP_CORREOS.columnas]
    valores = dict(zip(columnas, fila))
    assert valores["Fecha correo"] == datetime(2026, 10, 18, 10, 31)
    assert valores["Es Entrante"] == Decimal(1)
    assert valores["Número del caso"] == "19426116"
    assert valores["RUC"] == "765939593"


def test_correos_replace_nbsp_antes_de_convertir_la_fecha():
    (fila,) = transformar(m.FLUJO_TEMP_CORREOS, [fila_correos(c2="18-10-2026 2:31 p.\xa0m.")])
    assert fila[2] == datetime(2026, 10, 18, 14, 31)


def test_celda_vacia_queda_como_texto_vacio_no_null():
    (fila,) = transformar(m.FLUJO_TEMP_CORREOS, [fila_correos(c4="")])
    assert fila[4] == ""


def test_fecha_vacia_falla_como_failcomponent():
    with pytest.raises(ValidacionError, match="Fecha del mensaje"):
        transformar(m.FLUJO_TEMP_CORREOS, [fila_correos(c2="")])


def test_numerico_invalido_falla():
    with pytest.raises(ValidacionError, match="Es Entrante"):
        transformar(m.FLUJO_TEMP_CORREOS, [fila_correos(c5="si")])


def test_truncamiento_failcomponent_detiene():
    with pytest.raises(ValidacionError, match="DT_WSTR\\(15\\)"):
        transformar(m.FLUJO_TEMP_CORREOS, [fila_correos(c3="1" * 16)])


def test_ancho_de_salida_del_flat_file_source():
    with pytest.raises(ValidacionError, match="Flat File Source"):
        transformar(m.FLUJO_TEMP_CORREOS, [fila_correos(c2="1" * 51)])


def fila_casos_b(**valores):
    base = ["19412328", "", "Sub", "Tipo", "Baja", "Peticion", "Sí", "3. Cliente", "Solucion", "Alta", "Ambito", "", "Funcion", ""]
    for i, v in valores.items():
        base[int(i[1:])] = v
    return base


def _col(flujo, destino):
    return [c.destino for c in flujo.columnas].index(destino)


def test_casos_b_truncamiento_ignorefailure_trunca_tipo():
    (fila,) = transformar(m.FLUJO_TEMP_CASOS_B, [fila_casos_b(c3="T" * 45)])
    assert fila[_col(m.FLUJO_TEMP_CASOS_B, "Tipo")] == "T" * 40


def test_casos_b_left_10_y_dt_str_1252():
    (fila,) = transformar(m.FLUJO_TEMP_CASOS_B, [fila_casos_b(c0="12345678901234")])
    assert fila[_col(m.FLUJO_TEMP_CASOS_B, "Número del caso")] == "1234567890"
    with pytest.raises(ValidacionError, match="1252"):
        transformar(m.FLUJO_TEMP_CASOS_B, [fila_casos_b(c0="12中")])


def test_casos_fecha_de_recepcion_es_dt_date_en_el_origen():
    fila = [""] * 42
    fila[4] = "06-10-2026 10:13"
    fila[31] = "17-10-2026 9:15"
    idx = _col(m.FLUJO_TEMP_REPORTE_CASOS, "Fecha de recepción")
    (vacia,) = transformar(m.FLUJO_TEMP_REPORTE_CASOS, [fila])
    assert vacia[idx] is None
    fila[5] = "16-10-2026 9:08"
    (con_fecha,) = transformar(m.FLUJO_TEMP_REPORTE_CASOS, [fila])
    assert con_fecha[idx] == "2026-10-16 09:08:00"
    # los demas textos de fecha pasan tal cual (los convierte el T-SQL)
    assert con_fecha[_col(m.FLUJO_TEMP_REPORTE_CASOS, "Fecha/Hora de apertura")] == "06-10-2026 10:13"


def test_comentarios_left_y_caso_publico():
    fila = ["19434355", "Melody", "23-10-2026 14:31", "1", "Comentario"]
    (out,) = transformar(m.FLUJO_TEMP_COMENTARIOS, [fila])
    valores = dict(zip([c.destino for c in m.FLUJO_TEMP_COMENTARIOS.columnas], out))
    assert valores["Número del caso"] == "19434355"
    assert valores["Caso público comentado"] == "1"
    assert valores["Fecha de creación de Comentario del caso"] == datetime(2026, 10, 23, 14, 31)


def test_error_ignorefailure_deja_null():
    col = replace(m.FLUJO_TEMP_CORREOS.columnas[2], conversion=m.Conversion(m.FECHA, error_ignora=True))
    flujo = replace(m.FLUJO_TEMP_CORREOS, columnas=(col,), reemplazos=())
    assert transformar(flujo, [fila_correos(c2="no es fecha")]) == [(None,)]


def test_reporta_varios_errores_con_fila():
    with pytest.raises(ValidacionError) as exc:
        transformar(m.FLUJO_TEMP_CORREOS, [fila_correos(), fila_correos(c2="x"), fila_correos(c5="y")])
    assert "2 error(es)" in str(exc.value)
    assert "fila 3" in str(exc.value) and "fila 4" in str(exc.value)

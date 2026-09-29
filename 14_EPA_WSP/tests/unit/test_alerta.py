"""Alerta de actualizacion (enviar_alerta_encuesta.py)."""

from datetime import date, datetime, timedelta

import pandas as pd
import pytest

import alerta
from tests.unit.fakes import FakeCarpeta, FakeCsvReader
from tools import oraculos


@pytest.mark.parametrize("dias", range(14))
def test_fecha_limite_identica_al_original_todos_los_dias_de_la_semana(dias):
    hoy = date(2026, 9, 21) + timedelta(days=dias)  # lunes 21/09/2026 ...
    assert alerta.obtener_fecha_limite(hoy) == oraculos.obtener_fecha_limite(hoy)


def test_lunes_valida_contra_el_viernes_a_las_17():
    assert alerta.obtener_fecha_limite(date(2026, 9, 28)) == datetime(2026, 9, 25, 17, 0)
    assert alerta.obtener_fecha_limite(date(2026, 9, 29)) == datetime(2026, 9, 28, 17, 0)


def _encuesta(filas):
    return pd.DataFrame(filas, columns=["fecha_de_evento", "hora_evento"], dtype=str)


def test_fecha_maxima_combina_fecha_y_hora_e_ignora_nulos():
    df = _encuesta([["2026-09-27", "22:31:00"], ["2026-09-28", ""], ["", "23:00:00"], ["2026-09-27", "08:00:00"]])
    assert alerta.obtener_fecha_maxima(df) == datetime(2026, 9, 27, 22, 31)


def test_fecha_maxima_descarta_fraccion_de_segundo_como_datediff():
    assert alerta.obtener_fecha_maxima(_encuesta([["2026-09-27", "22:31:05.900"]])) == datetime(2026, 9, 27, 22, 31, 5)


def test_fecha_maxima_sin_datos():
    assert alerta.obtener_fecha_maxima(_encuesta([["", ""]])) is None


def test_mensajes_identicos_al_original():
    lim, ahora = datetime(2026, 9, 25, 17), datetime(2026, 9, 28, 11, 49, 17)
    ok = alerta.generar_mensaje(datetime(2026, 9, 27, 22, 31), lim, ahora)
    assert ok == (
        "TABLA ENCUESTA ACTUALIZADA ✅\n\n- Tabla: dbo.ENCUESTA\n- Columna evaluada: Fecha_de_evento\n"
        "- Último registro: 27/09/2026 22:31:00\n- Fecha mínima esperada: 25/09/2026 17:00:00\n"
        "- Fecha de validación: 28/09/2026 11:49:17\n\n"
        "Resultado: La tabla contiene registros posteriores o iguales a la fecha mínima esperada."
    )
    viejo = alerta.generar_mensaje(datetime(2026, 9, 20, 10), lim, ahora)
    assert viejo.startswith("TABLA ENCUESTA DESACTUALIZADA ⚠️") and "mínima esperada..\n\n" in viejo
    vacio = alerta.generar_mensaje(None, lim, ahora)
    assert "No se encontraron fechas válidas" in vacio


def test_enviar_alerta_borra_espera_y_recrea_txt_con_bom_en_sharepoint():
    carpeta = FakeCarpeta({"resultado.txt": b"anterior"})
    esperas = []
    reader = FakeCsvReader({"ENCUESTA.csv": _encuesta([["2026-09-28", "18:00:00"]])})
    ok = alerta.enviar_alerta(
        reader, carpeta, "resultado.txt", 30, ahora=lambda: datetime(2026, 9, 29, 8), dormir=esperas.append
    )
    assert ok is True and esperas == [30]
    assert carpeta.operaciones == [("eliminar", "resultado.txt"), ("escribir", "resultado.txt")]
    contenido = carpeta.archivos["resultado.txt"]
    assert contenido.startswith(b"\xef\xbb\xbf")  # UTF-8 con BOM
    assert contenido.decode("utf-8-sig").startswith("TABLA ENCUESTA ACTUALIZADA")


def test_sin_txt_anterior_no_espera():
    carpeta, esperas = FakeCarpeta(), []
    reader = FakeCsvReader({"ENCUESTA.csv": _encuesta([["2026-09-28", "18:00:00"]])})
    alerta.enviar_alerta(reader, carpeta, "resultado.txt", 30, dormir=esperas.append)
    assert esperas == [] and "resultado.txt" in carpeta.archivos


def test_enviar_alerta_nunca_lanza_y_deja_txt_de_error():
    carpeta = FakeCarpeta()
    ok = alerta.enviar_alerta(FakeCsvReader({}), carpeta, "resultado.txt", 0, dormir=lambda s: None)
    assert ok is False
    assert carpeta.archivos["resultado.txt"].decode("utf-8-sig").startswith("ERROR EN LA VALIDACIÓN ❌")


def test_enviar_alerta_nunca_lanza_aunque_sharepoint_falle():
    carpeta = FakeCarpeta(falla_al_escribir=True)
    reader = FakeCsvReader({"ENCUESTA.csv": _encuesta([["2026-09-28", "18:00:00"]])})
    assert alerta.enviar_alerta(reader, carpeta, "resultado.txt", 0, dormir=lambda s: None) is False

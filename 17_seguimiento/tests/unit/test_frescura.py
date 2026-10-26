from __future__ import annotations

from datetime import datetime, timedelta, timezone

import mappings as m
from frescura import EstadoArchivo, ReglasFrescura, evaluar, revisar

AHORA = datetime(2026, 10, 26, 18, 0, tzinfo=timezone.utc)  # 13:00 en Lima
REGLAS = ReglasFrescura(max_min=150, ventana_min=15, reciente_min=10)
ARCHIVOS = [m.ARCHIVO_CASOS, m.ARCHIVO_NOMBRE_CONTACTO, m.ARCHIVO_CASOS_B, m.ARCHIVO_CORREOS]


def estados(*minutos, tamano=1000) -> list[EstadoArchivo]:
    """Un estado por archivo, modificado hace 'minutos'."""
    return [EstadoArchivo(a, AHORA - timedelta(minutes=mm), tamano) for a, mm in zip(ARCHIVOS, minutos)]


def test_publicacion_normal_del_bot_esta_ok():
    # bot 12:30 -> archivos entre 12:31 y 12:36, carga a las 13:00
    ev = evaluar(estados(29, 28, 27, 24), AHORA, REGLAS)
    assert ev.omitir == {} and ev.publicando == {}


def test_datos_viejos_se_omiten():
    # se perdieron dos publicaciones: archivos de las 10:30
    ev = evaluar(estados(150.5, 29, 28, 27), AHORA, REGLAS)
    assert list(ev.omitir) == [m.ARCHIVO_CASOS]
    assert "datos viejos" in ev.omitir[m.ARCHIVO_CASOS] and "maximo 150 min" in ev.omitir[m.ARCHIVO_CASOS]


def test_una_publicacion_perdida_se_tolera():
    # bot 12:30 fallo: archivos de las 11:00 (120 min) -> todavia se cargan
    ev = evaluar(estados(120, 119, 118, 116), AHORA, REGLAS)
    assert ev.omitir == {} and ev.publicando == {}


def test_fin_de_semana_todo_viejo():
    # viernes 15:30 -> lunes 07:00
    ev = evaluar(estados(3810, 3809, 3808, 3806), AHORA, REGLAS)
    assert set(ev.omitir) == set(ARCHIVOS)


def test_bot_publicando_archivo_recien_modificado():
    # el bot empezo una publicacion: Casos es nuevo y los demas todavia son de la anterior
    ev = evaluar(estados(3, 29, 28, 27), AHORA, REGLAS)
    assert set(ev.publicando) == set(ARCHIVOS)
    assert "esta publicando" in ev.publicando[m.ARCHIVO_CASOS]
    assert "version anterior" in ev.publicando[m.ARCHIVO_CORREOS]


def test_versiones_mezcladas_la_anterior_queda_en_publicacion():
    # el bot ya subio 3 archivos de las 12:30 y falta uno (sigue el de las 11:00)
    ev = evaluar(estados(25, 24, 23, 118), AHORA, REGLAS)
    assert list(ev.publicando) == [m.ARCHIVO_CORREOS]
    assert "version anterior" in ev.publicando[m.ARCHIVO_CORREOS]


def test_archivo_vacio_y_sin_metadatos():
    lista = estados(29, 28, 27, 24)
    lista[0] = EstadoArchivo(m.ARCHIVO_CASOS, AHORA - timedelta(minutes=29), 0)
    lista[1] = EstadoArchivo(m.ARCHIVO_NOMBRE_CONTACTO, None, None, "Archivo no encontrado")
    ev = evaluar(lista, AHORA, REGLAS)
    assert "vacio" in ev.omitir[m.ARCHIVO_CASOS]
    assert "no encontrado" in ev.omitir[m.ARCHIVO_NOMBRE_CONTACTO]


def test_revisar_espera_si_el_bot_esta_publicando_y_luego_carga():
    lecturas = iter([estados(2, 29, 28, 27), estados(31, 34, 33, 32)])
    esperas = []
    omitir = revisar(lambda: next(lecturas), REGLAS, reintentos=3, espera_s=300, esperar=esperas.append, ahora=lambda: AHORA)
    assert esperas == [300] and omitir == {}


def test_revisar_omite_lo_que_sigue_publicandose_tras_los_reintentos():
    esperas = []
    omitir = revisar(lambda: estados(2, 29, 28, 27), REGLAS, reintentos=3, espera_s=300, esperar=esperas.append, ahora=lambda: AHORA)
    assert esperas == [300, 300, 300]
    assert set(omitir) == set(ARCHIVOS) and all("tras 3 reintento(s)" in motivo for motivo in omitir.values())


def test_revisar_no_espera_por_datos_viejos():
    esperas = []
    omitir = revisar(lambda: estados(500, 29, 28, 27), REGLAS, esperar=esperas.append, ahora=lambda: AHORA)
    assert esperas == [] and list(omitir) == [m.ARCHIVO_CASOS]

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import mappings as m
from frescura import EstadoArchivo, evaluar, revisar

AHORA = datetime(2026, 10, 26, 18, 0, tzinfo=timezone.utc)  # 13:00 en Lima
MAX_MIN = 150
ARCHIVOS = [m.ARCHIVO_CASOS, m.ARCHIVO_NOMBRE_CONTACTO, m.ARCHIVO_CASOS_B, m.ARCHIVO_CORREOS]


def estados(*minutos, tamano=1000) -> list[EstadoArchivo]:
    """Un estado por archivo, modificado hace 'minutos'."""
    return [EstadoArchivo(a, AHORA - timedelta(minutes=mm), tamano) for a, mm in zip(ARCHIVOS, minutos)]


def test_publicacion_normal_del_bot_esta_ok():
    # bot 12:30 -> archivos entre 12:31 y 12:36, carga a las 13:00
    assert evaluar(estados(29, 28, 27, 24), AHORA, MAX_MIN) == {}


def test_no_actualizado_se_omite():
    # se perdieron dos publicaciones: Casos es de las 10:30
    omitir = evaluar(estados(150.5, 29, 28, 27), AHORA, MAX_MIN)
    assert list(omitir) == [m.ARCHIVO_CASOS]
    assert "no actualizado" in omitir[m.ARCHIVO_CASOS] and "maximo 150 min" in omitir[m.ARCHIVO_CASOS]


def test_una_publicacion_perdida_se_tolera():
    # bot 12:30 fallo: archivos de las 11:00 (120 min) -> todavia se cargan
    assert evaluar(estados(120, 119, 118, 116), AHORA, MAX_MIN) == {}


def test_bot_publicando_ahora_no_espera_y_toma_lo_que_hay():
    # el bot empezo a publicar: Casos es de hace 2 min y los demas de la publicacion anterior
    assert evaluar(estados(2, 92, 91, 89), AHORA, MAX_MIN) == {}


def test_versiones_mezcladas_dentro_del_maximo_se_cargan():
    assert evaluar(estados(25, 24, 23, 118), AHORA, MAX_MIN) == {}


def test_fin_de_semana_todo_viejo():
    # viernes 15:30 -> lunes 07:00
    assert set(evaluar(estados(3810, 3809, 3808, 3806), AHORA, MAX_MIN)) == set(ARCHIVOS)


def test_archivo_vacio_y_sin_metadatos():
    lista = estados(29, 28, 27, 24)
    lista[0] = EstadoArchivo(m.ARCHIVO_CASOS, AHORA - timedelta(minutes=29), 0)
    lista[1] = EstadoArchivo(m.ARCHIVO_NOMBRE_CONTACTO, None, None, "Archivo no encontrado")
    omitir = evaluar(lista, AHORA, MAX_MIN)
    assert "vacio" in omitir[m.ARCHIVO_CASOS]
    assert "no encontrado" in omitir[m.ARCHIVO_NOMBRE_CONTACTO]


def test_revisar_lee_una_sola_vez_y_no_espera():
    lecturas = []

    def leer():
        lecturas.append(1)
        return estados(2, 29, 28, 500)

    omitir = revisar(leer, MAX_MIN, ahora=lambda: AHORA)
    assert lecturas == [1]
    assert list(omitir) == [m.ARCHIVO_CORREOS]

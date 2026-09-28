from datetime import datetime

import pandas as pd

import alerta
from tests.unit.fakes import FakeCsvReader

AHORA = datetime(2026, 9, 28, 11, 40, 0)


def _reader(*starts):
    return FakeCsvReader({"ATENDIDA.csv": pd.DataFrame({"START_YYYYMMDD_HHMMSS": list(starts)}, dtype=str)})


def test_fecha_limite_es_las_17_del_dia_anterior():
    assert alerta.obtener_fecha_limite(AHORA) == datetime(2026, 9, 27, 17, 0, 0)


def test_actualizada(tmp_path):
    txt = tmp_path / "resultado.txt"
    ok = alerta.enviar_alerta(_reader("2026-09-27 16:00:00", "2026-09-28 07:05:23", ""), txt, 0, ahora=lambda: AHORA)
    contenido = txt.read_text(encoding="utf-8-sig")
    assert ok is True
    assert contenido.startswith("TABLA ACTUALIZADA ✅")
    assert "- Último registro: 28/09/2026 07:05:23" in contenido
    assert "- Fecha mínima esperada: 27/09/2026 17:00:00" in contenido


def test_desactualizada(tmp_path):
    txt = tmp_path / "resultado.txt"
    ok = alerta.enviar_alerta(_reader("2026-09-27 16:59:59"), txt, 0, ahora=lambda: AHORA)
    assert ok is False
    assert txt.read_text(encoding="utf-8-sig").startswith("TABLA DESACTUALIZADA ⚠️")


def test_sin_fechas_validas(tmp_path):
    txt = tmp_path / "resultado.txt"
    alerta.enviar_alerta(_reader("", ""), txt, 0, ahora=lambda: AHORA)
    assert "No se encontraron fechas válidas" in txt.read_text(encoding="utf-8-sig")


def test_borra_el_txt_anterior_y_espera_antes_de_recrearlo(tmp_path):
    txt = tmp_path / "resultado.txt"
    txt.write_text("viejo", encoding="utf-8")
    esperas = []
    alerta.enviar_alerta(_reader("2026-09-28 07:00:00"), txt, 30, ahora=lambda: AHORA, dormir=esperas.append)
    assert esperas == [30]
    assert "viejo" not in txt.read_text(encoding="utf-8-sig")


def test_error_no_detiene_y_deja_el_txt_de_error(tmp_path):
    txt = tmp_path / "resultado.txt"
    ok = alerta.enviar_alerta(FakeCsvReader({}), txt, 0, ahora=lambda: AHORA)  # ATENDIDA.csv no existe
    assert ok is False
    contenido = txt.read_text(encoding="utf-8-sig")
    assert contenido.startswith("ERROR EN LA VALIDACIÓN ❌")
    assert "ATENDIDA.csv" in contenido

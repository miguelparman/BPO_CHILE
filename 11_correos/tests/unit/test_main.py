"""Tests de main.py (punto de entrada unico): seleccion de etapas con
--desde/--solo, cuando hace falta el periodo, y restricciones de --completo."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

import main


@pytest.mark.parametrize(
    ("argv", "esperado"),
    [
        ([], ["ingesta", "bronze", "silver", "gold"]),
        (["--desde", "silver"], ["silver", "gold"]),
        (["--desde", "gold"], ["gold"]),
        (["--solo", "bronze"], ["bronze"]),
        (["--solo", "ingesta"], ["ingesta"]),
    ],
)
def test_seleccion_de_etapas(argv, esperado):
    assert main.parse_args(argv).etapas == esperado


@pytest.mark.parametrize("argv", [["--completo"], ["--solo", "bronze", "--completo"], ["--desde", "bronze", "--completo"]])
def test_completo_no_aplica_a_ingesta_ni_bronze(argv):
    with pytest.raises(SystemExit):
        main.parse_args(argv)


@pytest.mark.parametrize("argv", [["--solo", "silver", "--completo"], ["--desde", "silver", "--completo"]])
def test_completo_permitido_en_silver_y_gold(argv):
    assert main.parse_args(argv).completo


def test_desde_y_solo_son_excluyentes():
    with pytest.raises(SystemExit):
        main.parse_args(["--desde", "silver", "--solo", "gold"])


@pytest.mark.parametrize(
    ("no_copiados", "validacion", "estado", "hay_mensaje"),
    [
        (0, "OK", "OK", False),
        (0, None, "OK", False),  # gold no corrio
        (2, "OK", "ERROR", True),  # archivos que no se copiaron
        (0, "NO CUADRA", "ERROR", True),
    ],
)
def test_estado_final(no_copiados, validacion, estado, hay_mensaje):
    obtenido, mensaje = main.estado_final(no_copiados, validacion)
    assert obtenido == estado
    assert bool(mensaje) is hay_mensaje


@pytest.mark.parametrize(
    ("etapas", "completo", "necesita"),
    [
        (["ingesta"], False, False),  # la copia no usa periodo
        (["ingesta", "bronze", "silver", "gold"], False, True),
        (["silver", "gold"], True, False),  # completo: sin filtro de periodo
        (["gold"], False, True),
    ],
)
def test_necesita_periodo(etapas, completo, necesita):
    assert main._necesita_periodo(etapas, completo) is necesita


PERIODO = (datetime(2026, 9, 1), datetime(2026, 10, 1))


def _settings(inicio, fin):
    return SimpleNamespace(fecha_inicio=inicio, fecha_fin=fin)


def test_sin_aviso_con_periodo_automatico():
    assert main.aviso_periodo_manual(PERIODO, None, None, _settings("", "")) is None


def test_sin_aviso_si_la_corrida_no_usa_periodo():
    assert main.aviso_periodo_manual(None, "2026-09-01", "2026-09-30", _settings("2026-09-01", "2026-09-30")) is None


def test_aviso_con_fechas_por_linea_de_comandos():
    aviso = main.aviso_periodo_manual(PERIODO, "2026-09-01", "2026-09-30", _settings("2026-09-01", "2026-09-30"))
    assert "--fecha-inicio/--fecha-fin" in aviso
    assert "[2026-09-01 00:00, 2026-10-01 00:00)" in aviso
    assert "en vez del periodo automatico" in aviso


def test_aviso_con_fechas_en_env():
    aviso = main.aviso_periodo_manual(PERIODO, None, None, _settings("2026-09-01", "2026-09-30"))
    assert "'.env'" in aviso


def test_sin_validar_es_opcional():
    assert main.parse_args([]).sin_validar is False
    assert main.parse_args(["--solo", "gold", "--sin-validar"]).sin_validar is True

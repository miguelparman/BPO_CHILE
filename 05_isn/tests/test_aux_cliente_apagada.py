"""Las cargas de Reporte_isn_aux_cliente.csv y Reporte_isn_aux_contacto.csv estan apagadas por defecto
(config.isn_cargar_aux_cliente / isn_cargar_aux_contacto)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from isn import pipeline

BASE = {"delete_envios_consolidado_local", "tbls_auxiliares"}


@pytest.fixture
def ramas_lanzadas(monkeypatch):
    capturadas: dict = {}
    monkeypatch.setattr(pipeline, "_correr_ramas_paralelas", lambda ramas, etiqueta: capturadas.update(ramas))
    return capturadas


def _correr(monkeypatch, cliente: bool, contacto: bool) -> None:
    monkeypatch.setattr(
        pipeline, "settings", SimpleNamespace(isn_cargar_aux_cliente=cliente, isn_cargar_aux_contacto=contacto)
    )
    pipeline._contenedor_de_secuencias()


def test_ambas_apagadas_solo_quedan_2_ramas(monkeypatch, ramas_lanzadas):
    _correr(monkeypatch, cliente=False, contacto=False)
    assert set(ramas_lanzadas) == BASE


def test_cada_una_se_reactiva_por_separado(monkeypatch, ramas_lanzadas):
    _correr(monkeypatch, cliente=True, contacto=False)
    assert set(ramas_lanzadas) == BASE | {"aux_cliente"}
    ramas_lanzadas.clear()
    _correr(monkeypatch, cliente=False, contacto=True)
    assert set(ramas_lanzadas) == BASE | {"aux_contacto"}


def test_ambas_encendidas_lanza_las_4_ramas(monkeypatch, ramas_lanzadas):
    _correr(monkeypatch, cliente=True, contacto=True)
    assert set(ramas_lanzadas) == BASE | {"aux_cliente", "aux_contacto"}
    assert ramas_lanzadas["aux_cliente"] is pipeline._rama_aux_cliente
    assert ramas_lanzadas["aux_contacto"] is pipeline._rama_aux_contacto


@pytest.mark.parametrize("variable,atributo", [("ISN_CARGAR_AUX_CLIENTE", "isn_cargar_aux_cliente"), ("ISN_CARGAR_AUX_CONTACTO", "isn_cargar_aux_contacto")])
@pytest.mark.parametrize(
    "valor,esperado", [(None, False), ("false", False), ("", False), ("true", True), ("TRUE", True), ("1", True), ("si", True)]
)
def test_interruptor_por_variable_de_entorno(monkeypatch, variable, atributo, valor, esperado):
    import importlib

    import config

    if valor is None:
        monkeypatch.delenv(variable, raising=False)
    else:
        monkeypatch.setenv(variable, valor)
    try:
        recargado = importlib.reload(config)
        assert getattr(recargado.settings, atributo) is esperado
    finally:
        monkeypatch.delenv(variable, raising=False)
        importlib.reload(config)

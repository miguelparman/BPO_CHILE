from datetime import datetime

import pytest

import mappings
from exceptions import ValidacionError
from validacion.validator import Validator


def _fila(**valores):
    base = {"Caso SF": 1.0, "Fecha": datetime(2026, 1, 1), "Causa Raiz": "c", "Motivo C/R": "m", "Derivado": "d",
            "cargo": "g", "SM Quiebre": "s", "Coordinador de Quiebre": "k"}
    base.update(valores)
    return base


def test_valido():
    assert Validator().validar(mappings.ESCALAMIENTO, [_fila()]).ok


def test_fail_component_por_largo_indica_fila_excel():
    filas = [_fila(), _fila(**{"Causa Raiz": "X" * 31})]
    with pytest.raises(ValidacionError, match=r"fila 3, columna 'Causa Raiz': largo 31 > DT_STR\(30\)"):
        Validator().validar(mappings.ESCALAMIENTO, filas)


def test_fail_component_por_code_page():
    with pytest.raises(ValidacionError, match="code page 1252"):
        Validator().validar(mappings.T_ATIENDO, [_fila(cargo="✓")])


def test_fail_component_en_caso_convertido():
    with pytest.raises(ValidacionError, match="Caso SF"):
        Validator().validar(mappings.T_ATIENDO, [_fila(**{"Caso SF": 123456789012345678.0})])  # '1.23456789012346E+17'


def test_columnas_ampliadas_ya_no_truncan_los_valores_reales():
    """cargo (48) y Causa Raiz (33) truncaban a 30; ampliadas a 255."""
    assert Validator().validar(mappings.ESCALAMIENTO, [_fila(cargo="G" * 48)]).truncados == {}
    assert Validator().validar(mappings.CLOSE_THE_LOOP, [_fila(**{"Causa Raiz": "X" * 33})]).truncados == {}


def test_ignore_failure_solo_cuenta_truncados():
    resultado = Validator().validar(mappings.ESCALAMIENTO, [_fila(cargo="G" * 256), _fila(cargo="G" * 300)])
    assert resultado.ok and resultado.truncados == {"cargo": 2}


def test_close_the_loop_todo_ignore():
    resultado = Validator().validar(mappings.CLOSE_THE_LOOP, [_fila(Derivado="X" * 101, cargo="✓")])
    assert resultado.ok and resultado.truncados == {"Derivado": 1}


def test_nulos_no_se_validan():
    assert Validator().validar(mappings.GERENCIA, [dict.fromkeys(mappings.GERENCIA.columnas_origen)]).ok

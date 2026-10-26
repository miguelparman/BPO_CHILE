from __future__ import annotations

import pytest

import mappings as m
from exceptions import ValidacionError
from tests.unit.fakes import esquema_de
from validacion.validator import validar_anchos_destino, validar_esquema, validar_estructura


def test_estructura_exige_el_numero_de_columnas_del_connection_manager():
    validar_estructura(m.ARCHIVO_HISTORIAL, [["a"] * 6])
    with pytest.raises(ValidacionError, match="fila 3: 5 columnas"):
        validar_estructura(m.ARCHIVO_HISTORIAL, [["a"] * 6, ["a"] * 5])


def test_esquema_tabla_inexistente_o_sin_columna():
    with pytest.raises(ValidacionError, match="no existe"):
        validar_esquema(m.FLUJO_TEMP_HISTORIAL, {})
    esquema = esquema_de(m.FLUJO_TEMP_HISTORIAL)
    del esquema["Valor nuevo"]
    with pytest.raises(ValidacionError, match="Valor nuevo"):
        validar_esquema(m.FLUJO_TEMP_HISTORIAL, esquema)


def test_anchos_reales_de_la_columna_destino():
    # Estado: Data Conversion DT_WSTR(50) pero la staging es nvarchar(25)
    flujo = m.FLUJO_TEMP_REPORTE_CASOS
    esquema = esquema_de(flujo)
    esquema["Estado"] = ("nvarchar", 25)
    fila = [""] * len(flujo.columnas_insert)
    fila[flujo.columnas_insert.index("Estado")] = "E" * 26
    with pytest.raises(ValidacionError, match=r"\[Estado\] \(25\)"):
        validar_anchos_destino(flujo, [tuple(fila)], esquema)
    esquema["Estado"] = ("nvarchar", -1)  # MAX
    validar_anchos_destino(flujo, [tuple(fila)], esquema)


def test_anchos_de_las_columnas_que_completa_el_cruce():
    flujo = m.FLUJO_TEMP_REPORTE_CASOS
    esquema = esquema_de(flujo)
    esquema["Móvil Contacto"] = ("nvarchar", 30)
    fila = [""] * len(flujo.columnas_insert)
    fila[-1] = "9" * 31
    with pytest.raises(ValidacionError, match="Móvil Contacto"):
        validar_anchos_destino(flujo, [tuple(fila)], esquema)

import pytest

from exceptions import ValidacionError
from mappings import COLUMNAS
from validacion.validator import validar_anchos_destino, validar_encabezados, validar_esquema_destino

ENCABEZADOS = [
    "Estado", "Línea de Negocio", "Motivo de contacto", "Tipología", "Subtipología", "SLA Real", "Dia/Hora", "Condicion",
]
ESQUEMA = {
    "Estado": ("varchar", 15), "Línea de Negocio": ("varchar", 15), "Motivo de contacto": ("varchar", 50),
    "Tipología": ("varchar", 150), "Subtipología": ("varchar", 200), "SLA": ("int", None),
    "Día/Hora": ("varchar", 10), "Calendario/Laboral": ("varchar", 15), "Llave": ("varchar", 500),
}


def test_encabezados_por_nombre_y_sin_importar_el_orden():
    posiciones = validar_encabezados(list(reversed(ENCABEZADOS)) + ["Extra"])
    assert posiciones["Estado"] == len(ENCABEZADOS) - 1
    assert set(posiciones) == {c.origen for c in COLUMNAS}


def test_encabezados_falta_una_columna_falla():
    with pytest.raises(ValidacionError, match="Condicion"):
        validar_encabezados([e for e in ENCABEZADOS if e != "Condicion"])


def test_esquema_destino_ok_y_con_problemas():
    validar_esquema_destino(ESQUEMA)
    with pytest.raises(ValidacionError, match="no existe"):
        validar_esquema_destino({k: v for k, v in ESQUEMA.items() if k != "SLA"})
    with pytest.raises(ValidacionError, match="numerica"):
        validar_esquema_destino({**ESQUEMA, "SLA": ("varchar", 10)})
    # SLA puede ser int (la tabla real, antes del ajuste) o decimal (despues)
    validar_esquema_destino({**ESQUEMA, "SLA": ("decimal", None)})


def test_anchos_reales_del_destino():
    fila = ("T" * 150, "Horas", 1, "Laboral", "Vigente", "", "M", "S")
    validar_anchos_destino([fila], ESQUEMA)
    with pytest.raises(ValidacionError, match="Tipología"):
        validar_anchos_destino([("T" * 151,) + fila[1:]], ESQUEMA)

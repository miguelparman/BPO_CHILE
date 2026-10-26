import io

import pytest
from openpyxl import Workbook

from exceptions import ExtraccionError
from extraccion.extractor import FuenteLocal, leer_excel


def _xlsx(filas, hoja="SLA - Carterizado") -> bytes:
    libro = Workbook()
    libro.active.title = hoja
    for f in filas:
        libro.active.append(f)
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def test_lee_encabezados_y_filas_tal_cual():
    encabezados, filas = leer_excel(_xlsx([("A", "B"), ("x", 1.5), (None, 2)]), "SLA - Carterizado")
    assert encabezados == ["A", "B"]
    assert filas == [("x", 1.5), (None, 2)]


def test_omite_filas_totalmente_vacias():
    _, filas = leer_excel(_xlsx([("A", "B"), ("x", 1), (None, None), ("y", 2)]), "SLA - Carterizado")
    assert filas == [("x", 1), ("y", 2)]


def test_hoja_inexistente_o_archivo_invalido():
    with pytest.raises(ExtraccionError, match="no tiene la hoja"):
        leer_excel(_xlsx([("A",)], hoja="Otra"), "SLA - Carterizado")
    with pytest.raises(ExtraccionError, match="No se pudo abrir"):
        leer_excel(b"no es un xlsx", "SLA - Carterizado")


def test_fuente_local_error(tmp_path):
    with pytest.raises(ExtraccionError):
        FuenteLocal(tmp_path / "no_existe.xlsx").leer()

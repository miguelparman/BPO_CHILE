import pytest

import mappings
from exceptions import ExtraccionError
from extraccion.extractor import Extractor, FuenteLocal, FuenteSharePoint, leer_hoja
from tests.unit.fakes import CABECERA, FakeProveedor, fila, xlsx


def test_lee_las_siete_columnas_como_texto():
    filas = leer_hoja(xlsx([fila()]))
    assert filas == [dict(zip(CABECERA, ["51030001", "Place_1", "PLAT", "1-9", "Ana", "123", "a@b.cl"]))]


def test_celda_numerica_en_columna_texto_llega_null_como_ace():
    filas = leer_hoja(xlsx([fila(id_=51030001, dni=123)]))
    assert filas[0]["id"] is None and filas[0]["DNI"] is None
    assert filas[0]["Asesor"] == "Ana"


def test_filas_vacias_se_devuelven_con_todo_null():
    filas = leer_hoja(xlsx([fila(), [None] * 7]))
    assert len(filas) == 2 and all(v is None for v in filas[1].values())


def test_columnas_extra_se_ignoran_y_el_orden_no_importa():
    cabecera = ["extra", "Correo Electronico", "DNI", "Asesor", "RUT", "plataforma", "Etiqueta", "id"]
    filas = leer_hoja(xlsx([["x", "c", "9", "A", "R", "P", "E", "I"]], cabecera=cabecera))
    assert filas[0] == {"id": "I", "Etiqueta": "E", "plataforma": "P", "RUT": "R", "Asesor": "A", "DNI": "9",
                        "Correo Electronico": "c"}


def test_falta_columna_levanta_extraccion_error():
    with pytest.raises(ExtraccionError, match="faltan las columnas"):
        leer_hoja(xlsx([], cabecera=CABECERA[:-1]))


def test_sin_hoja1_levanta_extraccion_error():
    with pytest.raises(ExtraccionError, match="Hoja1"):
        leer_hoja(xlsx([], hoja="Otra"))


def test_archivo_corrupto():
    with pytest.raises(ExtraccionError, match="No se pudo abrir"):
        leer_hoja(b"no es un xlsx")


def test_fuente_local(tmp_path):
    ruta = tmp_path / "x.xlsx"
    ruta.write_bytes(xlsx([fila()]))
    assert len(Extractor(FuenteLocal(ruta)).extraer()) == 1
    with pytest.raises(ExtraccionError, match="No existe"):
        FuenteLocal(tmp_path / "no.xlsx").leer()


def test_fuente_sharepoint_descarga_la_ruta_del_dtsx_migrada():
    class Cliente:
        def download_file(self, drive_id, ruta):
            assert ruta == "REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/05 CARTERA/Place utilizados.xlsx"
            return xlsx([fila()])

    assert len(Extractor(FuenteSharePoint(FakeProveedor(Cliente()))).extraer()) == 1
    assert mappings.RUTA_REPORTING.endswith("Place utilizados.xlsx")

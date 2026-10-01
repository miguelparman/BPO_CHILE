import pytest

import mappings
from exceptions import ExtraccionError
from extraccion.extractor import extraer, parsear_archivo_plano
from tests.unit.fakes import CABECERA, FakeFuente, csv_bytes, fila_csv


def test_parsea_cabecera_filas_y_cp1252():
    a = parsear_archivo_plano(csv_bytes(fila_csv(nombre="Muñoz León, Iván")))
    assert a.cabecera == list(mappings.COLUMNAS_ORIGEN)
    assert len(a.filas) == 1
    df = a.a_dataframe()
    assert df.loc[0, "AGENT_NOMBRE"] == "Muñoz León, Iván"
    assert df.loc[0, "MES"] == "9"


def test_retain_nulls_campo_vacio_es_none():
    df = parsear_archivo_plano(csv_bytes(fila_csv(nombre=""))).a_dataframe()
    assert df.loc[0, "AGENT_NOMBRE"] is None


def test_punto_y_coma_extra_queda_en_la_ultima_columna():
    fila = fila_csv() + ";extra"
    a = parsear_archivo_plano(csv_bytes(fila))
    assert len(a.filas[0]) == 45
    assert a.filas[0][-1] == "0;extra"


def test_lf_suelto_y_comillas_son_parte_del_dato():
    a = parsear_archivo_plano(csv_bytes(fila_csv(nombre='"Ana\nMaria"')))
    assert a.filas[0][mappings.COLUMNAS_ORIGEN.index("AGENT_NOMBRE")] == '"Ana\nMaria"'


def test_byte_no_definido_en_cp1252_no_rompe_la_lectura():
    contenido = csv_bytes(fila_csv(nombre="X")).replace(b";X;", b";\x81;")
    a = parsear_archivo_plano(contenido)
    assert a.filas[0][mappings.COLUMNAS_ORIGEN.index("AGENT_NOMBRE")] == "\x81"


def test_espacio_duro_se_conserva():
    a = parsear_archivo_plano(csv_bytes(fila_csv(nombre="Ana\xa0Perez")))
    assert a.filas[0][mappings.COLUMNAS_ORIGEN.index("AGENT_NOMBRE")] == "Ana\xa0Perez"


def test_sin_crlf_final():
    contenido = (CABECERA + "\r\n" + fila_csv()).encode("cp1252")
    assert len(parsear_archivo_plano(contenido).filas) == 1


def test_archivo_vacio():
    with pytest.raises(ExtraccionError):
        parsear_archivo_plano(b"")


def test_error_de_descarga_se_envuelve():
    class Rota:
        descripcion = "x"

        def leer(self):
            raise RuntimeError("404")

    with pytest.raises(ExtraccionError, match="No se pudo descargar"):
        extraer(Rota())


def test_extraer_desde_fuente():
    assert len(extraer(FakeFuente(csv_bytes(fila_csv(), fila_csv(dia="24")))).filas) == 2

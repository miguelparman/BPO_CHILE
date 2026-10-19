from datetime import date, datetime

import pytest

import mappings
from exceptions import ExtraccionError
from extraccion.extractor import Extractor, FuenteLocal, FuenteSharePoint, leer_hoja, valor_ace
from tests.unit.fakes import CABECERA, FakeProveedor, FakeSharePoint, fila, xlsx

G = mappings.GERENCIA


def test_tipos_como_ace():
    filas = leer_hoja(xlsx([fila(datetime(2026, 10, 5, 14, 30), 12239535)]), G)
    assert filas == [
        {"Caso SF": 12239535.0, "Fecha": datetime(2026, 10, 5, 14, 30), "Causa Raiz": "c", "Motivo C/R": "m",
         "Derivado": "d", "cargo": "g", "SM Quiebre": "s", "Coordinador de Quiebre": "k"}
    ]
    assert isinstance(filas[0]["Caso SF"], float)


@pytest.mark.parametrize(
    "tipo,valor,esperado",
    [
        (mappings.CASO, "SIN CASO", None),  # texto en columna DT_R8 -> NULL (tipo minoritario)
        (mappings.CASO, "12345678", None),  # numero guardado como texto tambien
        (mappings.CASO, True, None),
        (mappings.CASO, 1.5, 1.5),
        (mappings.FECHA, "04/0272025", None),
        (mappings.FECHA, "\xa0", None),
        (mappings.FECHA, 45000, None),
        (mappings.FECHA, date(2026, 1, 2), datetime(2026, 1, 2)),
        (mappings.TEXTO, 123, None),  # numero en columna DT_WSTR -> NULL
        (mappings.TEXTO, "\xa0", "\xa0"),  # se conserva tal cual (asi esta en la tabla SSIS)
        (mappings.TEXTO, None, None),
    ],
)
def test_valor_ace(tipo, valor, esperado):
    assert valor_ace(tipo, valor) == esperado


def test_filas_vacias_se_conservan():
    filas = leer_hoja(xlsx([fila(datetime(2026, 1, 1), 1), [None] * len(CABECERA), fila(None, 2)]), G)
    assert len(filas) == 3
    assert all(v is None for v in filas[1].values())


def test_columnas_por_nombre_no_por_posicion():
    cabecera = list(reversed(CABECERA))
    filas = leer_hoja(xlsx([list(reversed(fila(datetime(2026, 1, 1), 7)))], cabecera=cabecera), G)
    assert filas[0]["Caso SF"] == 7.0 and filas[0]["Causa Raiz"] == "c"


def test_cabecera_repetida_usa_la_primera():
    cabecera = CABECERA + ["Derivado"]
    filas = leer_hoja(xlsx([fila(datetime(2026, 1, 1), 1) + ["otro"]], cabecera=cabecera), G)
    assert filas[0]["Derivado"] == "d"


def test_falta_columna():
    cabecera = [c for c in CABECERA if c != "cargo"]
    with pytest.raises(ExtraccionError, match="cargo"):
        leer_hoja(xlsx([], cabecera=cabecera), G)


def test_falta_hoja():
    with pytest.raises(ExtraccionError, match="Hoja1"):
        leer_hoja(xlsx([], hoja="Datos"), G)


def test_lee_hoja1_aunque_no_sea_la_primera():
    contenido = xlsx([fila(datetime(2026, 1, 1), 9)], otras_hojas=["Causa raiz"])
    assert leer_hoja(contenido, G)[0]["Caso SF"] == 9.0


def test_archivo_corrupto():
    with pytest.raises(ExtraccionError, match="No se pudo abrir"):
        leer_hoja(b"no es un xlsx", G)


def test_fuente_sharepoint_lee_de_reporting():
    sp = FakeSharePoint({G.ruta_reporting: xlsx([fila(datetime(2026, 1, 1), 3)])})
    assert Extractor(FuenteSharePoint(FakeProveedor(sp))).extraer(G)[0]["Caso SF"] == 3.0


def test_fuente_local(tmp_path):
    (tmp_path / G.subcarpeta).mkdir()
    (tmp_path / G.subcarpeta / G.archivo).write_bytes(xlsx([fila(datetime(2026, 1, 1), 4)]))
    assert Extractor(FuenteLocal(tmp_path)).extraer(G)[0]["Caso SF"] == 4.0
    with pytest.raises(ExtraccionError, match="No existe"):
        FuenteLocal(tmp_path).leer(mappings.T_ATIENDO)

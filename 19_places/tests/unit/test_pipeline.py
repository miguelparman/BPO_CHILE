from datetime import date

import pytest

from carga.historico import HistoricoLoader
from carga.loader import PlacesLoader
from exceptions import ConexionError, ExtraccionError
from extraccion.extractor import Extractor
from logs_proceso import LogsProceso
from pipeline import PlacesPipeline
from tests.unit.fakes import FakeDb, fila, xlsx
from transformacion.transformer import Transformer
from validacion.validator import Validator


class Fuente:
    def __init__(self, contenido=None, falla=None):
        self._c, self._f = contenido, falla

    def leer(self):
        if self._f:
            raise self._f
        return self._c

    def describir(self):
        return "fuente de prueba"


def armar(db, fuente, validar=None, escribe=True):
    return PlacesPipeline(
        validar,
        Extractor(fuente),
        Validator(),
        Transformer(),
        PlacesLoader(db) if escribe else None,
        HistoricoLoader(db, hoy=lambda: date(2026, 10, 29)) if escribe else None,
        LogsProceso(db) if escribe else None,
    )


def test_orden_log_inicio_carga_historico_log_fin():
    db = FakeDb()
    resultado = armar(db, Fuente(xlsx([fila(), fila(id_=None)]))).run()
    # transacciones: Log Inicio, historico, Log Fin; recarga de TBL_PLACES va aparte.
    assert len(db.transacciones) == 3 and len(db.recargas) == 1
    assert "LOGS_PROCESOS" in db.transacciones[0][0][0] and "'exec...'" in db.transacciones[0][0][0]
    assert "TBL_HISTORICO_PLACES" in db.transacciones[1][0][0]
    assert "'OK'" in db.transacciones[2][0][0]
    assert (resultado.filas_leidas, resultado.carga.insertadas, resultado.carga.finales) == (2, 2, 1)


def test_conexion_caida_no_toca_nada():
    db = FakeDb()

    def cae():
        raise ConexionError("sin conexion")

    with pytest.raises(ConexionError):
        armar(db, Fuente(xlsx([fila()])), validar=cae).run()
    assert db.recargas == [] and db.transacciones == []


def test_falla_la_lectura_no_hay_log_fin_ni_historico():
    db = FakeDb()
    with pytest.raises(ExtraccionError):
        armar(db, Fuente(falla=ExtraccionError("x"))).run()
    assert len(db.transacciones) == 1  # solo Log Inicio (queda 'exec...', como en SSIS)
    assert db.recargas == []


def test_valor_invalido_detiene_antes_de_truncar():
    db = FakeDb()
    with pytest.raises(Exception, match="DT_STR"):
        armar(db, Fuente(xlsx([fila(id_="123456789")]))).run()
    assert db.recargas == []


def test_solo_validar_no_escribe_en_sql():
    db = FakeDb()
    r = armar(db, Fuente(xlsx([fila()])), escribe=False).run()
    assert r.filas_leidas == 1 and r.carga is None
    assert db.recargas == [] and db.transacciones == []

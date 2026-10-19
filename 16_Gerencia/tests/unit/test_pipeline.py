from datetime import date, datetime

import pytest

import mappings
from carga.loader import VolumetriaLoader
from exceptions import CargaError, ConexionError
from extraccion.extractor import Extractor, FuenteSharePoint
from ingesta.copiar import CopiadorSharePoint
from pipeline import GerenciaPipeline
from tests.unit.fakes import FakeDb, FakeProveedor, FakeSharePoint, fila, xlsx
from transformacion.transformer import Transformer
from validacion.validator import Validator

FLUJOS = mappings.FLUJOS


def _entorno(filas_por_flujo=None, falta_en_bpo=()):
    filas_por_flujo = filas_por_flujo or {}
    bpo = FakeSharePoint(
        {f.ruta_bpo: xlsx(filas_por_flujo.get(f.nombre, [fila(datetime(2026, 10, 1, 9), 100), fila(None, "SIN CASO")]))
         for f in FLUJOS if f.nombre not in falta_en_bpo}
    )
    reporting = FakeSharePoint(carpetas=[f.carpeta_reporting for f in FLUJOS])
    return bpo, reporting


def _pipeline(bpo, reporting, db, validar=None, copiar=True, cargar=True, flujos=FLUJOS):
    destino = FakeProveedor(reporting)
    return GerenciaPipeline(
        flujos,
        validar,
        CopiadorSharePoint(FakeProveedor(bpo), destino) if copiar else None,
        Extractor(FuenteSharePoint(destino)),
        Validator(),
        Transformer(),
        VolumetriaLoader(db) if cargar else None,
    )


def test_corrida_completa():
    bpo, reporting = _entorno()
    db = FakeDb()
    resultado = _pipeline(bpo, reporting, db).run()
    assert resultado.ok
    assert [c["truncate"] for c in db.llamadas] == [f.sql_truncate for f in FLUJOS]
    gerencia = db.llamadas[0]["filas"]
    assert gerencia == [("100", date(2026, 10, 1), "c", "m", "d", "g", "s", "k"), (None, None, "c", "m", "d", "g", "s", "k")]
    assert [f.carga.finales for f in resultado.flujos] == [1, 1, 1, 1]


def test_falla_conexion_no_ejecuta_nada():
    bpo, reporting = _entorno()
    db = FakeDb()

    def validar():
        raise ConexionError("sin red")

    with pytest.raises(ConexionError):
        _pipeline(bpo, reporting, db, validar=validar).run()
    assert reporting.subidas == [] and db.llamadas == []


def test_fallo_de_copia_omite_solo_ese_flujo():
    bpo, reporting = _entorno(falta_en_bpo={"ESCALAMIENTO"})
    db = FakeDb()
    resultado = _pipeline(bpo, reporting, db).run()
    assert not resultado.ok
    assert [(f.flujo, f.ok, f.omitido) for f in resultado.flujos] == [
        ("GERENCIA", True, False), ("ESCALAMIENTO", False, True), ("CLOSE THE LOOP", True, False), ("T-ATIENDO", True, False)
    ]
    assert mappings.ESCALAMIENTO.sql_truncate not in [c["truncate"] for c in db.llamadas]


def test_fail_component_detiene_solo_ese_flujo_sin_tocar_la_tabla():
    bpo, reporting = _entorno({"T-ATIENDO": [fila(datetime(2026, 1, 1), 1, causa="X" * 31)]})
    db = FakeDb()
    resultado = _pipeline(bpo, reporting, db).run()
    t_atiendo = resultado.flujos[-1]
    assert not t_atiendo.ok and "FailComponent" in t_atiendo.error
    assert len(db.llamadas) == 3 and mappings.T_ATIENDO.sql_truncate not in [c["truncate"] for c in db.llamadas]


def test_error_de_carga_no_detiene_los_demas():
    bpo, reporting = _entorno()
    resultado = _pipeline(bpo, reporting, FakeDb(falla=CargaError("rollback"))).run()
    assert not resultado.ok and len(resultado.flujos) == 4 and all(not f.ok for f in resultado.flujos)


def test_solo_validar_no_escribe():
    bpo, reporting = _entorno()
    db = FakeDb()
    resultado = _pipeline(bpo, reporting, db, cargar=False).run()
    assert resultado.ok and db.llamadas == [] and all(f.carga is None for f in resultado.flujos)


def test_sin_copia_lee_lo_que_ya_esta_en_reporting():
    bpo, reporting = _entorno()
    reporting.archivos = {f.ruta_reporting: xlsx([fila(datetime(2026, 1, 1), 5)]) for f in FLUJOS}
    db = FakeDb()
    resultado = _pipeline(bpo, reporting, db, copiar=False, flujos=[mappings.GERENCIA]).run()
    assert resultado.ok and resultado.copias == [] and db.llamadas[0]["filas"][0][0] == "5"

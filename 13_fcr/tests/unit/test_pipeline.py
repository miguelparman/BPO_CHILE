"""Orden del Control Flow y comportamiento ante fallos (con el fake de la base)."""

import pytest

import mappings
from exceptions import PipelineError
from pipeline import FcrPipeline
from tests.unit.fakes import FakeDatabaseGateway


def _selects(periodo):
    return [(f"SELECT {b.tabla_temporal}", (periodo,)) for b in mappings.BASES]


def test_orden_del_control_flow():
    db = FakeDatabaseGateway()
    resultado = FcrPipeline(db=db).run(202609)
    assert db.eventos == [
        ("Log Inicio", ()),
        *_selects(202609),
        "BEGIN",
        ("COUNT", (202609,)),
        ("Limpia Tabla", (202609,)),
        ("INSERT TBL_FCR", 10),
        "COMMIT",
        ("Log Fin", ()),
    ]
    assert resultado.filas_insertadas == 10 and resultado.filas_borradas == 7
    assert resultado.filas_por_base == {b.tabla_temporal: 2 for b in mappings.BASES}
    assert list(db.inserted["TBL_FCR"].columns) == list(mappings.NOMBRES_DESTINO)


def test_fallo_en_el_insert_hace_rollback_del_delete_y_no_registra_log_fin():
    db = FakeDatabaseGateway()
    db.fallar_en = "TBL_FCR"
    with pytest.raises(PipelineError, match="Proceso Carga Tabla"):
        FcrPipeline(db=db).run(202609)
    assert db.rollbacks == 1 and db.commits == 0
    assert ("Log Fin", ()) not in db.eventos


def test_fallo_leyendo_origen_no_borra_nada():
    db = FakeDatabaseGateway()
    db.fallar_en = mappings.BASES[3].tabla_temporal
    with pytest.raises(PipelineError, match="extraccion"):
        FcrPipeline(db=db).run(202609)
    assert ("Limpia Tabla", (202609,)) not in db.eventos
    assert "BEGIN" not in db.eventos


def test_solo_validar_no_escribe():
    db = FakeDatabaseGateway()
    FcrPipeline(db=db).run(202609, solo_validar=True)
    assert db.eventos == _selects(202609)
    assert db.inserted == {}

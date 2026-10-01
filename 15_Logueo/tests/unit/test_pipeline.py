import pytest

from exceptions import PipelineError
from periodo import Periodo
from pipeline import ORDEN_PASOS, LogueoPipeline
from tests.unit.fakes import FakeFuente, FakeLoader, csv_bytes, fila_csv

# Orden de las tareas del .dtsx (Precedence Constraints). Lo reutiliza
# tests/equivalencia/test_equivalencia_dtsx.py para compararlo con el paquete.
ORDEN_ESPERADO = ["Log Inicio", "LOGUEO CHILE\\CARGA TABLA", "LOGUEO CHILE\\AGREGA DNI", "Log Fin", "SP"]

PERIODO = Periodo(202609, "regla dia<=4")


def _pipeline(referencia=None, filas=None):
    eventos: list = []
    loader = FakeLoader(eventos, referencia)
    fuente = FakeFuente(csv_bytes(*(filas or [fila_csv(), fila_csv(intervalo="9:00")])), eventos)
    return LogueoPipeline(loader, fuente, PERIODO), loader, eventos


def test_orden_del_control_flow():
    p, loader, eventos = _pipeline()
    r = p.run()
    assert list(ORDEN_PASOS) == ORDEN_ESPERADO
    assert r.pasos_ejecutados == ORDEN_ESPERADO
    assert eventos == [
        "Log Inicio",
        "esquema destino",
        "referencia Lookup",
        "leer archivo",
        "INSERT TBL_CONEXIONES",
        "AGREGA DNI",
        "Log Fin",
        "SP",
    ]


def test_inserta_solo_las_no_coincidentes_y_pasa_el_periodo():
    p, loader, _ = _pipeline(referencia=[("20260923", "08:30", "51030151")])
    r = p.run()
    assert r.filas_archivo == 2
    assert r.filas_coincidentes == 1
    assert loader.insertado["HORA"].tolist() == ["09:00"]
    assert r.filas_insertadas == 1
    assert loader.periodo_dni == 202609
    assert r.filas_dni == 7


@pytest.mark.parametrize("falla", ["Log Inicio", "INSERT TBL_CONEXIONES", "AGREGA DNI", "Log Fin", "SP"])
def test_un_fallo_detiene_el_proceso_como_ssis(falla):
    p, loader, eventos = _pipeline()
    loader.fallar_en.add(falla)
    with pytest.raises(PipelineError):
        p.run()
    assert eventos[-1] == falla  # nada se ejecuta despues
    if falla != "Log Fin" and falla != "SP":
        assert "Log Fin" not in eventos  # LOGS_PROCESOS queda en 'exec...'


def test_archivo_invalido_no_inserta_ni_cierra_el_log():
    p, loader, eventos = _pipeline(filas=[fila_csv(mes="SEP")])
    with pytest.raises(PipelineError, match="CARGA TABLA"):
        p.run()
    assert "INSERT TBL_CONEXIONES" not in eventos
    assert "Log Fin" not in eventos


def test_solo_validar_no_escribe():
    p, loader, eventos = _pipeline(referencia=[("20260923", "08:30", "51030151")])
    r = p.run(solo_validar=True)
    assert eventos == ["esquema destino", "referencia Lookup", "leer archivo"]
    assert r.filas_no_coincidentes == 1
    assert r.filas_insertadas == 0
    assert loader.insertado is None

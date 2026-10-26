import io

import pytest
from openpyxl import Workbook

from conexiones import Verificacion, validar_conexiones
from exceptions import ConexionError, PipelineError, ValidacionError
from mappings import MODO_PRUEBA, destino_para
from pipeline import OK, OMITIDA, TAREA_PUNTUALIDAD, TAREA_SLA, PuntualidadPipeline


# ---------------------------- conexiones ---------------------------------- #
def test_conexiones_reintenta_solo_las_fallidas_y_espera():
    llamadas = {"a": 0, "b": 0}
    esperas = []

    def a():
        llamadas["a"] += 1

    def b():
        llamadas["b"] += 1
        if llamadas["b"] < 3:
            raise RuntimeError("caida")

    validar_conexiones([Verificacion("a", a), Verificacion("b", b)], reintentos=3, espera_s=300, esperar=esperas.append)
    assert llamadas == {"a": 1, "b": 3} and esperas == [300, 300]


def test_conexiones_falla_tras_los_reintentos():
    esperas = []
    with pytest.raises(ConexionError, match="Sin conexion"):
        validar_conexiones([Verificacion("x", lambda: 1 / 0)], reintentos=2, espera_s=5, esperar=esperas.append)
    assert esperas == [5, 5]


# ------------------------------ pipeline ----------------------------------- #
class FakeLoader:
    destino = destino_para(MODO_PRUEBA)

    def __init__(self, falla_sla=False):
        self.llamadas = []
        self.falla_sla = falla_sla

    def esquema_sla(self):
        return {
            "Estado": ("varchar", 15), "Línea de Negocio": ("varchar", 15), "Motivo de contacto": ("varchar", 50),
            "Tipología": ("varchar", 150), "Subtipología": ("varchar", 200), "SLA": ("int", None),
            "Día/Hora": ("varchar", 10), "Calendario/Laboral": ("varchar", 15),
        }

    def cargar_sla(self, filas):
        self.llamadas.append(("sla", len(filas)))
        if self.falla_sla:
            raise RuntimeError("fallo SQL")
        return len(filas)

    def generar_puntualidad(self):
        self.llamadas.append(("puntualidad",))
        return 7


class FakeFuente:
    def __init__(self, contenido):
        self.contenido = contenido

    def leer(self):
        return self.contenido

    def describir(self):
        return "fake.xlsx"


def _excel(filas):
    libro = Workbook()
    libro.active.title = "SLA - Carterizado"
    for f in filas:
        libro.active.append(f)
    b = io.BytesIO()
    libro.save(b)
    return b.getvalue()


ENC = ("Estado", "Línea de Negocio", "Motivo de contacto", "Tipología", "Subtipología", "SLA Real", "Dia/Hora", "Condicion")
FILA = ("Vigente", None, "M", "T", "S", 2, "Dias", "Laboral")


def test_orden_sla_luego_puntualidad():
    loader = FakeLoader()
    r = PuntualidadPipeline(loader, FakeFuente(_excel([ENC, FILA])), "SLA - Carterizado").run()
    assert [t.tarea for t in r.tareas] == [TAREA_SLA, TAREA_PUNTUALIDAD]
    assert [t.estado for t in r.tareas] == [OK, OK]
    assert loader.llamadas == [("sla", 1), ("puntualidad",)]


def test_solo_validar_no_escribe():
    loader = FakeLoader()
    r = PuntualidadPipeline(loader, FakeFuente(_excel([ENC, FILA])), "SLA - Carterizado").run(solo_validar=True)
    assert loader.llamadas == [] and [t.estado for t in r.tareas] == [OMITIDA, OMITIDA]
    assert r.tareas[0].filas == 1


def test_si_falla_sla_no_corre_puntualidad():
    loader = FakeLoader(falla_sla=True)
    with pytest.raises(PipelineError, match="SLA PRUEBA"):
        PuntualidadPipeline(loader, FakeFuente(_excel([ENC, FILA])), "SLA - Carterizado").run()
    assert loader.llamadas == [("sla", 1)]


def test_excel_malo_se_detecta_antes_de_tocar_la_base():
    loader = FakeLoader()
    malo = _excel([ENC[:-1], FILA[:-1]])  # falta 'Condicion'
    with pytest.raises(PipelineError) as e:
        PuntualidadPipeline(loader, FakeFuente(malo), "SLA - Carterizado").run()
    assert isinstance(e.value.causa, ValidacionError) and loader.llamadas == []


def test_solo_puntualidad_no_necesita_excel():
    loader = FakeLoader()
    PuntualidadPipeline(loader, None, "SLA - Carterizado").run([TAREA_PUNTUALIDAD])
    assert loader.llamadas == [("puntualidad",)]

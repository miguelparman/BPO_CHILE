"""Tests de comun/conexiones.py: que conexiones se prueban segun las etapas,
y el flujo reintentar / cancelar / sin respuesta (reintentos automaticos)."""

from __future__ import annotations

import pytest

from comun import conexiones
from comun.conexiones import (
    CANCELAR,
    ESPERA_ENTRE_REINTENTOS_S,
    REINTENTAR,
    REINTENTOS_AUTOMATICOS,
    Verificacion,
    preguntar_reintento,
    probar,
    validar_conexiones,
    verificaciones_para,
)
from comun.config import DbSettings, Settings, SharePointDestinoSettings, SharePointOrigenSettings
from silver.mappings import TABLA_HISTORICO_PLACES, TABLA_SEGUIMIENTO


def _settings() -> Settings:
    origen = SharePointOrigenSettings("t", "c", "s", "host", "/sites/BPO", "Control Correos Chile")
    destino = SharePointDestinoSettings("t", "c", "s", "host", "/sites/ReportingFractalia", "Data Reporting", "14 CORREOS")
    return Settings(origen=origen, destino=destino)


_DB = DbSettings(server="172.17.0.162", database="CL_MOVIL", user="u", password="p")


class _Conexion:
    """Conexion simulada: falla las primeras 'fallas' veces que se prueba."""

    def __init__(self, nombre: str, fallas: int = 0) -> None:
        self.nombre = nombre
        self.fallas = fallas
        self.intentos = 0

    def probar(self) -> None:
        self.intentos += 1
        if self.intentos <= self.fallas:
            raise ConnectionError(f"{self.nombre} no responde")

    @property
    def verificacion(self) -> Verificacion:
        return Verificacion(self.nombre, self.probar)


def _respuestas(*valores):
    pendientes = list(valores)
    return lambda: pendientes.pop(0)


def _sin_preguntar():
    raise AssertionError("no deberia preguntar")


@pytest.mark.parametrize(
    ("etapas", "esperadas"),
    [
        (["ingesta", "bronze", "silver", "gold"], ["SQL Server", "HISTORICO_PLACES", "TBL_SEGUIMIENTO", "origen", "destino"]),
        (["bronze"], ["SQL Server", "destino"]),
        (["silver", "gold"], ["SQL Server", "HISTORICO_PLACES", "TBL_SEGUIMIENTO"]),
        (["gold"], ["SQL Server"]),
    ],
)
def test_verificaciones_segun_etapas(etapas, esperadas):
    nombres = [v.nombre for v in verificaciones_para(etapas, False, _settings(), _DB)]
    assert len(nombres) == len(esperadas)
    for nombre, esperado in zip(nombres, esperadas):
        assert esperado in nombre


def test_verificar_copia_solo_usa_sharepoint():
    nombres = [v.nombre for v in verificaciones_para([], True, _settings(), None)]
    assert len(nombres) == 2
    assert "origen" in nombres[0] and "destino" in nombres[1]


def test_verificaciones_sql_consultan_las_tablas_cruzadas(monkeypatch):
    consultas = []
    monkeypatch.setattr(conexiones, "_probar_sql", lambda db, consulta: consultas.append(consulta))
    for v in verificaciones_para(["silver"], False, _settings(), _DB):
        v.probar()
    assert consultas == [
        "SELECT 1",
        f"SELECT TOP 0 * FROM {TABLA_HISTORICO_PLACES}",
        f"SELECT TOP 0 * FROM {TABLA_SEGUIMIENTO}",
    ]


def test_probar_registra_todas_aunque_falle_la_primera():
    a, b = _Conexion("A", fallas=1), _Conexion("B")
    resultados = probar([a.verificacion, b.verificacion])
    assert [(r.nombre, r.ok) for r in resultados] == [("A", False), ("B", True)]
    assert resultados[0].detalle == "A no responde"
    assert b.intentos == 1


def test_todas_ok_no_pregunta():
    assert validar_conexiones([_Conexion("A").verificacion], preguntar=_sin_preguntar) is True


def test_cancelar_no_ejecuta():
    a = _Conexion("A", fallas=99)
    assert validar_conexiones([a.verificacion], preguntar=_respuestas(CANCELAR)) is False
    assert a.intentos == 1


def test_reintentar_prueba_solo_las_que_fallaron():
    a, b = _Conexion("A", fallas=1), _Conexion("B")
    assert validar_conexiones([a.verificacion, b.verificacion], preguntar=_respuestas(REINTENTAR)) is True
    assert (a.intentos, b.intentos) == (2, 1)


def test_reintentar_varias_veces_y_luego_cancelar():
    a = _Conexion("A", fallas=99)
    assert validar_conexiones([a.verificacion], preguntar=_respuestas(REINTENTAR, REINTENTAR, CANCELAR)) is False
    assert a.intentos == 3


def test_sin_respuesta_reintenta_solo_y_cancela_al_agotar():
    a = _Conexion("A", fallas=99)
    esperas = []
    assert validar_conexiones([a.verificacion], preguntar=_respuestas(None), esperar=esperas.append) is False
    assert a.intentos == 1 + REINTENTOS_AUTOMATICOS
    # El primer reintento va enseguida (ya se esperaron los 5 min de la respuesta).
    assert esperas == [ESPERA_ENTRE_REINTENTOS_S] * (REINTENTOS_AUTOMATICOS - 1)


def test_sin_respuesta_sigue_si_la_conexion_vuelve():
    a = _Conexion("A", fallas=2)
    esperas = []
    assert validar_conexiones([a.verificacion], preguntar=_respuestas(None), esperar=esperas.append) is True
    assert a.intentos == 3
    assert esperas == [ESPERA_ENTRE_REINTENTOS_S]


@pytest.mark.parametrize(
    ("lecturas", "esperado"),
    [
        (["r"], REINTENTAR),
        ([" C "], CANCELAR),
        (["x", "", "R"], REINTENTAR),  # opcion invalida: vuelve a preguntar
        ([None], None),  # sin respuesta a tiempo / sin consola
    ],
)
def test_preguntar_reintento(lecturas, esperado):
    pendientes = list(lecturas)
    assert preguntar_reintento(leer=lambda mensaje, timeout: pendientes.pop(0)) == esperado
    assert pendientes == []

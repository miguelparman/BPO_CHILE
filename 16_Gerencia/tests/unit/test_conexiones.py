import pytest

import mappings
from config import DbSettings, GraphSettings
from conexiones import Verificacion, validar_conexiones, verificaciones_para
from exceptions import ConexionError


class _Conexion:
    """Falla las primeras 'fallos' veces que se prueba."""

    def __init__(self, nombre, fallos=0):
        self.nombre, self.fallos, self.intentos = nombre, fallos, 0

    def verificacion(self):
        return Verificacion(self.nombre, self.probar)

    def probar(self):
        self.intentos += 1
        if self.intentos <= self.fallos:
            raise OSError(f"{self.nombre} no responde")


def test_todo_ok_sin_esperas():
    esperas = []
    sql = _Conexion("sql")
    validar_conexiones([sql.verificacion()], 3, 300, esperas.append)
    assert esperas == [] and sql.intentos == 1


def test_recupera_en_el_segundo_reintento_y_solo_reprueba_las_fallidas():
    esperas = []
    sql, bpo = _Conexion("sql", fallos=2), _Conexion("bpo")
    validar_conexiones([sql.verificacion(), bpo.verificacion()], 3, 300, esperas.append)
    assert esperas == [300, 300]
    assert sql.intentos == 3 and bpo.intentos == 1


def test_tres_reintentos_cada_5_min_y_termina():
    esperas = []
    sql = _Conexion("sql", fallos=99)
    with pytest.raises(ConexionError, match="sql"):
        validar_conexiones([sql.verificacion()], 3, 300, esperas.append)
    assert esperas == [300, 300, 300]  # 3 reintentos, 5 min antes de cada uno
    assert sql.intentos == 4  # intento inicial + 3 reintentos


def test_recupera_en_el_ultimo_reintento():
    sql = _Conexion("sql", fallos=3)
    validar_conexiones([sql.verificacion()], 3, 300, lambda s: None)
    assert sql.intentos == 4


_DB = DbSettings("srv", "CL_MOVIL", "u", "p")
_SP = GraphSettings("t", "c", "s", "h", "/sites/BPO")
_RP = GraphSettings("t", "c", "s", "h", "/sites/ReportingFractalia", "Data Reporting")


@pytest.mark.parametrize(
    "copiar,leer_sp,cargar,esperadas",
    [
        (True, True, True, ["SQL Server", "SharePoint origen", "SharePoint destino"]),  # corrida normal
        (True, False, False, ["SharePoint origen", "SharePoint destino"]),  # --solo-copia
        (False, True, True, ["SQL Server", "SharePoint destino"]),  # --sin-copia
        (False, False, True, ["SQL Server"]),  # --archivo-dir
        (True, True, False, ["SharePoint origen", "SharePoint destino"]),  # --solo-validar
    ],
)
def test_verificaciones_segun_la_corrida(copiar, leer_sp, cargar, esperadas):
    nombres = [v.nombre for v in verificaciones_para(mappings.FLUJOS, copiar, leer_sp, cargar, _DB, _SP, _RP)]
    assert len(nombres) == len(esperadas)
    assert all(n.startswith(e) for n, e in zip(nombres, esperadas)), nombres

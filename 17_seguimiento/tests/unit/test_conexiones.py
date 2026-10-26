from __future__ import annotations

import pytest

import mappings as m
from conexiones import Verificacion, tablas_de, validar_conexiones
from exceptions import ConexionError
from paquetes import PAQUETES, archivos_de


def test_reintenta_cada_espera_y_luego_termina():
    esperas = []
    llamadas = {"sql": 0}

    def falla():
        llamadas["sql"] += 1
        raise RuntimeError("sin red")

    with pytest.raises(ConexionError, match="SQL"):
        validar_conexiones([Verificacion("SQL", falla)], reintentos=3, espera_s=300, esperar=esperas.append)
    assert esperas == [300, 300, 300]
    assert llamadas["sql"] == 4


def test_solo_reprueba_las_que_fallaron_y_se_recupera():
    estado = {"n": 0, "ok": 0}

    def intermitente():
        estado["n"] += 1
        if estado["n"] < 2:
            raise RuntimeError("caida")

    def siempre_ok():
        estado["ok"] += 1

    validar_conexiones([Verificacion("A", intermitente), Verificacion("B", siempre_ok)], esperar=lambda s: None)
    assert estado == {"n": 2, "ok": 1}


def test_tablas_y_archivos_de_los_paquetes():
    tablas = tablas_de(PAQUETES)
    assert "[BBDD_GENERAL].[dbo].[LOGS_PROCESOS]" in tablas
    assert "[CL_TEMPORALES].[dbo].[TBL_DESCRIPCIONES_NC]" in tablas
    assert not any("PE_" in t or "TIPIFICACIONES" in t or "DATOS_CONTACTO" in t for t in tablas)
    nombres = {a.nombre for a in archivos_de(PAQUETES)}
    assert nombres == {f.archivo.nombre for f in m.TODOS_LOS_FLUJOS} | {
        m.ARCHIVO_NOMBRE_CONTACTO.nombre,  # entra por el cruce
        m.ARCHIVO_DESCRIPCIONES_NC.nombre,
    }
    assert "Reporte_Tipificaciones_Casos_Chile.csv" not in nombres
    assert archivos_de([p for p in PAQUETES if p.codigo == "07"]) == []

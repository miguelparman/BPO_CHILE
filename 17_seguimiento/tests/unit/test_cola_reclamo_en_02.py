"""Cola de reclamos: carga acumulativa agregada al paquete 02 (no existe en el .dtsx)."""

from __future__ import annotations

import pytest

import mappings as m
import sql
from exceptions import PipelineError
from paquetes import PAQUETES, archivos_de
from paquetes.base import TareaDataFlow, TareaTransaccion
from pipeline import ADVERTENCIA, OK, OMITIDA, SeguimientoPipeline
from tests.unit.fakes import FuenteFalsa, LoaderFalso, csv_crudo, esquema_de
from tests.unit.test_pipeline import _archivos_validos

P02 = PAQUETES[0]
ARCHIVO = m.ARCHIVO_COLA_RECLAMO
FLUJO = m.FLUJO_COLA_RECLAMO
ENC = [c.nombre for c in ARCHIVO.columnas]
ESQUEMA_REAL = {  # INFORMATION_SCHEMA de CL_FACTURACION.dbo.TBL_COLA_CHI_RECLAMO_PROPIETARIO
    "Número del caso": ("nvarchar", 10),
    "Propietario del caso": ("nvarchar", 125),
    "Email del propietario del caso": ("nvarchar", 125),
    "Subtipo de solicitud": ("nvarchar", 125),
}
_DF, _UPSERT = P02.tareas[-3], P02.tareas[-2]


def _correr(filas, **run):
    esquemas = {f.tabla: esquema_de(f) for f in m.TODOS_LOS_FLUJOS}
    esquemas[FLUJO.tabla] = ESQUEMA_REAL
    loader = LoaderFalso(esquemas)
    archivos = _archivos_validos()
    archivos[ARCHIVO.nombre] = csv_crudo(ENC, filas)
    return loader, SeguimientoPipeline(loader, FuenteFalsa(archivos), [P02]).run(**run)


def test_estructura_en_el_02_despues_de_casos_b_y_antes_del_log_fin():
    assert P02.codigo == "02"
    assert isinstance(_DF, TareaDataFlow) and isinstance(_UPSERT, TareaTransaccion)
    assert [t.nombre for t in _UPSERT.tareas] == [
        "Package\\CARGA COLA RECLAMO\\ACTUALIZA COLA RECLAMO",
        "Package\\CARGA COLA RECLAMO\\CARGA COLA RECLAMO",
    ]
    assert P02.tareas[0].nombre == "Package\\Log Inicio" and P02.tareas[-1].nombre == "Package\\Log Fin"
    bloque = next(b for b in P02.bloques if b.nombre == "Cola de reclamos")
    assert bloque.archivos == (ARCHIVO,) and set(bloque.tareas) == {_DF.nombre, _UPSERT.nombre}
    assert set(P02.agregadas) == {_DF.nombre, *(t.nombre for t in _UPSERT.tareas)}
    assert ARCHIVO in archivos_de([P02])
    assert FLUJO not in m.TODOS_LOS_FLUJOS and FLUJO.tabla not in m.TABLAS_TEMPORALES  # no es un flujo de los .dtsx


def test_corre_con_el_02_en_una_sola_sesion_y_hace_el_upsert_en_una_transaccion():
    loader, r = _correr([["1", "A", "a@x", ""], ["2", "B", "b@x", "S"]])
    assert all(t.estado == OK for t in r.tareas)
    assert loader.cargas[FLUJO.tabla] == [("1", "A", "a@x", ""), ("2", "B", "b@x", "S")]
    assert sum(1 for e in loader.eventos if e[0] == "sesion") == 1  # misma sesion del paquete 02
    transacciones = [e[1] for e in loader.eventos if e[0] == "transaccion"]
    assert transacciones[-1] == tuple(t.script for t in _UPSERT.tareas)  # UPDATE y luego INSERT, juntos


def test_la_temporal_se_crea_con_la_tabla_destino_como_molde():
    assert sql.crear_temporal(FLUJO.tabla, FLUJO.tipos_temporal, FLUJO.base) == (
        "DROP TABLE IF EXISTS #TBL_COLA_CHI_RECLAMO_PROPIETARIO; "
        "SELECT TOP 0 * INTO #TBL_COLA_CHI_RECLAMO_PROPIETARIO FROM [CL_FACTURACION].[dbo].[TBL_COLA_CHI_RECLAMO_PROPIETARIO];"
    )
    assert "[CL_TEMPORALES].[dbo].[TBL_SALESFORCE_REPORTE_CORREOS]" in sql.crear_temporal("TBL_SALESFORCE_REPORTE_CORREOS")


def test_los_scripts_son_acumulativos_sin_truncate_ni_delete():
    update, insert = (t.script for t in _UPSERT.tareas)
    todo = (update + insert).upper()
    assert "TRUNCATE" not in todo and "DELETE" not in todo and "DROP" not in todo
    assert "NOT EXISTS" in insert and "INSERT INTO [CL_FACTURACION].[dbo].[TBL_COLA_CHI_RECLAMO_PROPIETARIO]" in insert
    for s in (update, insert):
        assert "FROM #TBL_COLA_CHI_RECLAMO_PROPIETARIO" in s  # la #temporal del Data Flow
        assert "NULLIF" in s  # celda vacia = NULL, como el historico
        assert "ROW_NUMBER()" in s  # un caso repetido en el archivo cuenta una vez
    asigna = update.split("SET", 1)[1].split("FROM [CL_FACTURACION]")[0]
    assert "T.[Número del caso] =" not in asigna  # la clave no se modifica
    for c in ENC[1:]:
        assert f"T.[{c}] = S.[{c}]" in asigna
    assert "BIN2" in update and update.count("IS NULL") == 2 * 3  # comparacion binaria y NULL-segura


def test_solo_validar_no_escribe():
    loader, r = _correr([["1", "A", "a@x", ""]], solo_validar=True)
    assert loader.eventos == [] and {t.estado for t in r.tareas} == {OMITIDA}


def test_texto_mas_ancho_que_la_columna_destino_detiene_el_proceso():
    with pytest.raises(PipelineError, match="paquete 02"):
        _correr([["12345678901", "A", "a@x", ""]])  # Número del caso: nvarchar(10)


def test_cola_vieja_omite_solo_su_bloque_y_el_02_sigue():
    loader, r = _correr([["1", "A", "a@x", ""]], omitir={ARCHIVO: "no actualizado"})
    assert {t.tarea for t in r.advertencias} == {_DF.nombre, _UPSERT.nombre}
    tablas = {e[1] for e in loader.eventos if e[0] == "temporal"}
    assert FLUJO.tabla not in tablas and "TBL_SALESFORCE_CASOS" in tablas  # Casos y Casos B se cargan igual
    assert any(e[0] == "sql" and "Update_Carga_Casos_Chile" in e[1] for e in loader.eventos)  # el Log Fin del 02 corre


def test_cola_sin_filas_se_omite_con_advertencia():
    loader, r = _correr([])
    assert any(t.estado == ADVERTENCIA and "no trae filas" in t.detalle for t in r.advertencias)
    assert FLUJO.tabla not in {e[1] for e in loader.eventos if e[0] == "temporal"}

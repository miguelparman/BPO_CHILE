"""Tests de gold/cargar.py: orden y parametros de la carga del modelo estrella
(dimensiones antes que hechos, calendario por anios enteros, periodo vs
completo) y la validacion posterior. El T-SQL en si se valida en vivo contra
CL_MOVIL (ver README)."""

from __future__ import annotations

import re
from datetime import date, datetime

import pandas as pd

from comun.ejecucion import Ejecucion
from gold.cargar import cargar_periodo_gold, recargar_gold_completo, validar
from gold.mappings import (
    ESQUEMA_GOLD,
    PROCESO_CARGA_COMPLETO,
    PROCESO_CARGA_PERIODO,
    TABLA_DIM_ASUNTO_AGRUPADO,
    TABLA_DIM_BANDEJA,
    TABLA_DIM_FECHA,
    TABLA_DIM_JEFATURA,
    TABLA_DIM_TIPO,
    TABLA_FACT_MENSAJE,
)
from bronze.mappings import TABLA_BANDEJAS, TABLA_REGISTRO
from silver.mappings import REGLAS_ASUNTO_AGRUPADO, TABLA_BANDEJAS_SILVER
from tests.unit.fakes import FakeDatabaseGateway

_PERIODO = (datetime(2026, 9, 1), datetime(2026, 10, 1))
_EJECUCION = Ejecucion(id_ejecucion=42, fecha_carga=datetime(2026, 9, 24, 7, 30, 0))
_AUDITORIA_PERIODO = ("dbo.TBL_CORREO_REGISTRO_SILVER", PROCESO_CARGA_PERIODO, 42, datetime(2026, 9, 24, 7, 30, 0))
_AUDITORIA_COMPLETO = ("dbo.TBL_CORREO_REGISTRO_SILVER", PROCESO_CARGA_COMPLETO, 42, datetime(2026, 9, 24, 7, 30, 0))


def _rango(desde: date, hasta: date) -> pd.DataFrame:
    return pd.DataFrame({"DESDE": [desde], "HASTA": [hasta]})


def _tabla_de(sql: str) -> str:
    """Tabla gold que escribe la sentencia (INSERT INTO / MERGE / DELETE FROM)."""
    encontrada = re.search(rf"(?:INSERT INTO|MERGE|DELETE FROM) \[{ESQUEMA_GOLD}\]\.\[(\w+)\]", sql)
    return encontrada.group(1) if encontrada else "?"


def test_periodo_carga_dimensiones_antes_que_hechos():
    gateway = FakeDatabaseGateway()
    gateway.resultados_select = [_rango(date(2026, 9, 16), date(2026, 9, 23))]

    cargar_periodo_gold(gateway, *_PERIODO, _EJECUCION)

    tablas = [_tabla_de(sql) for sql, _ in gateway.deletes]
    assert tablas == [
        TABLA_DIM_FECHA,
        TABLA_DIM_TIPO,
        TABLA_DIM_ASUNTO_AGRUPADO,
        TABLA_DIM_JEFATURA,
        TABLA_DIM_BANDEJA,
        TABLA_FACT_MENSAJE,  # DELETE del periodo
        TABLA_FACT_MENSAJE,  # INSERT del periodo
    ]
    assert gateway.truncated_tables == []


def test_periodo_borra_e_inserta_hechos_del_mismo_rango():
    gateway = FakeDatabaseGateway()
    gateway.resultados_select = [_rango(date(2026, 9, 16), date(2026, 9, 23))]

    cargar_periodo_gold(gateway, *_PERIODO, _EJECUCION)

    (sql_delete, params_delete), (sql_insert, params_insert) = gateway.deletes[-2:]
    assert sql_delete.startswith("DELETE") and params_delete == _PERIODO
    assert "INSERT INTO" in sql_insert and "WHERE" in sql_insert
    # Auditoria (TABLA_ORIGEN, PROCESO_CARGA, ID_EJECUCION, FECHA_CARGA) y luego el periodo.
    assert params_insert == _AUDITORIA_PERIODO + _PERIODO
    for columna in ("TABLA_ORIGEN", "PROCESO_CARGA", "ID_EJECUCION", "FECHA_CARGA"):
        assert columna in sql_insert


def test_calendario_se_completa_por_anios_enteros():
    gateway = FakeDatabaseGateway()
    # Un periodo que cruza el anio (hora local) -> calendario de ambos anios completos.
    gateway.resultados_select = [_rango(date(2025, 12, 31), date(2026, 1, 2))]

    cargar_periodo_gold(gateway, datetime(2026, 1, 1), datetime(2026, 1, 3), _EJECUCION)

    _, params_fecha = gateway.deletes[0]
    assert params_fecha == (date(2025, 1, 1), date(2026, 12, 31))


def test_sin_datos_en_el_periodo_no_toca_el_calendario():
    gateway = FakeDatabaseGateway()
    gateway.resultados_select = [_rango(None, None)]

    cargar_periodo_gold(gateway, *_PERIODO, _EJECUCION)

    assert TABLA_DIM_FECHA not in [_tabla_de(sql) for sql, _ in gateway.deletes]


def test_dim_asunto_recibe_todos_los_grupos_de_las_reglas():
    gateway = FakeDatabaseGateway()
    gateway.resultados_select = [_rango(date(2026, 9, 16), date(2026, 9, 23))]

    cargar_periodo_gold(gateway, *_PERIODO, _EJECUCION)

    _, params = next((sql, p) for sql, p in gateway.deletes if _tabla_de(sql) == TABLA_DIM_ASUNTO_AGRUPADO)
    assert params == tuple(regla.grupo for regla in REGLAS_ASUNTO_AGRUPADO)


def test_completo_trunca_solo_hechos_e_inserta_sin_filtro():
    gateway = FakeDatabaseGateway()
    gateway.resultados_select = [_rango(date(2026, 9, 16), date(2026, 9, 23))]

    recargar_gold_completo(gateway, _EJECUCION)

    assert gateway.truncated_tables == [TABLA_FACT_MENSAJE]
    assert not any(sql.lstrip().startswith("DELETE") for sql, _ in gateway.deletes)
    sql_insert, params_insert = gateway.deletes[-1]
    assert "INSERT INTO" in sql_insert and "WHERE" not in sql_insert
    assert params_insert == _AUDITORIA_COMPLETO


def test_gold_lee_solo_de_silver_nunca_de_bronze():
    gateway = FakeDatabaseGateway()
    gateway.resultados_select = [_rango(date(2026, 9, 16), date(2026, 9, 23))]

    cargar_periodo_gold(gateway, *_PERIODO, _EJECUCION)
    recargar_gold_completo(gateway, _EJECUCION)

    sentencias = [s for s, _ in gateway.deletes] + [s for s, _ in gateway.selects]
    for tabla_bronze in (TABLA_REGISTRO, TABLA_BANDEJAS):
        assert not any(f"[{tabla_bronze}]" in s for s in sentencias), tabla_bronze
    assert any(f"[{TABLA_BANDEJAS_SILVER}]" in s for s in sentencias)


def test_validar_ok_y_no_cuadra():
    gateway = FakeDatabaseGateway()
    def _fila(silver, fact, sin_clave, sin_auditoria, sin_jefatura=0):
        return pd.DataFrame(
            {
                "FILAS_SILVER": [silver],
                "FILAS_FACT": [fact],
                "FILAS_SIN_BANDEJA_O_TIPO": [sin_clave],
                "FILAS_SIN_AUDITORIA": [sin_auditoria],
                "FILAS_SIN_JEFATURA": [sin_jefatura],
            }
        )

    gateway.resultados_select = [
        _fila(10, 10, 0, 0),
        _fila(10, 9, 0, 0),
        _fila(10, 10, 1, 0),
        _fila(10, 10, 0, 3),  # filas sin columnas de auditoria -> no cuadra
        _fila(10, 10, 0, 0, 4),  # sin jefatura: solo advertencia, cuadra igual
    ]

    assert validar(gateway, _PERIODO) is True
    assert validar(gateway, _PERIODO) is False
    assert validar(gateway, None) is False
    assert validar(gateway, _PERIODO) is False
    assert validar(gateway, _PERIODO) is True
    assert gateway.selects[0][1] == _PERIODO * 5
    assert gateway.selects[2][1] == ()

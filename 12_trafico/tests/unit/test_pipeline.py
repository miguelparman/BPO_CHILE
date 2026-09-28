"""Orden del Control Flow y manejo de fallos del orquestador."""

from pathlib import Path

import pytest

import mappings
from exceptions import PipelineError, ValidacionError
from pipeline import TraficoPipeline
from tests.unit.fakes import FakeCsvReader, FakeDatabaseGateway, csv_minimo, csvs_minimos
from tests.unit.test_transformer import _temporales_minimas


def _build(archivos=None, alerta=None):
    eventos: list = []
    db_temp = FakeDatabaseGateway("CL_TEMPORALES", eventos)
    db_traf = FakeDatabaseGateway("CL_TRAFICO", eventos)
    db_temp.tables = _temporales_minimas()
    llamadas_alerta = []

    def alerta_fake(reader, txt, espera):
        llamadas_alerta.append(txt)
        eventos.append(("-", "enviar_alerta_trafico"))
        if alerta:
            return alerta()
        return True

    pipeline = TraficoPipeline(
        db_temporales=db_temp,
        db_trafico=db_traf,
        csv_reader=FakeCsvReader(archivos if archivos is not None else csvs_minimos()),
        alerta_txt_path=Path("resultado.txt"),
        enviar_alerta=alerta_fake,
    )
    return pipeline, eventos, db_temp, db_traf


def _nombres(eventos):
    return [e[1] for e in eventos]


def test_ejecuta_las_tareas_en_el_orden_del_control_flow():
    pipeline, eventos, _, db_traf = _build()
    resultado = pipeline.run(202609)

    esperado = (
        ["Log Inicio", "enviar_alerta_trafico", "BEGIN", "TRUNCA TABLAS"]
        + [f"INSERT {o.tabla_temporal}" for o in mappings.ORIGENES]
        + ["COMMIT", "UPDATE"]
        + [n for n, _ in __import__("sql").LIMPIA_TEMPORALES]
        + [f"SELECT {o.tabla_temporal}" for o in mappings.ORIGENES]
        + ["BEGIN", "DELETE PERIODO"]
        + [f"INSERT {d.tabla}" for d in mappings.DESTINOS]
        + ["COMMIT", "UPDATE_WSP", "Log Fin"]
    )
    assert _nombres(eventos) == esperado
    # Orden exacto de la secuencia TEMPORALES del .dtsx
    assert [o.paso for o in mappings.ORIGENES] == ["Atendidas", "Abandono", "Transfer", "Outbound", "Cleared", "Callback", "Cross_In"]
    assert resultado.filas_temporales["TBL_TRAFICO_ATENDIDA"] == 1


def test_cada_tarea_corre_en_el_connection_manager_del_dtsx():
    pipeline, eventos, _, _ = _build()
    pipeline.run(202609)
    conexion = {e[1]: e[0] for e in eventos}
    for tarea in ("Log Inicio", "DELETE PERIODO", "Log Fin"):
        assert conexion[tarea] == "CL_TRAFICO"
    for tarea in ("TRUNCA TABLAS", "UPDATE", "UPDATE RUT", "LLAMA CCAA?", "UPDATE_WSP"):
        assert conexion[tarea] == "CL_TEMPORALES"


def test_delete_periodo_recibe_user_periodo():
    pipeline, eventos, _, _ = _build()
    pipeline.run(202608)
    assert ("CL_TRAFICO", "DELETE PERIODO", (202608,)) in eventos


def test_csv_invalido_detiene_antes_de_truncar_nada():
    archivos = csvs_minimos()
    archivos["OUTBOUND.csv"] = csv_minimo(mappings.ORIGENES[3], [{"T_TALK": "abc"}])
    pipeline, eventos, _, _ = _build(archivos)
    with pytest.raises(PipelineError) as err:
        pipeline.run(202609)
    assert isinstance(err.value.causa, ValidacionError)
    assert "TRUNCA TABLAS" not in _nombres(eventos)
    assert "Log Fin" not in _nombres(eventos)  # LOGS_PROCESOS queda en 'exec...', como en SSIS


def test_csv_faltante_detiene_antes_de_truncar():
    archivos = csvs_minimos()
    del archivos["cross_inbound.csv"]
    pipeline, eventos, _, _ = _build(archivos)
    with pytest.raises(PipelineError, match="cross_inbound.csv"):
        pipeline.run(202609)
    assert "TRUNCA TABLAS" not in _nombres(eventos)


def test_fallo_de_la_alerta_no_detiene_el_proceso():
    pipeline, eventos, _, _ = _build(alerta=lambda: False)
    resultado = pipeline.run(202609)
    assert resultado.alerta_ok is False
    assert _nombres(eventos)[-1] == "Log Fin"


def test_fallo_al_insertar_una_temporal_hace_rollback_de_todas():
    pipeline, eventos, db_temp, _ = _build()
    db_temp.fallar_en = "TBL_TRAFICO_CALLBACK"
    with pytest.raises(PipelineError, match="TBL_TRAFICO_CALLBACK"):
        pipeline.run(202609)
    assert db_temp.rollbacks == 1 and db_temp.commits == 0
    assert "UPDATE" not in _nombres(eventos)


def test_fallo_en_carga_no_deja_el_periodo_borrado():
    pipeline, eventos, _, db_traf = _build()
    db_traf.fallar_en = "TBL_CALLBACK"
    with pytest.raises(PipelineError):
        pipeline.run(202609)
    # DELETE PERIODO + inserts en una transaccion: rollback del conjunto
    assert db_traf.rollbacks == 1
    assert _nombres(eventos)[-1] == "ROLLBACK"


def test_solo_validar_no_escribe_nada():
    pipeline, eventos, _, _ = _build()
    resultado = pipeline.run(202609, solo_validar=True)
    assert eventos == []  # ni Log Inicio, ni alerta, ni truncados
    assert resultado.filas_temporales["TBL_TRAFICO_ATENDIDA"] == 1

"""Orden del Control Flow y manejo de fallos del orquestador."""

import pytest

import mappings
from config import MedalliaSettings
from exceptions import PipelineError
from pipeline import EpaWspPipeline
from tests.unit.fakes import (
    FakeCarpeta, FakeCsvReader, FakeDatabaseGateway, csv_de, csv_medallia_df, csvs_minimos, fila_wsp,
)


def _build(archivos=None, descarga=None, estricto=False):
    eventos: list = []
    dbs = {n: FakeDatabaseGateway(n, eventos) for n in ("BBDD_GENERAL", "CL_CALIDAD", "CL_TEMPORALES_INDICADORES")}
    carpeta = FakeCarpeta()

    def alerta_fake(reader, destino, archivo, espera):
        assert destino is carpeta and archivo == "resultado.txt"
        eventos.append(("-", "enviar_alerta_encuesta_py"))
        return True

    def descarga_fake(settings, destino):
        assert destino is carpeta
        eventos.append(("-", "DESCARGA_MEDALLIA"))
        if descarga:
            descarga()
        return destino.ruta(settings.archivo)

    def leer_fake(origen, nombre):
        assert origen is carpeta and nombre == "Encuestas_Medallia.csv"
        eventos.append(("-", "leer Encuestas_Medallia.csv"))
        return csv_medallia_df([{}, {"ID de encuesta": "2"}])

    pipeline = EpaWspPipeline(
        db_general=dbs["BBDD_GENERAL"],
        db_calidad=dbs["CL_CALIDAD"],
        db_indicadores=dbs["CL_TEMPORALES_INDICADORES"],
        csv_reader=FakeCsvReader(archivos if archivos is not None else csvs_minimos()),
        medallia=MedalliaSettings(usuario="u", password="p"),
        carpeta_medallia=carpeta,
        estricto=estricto,
        enviar_alerta=alerta_fake,
        descargar_medallia=descarga_fake,
        leer_medallia=leer_fake,
    )
    return pipeline, eventos, dbs


def _nombres(eventos):
    return [e[1] for e in eventos]


ORDEN_ESPERADO = [
    "Log_Inicio",
    "enviar_alerta_encuesta_py",
    # WSP
    "BEGIN", "DELETE TBL_ENCUESTAS_WSP_MEDALLIA", "INSERT TBL_ENCUESTAS_WSP_MEDALLIA", "COMMIT",
    # EPA_ISN
    "BEGIN", "DELETE TBL_ENCUESTAS_CHILE <desde", "DELETE TBL_ENCUESTAS_CHILE", "INSERT TBL_ENCUESTAS_CHILE", "COMMIT",
    "SP_EPA_ISN_CHILE",
    # MEDALIA
    "DESCARGA_MEDALLIA", "leer Encuestas_Medallia.csv",
    "BEGIN", "TRUNCATE TBL_ENCUESTAS_MEDALLIA", "INSERT TBL_ENCUESTAS_MEDALLIA", "COMMIT",
    "SP_PROCESO_ENCUESTAS_MEDALLIA",
    "Log_Fin",
]


def test_ejecuta_las_tareas_en_serie_en_el_orden_del_control_flow():
    pipeline, eventos, dbs = _build()
    r = pipeline.run()
    assert _nombres(eventos) == ORDEN_ESPERADO
    assert r.exitoso and r.log_fin
    assert r.filas == {"TBL_ENCUESTAS_WSP_MEDALLIA": 1, "TBL_ENCUESTAS_CHILE": 2, "TBL_ENCUESTAS_MEDALLIA": 2}
    assert r.periodos["TBL_ENCUESTAS_CHILE"] == [202608, 202609]


def test_cada_tarea_usa_su_connection_manager():
    pipeline, eventos, _ = _build()
    pipeline.run()
    por_tarea = {e[1]: e[0] for e in eventos}
    assert por_tarea["Log_Inicio"] == por_tarea["Log_Fin"] == "BBDD_GENERAL"
    assert por_tarea["SP_EPA_ISN_CHILE"] == por_tarea["SP_PROCESO_ENCUESTAS_MEDALLIA"] == "CL_CALIDAD"
    assert por_tarea["DELETE TBL_ENCUESTAS_CHILE"] == "CL_TEMPORALES_INDICADORES"


def test_delete_de_la_ventana_con_los_periodos_del_csv():
    pipeline, eventos, _ = _build()
    pipeline.run()
    deletes = {e[1]: e[2] for e in eventos if e[1].startswith("DELETE")}
    assert deletes["DELETE TBL_ENCUESTAS_CHILE"] == ("202608", "202609")  # periodo_evento es nvarchar
    assert deletes["DELETE TBL_ENCUESTAS_CHILE <desde"] == (202601,)
    assert deletes["DELETE TBL_ENCUESTAS_WSP_MEDALLIA"] == (202609,)  # Periodo es int


def test_fallo_de_un_traslado_no_toca_su_tabla_y_el_proceso_continua():
    archivos = csvs_minimos()
    archivos[mappings.WSP.archivo] = csv_de([fila_wsp(SurveyID="no-es-int")])
    pipeline, eventos, dbs = _build(archivos)
    r = pipeline.run()
    nombres = _nombres(eventos)
    assert "DELETE TBL_ENCUESTAS_WSP_MEDALLIA" not in nombres  # tabla intacta
    assert "INSERT TBL_ENCUESTAS_CHILE" in nombres and "SP_EPA_ISN_CHILE" in nombres
    assert "Log_Fin" in nombres  # como en SSIS: el Execute Process fallido no detiene el paquete
    assert not r.exitoso and r.pasos_fallidos[0][0] == "WSP"


def test_fallo_del_insert_hace_rollback_del_delete():
    pipeline, eventos, dbs = _build()
    dbs["CL_TEMPORALES_INDICADORES"].fallar_en = {"INSERT TBL_ENCUESTAS_CHILE"}
    r = pipeline.run()
    assert dbs["CL_TEMPORALES_INDICADORES"].rollbacks == 1
    assert [p for p, _ in r.pasos_fallidos] == ["EPA_ISN"]


def test_fallo_de_sp_epa_isn_no_ejecuta_log_fin_pero_si_medallia():
    pipeline, eventos, dbs = _build()
    dbs["CL_CALIDAD"].fallar_en = {"SP_EPA_ISN_CHILE"}
    r = pipeline.run()
    nombres = _nombres(eventos)
    assert "SP_PROCESO_ENCUESTAS_MEDALLIA" in nombres  # rama paralela en SSIS
    assert "Log_Fin" not in nombres and not r.log_fin


def test_fallo_de_la_descarga_medallia_carga_el_csv_existente():
    def falla():
        raise RuntimeError("portal caido")

    pipeline, eventos, _ = _build(descarga=falla)
    r = pipeline.run()
    nombres = _nombres(eventos)
    assert "INSERT TBL_ENCUESTAS_MEDALLIA" in nombres and "Log_Fin" in nombres
    assert r.medallia_descargado is None and r.pasos_fallidos[0][0] == "MEDALIA / DESCARGA_MEDALLIA"


def test_insert_masivo_medallia_fallido_reintenta_fila_a_fila():
    pipeline, eventos, dbs = _build()
    ind = dbs["CL_TEMPORALES_INDICADORES"]
    ind.fallar_en = {"INSERT TBL_ENCUESTAS_MEDALLIA"}
    ind.filas_que_fallan = {2}
    r = pipeline.run()
    nombres = _nombres(eventos)
    assert "INSERT FILA A FILA TBL_ENCUESTAS_MEDALLIA" in nombres
    assert r.filas["TBL_ENCUESTAS_MEDALLIA"] == 1 and r.medallia_rechazadas == 1


def test_fallo_de_log_inicio_detiene_todo():
    pipeline, eventos, dbs = _build()
    dbs["BBDD_GENERAL"].fallar_en = {"Log_Inicio"}
    with pytest.raises(PipelineError, match="Log_Inicio"):
        pipeline.run()
    assert _nombres(eventos) == ["Log_Inicio"]


def test_modo_estricto_se_detiene_en_el_primer_fallo():
    archivos = csvs_minimos()
    del archivos[mappings.WSP.archivo]
    pipeline, eventos, _ = _build(archivos, estricto=True)
    with pytest.raises(PipelineError, match="WSP"):
        pipeline.run()
    assert "INSERT TBL_ENCUESTAS_CHILE" not in _nombres(eventos)


def test_solo_validar_no_escribe_nada():
    pipeline, eventos, _ = _build()
    r = pipeline.run(solo_validar=True)
    escrituras = [n for n in _nombres(eventos) if n.split()[0] in ("DELETE", "INSERT", "TRUNCATE", "BEGIN")]
    assert escrituras == []
    assert "Log_Inicio" not in _nombres(eventos) and "DESCARGA_MEDALLIA" not in _nombres(eventos)
    assert r.filas["TBL_ENCUESTAS_CHILE"] == 2

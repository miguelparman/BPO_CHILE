"""Previsto (TBL_PREVISTO_CL): transformacion, regla acumulativa y tolerancia a fallos en el pipeline."""

from datetime import date, time
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

import previsto
from exceptions import ValidacionError
from pipeline import TraficoPipeline
from tests.unit.fakes import FakeCsvReader, FakeDatabaseGateway, csvs_minimos
from tests.unit.test_transformer import _temporales_minimas

HOY = date(2026, 11, 23)


def _csv(filas):
    base = dict(PROVEEDOR="Fractalia", REQUERIDOVOZ="99", PRONOSTICOTMO="255", REQUERIDOCALLBACK="0,0643",
                REQUERIDOMULTISKILL="0", REQUERIDO="2,06", AGENTEPROGRAMADO="3", AGENTEOJT="0")
    return pd.DataFrame(
        [{**base, "FECHA": f, "INTERVALO": i, "PCRC": p, "PRONOSTICO": v} for f, i, p, v in filas], dtype=str
    )


def test_transformar_mapea_columnas_y_formatos():
    df = previsto.transformar(_csv([("2026-09-01", "23:30:00", "Usuarios Empresa", "2"),
                                    ("2026-09-01", "00:00:00", "Usuarios Empresa", "1,5")]))
    assert list(df.columns) == previsto.COLUMNAS_TABLA
    fila = df.iloc[0]
    assert (fila.Servicio, fila.Fecha, fila.Tramo) == ("USUARIOS", date(2026, 9, 1), time(23, 30))
    assert fila.ID_Tramo == "1/09/202623:30"  # d/MM/yyyy (dia sin cero, como 2025) + HH:mm, sin separador
    assert previsto.id_tramo(date(2026, 11, 28), time(0, 30)) == "28/11/202600:30"
    assert fila.Tramo_Horario == "23:30-24:00"  # el ultimo tramo termina en 24:00
    assert fila.Prev_Voz == Decimal("2.0000") and fila.Prev_Chat == Decimal("0.0000")
    assert (df["Prev_Voz"] != Decimal("99")).all()  # REQUERIDOVOZ (99 en el CSV de prueba) no se usa
    assert df.iloc[1].Servicio == "USUARIOS" and df.iloc[1].Prev_Voz == Decimal("1.5000")
    assert df.iloc[1].Tramo_Horario == "00:00-00:30"


def test_transformar_solo_carga_usuarios_e_ignora_carterizados_y_triadas():
    df = previsto.transformar(_csv([
        ("2026-09-01", "22:30:00", "Usuarios Empresa", "2"),
        ("2026-09-01", "22:30:00", "PYMES CARTERIZADOS", "0"),
        ("2026-09-01", "22:30:00", "TRIADA NO CARTERIZADO MICRO", "0"),
    ]))
    assert list(df["Servicio"]) == ["USUARIOS"]
    with pytest.raises(ValidacionError, match="servicios a cargar"):  # solo traia ignorados
        previsto.transformar(_csv([("2026-09-01", "22:30:00", "PYMES CARTERIZADOS", "0")]))


@pytest.mark.parametrize("fila", [
    ("2026-09-01", "22:30:00", "OTRO SERVICIO", "1"),  # PCRC sin mapeo
    ("2026-09-01", "22:15:00", "Usuarios Empresa", "1"),  # fuera de la grilla de 30 min
    ("01/09/2026", "22:30:00", "Usuarios Empresa", "1"),  # fecha no ISO
    ("2026-09-01", "22:30:00", "Usuarios Empresa", "abc"),
    ("2026-09-01", "22:30:00", "Usuarios Empresa", "-1"),
])
def test_transformar_rechaza_datos_invalidos(fila):
    with pytest.raises(ValidacionError):
        previsto.transformar(_csv([fila]))


def test_transformar_rechaza_llave_repetida_cabecera_incompleta_y_vacio():
    f = ("2026-09-01", "22:30:00", "Usuarios Empresa", "1")
    with pytest.raises(ValidacionError, match="repetida"):
        previsto.transformar(_csv([f, f]))
    with pytest.raises(ValidacionError, match="faltan las columnas"):
        previsto.transformar(_csv([f]).drop(columns=["PRONOSTICO"]))
    with pytest.raises(ValidacionError, match="no trae filas"):
        previsto.transformar(_csv([f]).iloc[0:0])


def _existente(*filas):
    return pd.DataFrame(filas, columns=["Servicio", "Fecha", "Tramo", "Prev_Voz"])


def test_planificar_inserta_faltantes_del_pasado_y_reemplaza_el_futuro_sin_tocar_lo_existente():
    archivo = previsto.transformar(_csv([
        ("2026-11-22", "10:00:00", "Usuarios Empresa", "5"),  # pasado, ya existe (valor distinto)
        ("2026-11-22", "10:30:00", "Usuarios Empresa", "6"),  # pasado, falta -> insertar
        ("2026-11-23", "00:00:00", "Usuarios Empresa", "7"),  # HOY cuenta como pasado: falta -> insertar
        ("2026-11-24", "00:00:00", "Usuarios Empresa", "8"),  # manana: futuro -> reemplazar
    ]))
    existente = _existente(("USUARIOS", date(2026, 11, 22), time(10, 0), Decimal("1.0000")))
    plan = previsto.planificar(archivo, existente, HOY, futuro_en_tabla=10)
    assert sorted(plan.insertar_pasado["Tramo"]) == [time(0, 0), time(10, 30)]
    assert list(plan.reemplazar_futuro["Fecha"]) == [date(2026, 11, 24)]
    assert (plan.pasado_existente, plan.pasado_distinto, plan.futuro_en_tabla) == (1, 1, 10)


def test_planificar_segunda_corrida_no_inserta_nada_del_pasado():
    archivo = previsto.transformar(_csv([("2026-11-22", "10:00:00", "Usuarios Empresa", "5")]))
    existente = _existente(("USUARIOS", date(2026, 11, 22), time(10, 0), Decimal("5.0000")))
    plan = previsto.planificar(archivo, existente, HOY)
    assert plan.insertar_pasado.empty and plan.pasado_distinto == 0


def _pipeline(csv_previsto=None, falla_lectura=False):
    eventos: list = []
    db_temp = FakeDatabaseGateway("CL_TEMPORALES", eventos)
    db_traf = FakeDatabaseGateway("CL_TRAFICO", eventos)
    db_data = FakeDatabaseGateway("CL_DATA", eventos)
    db_temp.tables = _temporales_minimas()
    previsto_reader = FakeCsvReader({} if falla_lectura else {previsto.ARCHIVO: csv_previsto})
    p = TraficoPipeline(
        db_temporales=db_temp, db_trafico=db_traf, csv_reader=FakeCsvReader(csvs_minimos()),
        alerta_txt_path=Path("resultado.txt"), enviar_alerta=lambda *a: True,
        db_data=db_data, previsto_reader=previsto_reader, hoy=lambda: HOY,
    )
    return p, eventos, db_data, db_traf


def test_pipeline_carga_el_previsto_en_cl_data_dentro_del_bloque_temporales():
    csv = _csv([("2026-11-23", "00:00:00", "Usuarios Empresa", "7"), ("2026-11-24", "00:00:00", "Usuarios Empresa", "8")])
    p, eventos, db_data, _ = _pipeline(csv)
    resultado = p.run(202611)
    nombres = [e[1] for e in eventos]
    assert nombres.index("INSERT TBL_TRAFICO_CROSS_INBOUND") < nombres.index("INSERT TBL_PREVISTO_CL") < nombres.index("UPDATE")
    assert any(e[0] == "CL_DATA" and e[1].startswith("DELETE FROM [dbo].[TBL_PREVISTO_CL]") and e[2] == (HOY,) for e in eventos)
    assert resultado.previsto == {"ok": True, "borradas": 0, "insertadas_pasado": 1, "insertadas_futuro": 1}
    assert db_data.commits == 1


def test_pipeline_sin_filas_futuras_en_el_archivo_no_borra_el_futuro_de_la_tabla():
    p, eventos, _, _ = _pipeline(_csv([("2026-11-23", "00:00:00", "Usuarios Empresa", "7")]))
    p.run(202611)
    assert not any(str(e[1]).startswith("DELETE FROM [dbo].[TBL_PREVISTO_CL]") for e in eventos)


def test_pipeline_continua_si_el_previsto_falla_en_la_lectura():
    p, eventos, db_data, _ = _pipeline(falla_lectura=True)
    resultado = p.run(202611)
    assert resultado.previsto["ok"] is False
    assert db_data.commits == 0 and not any(e[0] == "CL_DATA" and e[1] == "BEGIN" for e in eventos)
    assert [e[1] for e in eventos][-1] == "Log Fin"  # el trafico termino igual


def test_pipeline_continua_si_el_previsto_falla_al_escribir_y_revierte():
    p, eventos, db_data, _ = _pipeline(_csv([("2026-11-23", "00:00:00", "Usuarios Empresa", "7")]))
    db_data.fallar_en = "TBL_PREVISTO_CL"
    resultado = p.run(202611)
    assert resultado.previsto["ok"] is False and db_data.rollbacks == 1
    assert [e[1] for e in eventos][-1] == "Log Fin"


def test_solo_validar_no_escribe_en_cl_data():
    p, eventos, _, _ = _pipeline(_csv([("2026-11-24", "00:00:00", "Usuarios Empresa", "8")]))
    resultado = p.run(202611, solo_validar=True)
    assert resultado.previsto["ensayo"] is True
    assert not any(e[0] == "CL_DATA" and (e[1] == "BEGIN" or str(e[1]).startswith(("INSERT", "DELETE"))) for e in eventos)


def test_run_previsto_no_toca_trafico_ni_logs():
    p, eventos, _, _ = _pipeline(_csv([("2026-11-24", "00:00:00", "Usuarios Empresa", "8")]))
    assert p.run_previsto()["ok"] is True
    assert {e[0] for e in eventos} == {"CL_DATA"}


def test_solo_faltantes_inserta_solo_el_pasado_que_falta_y_no_toca_el_futuro():
    csv = _csv([
        ("2026-11-22", "00:00:00", "Usuarios Empresa", "5"),  # pasado que falta -> insertar
        ("2026-11-24", "00:00:00", "Usuarios Empresa", "8"),  # futuro -> NO se toca
    ])
    p, eventos, db_data, _ = _pipeline(csv)
    db_data.futuras_previsto = 100  # hay futuro en la tabla: no debe borrarse
    resultado = p.run_previsto(solo_faltantes=True)
    assert resultado == {"ok": True, "borradas": 0, "insertadas_pasado": 1, "insertadas_futuro": 0}
    assert not any(str(e[1]).startswith("DELETE") for e in eventos)


def test_se_omite_el_previsto_si_el_archivo_no_trae_registros_de_hoy_en_adelante():
    p, eventos, db_data, _ = _pipeline(_csv([("2026-11-22", "00:00:00", "Usuarios Empresa", "7")]))  # ayer
    resultado = p.run(202611)
    assert resultado.previsto["ok"] is True and "omitido" in resultado.previsto
    assert not any(e[0] == "CL_DATA" for e in eventos)  # ni lee ni escribe la tabla: se mantiene
    assert [e[1] for e in eventos][-1] == "Log Fin"  # el trafico sigue normal


def test_se_carga_el_previsto_si_el_archivo_trae_registros_de_hoy():
    p, _, db_data, _ = _pipeline(_csv([("2026-11-23", "00:00:00", "Usuarios Empresa", "7")]))  # hoy
    resultado = p.run(202611)
    assert "omitido" not in resultado.previsto and resultado.previsto["ok"] is True and db_data.commits == 1


def test_el_ensayo_informa_la_omision_y_el_relleno_unico_no_la_aplica():
    csv = _csv([("2026-11-22", "00:00:00", "Usuarios Empresa", "7")])
    p, eventos, db_data, _ = _pipeline(csv)
    assert "omitido" in p.run_previsto(solo_validar=True)
    assert not any(e[0] == "CL_DATA" for e in eventos)
    r = p.run_previsto(solo_faltantes=True)  # relleno historico: no exige registros >= hoy
    assert r == {"ok": True, "borradas": 0, "insertadas_pasado": 1, "insertadas_futuro": 0}

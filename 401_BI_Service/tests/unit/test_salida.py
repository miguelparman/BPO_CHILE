from datetime import datetime

import openpyxl
import pandas as pd

from extractor import Extractor
from salida import ARCHIVO_EXCEL, ARCHIVO_HISTORICO, actualizar_historico, escribir_libro, leer_historico
from tests.unit.fakes import REFRESH_FALLO, FakeCliente
from transformer import transformar

ZONA = "America/Lima"


def _actualizaciones(cliente=None, extraido=datetime(2026, 10, 22, 9, 0)):
    return transformar(Extractor(cliente or FakeCliente()).extraer(), ZONA, extraido).actualizaciones


def test_primera_corrida_crea_csv(tmp_path):
    hist, csv, nuevas = actualizar_historico(_actualizaciones(), tmp_path, ZONA)
    assert csv.name == ARCHIVO_HISTORICO and csv.exists()
    assert (len(hist), nuevas) == (2, 2)


def test_segunda_corrida_no_duplica_y_conserva_lo_que_la_api_ya_no_devuelve(tmp_path, monkeypatch):
    actualizar_historico(_actualizaciones(), tmp_path, ZONA)

    # La API ya no devuelve REFRESH_OK y aparece una nueva actualizacion.
    nueva = {**REFRESH_FALLO, "id": 103, "requestId": "req-nueva", "status": "Unknown",
             "startTime": "2026-10-22T12:00:00Z", "endTime": None}
    cliente = FakeCliente()
    monkeypatch.setattr(cliente, "actualizaciones", lambda ws, ds, top: [REFRESH_FALLO, nueva] if ds == "ds-1" else [])
    hist, csv, nuevas = actualizar_historico(_actualizaciones(cliente), tmp_path, ZONA)

    assert (len(hist), nuevas) == (3, 1)
    leido = leer_historico(csv)
    assert set(leido["REQUEST_ID"]) == {"req-ok", "req-fallo", "req-nueva"}
    assert leido["INICIO_UTC"].dtype.kind == "M"


def test_actualizacion_en_curso_se_actualiza_al_terminar(tmp_path, monkeypatch):
    en_curso = {**REFRESH_FALLO, "status": "Unknown", "endTime": None}
    cliente = FakeCliente()
    monkeypatch.setattr(cliente, "actualizaciones", lambda ws, ds, top: [en_curso] if ds == "ds-1" else [])
    actualizar_historico(_actualizaciones(cliente), tmp_path, ZONA)

    hist, _, _ = actualizar_historico(_actualizaciones(), tmp_path, ZONA)
    hist = hist.set_index("REQUEST_ID")
    assert len(hist) == 2
    assert hist.loc["req-fallo", "ESTADO"] == "Failed"
    assert hist.loc["req-fallo", "FIN_UTC"] == pd.Timestamp("2026-10-22 10:01:00")


def test_cambio_de_zona_recalcula_horas_locales_del_historico(tmp_path):
    actualizar_historico(_actualizaciones(), tmp_path, "America/Santiago")
    hist, _, _ = actualizar_historico(_actualizaciones().iloc[:0], tmp_path, ZONA)
    ok = hist.set_index("REQUEST_ID").loc["req-ok"]
    assert ok["INICIO_LOCAL"] == pd.Timestamp("2026-10-21 05:00:00")  # Lima, UTC-5


def test_libro_omite_columnas_internas(tmp_path):
    ruta = escribir_libro(tmp_path, {"Hoja": pd.DataFrame({"A": [1], "_interna": [2]})})
    assert ruta.name == ARCHIVO_EXCEL
    hoja = openpyxl.load_workbook(ruta)["Hoja"]
    assert [c.value for c in hoja[1]] == ["A"]

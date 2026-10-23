from datetime import datetime

import pandas as pd

from extractor import Extractor, Inventario
from tests.unit.fakes import FakeCliente
from transformer import COLUMNAS_ACTUALIZACIONES, transformar

EXTRAIDO = datetime(2026, 10, 22, 9, 0)


def _tablas():
    return transformar(Extractor(FakeCliente()).extraer(), "America/Santiago", EXTRAIDO)


def test_actualizaciones_fechas_duracion_y_error():
    act = _tablas().actualizaciones
    assert list(act.columns) == COLUMNAS_ACTUALIZACIONES
    assert list(act["REQUEST_ID"]) == ["req-fallo", "req-ok"]  # mas reciente primero
    ok = act[act["REQUEST_ID"] == "req-ok"].iloc[0]
    assert ok["INICIO_UTC"] == pd.Timestamp("2026-10-21 10:00:00")
    assert ok["INICIO_LOCAL"] == pd.Timestamp("2026-10-21 07:00:00")  # Chile en horario de verano (UTC-3)
    assert ok["DURACION_MIN"] == 5.5
    assert ok["REFRESH_ID"] == "101"
    fallo = act[act["REQUEST_ID"] == "req-fallo"].iloc[0]
    assert fallo["ERROR_CODIGO"] == "ModelRefresh_ShortMessage_CredentialsNotSpecified"
    assert fallo["INTENTOS"] == 2


def test_datasets_resume_ultima_y_ultima_ok():
    ds = _tablas().datasets.set_index("DATASET_ID")
    assert ds.loc["ds-1", "ULTIMO_ESTADO"] == "Failed"
    assert ds.loc["ds-1", "ULTIMO_OK_LOCAL"] == pd.Timestamp("2026-10-21 07:05:30")
    assert ds.loc["ds-1", "N_INFORMES"] == 1
    assert pd.isna(ds.loc["ds-2", "ULTIMO_ESTADO"])


def test_informes_y_workspaces():
    t = _tablas()
    assert t.informes.iloc[0]["DATASET"] == "Modelo Ventas"
    assert t.workspaces.set_index("WORKSPACE").loc["Ventas", "N_DATASETS"] == 2


def test_inventario_vacio_no_falla():
    t = transformar(Inventario(), "America/Santiago", EXTRAIDO)
    assert t.actualizaciones.empty and t.datasets.empty and t.errores.empty

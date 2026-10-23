from datetime import date, datetime

import pandas as pd

from analisis import analizar, asignar_a_horario, ocupacion, tabla_cruces
from extractor import Extractor
from tests.unit.fakes import FakeCliente
from transformer import transformar
from zonas import convertir_horario

ZONA = "America/Lima"
AHORA = datetime(2026, 10, 22, 23, 0)


def _tablas():
    return transformar(Extractor(FakeCliente()).extraer(), ZONA, datetime(2026, 10, 22, 9, 0))


def test_convertir_horario_cambia_zona_y_dia():
    lunes = date(2026, 10, 19)
    assert convertir_horario(1, "15:00", "UTC", ZONA, lunes) == (1, "10:00")
    assert convertir_horario(1, "02:00", "UTC", ZONA, lunes) == (0, "21:00")  # cruza medianoche
    assert convertir_horario(1, "08:00", "America/Santiago", ZONA, lunes) == (1, "06:00")  # Chile en verano


def test_programacion_en_zona_local():
    prog = _tablas().programacion.set_index(["DATASET_ID", "HORA_ORIGEN"])
    assert prog.loc[("ds-3", "15:00"), "HORA_LOCAL"] == "10:00"  # UTC -> Lima
    assert prog.loc[("ds-1", "05:00"), "HORA_LOCAL"] == "05:00"  # SA Pacific = Lima
    assert prog.loc[("ds-1", "05:00"), "DIAS_LOCAL"] == "Miercoles, Jueves"
    assert prog.loc[("ds-1", "05:00"), "INFORME"] == "Informe Ventas"


def test_asigna_ejecuciones_al_horario_con_retraso():
    t = _tablas()
    asignadas = asignar_a_horario(t.programacion, t.actualizaciones).set_index("REQUEST_ID")
    # REFRESH_OK: miercoles 10:00 UTC = 05:00 Lima -> horario 05:00, sin retraso.
    assert asignadas.loc["req-ok", "HORA_ORIGEN"] == "05:00"
    assert asignadas.loc["req-ok", "RETRASO_MIN"] == 0
    # REFRESH_FALLO: jueves 10:00 UTC = 05:00 Lima.
    assert asignadas.loc["req-fallo", "HORA_ORIGEN"] == "05:00"


def test_hojas_de_analisis():
    t = _tablas()
    hojas = analizar(t.programacion, t.actualizaciones, 60, AHORA)
    prog = hojas["Programacion"].set_index(["DATASET_ID", "HORA_ORIGEN"])
    fila = prog.loc[("ds-1", "05:00")]
    assert (fila["N_EJECUCIONES"], fila["N_FALLIDAS"], fila["PCT_FALLO"]) == (2, 1, 50.0)
    assert fila["DURACION_MEDIANA_MIN"] == 5.5
    assert fila["FIN_ESTIMADO"] == "05:06"
    assert prog.loc[("ds-1", "10:00"), "N_EJECUCIONES"] == 0
    assert list(hojas["Mapa_cruces"].columns[:2]) == ["BLOQUE", "Lunes"]
    assert len(hojas["Mapa_cruces"]) == 96
    assert hojas["Fallos"].iloc[0]["ERROR_CODIGO"] == "ModelRefresh_ShortMessage_CredentialsNotSpecified"


def test_cruce_entre_dos_datasets_a_la_misma_hora():
    # ds-1 10:00 Lima (sin historial -> 5 min) y ds-3 15:00 UTC = 10:00 Lima, ambos el miercoles.
    t = _tablas()
    hojas = analizar(t.programacion, t.actualizaciones, 60, AHORA)
    cruces = tabla_cruces(ocupacion(hojas["Programacion"]))
    assert len(cruces) == 1
    assert cruces.iloc[0]["BLOQUE"] == "10:00-10:15"
    assert cruces.iloc[0]["DIAS"] == "Miercoles"
    assert cruces.iloc[0]["INFORMES"] == "Informe Ventas | Modelo RRHH"
    assert hojas["Mapa_cruces"].set_index("BLOQUE").loc["10:00-10:15", "Miercoles"] == 2


def test_concurrencia_real_por_hora():
    t = _tablas()
    act = t.actualizaciones.copy()
    # Otra actualizacion superpuesta con REFRESH_OK (miercoles 05:00-05:05 Lima).
    extra = act[act["REQUEST_ID"] == "req-ok"].assign(
        DATASET_ID="ds-3", DATASET="Modelo RRHH", INFORME=None, REQUEST_ID="x", REFRESH_ID="9",
        INICIO_UTC=pd.Timestamp("2026-10-21 10:02:00"), INICIO_LOCAL=pd.Timestamp("2026-10-21 05:02:00"),
    )
    hojas = analizar(t.programacion, pd.concat([act, extra], ignore_index=True), 60, AHORA)
    hora = hojas["Concurrencia_hora"].set_index("HORA").loc["05:00"]
    assert (hora["EJECUCIONES"], hora["FALLIDAS"], hora["CONCURRENCIA_MAX"]) == (3, 1, 1)


def test_horario_movido_no_toma_ejecuciones_antiguas_como_retraso(monkeypatch):
    # ds-1 se movio de 05:00 a 04:30: las ejecuciones de las 05:00 no son de ese horario.
    from tests.unit import fakes

    monkeypatch.setitem(fakes.PROGRAMACIONES, "ds-1", {**fakes.PROGRAMACIONES["ds-1"], "times": ["04:30"]})
    t = _tablas()
    hojas = analizar(t.programacion, t.actualizaciones, 60, AHORA)
    fila = hojas["Programacion"].set_index(["DATASET_ID", "HORA_ORIGEN"]).loc[("ds-1", "04:30")]
    assert fila["N_EJECUCIONES"] == 0
    assert fila["INICIO_REAL_ESTIMADO"] == "04:30"
    assert fila["DURACION_MEDIANA_MIN"] == 5.5  # duracion habitual del dataset
    assert fila["BASE_DURACION"] == "dataset (horario sin ejecuciones)"
    assert hojas["Mapa_cruces"].set_index("BLOQUE").loc["04:30-04:45", "Miercoles"] == 1
    assert hojas["Mapa_cruces"].set_index("BLOQUE").loc["05:00-05:15", "Miercoles"] == 0

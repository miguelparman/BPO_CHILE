from datetime import datetime

import pytest

import mappings
from exceptions import ValidacionError
from tests.unit.fakes import FakeDatabaseGateway, bases_minimas, esquema_destino_ok, origen
from transformacion import transformer
from validacion import validator


def test_esquema_ok():
    validator.validar_esquemas(FakeDatabaseGateway())


def test_esquema_destino_con_columnas_en_otro_orden_falla():
    db = FakeDatabaseGateway()
    cols = list(esquema_destino_ok().items())
    cols[0], cols[1] = cols[1], cols[0]
    db.esquemas[mappings.TABLA_DESTINO] = dict(cols)
    with pytest.raises(ValidacionError, match="no coincide"):
        validator.validar_esquemas(db)


def test_esquema_destino_con_largo_distinto_falla():
    db = FakeDatabaseGateway()
    db.esquemas[mappings.TABLA_DESTINO] = {**esquema_destino_ok(), "ANI": ("varchar", 20)}
    with pytest.raises(ValidacionError):
        validator.validar_esquemas(db)


def test_agent_start_no_datetime_falla():
    db = FakeDatabaseGateway()
    db.esquemas["TBL_CHAT"] = {**mappings.COLUMNAS_ORIGEN, mappings.COLUMNA_INICIO: ("datetime2", None)}
    with pytest.raises(ValidacionError, match="datetime"):
        validator.validar_esquemas(db)


def test_extraccion_con_agent_start_null_falla():
    with pytest.raises(ValidacionError, match="NULL"):
        validator.validar_extraccion(origen([(None, "1", "TRIADAS", "u")]), mappings.BASES[0])


def test_extraccion_con_servicio_de_otra_base_falla():
    with pytest.raises(ValidacionError, match="SERVICIO"):
        validator.validar_extraccion(origen([(datetime(2026, 9, 1), "1", "USUARIOS", "u")]), mappings.BASES[0])


def test_resultado_ok():
    validator.validar_resultado(transformer.transformar(bases_minimas()))


def test_resultado_con_texto_mas_ancho_que_el_destino_falla():
    df = transformer.transformar(bases_minimas())
    df.loc[0, "LOGINID"] = "x" * 16
    with pytest.raises(ValidacionError, match="LOGINID"):
        validator.validar_resultado(df)

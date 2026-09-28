import pytest

import mappings
from exceptions import ValidacionError
from extraccion import extractor
from tests.unit.fakes import FakeDatabaseGateway, csv_minimo, esquema_ok
from validacion import validator

ATENDIDA = mappings.ORIGENES[0]


def test_esquemas_ok():
    validator.validar_esquemas(FakeDatabaseGateway("t"), FakeDatabaseGateway("d"))


def test_detecta_columna_con_otro_ancho_en_cl_trafico():
    db_trafico = FakeDatabaseGateway("d")
    esquema = esquema_ok("TBL_LLAMADAS_ATENDIDAS_INBOUND")
    esquema["CONNID"] = ("varchar", 20)
    db_trafico.esquemas["TBL_LLAMADAS_ATENDIDAS_INBOUND"] = esquema
    with pytest.raises(ValidacionError, match=r"CONNID.*varchar\(25\).*varchar\(20\)"):
        validator.validar_esquemas(FakeDatabaseGateway("t"), db_trafico)


def test_detecta_columna_faltante_en_temporal():
    db_temp = FakeDatabaseGateway("t")
    esquema = esquema_ok("TBL_TRAFICO_CALLBACK")
    del esquema["EXCLUSION"]
    db_temp.esquemas["TBL_TRAFICO_CALLBACK"] = esquema
    with pytest.raises(ValidacionError, match="EXCLUSION.*no existe"):
        validator.validar_esquemas(db_temp, FakeDatabaseGateway("d"))


def test_valor_que_excede_el_ancho_de_la_temporal():
    # CALC_NUM_TELEFONO es nvarchar(50) en TBL_TRAFICO_ATENDIDA
    df = extractor.tipificar(csv_minimo(ATENDIDA, [{"CALC_NUM_TELEFONO": "9" * 51}]), ATENDIDA)
    with pytest.raises(ValidacionError, match=r"CALC_NUM_TELEFONO.*nvarchar\(50\)"):
        validator.validar_origen(df, ATENDIDA)


def test_valor_en_el_limite_del_ancho_es_valido():
    df = extractor.tipificar(csv_minimo(ATENDIDA, [{"CALC_NUM_TELEFONO": "9" * 50}]), ATENDIDA)
    validator.validar_origen(df, ATENDIDA)

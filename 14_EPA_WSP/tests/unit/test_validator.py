"""Validaciones previas a cualquier escritura."""

import pandas as pd
import pytest

import mappings
from exceptions import ValidacionError
from tests.unit.fakes import FakeDatabaseGateway
from validacion import validator


def test_esquema_identico_pasa():
    validator.validar_esquemas(FakeDatabaseGateway("IND"))


def test_esquema_con_tipo_distinto_falla():
    db = FakeDatabaseGateway("IND")
    esquema = dict(mappings.WSP.esquema)
    esquema["loginid"] = ("nvarchar", 10)
    db.esquemas[mappings.WSP.tabla] = esquema
    with pytest.raises(ValidacionError, match="loginid"):
        validator.validar_esquemas(db)


def test_tabla_inexistente_falla():
    db = FakeDatabaseGateway("IND")
    db.esquemas[mappings.ENCUESTA.tabla] = {}
    with pytest.raises(ValidacionError, match="no existe"):
        validator.validar_esquemas(db, (mappings.ENCUESTA,))


def test_anchos_excedidos_en_encuesta_fallan():
    df = pd.DataFrame({"IV": ["abcd"], "pcrc": ["x"]}, dtype=object)
    with pytest.raises(ValidacionError, match=r"\[IV\] varchar\(3\)"):
        validator.validar_anchos(df, mappings.ENCUESTA)


def test_periodos_de_la_ventana():
    df = pd.DataFrame({"periodo_evento": ["202609", "202608", "202609"]}, dtype=object)
    assert validator.validar_periodos(df, mappings.ENCUESTA) == [202608, 202609]


def test_sin_filas_no_se_borra_nada():
    with pytest.raises(ValidacionError, match="no se borra nada"):
        validator.validar_periodos(pd.DataFrame({"Periodo": []}, dtype=object), mappings.WSP)


def test_fila_sin_periodo_falla():
    df = pd.DataFrame({"Periodo": [202609, None]}, dtype=object)
    with pytest.raises(ValidacionError, match="sin 'Periodo'"):
        validator.validar_periodos(df, mappings.WSP)


def test_periodo_invalido_falla():
    df = pd.DataFrame({"Periodo": [202613]}, dtype=object)
    with pytest.raises(ValidacionError, match="invalidos"):
        validator.validar_periodos(df, mappings.WSP)

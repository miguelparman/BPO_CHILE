import pytest

from exceptions import ValidacionError
from transformacion.transformer import Transformer
from validacion.validator import Validator

BASE = {"id": "1", "Etiqueta": "e", "plataforma": "p", "RUT": "r", "Asesor": "a", "DNI": "d", "Correo Electronico": "c"}


def con(**cambios):
    return {**BASE, **cambios}


@pytest.mark.parametrize(
    "columna, ancho", [("id", 8), ("Etiqueta", 30), ("plataforma", 30), ("RUT", 50), ("Asesor", 100), ("DNI", 15)]
)
def test_ancho_exacto_pasa_y_uno_mas_falla(columna, ancho):
    Validator().validar([con(**{columna: "x" * ancho})])
    with pytest.raises(ValidacionError, match=f"DT_STR\\({ancho}\\)"):
        Validator().validar([con(**{columna: "x" * (ancho + 1)})])


def test_caracter_fuera_de_cp1252_falla():
    with pytest.raises(ValidacionError, match="1252"):
        Validator().validar([con(Asesor="Ana 中")])


def test_enie_y_tildes_caben_en_cp1252():
    Validator().validar([con(Asesor="Peña Núñez")])


def test_correo_no_se_valida_ni_se_convierte():
    Validator().validar([con(**{"Correo Electronico": "x" * 500})])
    assert len(Transformer().transformar([con()])[0]) == 6


def test_reporta_fila_excel_y_limita_ejemplos():
    filas = [con(id="x" * 9) for _ in range(30)]
    with pytest.raises(ValidacionError) as exc:
        Validator().validar(filas)
    assert "30 valor(es)" in str(exc.value) and "fila 2," in str(exc.value)
    assert str(exc.value).count("columna 'id'") == 10


def test_null_no_falla_y_se_conserva():
    Validator().validar([con(id=None, RUT=None)])
    assert Transformer().transformar([con(id=None, RUT=None)]) == [(None, "e", "p", None, "a", "d")]


def test_transformar_respeta_el_orden_del_insert():
    assert Transformer().transformar([BASE]) == [("1", "e", "p", "r", "a", "d")]

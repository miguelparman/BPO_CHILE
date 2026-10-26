from __future__ import annotations

from tests.unit.fakes import csv_crudo
from transformacion.descripciones_nc import leer_descripciones_nc


def test_como_el_script_original_con_pandas_sobre_el_crudo():
    crudo = csv_crudo(
        ["Número del caso", "Descripción"],
        [["12250117", "Estimada\nMarta"], ["15030368", ""], ["15030369", "NA"], ["15030370", "Sí"]],
    )
    assert leer_descripciones_nc(crudo) == [
        ("12250117", "Estimada\r\nMarta"),  # salto de linea -> CRLF (como en 'Nuevo')
        ("15030368", None),  # celda vacia -> NaN -> NULL
        ("15030369", None),  # 'NA' tambien es NaN para pandas
        ("15030370", "Sí"),
    ]


def test_tildes_mal_codificadas_se_reparan():
    crudo = b'"N","D"\n"1","ARTA\x8dCULOS"\n"2","MU\xc3\x91OZ"\n'  # SSIS guardaba 'ARTA?CULOS' y 'MUÃ‘OZ'
    assert leer_descripciones_nc(crudo) == [("1", "ARTÍCULOS"), ("2", "MUÑOZ")]


def test_caracter_no_representable_en_cp1252_llega_como_signo_de_interrogacion():
    crudo = '"N","D"\n"1","flecha →"\n'.encode("utf-8")  # 'â†’' en cp1252: sin bytes indefinidos
    assert "?" not in leer_descripciones_nc(crudo)[0][1]
    assert leer_descripciones_nc('"N","D"\n"1","x"\n'.encode("cp1252")) == [("1", "x")]

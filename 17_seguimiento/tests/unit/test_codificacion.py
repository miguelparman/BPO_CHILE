from __future__ import annotations

import pytest

from extraccion.extractor import CODIFICACION_BOT, CONSERVAR_BYTES
from transformacion import codificacion
from transformacion.codificacion import reparar_codificacion, sin_reparar_como_ssis


def leido(crudo: bytes) -> str:
    """Como lo lee el extractor (cp1252 conservando los bytes no definidos)."""
    return crudo.decode(CODIFICACION_BOT, CONSERVAR_BYTES)


@pytest.mark.parametrize(
    "crudo,esperado",
    [
        # bytes reales de los CSV del 2026-10-26
        (b"AGRA\x8dCOLAS", "AGRÍCOLAS"),
        (b"ARTA\x8dCULOS", "ARTÍCULOS"),
        (b"ASESORIA\x8dAS", "ASESORÍAS"),  # la I sin tilde repetida antes sobra
        (b"BELTRA\x81N", "BELTRÁN"),
        (b"CAFETER\xcd\x8dA", "CAFETERÍA"),  # letra ya correcta + byte de sobra
        (b"FERRETERA\x8dA", "FERRETERÍA"),
        (b"FA\x81BRICA", "FÁBRICA"),
        (b"INFORMA\x81TICOS", "INFORMÁTICOS"),
        (b"MINERA\x8dA", "MINERÍA"),
        (b"RAMA\x8dREZ", "RAMÍREZ"),
        (b"IRARR\xc3\x81ZABAL", "IRARRÁZABAL"),
        (b"MU\xc3\x91OZ", "MUÑOZ"),  # 0x91 si existe en cp1252 (comilla)
        (b"DISE\xc3\x91O", "DISEÑO"),
        (b"Jos\xc3\xa9", "José"),
        (b"Santiba\xc3\xb1ez", "Santibañez"),
        (b"N\xc2\xb0DE", "N°DE"),
    ],
)
def test_repara_las_tildes_mal_codificadas(crudo, esperado):
    assert reparar_codificacion(leido(crudo)) == esperado


@pytest.mark.parametrize(
    "texto",
    ["Razón Social", "JOÃO", "AÑO", "IÍ", "ADMINISTRACIÃ?N", "PEÃ?A", "", "texto normal 123"],
)
def test_no_toca_texto_correcto_ni_lo_irrecuperable(texto):
    # 'Ã?': el segundo byte ya llego como '?' literal desde Salesforce; la
    # letra original no se puede saber (O, N o I con tilde segun el caso).
    assert reparar_codificacion(texto) == texto


def test_byte_suelto_sin_patron_se_elimina():
    assert reparar_codificacion(leido(b"X\x9dY")) == "XY"


def test_el_extractor_conserva_los_bytes_no_definidos():
    assert leido(b"A\x81\x8d\x8f\x90\x9d") == "A\x81\x8d\x8f\x90\x9d"


def test_modo_ssis_deja_los_bytes_como_caracter_de_reemplazo(monkeypatch):
    monkeypatch.setattr(codificacion, "REPARAR", False)
    assert reparar_codificacion(leido(b"AGRA\x8dCOLAS")) == "AGRA�COLAS"
    assert sin_reparar_como_ssis(leido(b"MU\xc3\x91OZ")) == "MU\xc3‘OZ"  # SSIS no reparaba nada

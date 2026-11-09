"""Los extractores de CSV reciben los bytes (en produccion vienen de Graph), asi que
se prueban sin red ni credenciales."""
from dataclasses import replace
from pathlib import Path

import pytest

from contactos import extractor as contactos_extractor
from contactos.columns import COLUMNAS_ORIGEN
from isn.columns import COLUMNAS_AUX_CLIENTE, COLUMNAS_AUX_CONTACTO
from isn.extractors import aux_cliente_extractor, aux_contacto_extractor

MUESTRA = Path(__file__).resolve().parent.parent / "sample_data" / "Reporte_Contactos_Salesforce_BI_test.csv"


def _csv(columnas: list[str], filas: int = 2) -> bytes:
    lineas = [",".join(f'"{c}"' for c in columnas)]
    lineas += [",".join(f'"v{i}"' for _ in columnas) for i in range(filas)]
    return "\n".join(lineas).encode("latin-1")


def test_contactos_desde_bytes_de_muestra():
    df = contactos_extractor.leer_csv_contactos(MUESTRA.read_bytes())
    assert list(df.columns) == COLUMNAS_ORIGEN
    assert len(df) > 0


def test_contactos_sin_bytes_usa_csv_de_muestra_en_modo_prueba(monkeypatch):
    monkeypatch.setattr(
        contactos_extractor, "settings", replace(contactos_extractor.settings, contactos_csv_muestra=str(MUESTRA))
    )
    monkeypatch.setattr(
        contactos_extractor, "descargar_archivo", lambda *a, **k: pytest.fail("no debe llamar a Graph en modo prueba")
    )
    assert len(contactos_extractor.leer_csv_contactos()) > 0


def test_contactos_columnas_incorrectas_falla():
    with pytest.raises(ValueError, match="columnas"):
        contactos_extractor.leer_csv_contactos(_csv(["a", "b"]))


def test_aux_cliente_desde_bytes():
    df = aux_cliente_extractor.leer_aux_cliente(_csv(COLUMNAS_AUX_CLIENTE))
    assert list(df.columns) == COLUMNAS_AUX_CLIENTE and len(df) == 2


def test_aux_contacto_desde_bytes():
    df = aux_contacto_extractor.leer_aux_contacto(_csv(COLUMNAS_AUX_CONTACTO))
    assert list(df.columns) == COLUMNAS_AUX_CONTACTO and len(df) == 2


def test_aux_columnas_incorrectas_falla():
    with pytest.raises(ValueError, match="columnas"):
        aux_cliente_extractor.leer_aux_cliente(_csv(["a"]))
    with pytest.raises(ValueError, match="columnas"):
        aux_contacto_extractor.leer_aux_contacto(_csv(["a"]))

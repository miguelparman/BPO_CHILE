"""Descarga del portal Medallia con Playwright, probada con una pagina falsa
(sin navegador ni red): orden de las acciones, selectores equivalentes a los
de Selenium, timeouts, subida a SharePoint y manejo de errores."""

from contextlib import contextmanager
from pathlib import Path

import pytest

from config import MedalliaSettings
from exceptions import ExtraccionError
from extraccion import medallia_descarga as md
from tests.unit.fakes import FakeCarpeta

PREFIJO = "Telefonica Moviles Chile SA_export_"


class FakeDownload:
    def __init__(self, nombre: str, contenido: str = "ID de encuesta\n1\n", falla_al_guardar=False):
        self.suggested_filename = nombre
        self._contenido = contenido
        self._falla = falla_al_guardar

    def save_as(self, ruta: str) -> None:
        Path(ruta).write_bytes(self._contenido.encode("latin1"))  # bytes tal cual, como Download.save_as
        if self._falla:
            raise OSError("disco lleno")


class FakeLocator:
    def __init__(self, page, selector):
        self.page, self.selector = page, selector

    def wait_for(self, timeout):
        self.page.acciones.append(("wait_for", self.selector, timeout))

    def fill(self, valor):
        self.page.acciones.append(("fill", self.selector, valor))

    def click(self, timeout=None):
        self.page.acciones.append(("click", self.selector, timeout))
        if self.selector == self.page.falla_en:
            raise TimeoutError(f"Timeout esperando {self.selector}")


class FakePage:
    def __init__(self, descarga=None, falla_en=None, url_tras_login="https://telefonicacl.medallia.com/telefonicacl/home"):
        self.acciones: list = []
        self.url_tras_login = url_tras_login
        self.url = ""
        self.descarga = descarga or FakeDownload(f"{PREFIJO}20260929.csv")
        self.falla_en = falla_en
        self.capturas: list = []

    def goto(self, url):
        self.acciones.append(("goto", url))
        self.url = url

    def locator(self, selector):
        return FakeLocator(self, selector)

    def wait_for_url(self, predicado, timeout):
        self.url = self.url_tras_login
        assert predicado(self.url) and not predicado("https://telefonicacl.medallia.com/telefonicacl/")
        self.acciones.append(("wait_for_url", timeout))

    @contextmanager
    def expect_download(self, timeout):
        self.acciones.append(("expect_download", timeout))

        class Info:
            value = self.descarga

        yield Info()

    def screenshot(self, path, full_page):
        self.capturas.append(path)
        Path(path).write_bytes(b"png")


def _settings(tmp_path) -> MedalliaSettings:
    return MedalliaSettings(
        usuario="usuario", password="secreto", segundos_espera_descarga=60, carpeta_capturas=tmp_path / "logs",
    )


def _abridor(page):
    @contextmanager
    def abrir(settings):
        yield page

    return abrir


def test_recorre_el_portal_en_el_mismo_orden_que_el_script_selenium(tmp_path):
    s, carpeta, page = _settings(tmp_path), FakeCarpeta(), FakePage()
    ruta = md.descargar_encuestas(s, carpeta, abrir_pagina=_abridor(page))
    assert ruta == "REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/16 MEDALLIA/Encuestas_Medallia.csv"
    assert page.acciones == [
        ("goto", s.url_login),
        ("wait_for", '[name="username"]', 20_000),
        ("fill", '[name="username"]', "usuario"),
        ("fill", '[name="password"]', "secreto"),
        ("click", 'button[type="submit"]', None),
        ("wait_for_url", 20_000),
        ("goto", s.url_registros),
        ("click", "#openExportMenu", 30_000),
        ("expect_download", 60_000),
        ("click", 'button[data-title="CSV"]', 30_000),
    ]


def test_sube_el_export_a_sharepoint_reemplazando_el_csv_anterior(tmp_path):
    s = _settings(tmp_path)
    carpeta = FakeCarpeta({"Encuestas_Medallia.csv": b"viejo"})
    md.descargar_encuestas(s, carpeta, abrir_pagina=_abridor(FakePage()))
    assert carpeta.archivos["Encuestas_Medallia.csv"] == "ID de encuesta\n1\n".encode("latin1")
    assert carpeta.operaciones == [("escribir", "Encuestas_Medallia.csv")]
    assert not (tmp_path / "logs").exists()  # sin errores, sin capturas


def test_rechaza_una_descarga_que_no_es_el_export_esperado(tmp_path):
    carpeta = FakeCarpeta({"Encuestas_Medallia.csv": b"viejo"})
    page = FakePage(descarga=FakeDownload("otro_reporte.csv"))
    with pytest.raises(ExtraccionError, match="no comienza con"):
        md.descargar_encuestas(_settings(tmp_path), carpeta, abrir_pagina=_abridor(page))
    assert carpeta.archivos["Encuestas_Medallia.csv"] == b"viejo"  # el CSV anterior queda intacto
    assert carpeta.operaciones == []


def test_export_vacio_no_pisa_el_csv(tmp_path):
    carpeta = FakeCarpeta({"Encuestas_Medallia.csv": b"viejo"})
    page = FakePage(descarga=FakeDownload(f"{PREFIJO}x.csv", contenido=""))
    with pytest.raises(ExtraccionError, match="vacio"):
        md.descargar_encuestas(_settings(tmp_path), carpeta, abrir_pagina=_abridor(page))
    assert carpeta.archivos["Encuestas_Medallia.csv"] == b"viejo"


def test_fallo_al_guardar_localmente_no_sube_nada(tmp_path):
    carpeta = FakeCarpeta({"Encuestas_Medallia.csv": b"viejo"})
    page = FakePage(descarga=FakeDownload(f"{PREFIJO}x.csv", falla_al_guardar=True))
    with pytest.raises(ExtraccionError):
        md.descargar_encuestas(_settings(tmp_path), carpeta, abrir_pagina=_abridor(page))
    assert carpeta.operaciones == [] and carpeta.archivos["Encuestas_Medallia.csv"] == b"viejo"


def test_fallo_de_sharepoint_es_extraccion_error(tmp_path):
    carpeta = FakeCarpeta(falla_al_escribir=True)
    with pytest.raises(ExtraccionError, match="Graph 503"):
        md.descargar_encuestas(_settings(tmp_path), carpeta, abrir_pagina=_abridor(FakePage()))


def test_timeout_en_el_portal_es_extraccion_error_con_captura(tmp_path):
    s = _settings(tmp_path)
    page = FakePage(falla_en="#openExportMenu")
    with pytest.raises(ExtraccionError, match="openExportMenu"):
        md.descargar_encuestas(s, FakeCarpeta(), abrir_pagina=_abridor(page))
    assert len(page.capturas) == 1 and Path(page.capturas[0]).parent == s.carpeta_capturas


def test_contrasena_caducada_es_extraccion_error_clara_con_captura(tmp_path):
    s = _settings(tmp_path)
    page = FakePage(url_tras_login="https://telefonicacl.medallia.com/telefonicacl/resetPassword.do?showError=true")
    with pytest.raises(ExtraccionError, match="caduco"):
        md.descargar_encuestas(s, FakeCarpeta(), abrir_pagina=_abridor(page))
    assert ("goto", s.url_registros) not in page.acciones
    assert len(page.capturas) == 1


def test_navegador_invalido(tmp_path):
    pytest.importorskip("playwright")
    s = MedalliaSettings(usuario="u", password="p", navegador="netscape")
    with pytest.raises(ExtraccionError, match="MEDALLIA_NAVEGADOR invalido"):
        md.descargar_encuestas(s, FakeCarpeta())

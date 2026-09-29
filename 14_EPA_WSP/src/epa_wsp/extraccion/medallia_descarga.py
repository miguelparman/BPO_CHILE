"""Migracion de 102_calidad/CL_Descarga_encuestas_Medallia.py (Execute Process
'Package\\MEDALIA\\DESCARGA_MEDALLIA CL_Descarga_encuestas_Medallia_PY'),
reimplementada con Playwright (antes Selenium + geckodriver).

Mismo flujo en el portal: login -> pagina de registros -> menu de
exportacion -> CSV -> el archivo descargado ('Telefonica Moviles Chile
SA_export_*') queda como Encuestas_Medallia.csv, ahora en SharePoint
(Data Reporting/REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/16 MEDALLIA, via Graph)
en vez de la carpeta local '...\\Data Analytics Reporting Fractalia - Medallia'.
Mismos selectores:

    Selenium (original)                          Playwright
    By.NAME "username" / "password"          ->  [name="username"] / [name="password"]
    By.CSS_SELECTOR "button[type='submit']"  ->  button[type="submit"]
    EC.url_changes(url_login)                ->  page.wait_for_url(url != url_login)
    By.ID "openExportMenu"                   ->  #openExportMenu
    By.XPATH '//button[@data-title="CSV"]'   ->  button[data-title="CSV"]

Cambios respecto del original:
- Navegador de Playwright (Firefox por defecto, MEDALLIA_NAVEGADOR) en vez de
  geckodriver/webdriver-manager: no hay que descargar drivers en cada corrida
  ('python -m playwright install firefox' una sola vez).
- La descarga se captura con page.expect_download(): no se usa la carpeta
  de descargas del navegador, ni un sleep(10) fijo, ni se busca "el archivo
  mas reciente con el prefijo" (que podia ser de una descarga anterior).
  Se espera hasta MEDALLIA_SEGUNDOS_ESPERA_DESCARGA; el export se guarda en
  un temporal local y se sube a SharePoint reemplazando el CSV anterior.
- Usuario y password del portal salen de '.env' (antes en texto plano).
- El original capturaba cualquier error, lo imprimia y terminaba con codigo
  0: la carga leia en silencio el CSV del dia anterior. Aqui el error se
  propaga como ExtraccionError (con una captura de pantalla en logs/); el
  pipeline lo registra como paso fallido y -- igual que el .dtsx
  (FailTaskIfReturnCodeIsNotSuccessValue=False) -- continua con la carga del
  CSV existente.
"""

from __future__ import annotations

import logging
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator

from config import MedalliaSettings
from exceptions import ExtraccionError

logger = logging.getLogger("epa_wsp")

SEL_USUARIO = '[name="username"]'
SEL_PASSWORD = '[name="password"]'
SEL_INGRESAR = 'button[type="submit"]'
SEL_MENU_EXPORTAR = "#openExportMenu"
SEL_EXPORTAR_CSV = 'button[data-title="CSV"]'

# Timeouts del original (WebDriverWait), en milisegundos.
TIMEOUT_LOGIN_MS = 20_000
TIMEOUT_EXPORTAR_MS = 30_000


@contextmanager
def _abrir_pagina_playwright(settings: MedalliaSettings) -> Iterator[object]:
    """Navegador + contexto (sin cache, con descargas) + pagina; se cierran al salir."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        tipo = getattr(pw, settings.navegador, None)
        if tipo is None:
            raise ExtraccionError(f"MEDALLIA_NAVEGADOR invalido: {settings.navegador!r} (firefox, chromium o webkit)")
        navegador = tipo.launch(headless=settings.headless)
        try:
            contexto = navegador.new_context(accept_downloads=True)
            yield contexto.new_page()
        finally:
            navegador.close()


def exportar_csv(page, settings: MedalliaSettings):
    """Recorre el portal y devuelve el objeto Download del export CSV."""
    page.goto(settings.url_login)
    page.locator(SEL_USUARIO).wait_for(timeout=TIMEOUT_LOGIN_MS)
    page.locator(SEL_USUARIO).fill(settings.usuario)
    page.locator(SEL_PASSWORD).fill(settings.password)
    page.locator(SEL_INGRESAR).click()
    page.wait_for_url(lambda url: url != settings.url_login, timeout=TIMEOUT_LOGIN_MS)
    logger.info("Medallia: sesion iniciada; abriendo la pagina de registros.")

    page.goto(settings.url_registros)
    page.locator(SEL_MENU_EXPORTAR).click(timeout=TIMEOUT_EXPORTAR_MS)
    with page.expect_download(timeout=settings.segundos_espera_descarga * 1000) as descarga:
        page.locator(SEL_EXPORTAR_CSV).click(timeout=TIMEOUT_EXPORTAR_MS)
        logger.info("Medallia: exportacion CSV solicitada; esperando la descarga...")
    return descarga.value


def guardar_descarga(download, settings: MedalliaSettings, carpeta) -> str:
    """Valida el nombre del export y lo sube a SharePoint como
    settings.archivo (Graph reemplaza el archivo en una sola operacion: si la
    subida falla, el CSV anterior queda intacto). Devuelve la ruta en SharePoint."""
    nombre = download.suggested_filename
    if not nombre.startswith(settings.prefijo_archivo):
        raise ExtraccionError(
            f"El portal descargo '{nombre}', que no comienza con '{settings.prefijo_archivo}'."
        )
    with tempfile.TemporaryDirectory(prefix="medallia_") as tmp:
        local = Path(tmp) / nombre
        download.save_as(str(local))
        contenido = local.read_bytes()
    if not contenido:
        raise ExtraccionError(f"El export '{nombre}' descargado del portal esta vacio.")
    carpeta.escribir(settings.archivo, contenido)
    logger.info(
        "Medallia: '%s' descargado (%s bytes) y guardado en SharePoint: %s",
        nombre, len(contenido), carpeta.url(settings.archivo),
    )
    return carpeta.ruta(settings.archivo)


def _captura_de_error(page, settings: MedalliaSettings) -> None:
    try:
        settings.carpeta_capturas.mkdir(parents=True, exist_ok=True)
        ruta = settings.carpeta_capturas / f"medallia_error_{datetime.now():%Y%m%d_%H%M%S}.png"
        page.screenshot(path=str(ruta), full_page=True)
        logger.info("Medallia: captura de pantalla del error en %s", ruta)
    except Exception as exc:  # noqa: BLE001 - la captura es solo diagnostico
        logger.debug("No se pudo tomar la captura de pantalla: %s", exc)


def descargar_encuestas(
    settings: MedalliaSettings,
    carpeta,
    abrir_pagina: Callable[[MedalliaSettings], object] = _abrir_pagina_playwright,
) -> str:
    """Descarga el export CSV del portal y lo guarda en la carpeta de
    SharePoint (sharepoint.carpeta.CarpetaSharePoint) como settings.archivo."""
    logger.info(
        "Medallia: iniciando %s%s con Playwright...", settings.navegador, " (headless)" if settings.headless else ""
    )
    try:
        with abrir_pagina(settings) as page:
            try:
                download = exportar_csv(page, settings)
                return guardar_descarga(download, settings, carpeta)
            except Exception:
                _captura_de_error(page, settings)
                raise
    except ExtraccionError:
        raise
    except Exception as exc:  # noqa: BLE001 - errores de Playwright (timeouts, login, navegador)
        raise ExtraccionError(f"Fallo la descarga desde el portal Medallia: {exc}") from exc

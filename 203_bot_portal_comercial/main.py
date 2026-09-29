"""
Bot de descargas del Portal Comercial (comercial.telefonicachile.cl).

Flujos (una sola sesion de login):
1. REPORTE_AGENTES_FRACTALIA_SEM.csv (CALLCENTER > Fractalia) -> se sube via
   Microsoft Graph a SharePoint ReportingFractalia (15 PORTAL COMERCIAL).
   BPO (BASES_PANEL_CC) queda fuera: la app 'BPO' de Graph es solo lectura.
2. PVTA_PROYECCION_PPP_FRACTALIA_PERU.csv (CALLCENTER > Fractalia > POST
   VENTA > DIMENSIONAMIENTO) -> mismo destino SharePoint que el flujo 1.

Si un flujo falla, el otro se ejecuta igual; el proceso termina con codigo 1
si alguno fallo.

Requisitos
----------
- pip install playwright python-dotenv requests
- playwright install chromium
- Completar 203_bot_portal_comercial/.env (ver .env.example) con las
  credenciales del portal y de los tenants 'BPO' y 'ReportingFractalia'.
  No subir ese archivo a ningun repositorio ni chat.

Arquitectura: Page Object Model + capas (config / core / pages / services).
Este archivo es el composition root: arma settings, logger, navegador,
page objects y los servicios de cada caso de uso, y los ejecuta.
"""

import logging
import sys

from config.settings import cargar_settings
from core.browser_factory import crear_pagina
from core.logger import configurar_logger
from pages.file_explorer_page import FileExplorerPage
from pages.login_page import LoginPage
from services.descarga_dimensionamiento_service import DescargaDimensionamientoService
from services.descarga_reporte_agentes_service import DescargaReporteAgentesService


def main() -> None:
    settings = cargar_settings()
    log = configurar_logger(settings.log_dir)

    with crear_pagina(settings.headless) as page:
        login_page = LoginPage(page)
        explorer_page = FileExplorerPage(page)

        try:
            log.info("Accediendo al Portal Comercial...")
            login_page.ir_a_login(settings.portal_url)
            login_page.iniciar_sesion(settings.portal_usuario, settings.portal_password)
            log.info("Login OK")
        except Exception:
            log.exception("Error durante el login")
            login_page.screenshot_diagnostico(settings.log_dir, "login")
            raise

        servicios = [
            ("Reporte agentes", DescargaReporteAgentesService(settings, explorer_page, log)),
            ("Dimensionamiento", DescargaDimensionamientoService(settings, explorer_page, log)),
        ]
        fallidos = []
        for nombre, servicio in servicios:
            try:
                servicio.ejecutar()
            except Exception:
                fallidos.append(nombre)

    if fallidos:
        raise RuntimeError(f"Flujos con error: {', '.join(fallidos)}")
    log.info("Proceso finalizado OK")


def _mostrar_proyecto():
    """Muestra el nombre del proyecto en la consola y en el titulo de la ventana."""
    import ctypes
    import sys
    from pathlib import Path

    carpeta = Path(__file__).resolve().parent
    nombre = carpeta.name
    print("=" * 60, f" PROYECTO: {nombre}", "=" * 60, sep="\n", flush=True)
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetConsoleTitleW(nombre)


if __name__ == "__main__":
    _mostrar_proyecto()
    try:
        main()
    except Exception as e:
        logging.getLogger("bot_portal_comercial").error("Proceso finalizado con error: %s", e)
        sys.exit(1)

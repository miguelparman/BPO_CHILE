"""
Automatiza la exportación de la tabla "Detalle NC" del informe
"RESUMEN II - Analisis NC MiPYME" (Power BI Service) mediante Playwright.

Flujo (ETL): Extract (PowerBiDetalleNCExtractor) -> Load (FilesystemArchivoLoader)
RESUMEN II -> Detalle NC -> (...) -> Exportar datos -> Datos con diseño
actual -> Exportar -> guardar como NC_.xlsx

Arquitectura (Clean/Layered):
    app/domain/          Entidades y excepciones. Sin dependencias externas.
    app/application/     Puertos (interfaces) y el caso de uso que orquesta
                          Extract -> Load. Solo conoce domain/ y los puertos.
    app/infrastructure/  Implementaciones concretas: Playwright, .env,
                          filesystem, logging, diagnóstico.
    main.py (este archivo) Composition root: arma las piezas concretas de
                          infrastructure/ y las inyecta en el caso de uso.
                          Es el único punto que conoce ambas capas a la vez.

Configuración:
    Los valores se leen del archivo '.env' (junto a este script; ver
    '.env.example' para la lista completa). Si una variable no está
    definida en '.env', se usa el valor por defecto indicado en
    app/infrastructure/config.py.

Modo headless y login automático:
    Por defecto HEADLESS=true (se ejecuta sin ventana visible). Al iniciar,
    el script prueba primero en segundo plano; si Power BI pide iniciar
    sesión (perfil nuevo o sesión caducada) -- cosa que un navegador
    invisible no puede resolver -- se abre automáticamente y por única vez
    una ventana visible SOLO para ese paso. Completa el login ahí
    (usuario/contraseña/MFA); en cuanto el informe cargue, la ventana se
    cierra sola y el proceso continúa en segundo plano. La sesión queda
    guardada en la carpeta 'playwright_profile' (junto a este script), así
    que en próximas ejecuciones no debería volver a pedir login (salvo que
    la sesión de Microsoft caduque).

Diagnóstico:
    python main.py --diagnose
    Vuelca en el log las pestañas, títulos de visual y botones "..."
    detectados, útil si Power BI cambia su interfaz y hay que ajustar
    selectores.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import replace
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))  # permite 'import app.xxx' al correr como script suelto

from playwright.sync_api import Page, Playwright, sync_playwright

from app.application.use_cases import ExportarDetalleNCUseCase
from app.domain.models import ExportSettings
from app.infrastructure.config import cargar_configuracion
from app.infrastructure.diagnostics import diagnosticar_pagina, tomar_captura_error
from app.infrastructure.filesystem_loader import FilesystemArchivoLoader
from app.infrastructure.logging_setup import NOMBRE_LOGGER, configurar_logging
from app.infrastructure.playwright_browser import NavegadorPowerBI
from app.infrastructure.powerbi_extractor import PowerBiDetalleNCExtractor

# El logger se resuelve por nombre (getLogger devuelve siempre la misma
# instancia); configurar_logging() le adjunta los handlers al inicio de
# main(), antes de que _abrir_sesion() -- llamada solo desde main() -- lo use.
logger = logging.getLogger(NOMBRE_LOGGER)


def _abrir_sesion(
    settings: ExportSettings, playwright: Playwright, diagnose: bool
) -> tuple[NavegadorPowerBI, Page]:
    """
    Abre el navegador respetando HEADLESS. Si HEADLESS=true pero Power BI
    pide iniciar sesión (perfil nuevo o sesión caducada), un navegador
    headless no sirve para que el usuario complete el login: se cierra y se
    reabre temporalmente en modo visible SOLO para ese paso, y al terminar
    se vuelve a abrir en el modo headless configurado (la sesión ya quedó
    guardada en el perfil persistente).
    """
    navegador = NavegadorPowerBI(settings, playwright)
    navegador.iniciar()
    page = navegador.nueva_pagina()

    if not settings.headless:
        return navegador, page

    extractor = PowerBiDetalleNCExtractor(page, settings, diagnose=diagnose)
    extractor.navegar_al_informe()

    if not extractor.hay_pantalla_login():
        return navegador, page  # sesión ya válida, seguimos en headless

    logger.warning(
        "No hay una sesión de Power BI válida (o caducó): se necesita "
        "iniciar sesión manualmente. Abriendo un navegador visible solo "
        "para ese paso..."
    )
    navegador.cerrar()

    settings_visible = replace(settings, headless=False)
    navegador = NavegadorPowerBI(settings_visible, playwright)
    navegador.iniciar()
    page = navegador.nueva_pagina()
    extractor_visible = PowerBiDetalleNCExtractor(page, settings_visible, diagnose=diagnose)
    extractor_visible.navegar_al_informe()
    extractor_visible.esperar_login_manual()

    logger.info("Login completado. Cerrando el navegador visible y continuando en segundo plano (headless)...")
    navegador.cerrar()

    navegador = NavegadorPowerBI(settings, playwright)
    navegador.iniciar()
    page = navegador.nueva_pagina()
    return navegador, page


def main() -> int:
    diagnose = "--diagnose" in sys.argv

    settings = cargar_configuracion(BASE_DIR)
    settings.screenshots_dir.mkdir(exist_ok=True)
    configurar_logging(settings.log_file)

    page: Optional[Page] = None

    with sync_playwright() as playwright:
        navegador: Optional[NavegadorPowerBI] = None
        try:
            navegador, page = _abrir_sesion(settings, playwright, diagnose)

            extractor = PowerBiDetalleNCExtractor(page, settings, diagnose=diagnose)
            loader = FilesystemArchivoLoader()
            caso_de_uso = ExportarDetalleNCUseCase(
                extractor=extractor,
                loader=loader,
                destino_final=settings.destino_final,
            )

            resultado = caso_de_uso.ejecutar()

            logger.info("Proceso finalizado correctamente.")
            print(f"\nExportación completada. Archivo guardado en:\n{resultado.ruta_archivo}\n")
            return 0

        except Exception as exc:
            logger.error(f"Error durante la exportación: {exc}")
            logger.exception("Detalle del error:")
            tomar_captura_error(page, settings.screenshots_dir, "export_nc")
            if page is not None:
                try:
                    diagnosticar_pagina(page)
                except Exception:
                    pass
            print(f"\nOcurrió un error: {exc}\nRevisa '{settings.log_file.name}' y la carpeta 'screenshots'.\n")
            return 1

        finally:
            if navegador is not None:
                navegador.cerrar()


def _mostrar_proyecto():
    """Muestra el nombre del proyecto en la consola y en el titulo de la ventana."""
    import ctypes
    import sys
    from pathlib import Path

    carpeta = Path(__file__).resolve().parent
    nombre = f"{carpeta.parent.name} / {carpeta.name}"
    print("=" * 60, f" PROYECTO: {nombre}", "=" * 60, sep="\n", flush=True)
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetConsoleTitleW(nombre)


if __name__ == "__main__":
    _mostrar_proyecto()
    sys.exit(main())

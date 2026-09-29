"""
Punto de entrada de la automatizacion Salesforce -> SharePoint.

Uso:
    python main.py                (interactivo o programado, con consola)
    pythonw.exe main.py           (desatendido, sin consola -- el logger
                                   sigue escribiendo en logs/ igual)

El Programador de tareas de Windows llama a run_task.bat, que usa
python.exe (no pythonw.exe) precisamente para que el progreso se vea en
la consola de la tarea igual que al ejecutar main.py desde VSCode --
incluido el aviso de MFA si la sesion de Salesforce necesita renovarse.
Si se invoca con pythonw.exe (sys.stdout/sys.stderr en None), el logger
sigue funcionando sin consola, y cualquier fallo durante el arranque
(antes de que exista el logger, p.ej. un .env mal configurado) queda
registrado en logs/startup_error.log en vez de perderse en silencio. La
creacion de la tarea programada en si (Trigger, Accion, etc.) es un paso
manual documentado en README.md -- no se automatiza aqui.
"""

from __future__ import annotations

import sys

try:
    from app.config import settings
    from app.logger import log
    from app.salesforce.client import SalesforceClient
    from app.services.local_delivery import LocalDeliveryCopier
    from app.services.orchestrator import ReportOrchestrator, format_summary
    from app.services.process_lock import ProcessLock
    from app.services.retry import retry_call
    from app.sharepoint.auth import get_graph_token
    from app.sharepoint.client import SharePointClient, SharePointFolderResolver
    from app.sharepoint.uploader import SharePointUploader
    from config.reports import REPORTS
except Exception:
    # Sin esto, un fallo de configuracion (p.ej. falta una variable en
    # .env) durante una ejecucion desatendida con pythonw.exe (sin consola)
    # se perderia por completo: no hay stdout/stderr visibles y el logger
    # normal (app.logger) todavia no llego a inicializarse.
    import traceback
    from datetime import datetime
    from pathlib import Path

    fallback_dir = Path(__file__).resolve().parent / "logs"
    fallback_dir.mkdir(parents=True, exist_ok=True)
    with open(fallback_dir / "startup_error.log", "a", encoding="utf-8") as fh:
        fh.write(f"\n{datetime.now():%Y-%m-%d %H:%M:%S} | Fallo al iniciar la aplicacion:\n")
        fh.write(traceback.format_exc())

    if sys.stdout is not None:
        traceback.print_exc()
        print("\n" + "=" * 50)
        print("ERROR: no se pudo iniciar el bot (revise .env / dependencias).")
        print("Detalle guardado en logs/startup_error.log")
        print("=" * 50)
        try:
            input("\nPresione Enter para cerrar esta ventana...")
        except (EOFError, OSError):
            pass
    sys.exit(1)


def main() -> int:
    lock = ProcessLock(settings.base_dir / "bot.lock")
    lock.acquire()

    try:
        return _run()
    except Exception:
        # Ultima red de seguridad: sin esto, cualquier fallo no controlado
        # aqui (p.ej. el login interactivo de Salesforce) se pierde en
        # silencio total bajo pythonw.exe (sys.stderr es None, no queda
        # traceback en ninguna parte). Se deja constancia en el log del dia.
        log.exception("Fallo no controlado durante la ejecucion.")
        return 1
    finally:
        lock.release()


def _run() -> int:
    log.info("=" * 50)
    log.info("SALESFORCE -> SHAREPOINT AUTOMATION")
    log.info("=" * 50)
    log.info("Configuracion cargada correctamente.")
    log.info(
        "Modo headless: %s | DRY_RUN: %s | MAX_REPORTS: %s",
        settings.headless,
        settings.dry_run,
        settings.max_reports or "todos",
    )

    uploader = None
    folder_resolver = None
    local_copier = None
    if settings.dry_run:
        log.warning("DRY_RUN=true: no se autentica contra Graph ni se copia/sube nada.")
    else:
        local_copier = LocalDeliveryCopier(
            destination_dir=settings.local_copy_dir,
            overwrite=settings.overwrite_existing,
        )

        log.info("Autenticando contra Microsoft Graph...")
        token = retry_call(
            lambda: get_graph_token(
                tenant_id=settings.tenant_id,
                client_id=settings.client_id,
                client_secret=settings.client_secret,
                timeout_ms=settings.graph_timeout_ms,
            ),
            max_retries=settings.max_retries,
            what="Autenticacion en Microsoft Graph",
        )

        sharepoint_client = SharePointClient(token=token, timeout_ms=settings.graph_timeout_ms)
        target = retry_call(
            lambda: sharepoint_client.resolve_target(
                hostname=settings.sharepoint_hostname,
                site_path=settings.sharepoint_site_path,
                drive_name=settings.sharepoint_drive_name,
                folder_path=settings.sharepoint_folder_path,
                cached_site_id=settings.sharepoint_site_id,
                cached_drive_id=settings.sharepoint_drive_id,
                cached_folder_id=settings.sharepoint_folder_id,
            ),
            max_retries=settings.max_retries,
            what="Resolucion de site/drive/carpeta en SharePoint",
        )

        uploader = SharePointUploader(
            token=token,
            drive_id=target.drive_id,
            default_folder_id=target.folder_id,
            timeout_ms=settings.graph_timeout_ms,
            overwrite=settings.overwrite_existing,
        )
        folder_resolver = SharePointFolderResolver(
            client=sharepoint_client,
            drive_id=target.drive_id,
            default_folder_id=target.folder_id,
        )

    with SalesforceClient(
        domain=settings.salesforce_domain,
        username=settings.salesforce_username,
        password=settings.salesforce_password,
        auth_state_path=settings.auth_state_path,
        manual_login_timeout_minutes=settings.manual_login_timeout_minutes,
        page_timeout_ms=settings.page_timeout_ms,
        headless=settings.headless,
    ) as sf_client:
        log.info("Sesion de Salesforce lista.")

        orchestrator = ReportOrchestrator(
            sf_client=sf_client,
            sharepoint_uploader=uploader,
            folder_resolver=folder_resolver,
            local_copier=local_copier,
            settings=settings,
        )
        summary = orchestrator.run(REPORTS)

    log.info(format_summary(summary))
    return 1 if summary.failed else 0


def _pause_before_exit() -> None:
    """Mantiene la consola abierta tras un error para que se pueda leer.

    Sin esto, al ejecutarse desde el Programador de tareas (run_task.bat usa
    python.exe justamente para que la consola sea visible) o con doble clic,
    la ventana se cierra en el instante en que el proceso termina y el aviso
    de error (credenciales invalidas, fallo de descarga, etc.) desaparece
    antes de que alguien llegue a leerlo. Solo se pausa si hay consola: bajo
    pythonw.exe (sys.stdout es None) nadie podria presionar Enter y se
    bloquearian las ejecuciones desatendidas para siempre.
    """
    if sys.stdout is None:
        return
    try:
        input("\nPresione Enter para cerrar esta ventana...")
    except (EOFError, OSError):
        pass


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
    exit_code = main()
    if exit_code != 0:
        print("\n" + "=" * 50)
        print("ERROR: la ejecucion del bot fallo. Revise el detalle arriba y en logs/.")
        print("=" * 50)
        _pause_before_exit()
    sys.exit(exit_code)

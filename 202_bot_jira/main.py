"""Registra horas trabajadas (worklogs) en Jira a partir de una plantilla Excel.

Composition root: cablea infraestructura (Excel, Jira) con el caso de uso
de aplicación y ejecuta el flujo. La lógica de negocio vive en src/domain
y src/application; este archivo no debe contener reglas de negocio.
"""

import sys

from src.application.use_cases import RegistrarWorklogsUseCase
from src.config import load_settings
from src.domain.models import WorklogOutcome, WorklogRow
from src.infrastructure.excel_repository import ExcelWorklogRepository
from src.infrastructure.jira_gateway import JiraRestWorklogGateway


def _imprimir_estado(row: WorklogRow, outcome: WorklogOutcome) -> None:
    if outcome.skipped:
        return
    estado = "OK" if outcome.ok else outcome.registrado
    print(
        f"[{row.ticket_raw}] {estado} | Fecha: {row.fecha} | "
        f"Registrado: {outcome.registrado} | Comentario: {row.comentario}"
    )


def main():
    settings = load_settings(sys.argv)

    repository = ExcelWorklogRepository(settings.template_path)
    jira = JiraRestWorklogGateway(settings.jira_base_url, settings.jira_user, settings.jira_password)
    use_case = RegistrarWorklogsUseCase(repository, jira, settings.tz, on_row_processed=_imprimir_estado)

    summary = use_case.execute()
    print(summary)


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
    main()

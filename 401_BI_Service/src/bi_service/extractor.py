"""Recorre Power BI Service: workspaces -> datasets / informes -> historial de
actualizaciones y programacion de cada dataset actualizable.

Un error en un workspace o dataset (p.ej. 403 porque la app no tiene permiso)
no corta la corrida: se registra en 'errores' y se sigue con el resto.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol, Sequence

from exceptions import PowerBIApiError
from logging_setup import NOMBRE_LOGGER

logger = logging.getLogger(NOMBRE_LOGGER)


class ClientePowerBI(Protocol):
    def workspaces(self) -> list[dict]: ...
    def datasets(self, workspace_id: str) -> list[dict]: ...
    def informes(self, workspace_id: str) -> list[dict]: ...
    def actualizaciones(self, workspace_id: str, dataset_id: str, top: int) -> list[dict]: ...
    def programacion(self, workspace_id: str, dataset_id: str) -> dict: ...


@dataclass
class Inventario:
    """Respuestas crudas de la API; datasets/informes/actualizaciones/programaciones llevan
    ademas '_workspace' (y '_dataset') con el objeto padre."""

    workspaces: list[dict] = field(default_factory=list)
    datasets: list[dict] = field(default_factory=list)
    informes: list[dict] = field(default_factory=list)
    actualizaciones: list[dict] = field(default_factory=list)
    programaciones: list[dict] = field(default_factory=list)
    errores: list[dict] = field(default_factory=list)


def _seleccionar(workspaces: list[dict], filtro: Sequence[str] | None) -> list[dict]:
    if not filtro:
        return workspaces
    buscados = {f.strip().lower() for f in filtro}
    elegidos = [w for w in workspaces if w.get("name", "").lower() in buscados or w.get("id", "").lower() in buscados]
    encontrados = {w.get("name", "").lower() for w in elegidos} | {w.get("id", "").lower() for w in elegidos}
    for faltante in sorted(buscados - encontrados):
        logger.warning("Workspace %r no visible para la app (revisar que sea miembro).", faltante)
    return elegidos


class Extractor:
    def __init__(self, cliente: ClientePowerBI, top_actualizaciones: int = 100) -> None:
        self._cliente = cliente
        self._top = top_actualizaciones

    def _error(self, inv: Inventario, nivel: str, workspace: dict, objeto: str, exc: Exception) -> None:
        logger.error("  [%s] %s / %s: %s", nivel, workspace.get("name"), objeto, exc)
        inv.errores.append(
            {
                "NIVEL": nivel,
                "WORKSPACE": workspace.get("name"),
                "WORKSPACE_ID": workspace.get("id"),
                "OBJETO": objeto,
                "HTTP": getattr(exc, "status_code", None),
                "DETALLE": str(exc),
            }
        )

    def extraer(self, filtro_workspaces: Sequence[str] | None = None) -> Inventario:
        inv = Inventario()
        inv.workspaces = _seleccionar(self._cliente.workspaces(), filtro_workspaces)
        logger.info("Workspaces a recorrer: %s", len(inv.workspaces))

        for ws in inv.workspaces:
            try:
                datasets = self._cliente.datasets(ws["id"])
            except PowerBIApiError as exc:
                self._error(inv, "WORKSPACE", ws, "datasets", exc)
                continue
            try:
                informes = self._cliente.informes(ws["id"])
            except PowerBIApiError as exc:
                self._error(inv, "WORKSPACE", ws, "informes", exc)
                informes = []
            inv.informes.extend({**r, "_workspace": ws} for r in informes)

            n_act = 0
            for ds in datasets:
                inv.datasets.append({**ds, "_workspace": ws})
                if not ds.get("isRefreshable"):
                    continue
                try:
                    refreshes = self._cliente.actualizaciones(ws["id"], ds["id"], self._top)
                except PowerBIApiError as exc:
                    self._error(inv, "DATASET", ws, ds.get("name", ds["id"]), exc)
                    continue
                inv.actualizaciones.extend({**r, "_workspace": ws, "_dataset": ds} for r in refreshes)
                n_act += len(refreshes)
                try:
                    programacion = self._cliente.programacion(ws["id"], ds["id"])
                except PowerBIApiError as exc:
                    self._error(inv, "PROGRAMACION", ws, ds.get("name", ds["id"]), exc)
                    continue
                inv.programaciones.append({**programacion, "_workspace": ws, "_dataset": ds})
            logger.info(
                "  %s: %s dataset(s), %s informe(s), %s actualizacion(es)",
                ws.get("name"), len(datasets), len(informes), n_act,
            )
        return inv

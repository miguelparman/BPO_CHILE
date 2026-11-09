"""
SharePointClient (solo lectura): resolucion de Site/Drive y descarga de
archivos via Microsoft Graph. Mismo patron que
02_ventas/src/ventas/sharepoint/client.py (resolve_site / resolve_drive /
download_file), sin las funciones de subida que aqui no se necesitan.
"""
from __future__ import annotations

from urllib.parse import quote

import requests

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class SharePointResolutionError(Exception):
    """No se pudo resolver el site/drive, o descargar el archivo, en SharePoint."""


class SharePointClient:
    def __init__(self, token: str, timeout_ms: int) -> None:
        self._token = token
        self._timeout_s = timeout_ms / 1000

    def resolve_site(self, hostname: str, site_path: str) -> str:
        return self._get(f"{GRAPH_BASE}/sites/{hostname}:{site_path}")["id"]

    def resolve_drive(self, site_id: str, drive_name: str) -> str:
        drives = self._get(f"{GRAPH_BASE}/sites/{site_id}/drives").get("value", [])
        for drive in drives:
            if drive.get("name", "").strip().lower() == drive_name.strip().lower():
                return drive["id"]
        raise SharePointResolutionError(
            f"No se encontro el drive '{drive_name}' en el site. "
            f"Drives disponibles: {[d.get('name') for d in drives]}"
        )

    def download_file(self, drive_id: str, file_path: str) -> bytes:
        """Descarga el contenido binario de un archivo (ruta completa dentro del drive)."""
        url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{quote(file_path)}:/content"
        response = requests.get(url, headers=self._headers(), timeout=self._timeout_s)
        if response.status_code == 404:
            raise SharePointResolutionError(f"Archivo no encontrado en Graph: {file_path}")
        if not response.ok:
            raise SharePointResolutionError(
                f"Error Graph {response.status_code} descargando '{file_path}': {response.text[:500]}"
            )
        return response.content

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"}

    def _get(self, url: str) -> dict:
        response = requests.get(url, headers=self._headers(), timeout=self._timeout_s)
        if response.status_code == 404:
            raise SharePointResolutionError(f"Recurso no encontrado en Graph: {url}")
        if not response.ok:
            raise SharePointResolutionError(f"Error Graph {response.status_code} en {url}: {response.text[:500]}")
        return response.json()

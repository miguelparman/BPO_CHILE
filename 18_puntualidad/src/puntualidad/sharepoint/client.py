r"""
SharePointClient: resolucion de Site/Drive, metadatos y descarga de archivos
via Microsoft Graph (solo lectura).

Reutilizado de 17_seguimiento/08_cartera (mismo patron que 04_usuarios_y_retenciones y
30_parque). Reemplaza la lectura del Excel local
...\BPO - Insumos\Chile\INDICADORES CHILE\SLA Puntualidad\DB.xlsx que hacia
el Connection Manager Excel 'SLA' del paquete SSIS_CL_Puntualidad.
"""

from __future__ import annotations

from urllib.parse import quote

import requests

from config import SharePointSettings
from sharepoint.auth import get_graph_token

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class SharePointResolutionError(Exception):
    """No se pudo resolver el site/drive/carpeta, o descargar el archivo, en SharePoint."""


class SharePointClient:
    def __init__(self, token: str, timeout_ms: int) -> None:
        self._token = token
        self._timeout_s = timeout_ms / 1000

    def resolve_site(self, hostname: str, site_path: str) -> str:
        data = self._get(f"{GRAPH_BASE}/sites/{hostname}:{site_path}")
        return data["id"]

    def resolve_drive(self, site_id: str, drive_name: str) -> str:
        data = self._get(f"{GRAPH_BASE}/sites/{site_id}/drives")
        drives = data.get("value", [])
        for drive in drives:
            if drive.get("name", "").strip().lower() == drive_name.strip().lower():
                return drive["id"]
        available = [d.get("name") for d in drives]
        raise SharePointResolutionError(
            f"No se encontro el drive '{drive_name}' en el site. Drives disponibles: {available}"
        )

    def get_item(self, drive_id: str, file_path: str) -> dict:
        """Metadatos de un archivo (name, size, lastModifiedDateTime, ...)."""
        data = self._get(f"{GRAPH_BASE}/drives/{drive_id}/root:/{quote(file_path)}")
        if "file" not in data:
            raise SharePointResolutionError(f"'{file_path}' existe pero no es un archivo.")
        return data

    def download_file(self, drive_id: str, file_path: str) -> bytes:
        """Descarga el contenido binario de un archivo, dada su ruta completa
        dentro del drive (carpeta + nombre de archivo). 'requests' sigue
        automaticamente la redireccion que Graph hace hacia la URL de
        descarga pre-autenticada."""
        url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{quote(file_path)}:/content"
        response = requests.get(url, headers=self._headers(), timeout=self._timeout_s)
        if response.status_code == 404:
            raise SharePointResolutionError(f"Archivo no encontrado en SharePoint: {file_path}")
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
            raise SharePointResolutionError(
                f"Error Graph {response.status_code} en {url}: {response.text[:500]}"
            )
        return response.json()


def conectar(sp: SharePointSettings) -> tuple[SharePointClient, str]:
    """Autentica contra el tenant ReportingFractalia y resuelve el drive.
    Devuelve (cliente, drive_id)."""
    token = get_graph_token(sp.tenant_id, sp.client_id, sp.client_secret, sp.timeout_ms)
    cliente = SharePointClient(token, sp.timeout_ms)
    drive_id = cliente.resolve_drive(cliente.resolve_site(sp.hostname, sp.site_path), sp.drive_name)
    return cliente, drive_id

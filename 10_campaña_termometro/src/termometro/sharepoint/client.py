r"""
SharePointClient: resolucion de Site/Drive, descarga, subida y borrado de
archivos via Microsoft Graph.

Reutilizado tal cual de 15_Logueo (mismo patron que 04_usuarios, 08_cartera,
12_trafico, 14_EPA_WSP y 30_parque). En 10_campaña_termometro solo se usa
download_file: reemplaza la lectura de ACTUAL_.xlsx y Reporte_termometros.csv
desde la carpeta local sincronizada ...\BPO - Insumos\Chile\Campanhas\Termometro.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

import requests

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_SIMPLE_UPLOAD_MAX_BYTES = 4 * 1024 * 1024
_CHUNK_SIZE_BYTES = 5 * 1024 * 1024  # multiplo de 320 KiB, tamano recomendado por Graph


class SharePointResolutionError(Exception):
    """No se pudo resolver el site/drive/carpeta, o descargar el archivo, en SharePoint."""


@dataclass
class SharePointTarget:
    site_id: str
    drive_id: str
    folder_id: str


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

    def resolve_folder(self, drive_id: str, folder_path: str) -> str:
        data = self._get(f"{GRAPH_BASE}/drives/{drive_id}/root:/{quote(folder_path)}")
        return data["id"]

    def resolve_default_drive(self, site_id: str) -> str:
        """Devuelve el ID del drive por defecto del site."""
        data = self._get(f"{GRAPH_BASE}/sites/{site_id}/drive")
        return data["id"]

    def resolve_target(
        self, hostname: str, site_path: str, drive_name: str, folder_path: str
    ) -> SharePointTarget:
        site_id = self.resolve_site(hostname, site_path)
        drive_id = self.resolve_drive(site_id, drive_name)
        folder_id = self.resolve_folder(drive_id, folder_path)
        return SharePointTarget(site_id=site_id, drive_id=drive_id, folder_id=folder_id)

    def download_file(self, drive_id: str, file_path: str) -> bytes:
        """Descarga el contenido binario de un archivo, dada su ruta completa
        dentro del drive (carpeta + nombre de archivo). 'requests' sigue
        automaticamente la redireccion que Graph hace hacia la URL de
        descarga pre-autenticada."""
        url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{quote(file_path)}:/content"
        response = requests.get(url, headers=self._headers(), timeout=self._timeout_s)
        if response.status_code == 404:
            raise SharePointResolutionError(f"Archivo no encontrado en Graph: {url}")
        if not response.ok:
            raise SharePointResolutionError(
                f"Error Graph {response.status_code} descargando '{file_path}': {response.text[:500]}"
            )
        return response.content

    def upload_file(self, drive_id: str, file_path: str, contenido: bytes) -> dict:
        """Sube (y reemplaza) un archivo, dada su ruta completa dentro del
        drive. Mismo criterio que 01_servidor_chile/sharepoint/uploader.py:
        <= 4 MB con PUT .../content; mas grande, con createUploadSession en
        bloques de 5 MB (conflictBehavior=replace)."""
        if len(contenido) <= _SIMPLE_UPLOAD_MAX_BYTES:
            url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{quote(file_path)}:/content"
            response = requests.put(url, headers=self._headers(), data=contenido, timeout=self._timeout_s)
            self._raise_for_write(response, "subiendo", file_path)
            return response.json()

        session = requests.post(
            f"{GRAPH_BASE}/drives/{drive_id}/root:/{quote(file_path)}:/createUploadSession",
            headers=self._headers(),
            json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
            timeout=self._timeout_s,
        )
        self._raise_for_write(session, "creando la sesion de carga de", file_path)
        upload_url = session.json()["uploadUrl"]
        total = len(contenido)
        respuesta = None
        for offset in range(0, total, _CHUNK_SIZE_BYTES):
            bloque = contenido[offset : offset + _CHUNK_SIZE_BYTES]
            headers = {  # la sesion de carga es pre-autenticada (sin Authorization)
                "Content-Length": str(len(bloque)),
                "Content-Range": f"bytes {offset}-{offset + len(bloque) - 1}/{total}",
            }
            respuesta = requests.put(upload_url, headers=headers, data=bloque, timeout=self._timeout_s)
            self._raise_for_write(respuesta, "subiendo", file_path)
        return respuesta.json() if respuesta is not None and respuesta.content else {}

    def delete_file(self, drive_id: str, file_path: str) -> bool:
        """Elimina un archivo (a la papelera del sitio). False si no existia."""
        url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{quote(file_path)}"
        response = requests.delete(url, headers=self._headers(), timeout=self._timeout_s)
        if response.status_code == 404:
            return False
        self._raise_for_write(response, "eliminando", file_path)
        return True

    def _raise_for_write(self, response: requests.Response, accion: str, file_path: str) -> None:
        if not response.ok:
            raise SharePointResolutionError(
                f"Error Graph {response.status_code} {accion} '{file_path}': {response.text[:500]}"
            )

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

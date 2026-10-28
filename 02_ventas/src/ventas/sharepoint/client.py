"""
SharePointClient: resolucion de Site/Drive/Item, descarga y subida de
archivos via Microsoft Graph.

resolve_site/resolve_drive/resolve_folder/resolve_default_drive/download_file
son el mismo patron ya usado en 01_servidor_chile, 30_parque y 04_usuarios_y_retenciones.

upload_file es nuevo aqui: el paso 0 de 02_ventas ('FUNNEL VENTAS V2.xlsx'
del sitio 'BPO' hacia '07 CROSS' en 'ReportingFractalia') copia el archivo
DE UN TENANT DE MICROSOFT ENTRA A OTRO -- 'BPO' y 'ReportingFractalia'
requieren credenciales/App Registration distintas (ver config.py,
SharePointOrigenSettings), asi que no se puede usar el endpoint de copia
asincrona nativo de Graph ('POST .../copy'), que solo copia dentro del
mismo tenant/token. En vez de eso, copiar_funnel_ventas.py hace
download_file() con el token de origen y upload_file() con el token de
destino (2 instancias de SharePointClient, una por tenant).
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

import requests

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

_SIMPLE_UPLOAD_MAX_BYTES = 4 * 1024 * 1024
_CHUNK_SIZE_BYTES = 5 * 1024 * 1024  # multiplo de 320 KiB, tamano recomendado por Graph


class SharePointResolutionError(Exception):
    """No se pudo resolver el site/drive/carpeta/archivo, o descargar el
    archivo, en SharePoint."""


class SharePointUploadError(Exception):
    """Fallo subiendo un archivo a SharePoint."""


@dataclass(frozen=True)
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
        dentro del drive (carpeta + nombre de archivo)."""
        url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{quote(file_path)}:/content"
        response = requests.get(url, headers=self._headers(), timeout=self._timeout_s)
        if response.status_code == 404:
            raise SharePointResolutionError(f"Archivo no encontrado en Graph: {url}")
        if not response.ok:
            raise SharePointResolutionError(
                f"Error Graph {response.status_code} descargando '{file_path}': {response.text[:500]}"
            )
        return response.content

    def upload_file(self, drive_id: str, folder_id: str, filename: str, content: bytes) -> None:
        """Sube 'content' como 'filename' dentro de la carpeta 'folder_id'.
        Reemplaza si ya existe un archivo con ese nombre (mismo
        comportamiento pedido por el usuario para 'Señalizaciones.csv':
        "si encuentra un archivo del mismo nombre se reemplazará").
        Archivos <= 4 MB: PUT .../content (subida simple). Archivos > 4 MB:
        createUploadSession con chunks de 5 MB -- mismo patron que
        01_servidor_chile/sharepoint/uploader.py."""
        if len(content) <= _SIMPLE_UPLOAD_MAX_BYTES:
            self._upload_simple(drive_id, folder_id, filename, content)
        else:
            self._upload_in_chunks(drive_id, folder_id, filename, content)

    def _upload_simple(self, drive_id: str, folder_id: str, filename: str, content: bytes) -> None:
        url = f"{GRAPH_BASE}/drives/{drive_id}/items/{folder_id}:/{quote(filename)}:/content"
        response = requests.put(url, headers=self._headers(), data=content, timeout=self._timeout_s)
        self._raise_for_upload_error(response, filename)

    def _upload_in_chunks(self, drive_id: str, folder_id: str, filename: str, content: bytes) -> None:
        session_url = f"{GRAPH_BASE}/drives/{drive_id}/items/{folder_id}:/{quote(filename)}:/createUploadSession"
        session_response = requests.post(
            session_url,
            headers=self._headers(),
            json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
            timeout=self._timeout_s,
        )
        self._raise_for_upload_error(session_response, filename)
        upload_url = session_response.json()["uploadUrl"]

        size = len(content)
        offset = 0
        while offset < size:
            chunk = content[offset : offset + _CHUNK_SIZE_BYTES]
            chunk_headers = {
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {offset}-{offset + len(chunk) - 1}/{size}",
            }
            # La sesion de carga es publica (no lleva Authorization).
            chunk_response = requests.put(upload_url, headers=chunk_headers, data=chunk, timeout=self._timeout_s)
            self._raise_for_upload_error(chunk_response, filename)
            offset += len(chunk)

    def _raise_for_upload_error(self, response: requests.Response, filename: str) -> None:
        if response.ok:
            return
        raise SharePointUploadError(
            f"Fallo al subir '{filename}' a SharePoint (HTTP {response.status_code}): {response.text[:300]}"
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

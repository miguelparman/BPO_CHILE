"""
SharePointClient: resolucion de Site/Drive/Item, descarga y subida de
archivos via Microsoft Graph.

Mismo codigo que 16_Gerencia y 11_correos/src/correos/comun/sharepoint_client.py
(resolve_*, download_file, upload_file simple <=4MB / por chunks >4MB).
Agrega get_item (metadatos de un archivo: tamano, fecha) para validar que
los 4 Excel existen y para verificar la copia, y conectar() que resuelve
cliente + drive a partir de un GraphSettings.
"""

from __future__ import annotations

from urllib.parse import quote

import requests

from config import GraphSettings
from exceptions import SharePointResolutionError, SharePointUploadError
from sharepoint.auth import get_graph_token

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

_SIMPLE_UPLOAD_MAX_BYTES = 4 * 1024 * 1024
_CHUNK_SIZE_BYTES = 5 * 1024 * 1024  # multiplo de 320 KiB, tamano recomendado por Graph


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

    def resolve_default_drive(self, site_id: str) -> str:
        """ID del drive por defecto del site (util cuando el site solo tiene
        un drive, como 'BPO')."""
        data = self._get(f"{GRAPH_BASE}/sites/{site_id}/drive")
        return data["id"]

    def resolve_folder(self, drive_id: str, folder_path: str) -> str:
        data = self._get(f"{GRAPH_BASE}/drives/{drive_id}/root:/{quote(folder_path)}")
        if "folder" not in data:
            raise SharePointResolutionError(f"'{folder_path}' existe pero no es una carpeta.")
        return data["id"]

    def get_item(self, drive_id: str, file_path: str) -> dict:
        """Metadatos de un archivo (name, size, lastModifiedDateTime, ...)."""
        data = self._get(f"{GRAPH_BASE}/drives/{drive_id}/root:/{quote(file_path)}")
        if "file" not in data:
            raise SharePointResolutionError(f"'{file_path}' existe pero no es un archivo.")
        return data

    def download_file(self, drive_id: str, file_path: str) -> bytes:
        """Descarga el contenido binario de un archivo, dada su ruta completa
        dentro del drive (carpeta + nombre de archivo)."""
        url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{quote(file_path)}:/content"
        response = requests.get(url, headers=self._headers(), timeout=self._timeout_s)
        if response.status_code == 404:
            raise SharePointResolutionError(f"Archivo no encontrado en Graph: {file_path}")
        if not response.ok:
            raise SharePointResolutionError(
                f"Error Graph {response.status_code} descargando '{file_path}': {response.text[:500]}"
            )
        return response.content

    def upload_file(self, drive_id: str, folder_id: str, filename: str, content: bytes) -> None:
        """Sube 'content' como 'filename' dentro de la carpeta 'folder_id'.
        Reemplaza si ya existe un archivo con ese nombre. Archivos <= 4 MB:
        PUT .../content (subida simple). Archivos > 4 MB: createUploadSession
        con chunks de 5 MB."""
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
            raise SharePointResolutionError(f"Error Graph {response.status_code} en {url}: {response.text[:500]}")
        return response.json()


def conectar(sp: GraphSettings) -> tuple[SharePointClient, str]:
    """Autentica contra el tenant de 'sp' y resuelve su drive (el indicado o
    el por defecto del sitio). Devuelve (cliente, drive_id)."""
    token = get_graph_token(sp.tenant_id, sp.client_id, sp.client_secret, sp.timeout_ms)
    cliente = SharePointClient(token, sp.timeout_ms)
    site_id = cliente.resolve_site(sp.hostname, sp.site_path)
    drive_id = cliente.resolve_drive(site_id, sp.drive_name) if sp.drive_name else cliente.resolve_default_drive(site_id)
    return cliente, drive_id


class ConexionGraph:
    """(cliente, drive_id) de un sitio, resuelto al primer uso y reutilizado:
    los componentes la reciben armada en main.py pero no autentican hasta
    que el pipeline ya valido las conexiones."""

    def __init__(self, sp: GraphSettings, conectar_fn=conectar) -> None:
        self._sp = sp
        self._conectar = conectar_fn
        self._par: tuple[SharePointClient, str] | None = None

    def obtener(self) -> tuple[SharePointClient, str]:
        if self._par is None:
            self._par = self._conectar(self._sp)
        return self._par

"""
SharePointClient: resolucion de Site/Drive/Item, listado, descarga y subida
de archivos via Microsoft Graph.

resolve_site/resolve_drive/resolve_default_drive/resolve_folder/download_file
son el mismo patron ya usado en 01_servidor_chile, 30_parque, 04_usuarios_y_retenciones y
02_ventas. upload_file (subida simple <=4MB / por chunks >4MB) es el mismo
codigo que 02_ventas/src/ventas/sharepoint/client.py agrego para copiar
'FUNNEL VENTAS V2.xlsx' entre los tenants 'BPO' y 'ReportingFractalia'.

list_excel_files es nuevo aqui: '11_correos' copia TODOS los .xlsx de una
carpeta (no un archivo fijo), asi que hace falta enumerar el contenido de la
carpeta origen primero. Solo lista archivos del nivel raiz de la carpeta
indicada (no recorre subcarpetas -- 'Control Correos Chile' tiene una
subcarpeta 'Macros_Coordinadores' con macros .bas que no se debe copiar).
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

import requests

from comun.config import SharePointDestinoSettings
from comun.exceptions import SharePointResolutionError, SharePointUploadError
from comun.sharepoint_auth import get_graph_token

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

_SIMPLE_UPLOAD_MAX_BYTES = 4 * 1024 * 1024
_CHUNK_SIZE_BYTES = 5 * 1024 * 1024  # multiplo de 320 KiB, tamano recomendado por Graph
_EXCEL_EXTENSIONS = (".xlsx", ".xlsm", ".xls")


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

    def resolve_default_drive(self, site_id: str) -> str:
        """Devuelve el ID del drive por defecto del site (util cuando el site
        solo tiene un drive, como 'BPO')."""
        data = self._get(f"{GRAPH_BASE}/sites/{site_id}/drive")
        return data["id"]

    def resolve_folder(self, drive_id: str, folder_path: str) -> str:
        data = self._get(f"{GRAPH_BASE}/drives/{drive_id}/root:/{quote(folder_path)}")
        return data["id"]

    def resolve_target(
        self, hostname: str, site_path: str, drive_name: str, folder_path: str
    ) -> SharePointTarget:
        site_id = self.resolve_site(hostname, site_path)
        drive_id = self.resolve_drive(site_id, drive_name)
        folder_id = self.resolve_folder(drive_id, folder_path)
        return SharePointTarget(site_id=site_id, drive_id=drive_id, folder_id=folder_id)

    def list_excel_files(self, drive_id: str, folder_path: str) -> list[str]:
        """Devuelve los nombres de los archivos Excel (.xlsx/.xlsm/.xls) en el
        nivel raiz de 'folder_path', ignorando subcarpetas y cualquier otro
        tipo de archivo. Sigue la paginacion de Graph ('@odata.nextLink')."""
        nombres: list[str] = []
        url = (
            f"{GRAPH_BASE}/drives/{drive_id}/root:/{quote(folder_path)}:/children"
            "?$select=name,file,folder&$top=200"
        )
        while url:
            data = self._get(url)
            for item in data.get("value", []):
                if "file" not in item:
                    continue  # subcarpeta u otro tipo de item
                nombre = item.get("name", "")
                if nombre.lower().endswith(_EXCEL_EXTENSIONS):
                    nombres.append(nombre)
            url = data.get("@odata.nextLink")
        return nombres

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
            raise SharePointResolutionError(
                f"Error Graph {response.status_code} en {url}: {response.text[:500]}"
            )
        return response.json()


def conectar_destino(destino: SharePointDestinoSettings) -> tuple[SharePointClient, str]:
    """Autentica contra el tenant 'ReportingFractalia' y resuelve el drive de
    '14 CORREOS'. Devuelve (cliente, drive_id). La usan la copia (ingesta),
    la verificacion de la copia y la descarga de bronze."""
    token = get_graph_token(destino.tenant_id, destino.client_id, destino.client_secret, destino.timeout_ms)
    cliente = SharePointClient(token, destino.timeout_ms)
    site_id = cliente.resolve_site(destino.hostname, destino.site_path)
    return cliente, cliente.resolve_drive(site_id, destino.drive_name)

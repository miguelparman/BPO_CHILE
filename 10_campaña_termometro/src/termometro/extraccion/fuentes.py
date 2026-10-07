"""
De dónde se leen los archivos crudos.

- FuenteSharePoint: descarga el archivo vía Microsoft Graph (origen normal).
- FuenteLocal: lee el archivo desde disco (contingencia: --excel-local / --csv-local).

Ambas devuelven los bytes del archivo; el parseo (Excel/CSV) lo hacen los extractores.
"""
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

from sharepoint.client import SharePointClient


class Fuente(Protocol):
    descripcion: str

    def leer(self) -> bytes: ...


class FuenteSharePoint:
    def __init__(self, client: SharePointClient, drive_id: str, ruta: str, web_drive: str = "") -> None:
        self._client = client
        self._drive_id = drive_id
        self._ruta = ruta
        self.descripcion = f"{web_drive}/{quote(ruta)}" if web_drive else f"SharePoint:{ruta}"

    def leer(self) -> bytes:
        return self._client.download_file(self._drive_id, self._ruta)


class FuenteLocal:
    def __init__(self, ruta: Path) -> None:
        self._ruta = Path(ruta)
        self.descripcion = str(self._ruta)

    def leer(self) -> bytes:
        return self._ruta.read_bytes()

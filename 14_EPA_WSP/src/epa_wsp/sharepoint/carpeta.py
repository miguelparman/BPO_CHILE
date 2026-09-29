"""CarpetaSharePoint: una carpeta de SharePoint donde el proceso LEE y ESCRIBE
archivos via Microsoft Graph.

Reemplaza a las 2 carpetas locales que usaban los scripts originales:
  - ...\\Data Analytics Reporting Fractalia - Medallia\\Encuestas_Medallia.csv
    (lo escribia CL_Descarga_encuestas_Medallia.py y lo leia
    CL_Carga_de_encuestas_MEDALLIA.py), y
  - ...\\Gestion Indicadores MDS - Cl_encuesta\\resultado.txt
    (lo escribia enviar_alerta_encuesta.py para Power Automate).
Ambos quedan en Data Reporting/REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/16 MEDALLIA
(SHAREPOINT_FOLDER_MEDALLIA).
"""

from __future__ import annotations

from urllib.parse import quote

from sharepoint.client import SharePointClient


class CarpetaSharePoint:
    def __init__(self, client: SharePointClient, drive_id: str, folder_path: str, web_base: str = "") -> None:
        self._client = client
        self._drive_id = drive_id
        self.folder_path = folder_path.strip("/")
        self._web_base = web_base.rstrip("/")

    def ruta(self, nombre: str) -> str:
        return f"{self.folder_path}/{nombre}"

    def url(self, nombre: str) -> str:
        """Ruta legible para los logs (URL web si se conoce el drive)."""
        if self._web_base:
            return f"{self._web_base}/{quote(self.ruta(nombre))}"
        return self.ruta(nombre)

    def leer(self, nombre: str) -> bytes:
        return self._client.download_file(self._drive_id, self.ruta(nombre))

    def escribir(self, nombre: str, contenido: bytes) -> None:
        self._client.upload_file(self._drive_id, self.ruta(nombre), contenido)

    def eliminar(self, nombre: str) -> bool:
        """True si el archivo existia y se elimino."""
        return self._client.delete_file(self._drive_id, self.ruta(nombre))

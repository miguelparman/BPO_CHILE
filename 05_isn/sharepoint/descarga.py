"""Descarga de archivos de la carpeta SharePoint configurada (Settings.sharepoint_*)."""
from __future__ import annotations

import logging

from config import settings
from sharepoint.auth import get_graph_token
from sharepoint.client import SharePointClient

logger = logging.getLogger(__name__)


def descargar_archivo(nombre_archivo: str, carpeta: str | None = None) -> bytes:
    """Descarga `nombre_archivo` desde `carpeta` (por defecto sp_folder_path) (via Microsoft Graph,
    app-only) y devuelve su contenido en bytes."""
    s = settings
    token = get_graph_token(s.sp_tenant_id, s.sp_client_id, s.sp_client_secret, s.sp_timeout_ms)
    client = SharePointClient(token, s.sp_timeout_ms)
    site_id = client.resolve_site(s.sp_hostname, s.sp_site_path)
    drive_id = client.resolve_drive(site_id, s.sp_drive_name)
    ruta = f"{(carpeta or s.sp_folder_path).strip('/')}/{nombre_archivo}"
    logger.info("Descargando por Graph: %s/%s%s", s.sp_hostname, s.sp_site_path, "/" + ruta)
    contenido = client.download_file(drive_id, ruta)
    logger.info("Descargados %d bytes de %s", len(contenido), nombre_archivo)
    return contenido

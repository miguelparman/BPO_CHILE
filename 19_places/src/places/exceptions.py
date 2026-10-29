"""Jerarquia de errores del proceso. Todas heredan de PlacesError para que
main.py pueda distinguir errores esperados (log claro, exit 1) de bugs."""

from __future__ import annotations


class PlacesError(Exception):
    """Error base del proceso Carga Places."""


class ConfiguracionError(PlacesError):
    """Falta una variable de entorno o tiene un valor invalido."""


class ConexionError(PlacesError):
    """Alguna conexion no respondio tras los reintentos automaticos."""


class GraphAuthError(PlacesError):
    """Fallo obteniendo el access token de Microsoft Graph."""


class SharePointResolutionError(PlacesError):
    """No se pudo resolver un site/drive/carpeta/archivo en Graph."""


class SharePointUploadError(PlacesError):
    """Fallo la subida de un archivo a SharePoint."""


class ExtraccionError(PlacesError):
    """El Excel no se pudo leer o no tiene la hoja/columnas del .dtsx (Excel Source)."""


class ValidacionError(PlacesError):
    """Un valor provocaria FailComponent en la 'Conversion de datos' del .dtsx."""


class CargaError(PlacesError):
    """Fallo una sentencia o el INSERT en SQL Server (con rollback)."""

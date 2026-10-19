"""Jerarquia de errores del proceso. Todas heredan de GerenciaError para que
main.py pueda distinguir errores esperados (log claro, exit 1) de bugs."""

from __future__ import annotations


class GerenciaError(Exception):
    """Error base del proceso Volumetria Gerencia."""


class ConfiguracionError(GerenciaError):
    """Falta una variable de entorno o tiene un valor invalido."""


class ConexionError(GerenciaError):
    """Alguna conexion no respondio tras los reintentos automaticos."""


class GraphAuthError(GerenciaError):
    """Fallo obteniendo el access token de Microsoft Graph."""


class SharePointResolutionError(GerenciaError):
    """No se pudo resolver un site/drive/carpeta/archivo en Graph."""


class SharePointUploadError(GerenciaError):
    """Fallo la subida de un archivo a SharePoint."""


class CopiaError(GerenciaError):
    """Fallo la copia BPO -> ReportingFractalia de un archivo."""


class ExtraccionError(GerenciaError):
    """El Excel no se pudo leer o no tiene la hoja/columnas del .dtsx (Excel Source)."""


class ValidacionError(GerenciaError):
    """Un valor provocaria FailComponent en la 'Conversion de datos' del .dtsx."""


class CargaError(GerenciaError):
    """Fallo una sentencia o el INSERT en SQL Server (con rollback)."""

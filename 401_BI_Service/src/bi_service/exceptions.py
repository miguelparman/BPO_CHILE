"""Jerarquia de errores del proceso. Todas heredan de BIServiceError para que
main.py pueda distinguir errores esperados (log claro, exit 1) de bugs."""

from __future__ import annotations


class BIServiceError(Exception):
    """Error base del proceso 401_BI_Service."""


class ConfiguracionError(BIServiceError):
    """Falta una variable de entorno o tiene un valor invalido."""


class ConexionError(BIServiceError):
    """Alguna conexion no respondio tras los reintentos automaticos."""


class PowerBIAuthError(BIServiceError):
    """Fallo obteniendo el access token de Power BI."""


class PowerBIApiError(BIServiceError):
    """La API REST de Power BI respondio con error."""

    def __init__(self, mensaje: str, status_code: int | None = None) -> None:
        super().__init__(mensaje)
        self.status_code = status_code


class SalidaError(BIServiceError):
    """No se pudo escribir el Excel/CSV de salida (p.ej. el Excel esta abierto)."""

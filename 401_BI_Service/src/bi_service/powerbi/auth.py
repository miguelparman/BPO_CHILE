"""
Autenticacion contra la API REST de Power BI via OAuth 2.0 Client Credentials
(app-only, sin usuario interactivo).

Mismo patron que sharepoint/auth.py de 11_correos/16_Gerencia ('requests' +
endpoint v2 de Microsoft identity platform), con el scope de Power BI.
"""

from __future__ import annotations

import requests

from exceptions import PowerBIAuthError

_TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
SCOPE_POWERBI = "https://analysis.windows.net/powerbi/api/.default"


def get_powerbi_token(tenant_id: str, client_id: str, client_secret: str, timeout_s: float) -> tuple[str, int]:
    """Solicita un access token de aplicacion. Devuelve (token, segundos_de_vigencia)."""
    try:
        response = requests.post(
            _TOKEN_URL_TEMPLATE.format(tenant_id=tenant_id),
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": SCOPE_POWERBI,
            },
            timeout=timeout_s,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        respuesta = getattr(exc, "response", None)
        detalle = ""
        if respuesta is not None:
            try:
                detalle = f": {respuesta.json().get('error_description', '').splitlines()[0]}"
            except (ValueError, IndexError, AttributeError):
                detalle = f" (HTTP {respuesta.status_code})"
        error = PowerBIAuthError(f"No se pudo obtener el token de Power BI{detalle}")
        error.response = respuesta
        raise error from None

    datos = response.json()
    return datos["access_token"], int(datos.get("expires_in", 3599))

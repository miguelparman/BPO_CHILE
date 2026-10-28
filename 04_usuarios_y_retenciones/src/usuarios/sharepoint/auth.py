"""
Autenticacion contra Microsoft Graph via OAuth 2.0 Client Credentials
(app-only, sin usuario interactivo).

Identico al patron ya usado en 30_parque/sharepoint/auth.py,
01_servidor_chile/sharepoint/auth.py y 201_bot_salesforce/app/sharepoint/auth.py:
'requests' + endpoint v2 de Microsoft identity platform, sin msal ni
azure-identity, para mantener consistencia con el resto del repositorio.
"""

from __future__ import annotations

import requests

_TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"


class GraphAuthError(Exception):
    """Fallo obteniendo el access token de Microsoft Graph."""


def get_graph_token(tenant_id: str, client_id: str, client_secret: str, timeout_ms: int) -> str:
    """Solicita un access token de aplicacion (scope .default) y lo devuelve."""
    try:
        response = requests.post(
            _TOKEN_URL_TEMPLATE.format(tenant_id=tenant_id),
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "https://graph.microsoft.com/.default",
            },
            timeout=timeout_ms / 1000,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        error = GraphAuthError("No se pudo obtener el token de Microsoft Graph.")
        error.response = getattr(exc, "response", None)
        raise error from None

    return response.json()["access_token"]

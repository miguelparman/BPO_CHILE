"""Correo de aviso cuando el proceso falla (Microsoft Graph, POST /users/{remitente}/sendMail).

Usa un app registration PROPIO del correo (MAIL_TENANT_ID / MAIL_CLIENT_ID /
MAIL_CLIENT_SECRET), distinto del de SharePoint, con el permiso de aplicacion
'Mail.Send' aprobado. Desactivado mientras falte alguno de esos datos, el
remitente o los destinatarios. Un fallo al enviar el correo NUNCA rompe el
proceso: solo se registra.
"""

from __future__ import annotations

import logging
from typing import Callable

import requests

from config import MailSettings
from sharepoint.auth import get_graph_token

logger = logging.getLogger("epa_wsp")

_URL = "https://graph.microsoft.com/v1.0/users/{remitente}/sendMail"


def enviar_aviso_fallo(
    mail: MailSettings,
    asunto: str,
    cuerpo: str,
    post: Callable[..., requests.Response] = requests.post,
    obtener_token: Callable[[MailSettings], str] | None = None,
) -> bool:
    """Envia el correo. Devuelve True si Graph lo acepto; False si esta
    desactivado o fallo (en ese caso lo registra y sigue)."""
    if not mail.activo:
        logger.info("Aviso por correo desactivado (faltan datos MAIL_* en el .env).")
        return False
    obtener_token = obtener_token or (
        lambda m: get_graph_token(m.tenant_id, m.client_id, m.client_secret, 30_000)
    )
    try:
        respuesta = post(
            _URL.format(remitente=mail.remitente),
            headers={"Authorization": f"Bearer {obtener_token(mail)}"},
            json={
                "message": {
                    "subject": asunto,
                    "body": {"contentType": "Text", "content": cuerpo},
                    "toRecipients": [{"emailAddress": {"address": d}} for d in mail.destinatarios],
                },
                "saveToSentItems": False,
            },
            timeout=30,
        )
        if respuesta.status_code != 202:
            pista = " (falta el permiso de aplicacion 'Mail.Send' aprobado en el app registration)" if respuesta.status_code in (401, 403) else ""
            raise RuntimeError(f"Graph respondio {respuesta.status_code}{pista}: {respuesta.text[:300]}")
    except Exception as exc:  # noqa: BLE001 - el aviso no debe romper el proceso
        logger.warning("No se pudo enviar el correo de aviso por Graph: %s", exc)
        return False
    logger.info("Correo de aviso enviado a %s.", ", ".join(mail.destinatarios))
    return True

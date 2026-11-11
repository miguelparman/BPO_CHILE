"""Correo de aviso cuando el proceso falla (SMTP).

Desactivado mientras falten MAIL_SERVIDOR / MAIL_REMITENTE / MAIL_DESTINATARIOS.
Un fallo al enviar el correo NUNCA rompe el proceso: solo se registra.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Callable

from config import MailSettings

logger = logging.getLogger("epa_wsp")


def enviar_aviso_fallo(
    mail: MailSettings,
    asunto: str,
    cuerpo: str,
    smtp_factory: Callable[..., smtplib.SMTP] = smtplib.SMTP,
) -> bool:
    """Envia el correo. Devuelve True si el servidor lo acepto; False si esta
    desactivado o fallo (en ese caso lo registra y sigue)."""
    if not mail.activo:
        logger.info("Aviso por correo desactivado (MAIL_SERVIDOR / MAIL_REMITENTE / MAIL_DESTINATARIOS vacios).")
        return False
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = asunto, mail.remitente, ", ".join(mail.destinatarios)
    msg.set_content(cuerpo)
    try:
        with smtp_factory(mail.servidor, mail.puerto, timeout=30) as smtp:
            if mail.starttls:
                smtp.starttls()
            if mail.usuario:
                smtp.login(mail.usuario, mail.password)
            smtp.send_message(msg)
    except Exception as exc:  # noqa: BLE001 - el aviso no debe romper el proceso
        logger.warning("No se pudo enviar el correo de aviso por SMTP (%s:%s): %s", mail.servidor, mail.puerto, exc)
        return False
    logger.info("Correo de aviso enviado a %s.", ", ".join(mail.destinatarios))
    return True

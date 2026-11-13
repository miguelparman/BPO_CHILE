"""Correo de aviso de fallo (Graph sendMail) con un POST falso."""

from config import MailSettings
from notificacion import enviar_aviso_fallo


class Resp:
    def __init__(self, codigo, texto=""):
        self.status_code, self.text = codigo, texto


def _mail(**kw):
    base = dict(tenant_id="t", client_id="c", client_secret="s", remitente="a@x.com", destinatarios=("a@x.com", "b@x.com"))
    base.update(kw)
    return MailSettings(**base)


def _token(m):
    return f"TOKEN-{m.client_id}"


def test_desactivado_si_falta_cualquier_dato():
    llamadas = []
    for m in (MailSettings(), _mail(client_secret=""), _mail(remitente=""), _mail(destinatarios=())):
        assert enviar_aviso_fallo(m, "s", "c", post=lambda *a, **k: llamadas.append(1), obtener_token=_token) is False
    assert not llamadas


def test_envia_con_el_formato_de_graph():
    capt = {}

    def post(url, headers, json, timeout):
        capt.update(url=url, headers=headers, json=json)
        return Resp(202)

    assert enviar_aviso_fallo(_mail(), "asunto", "cuerpo", post=post, obtener_token=_token) is True
    assert capt["url"].endswith("/users/a@x.com/sendMail")
    assert capt["headers"]["Authorization"] == "Bearer TOKEN-c"
    msg = capt["json"]["message"]
    assert msg["subject"] == "asunto" and msg["body"]["content"] == "cuerpo"
    assert [r["emailAddress"]["address"] for r in msg["toRecipients"]] == ["a@x.com", "b@x.com"]


def test_error_de_graph_no_rompe_el_proceso(caplog):
    r = enviar_aviso_fallo(_mail(), "s", "c", post=lambda *a, **k: Resp(403, "denied"), obtener_token=_token)
    assert r is False and "Mail.Send" in caplog.text


def test_fallo_al_obtener_token_o_enviar_no_se_propaga():
    def sin_token(m):
        raise ConnectionError("sin red")

    assert enviar_aviso_fallo(_mail(), "s", "c", post=lambda *a, **k: Resp(202), obtener_token=sin_token) is False

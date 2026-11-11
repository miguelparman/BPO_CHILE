"""Correo de aviso de fallo (SMTP) con un servidor falso."""

from config import MailSettings
from notificacion import enviar_aviso_fallo


class FakeSMTP:
    instancias: list = []

    def __init__(self, servidor, puerto, timeout):
        self.args, self.pasos, self.mensaje = (servidor, puerto, timeout), [], None
        FakeSMTP.instancias.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        self.pasos.append("starttls")

    def login(self, u, p):
        self.pasos.append(("login", u, p))

    def send_message(self, msg):
        self.mensaje = msg


def _mail(**kw):
    base = dict(servidor="smtp.x.com", remitente="a@x.com", destinatarios=("a@x.com", "b@x.com"),
                usuario="u", password="p")
    base.update(kw)
    return MailSettings(**base)


def test_desactivado_si_falta_servidor_remitente_o_destinatarios():
    FakeSMTP.instancias.clear()
    assert enviar_aviso_fallo(MailSettings(), "s", "c", smtp_factory=FakeSMTP) is False
    assert enviar_aviso_fallo(_mail(servidor=""), "s", "c", smtp_factory=FakeSMTP) is False
    assert not FakeSMTP.instancias


def test_envia_con_starttls_login_y_destinatarios():
    FakeSMTP.instancias.clear()
    assert enviar_aviso_fallo(_mail(), "asunto", "cuerpo", smtp_factory=FakeSMTP) is True
    s = FakeSMTP.instancias[0]
    assert s.args == ("smtp.x.com", 587, 30)
    assert s.pasos == ["starttls", ("login", "u", "p")]
    assert s.mensaje["Subject"] == "asunto" and s.mensaje["To"] == "a@x.com, b@x.com"
    assert s.mensaje.get_content().strip() == "cuerpo"


def test_sin_usuario_ni_starttls_no_autentica():
    FakeSMTP.instancias.clear()
    enviar_aviso_fallo(_mail(usuario="", starttls=False), "s", "c", smtp_factory=FakeSMTP)
    assert FakeSMTP.instancias[0].pasos == []


def test_error_del_servidor_no_rompe_el_proceso(caplog):
    def falla(*a, **k):
        raise ConnectionRefusedError("rechazado")

    assert enviar_aviso_fallo(_mail(), "s", "c", smtp_factory=falla) is False
    assert "No se pudo enviar el correo" in caplog.text

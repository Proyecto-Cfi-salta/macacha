from email.message import EmailMessage
from unittest.mock import MagicMock, patch

from agent import mail


def test_enviar_mail_usa_configuracion_del_entorno(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.ejemplo.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "usuario@ejemplo.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secreta")
    monkeypatch.setenv("SMTP_FROM", "notificaciones@macacha.gob.ar")

    smtp_instance = MagicMock()
    smtp_instance.__enter__.return_value = smtp_instance

    contexto = object()
    with patch("agent.mail.smtplib.SMTP", return_value=smtp_instance) as smtp_cls, patch(
        "ssl.create_default_context", return_value=contexto
    ):
        mail.enviar_mail(
            ["admin@ejemplo.com", "otro@ejemplo.com"],
            asunto="Nueva consulta de Juan",
            cuerpo_texto="Hola, tengo una consulta.",
        )

    smtp_cls.assert_called_once_with("smtp.ejemplo.com", 587, timeout=10)
    smtp_instance.starttls.assert_called_once_with(context=contexto)
    smtp_instance.login.assert_called_once_with("usuario@ejemplo.com", "secreta")

    assert smtp_instance.send_message.call_count == 1
    mensaje_enviado: EmailMessage = smtp_instance.send_message.call_args[0][0]
    assert mensaje_enviado["Subject"] == "Nueva consulta de Juan"
    assert mensaje_enviado["From"] == "notificaciones@macacha.gob.ar"
    assert mensaje_enviado["To"] == "admin@ejemplo.com, otro@ejemplo.com"
    assert mensaje_enviado.get_content().strip() == "Hola, tengo una consulta."


def test_enviar_mail_sin_destinatarios_no_hace_nada(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.ejemplo.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "usuario@ejemplo.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secreta")
    monkeypatch.setenv("SMTP_FROM", "notificaciones@macacha.gob.ar")

    with patch("agent.mail.smtplib.SMTP") as smtp_cls:
        mail.enviar_mail([], asunto="Asunto", cuerpo_texto="Cuerpo")

    smtp_cls.assert_not_called()


def _configurar_smtp(monkeypatch, puerto):
    monkeypatch.setenv("SMTP_HOST", "smtp.ejemplo.com")
    monkeypatch.setenv("SMTP_PORT", str(puerto))
    monkeypatch.setenv("SMTP_USER", "usuario@ejemplo.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secreta")
    monkeypatch.setenv("SMTP_FROM", "notificaciones@macacha.gob.ar")


def _smtp_falso():
    instancia = MagicMock()
    instancia.__enter__.return_value = instancia
    return instancia


def test_enviar_mail_en_puerto_465_usa_ssl_implicito_sin_starttls(monkeypatch):
    _configurar_smtp(monkeypatch, 465)
    smtp_ssl = _smtp_falso()
    contexto = object()

    with patch("agent.mail.smtplib.SMTP_SSL", return_value=smtp_ssl) as ssl_cls, patch(
        "agent.mail.smtplib.SMTP"
    ) as smtp_cls, patch("ssl.create_default_context", return_value=contexto):
        mail.enviar_mail(["admin@ejemplo.com"], asunto="Asunto", cuerpo_texto="Cuerpo")

    ssl_cls.assert_called_once_with("smtp.ejemplo.com", 465, timeout=10, context=contexto)
    smtp_cls.assert_not_called()
    smtp_ssl.starttls.assert_not_called()
    smtp_ssl.login.assert_called_once_with("usuario@ejemplo.com", "secreta")
    assert smtp_ssl.send_message.call_count == 1


def test_enviar_mail_en_puerto_587_sigue_usando_starttls(monkeypatch):
    _configurar_smtp(monkeypatch, 587)
    smtp = _smtp_falso()
    contexto = object()

    with patch("agent.mail.smtplib.SMTP", return_value=smtp) as smtp_cls, patch(
        "agent.mail.smtplib.SMTP_SSL"
    ) as ssl_cls, patch("ssl.create_default_context", return_value=contexto):
        mail.enviar_mail(["admin@ejemplo.com"], asunto="Asunto", cuerpo_texto="Cuerpo")

    smtp_cls.assert_called_once_with("smtp.ejemplo.com", 587, timeout=10)
    ssl_cls.assert_not_called()
    smtp.starttls.assert_called_once_with(context=contexto)
    assert smtp.send_message.call_count == 1

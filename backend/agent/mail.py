import os
import smtplib
from email.message import EmailMessage


def enviar_mail(destinatarios: list[str], asunto: str, cuerpo_texto: str) -> None:
    if not destinatarios:
        return

    mensaje = EmailMessage()
    mensaje["Subject"] = asunto
    mensaje["From"] = os.environ["SMTP_FROM"]
    mensaje["To"] = ", ".join(destinatarios)
    mensaje.set_content(cuerpo_texto)

    host = os.environ["SMTP_HOST"]
    port = int(os.environ["SMTP_PORT"])
    with smtplib.SMTP(host, port) as smtp:
        smtp.starttls()
        smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        smtp.send_message(mensaje)

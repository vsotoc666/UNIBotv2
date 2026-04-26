import logging
import os
import json
import base64
import smtplib
from email.mime.base import MIMEBase
from email import encoders
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.utils import timezone

from apps.agrupaciones.models import ConfiguracionBot

logger = logging.getLogger(__name__)


def _refresh_google_access_token(refresh_token: str) -> str:
    client_id = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("GOOGLE_CLIENT_SECRET") or "").strip()
    if not client_id or not client_secret or not refresh_token:
        return ""

    payload = urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
    ).encode("utf-8")
    req = Request(
        "https://oauth2.googleapis.com/token",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(req, timeout=15) as response:
        token_data = json.loads(response.read().decode("utf-8"))
    return (token_data.get("access_token") or "").strip()


def _send_via_gmail_api(
    *,
    subject: str,
    message: str,
    to_email: str,
    from_email: str,
    refresh_token: str,
    attachment_name: str = "",
    attachment_bytes: bytes = b"",
) -> bool:
    access_token = _refresh_google_access_token(refresh_token)
    if not access_token:
        return False

    if attachment_name and attachment_bytes:
        mime_msg = MIMEMultipart()
        mime_msg.attach(MIMEText(message, "plain", "utf-8"))
        part = MIMEBase("application", "pdf")
        part.set_payload(attachment_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{attachment_name}"')
        mime_msg.attach(part)
    else:
        mime_msg = MIMEText(message, "plain", "utf-8")
    mime_msg["to"] = to_email
    mime_msg["from"] = from_email
    mime_msg["subject"] = subject
    raw_message = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("utf-8")

    body = json.dumps({"raw": raw_message}).encode("utf-8")
    send_req = Request(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        data=body,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(send_req, timeout=20) as response:
        status_code = getattr(response, "status", None) or response.getcode()
    return int(status_code) in (200, 202)


def _send_via_personal_smtp(
    *,
    subject: str,
    message: str,
    to_email: str,
    from_email: str,
    app_password: str,
    attachment_name: str = "",
    attachment_bytes: bytes = b"",
) -> bool:
    if not from_email or not app_password:
        return False

    if attachment_name and attachment_bytes:
        mime_msg = MIMEMultipart()
        mime_msg.attach(MIMEText(message, "plain", "utf-8"))
        part = MIMEBase("application", "pdf")
        part.set_payload(attachment_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{attachment_name}"')
        mime_msg.attach(part)
    else:
        mime_msg = MIMEText(message, "plain", "utf-8")
    mime_msg["To"] = to_email
    mime_msg["From"] = from_email
    mime_msg["Subject"] = subject

    # Para Gmail: se usa la contraseña de aplicación de 16 caracteres.
    normalized_password = "".join((app_password or "").split())
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(from_email, normalized_password)
        smtp.sendmail(from_email, [to_email], mime_msg.as_string())
    return True


def enviar_correo_evento(
    *,
    evento,
    to_email: str,
    subject: str,
    message: str,
    attachment_name: str = "",
    attachment_bytes: bytes = b"",
) -> bool:
    config = ConfiguracionBot.objects.filter(agrupacion=evento.agrupacion).first()
    google_email = (getattr(config, "google_email", "") or "").strip()
    google_refresh_token = (getattr(config, "google_refresh_token", "") or "").strip()
    correo_remitente = (getattr(config, "correo_remitente", "") or "").strip()
    clave_app_remitente = (getattr(config, "clave_app_remitente", "") or "").strip()

    sent = False
    if google_email and google_refresh_token:
        try:
            sent = _send_via_gmail_api(
                subject=subject,
                message=message,
                to_email=to_email,
                from_email=google_email,
                refresh_token=google_refresh_token,
                attachment_name=attachment_name,
                attachment_bytes=attachment_bytes,
            )
        except Exception as e:
            logger.exception(
                "Fallo envío OAuth para %s (agrupación %s): %s",
                to_email,
                evento.agrupacion_id,
                e,
            )

    # Fallback a remitente personal si OAuth no está disponible o falló.
    if not sent and correo_remitente and clave_app_remitente:
        try:
            sent = _send_via_personal_smtp(
                subject=subject,
                message=message,
                to_email=to_email,
                from_email=correo_remitente,
                app_password=clave_app_remitente,
                attachment_name=attachment_name,
                attachment_bytes=attachment_bytes,
            )
        except Exception as e:
            logger.exception(
                "Fallo envío SMTP personal para %s (agrupación %s): %s",
                to_email,
                evento.agrupacion_id,
                e,
            )

    if not sent:
        logger.warning(
            "No se pudo enviar confirmación a %s. Configuración faltante o inválida en agrupación %s.",
            to_email,
            evento.agrupacion_id,
        )
        return False

    return sent


def enviar_confirmacion_inscripcion(inscripcion) -> bool:
    """
    Envía correo de confirmación y marca estado en la inscripción.
    Retorna True si se envió, False si hubo error/no aplica.
    """
    if not inscripcion or not inscripcion.correo:
        return False
    if inscripcion.confirmacion_email_enviada:
        return True

    evento = inscripcion.formulario.evento
    if not evento.enviar_confirmacion_email:
        return False

    subject = f"Confirmación de inscripción - {evento.titulo}"
    message = (
        f"Hola {inscripcion.nombre},\n\n"
        f"Tu inscripción al evento '{evento.titulo}' fue registrada correctamente.\n"
        f"Fecha de inicio: {evento.fecha_inicio}\n"
        f"Fecha de fin: {evento.fecha_fin}\n\n"
        "Gracias por registrarte."
    )
    sent = enviar_correo_evento(
        evento=evento,
        to_email=inscripcion.correo,
        subject=subject,
        message=message,
    )
    if sent:
        inscripcion.confirmacion_email_enviada = True
        inscripcion.confirmacion_email_enviada_en = timezone.now()
        inscripcion.save(
            update_fields=["confirmacion_email_enviada", "confirmacion_email_enviada_en"]
        )
    return sent

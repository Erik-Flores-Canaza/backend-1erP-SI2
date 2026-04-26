"""
Servicio de envío de correos vía Gmail OAuth 2.0.

Flujo:
  1. Usa el refresh_token almacenado en .env para obtener un access_token fresco.
  2. Construye el mensaje MIME y lo codifica en base64.
  3. Lo envía a través de la Gmail API (users.messages.send).

Si las credenciales no están configuradas (GMAIL_CLIENT_ID vacío), el envío
se omite y se registra un aviso — así el servidor arranca sin credenciales
durante el desarrollo sin lanzar excepciones.

Dependencias (agregar a requirements.txt):
  google-auth
  google-auth-oauthlib
  google-api-python-client
"""

import base64
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)


def _build_gmail_service():
    """Construye el cliente autenticado de la Gmail API."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=settings.GMAIL_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GMAIL_CLIENT_ID,
        client_secret=settings.GMAIL_CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/gmail.send"],
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _compose_message(destinatario: str, asunto: str, cuerpo_html: str) -> dict:
    """Construye el payload base64 que espera la Gmail API."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = asunto
    msg["From"] = settings.GMAIL_SENDER_EMAIL
    msg["To"] = destinatario
    msg.attach(MIMEText(cuerpo_html, "html", "utf-8"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return {"raw": raw}


def enviar_credenciales_admin_taller(
    destinatario: str,
    nombre: str,
    nombre_taller: str,
    contrasena_temporal: str,
) -> bool:
    """
    Envía al nuevo admin_taller su correo de bienvenida con la contraseña temporal.

    Returns:
        True  — correo enviado con éxito.
        False — no configurado o error (ver logs).
    """
    if not settings.GMAIL_CLIENT_ID:
        logger.warning(
            "Gmail OAuth no configurado (GMAIL_CLIENT_ID vacío). "
            "Se omite el envío de credenciales a %s.",
            destinatario,
        )
        return False

    asunto = "Bienvenido a la Plataforma de Emergencias — Tus credenciales de acceso"
    cuerpo = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #222; max-width: 600px; margin: auto;">
      <h2 style="color: #e53935;">¡Tu taller ha sido aprobado!</h2>
      <p>Hola <strong>{nombre}</strong>,</p>
      <p>
        Tu solicitud de registro para el taller <strong>"{nombre_taller}"</strong>
        ha sido <span style="color: #43a047;">aprobada</span> por el equipo de la plataforma.
      </p>
      <p>Puedes iniciar sesión en el panel de administración con las siguientes credenciales:</p>
      <table style="border-collapse: collapse; width: 100%;">
        <tr>
          <td style="padding: 8px; border: 1px solid #ddd; background:#f5f5f5;"><strong>Correo</strong></td>
          <td style="padding: 8px; border: 1px solid #ddd;">{destinatario}</td>
        </tr>
        <tr>
          <td style="padding: 8px; border: 1px solid #ddd; background:#f5f5f5;"><strong>Contraseña temporal</strong></td>
          <td style="padding: 8px; border: 1px solid #ddd; font-family: monospace; font-size: 1.1em;">
            {contrasena_temporal}
          </td>
        </tr>
      </table>
      <p style="margin-top: 16px;">
        <strong>Por tu seguridad, cambia esta contraseña al iniciar sesión por primera vez.</strong>
      </p>
      <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;">
      <p style="font-size: 0.85em; color: #888;">
        Plataforma Inteligente de Atención de Emergencias Vehiculares
      </p>
    </body>
    </html>
    """

    try:
        service = _build_gmail_service()
        payload = _compose_message(destinatario, asunto, cuerpo)
        service.users().messages().send(userId="me", body=payload).execute()
        logger.info("Credenciales enviadas a %s", destinatario)
        return True
    except Exception as exc:
        logger.error("Error al enviar correo a %s: %s", destinatario, exc)
        return False


def enviar_rechazo_solicitud(
    destinatario: str,
    nombre: str,
    nombre_taller: str,
    motivo: str,
) -> bool:
    """
    Notifica al solicitante que su solicitud fue rechazada.

    Returns:
        True  — correo enviado con éxito.
        False — no configurado o error (ver logs).
    """
    if not settings.GMAIL_CLIENT_ID:
        logger.warning(
            "Gmail OAuth no configurado. Se omite notificación de rechazo a %s.",
            destinatario,
        )
        return False

    asunto = "Actualización sobre tu solicitud de registro de taller"
    cuerpo = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #222; max-width: 600px; margin: auto;">
      <h2 style="color: #e53935;">Solicitud no aprobada</h2>
      <p>Hola <strong>{nombre}</strong>,</p>
      <p>
        Lamentamos informarte que tu solicitud para registrar el taller
        <strong>"{nombre_taller}"</strong> no pudo ser aprobada en este momento.
      </p>
      <p><strong>Motivo:</strong></p>
      <blockquote style="border-left: 4px solid #e53935; padding-left: 12px; color: #555;">
        {motivo}
      </blockquote>
      <p>
        Si consideras que hay un error o deseas aportar información adicional,
        puedes volver a enviar una solicitud corregida.
      </p>
      <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;">
      <p style="font-size: 0.85em; color: #888;">
        Plataforma Inteligente de Atención de Emergencias Vehiculares
      </p>
    </body>
    </html>
    """

    try:
        service = _build_gmail_service()
        payload = _compose_message(destinatario, asunto, cuerpo)
        service.users().messages().send(userId="me", body=payload).execute()
        logger.info("Notificación de rechazo enviada a %s", destinatario)
        return True
    except Exception as exc:
        logger.error("Error al enviar notificación de rechazo a %s: %s", destinatario, exc)
        return False

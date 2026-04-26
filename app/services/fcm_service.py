"""
Firebase Cloud Messaging — envío de push notifications a Flutter.
Se inicializa una sola vez al arrancar la app (lifespan).
Si FIREBASE_CREDENTIALS_PATH no está configurado, las funciones son no-op.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_initialized = False


def init_firebase() -> None:
    """Llamar una vez en el lifespan de FastAPI."""
    global _initialized
    try:
        import firebase_admin
        from firebase_admin import credentials
        from app.core.config import settings

        cred_path = getattr(settings, "FIREBASE_CREDENTIALS_PATH", None)
        if not cred_path:
            logger.warning("FCM: FIREBASE_CREDENTIALS_PATH no configurado — push desactivado")
            return

        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)

        _initialized = True
        logger.info("FCM: Firebase inicializado correctamente")
    except Exception as e:
        logger.warning(f"FCM: No se pudo inicializar Firebase — {e}")


def send_push(fcm_token: str | None, titulo: str, cuerpo: str, data: dict | None = None) -> None:
    """
    Envía una notificación push a un dispositivo Flutter via FCM.
    Si no hay token o Firebase no está inicializado, es no-op silencioso.
    """
    if not _initialized or not fcm_token:
        return
    try:
        from firebase_admin import messaging

        message = messaging.Message(
            notification=messaging.Notification(title=titulo, body=cuerpo),
            data={k: str(v) for k, v in (data or {}).items()},
            token=fcm_token,
        )
        messaging.send(message)
    except Exception as e:
        logger.warning(f"FCM: Error enviando push — {e}")

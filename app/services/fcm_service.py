"""
Firebase Cloud Messaging — envío de push notifications a Flutter.
Se inicializa una sola vez al arrancar la app (lifespan).

Orden de prioridad para las credenciales:
  1. FIREBASE_CREDENTIALS_JSON  — variable de entorno con el JSON completo (Railway/producción).
  2. FIREBASE_CREDENTIALS_PATH  — ruta a un archivo .json en disco (desarrollo local).

Si ninguna está configurada, las funciones son no-op silenciosas.
"""
from __future__ import annotations

import json
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

        if firebase_admin._apps:
            _initialized = True
            return

        # 1. Variable de entorno con el JSON completo (Railway)
        if settings.FIREBASE_CREDENTIALS_JSON:
            cred_dict = json.loads(settings.FIREBASE_CREDENTIALS_JSON)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            _initialized = True
            logger.info("FCM: Firebase inicializado desde variable de entorno")
            return

        # 2. Archivo en disco (desarrollo local)
        if settings.FIREBASE_CREDENTIALS_PATH:
            cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
            firebase_admin.initialize_app(cred)
            _initialized = True
            logger.info("FCM: Firebase inicializado desde archivo %s", settings.FIREBASE_CREDENTIALS_PATH)
            return

        logger.warning("FCM: Sin credenciales configuradas — push desactivado")
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

"""
Servicio de notificaciones — CU-21
Inserta registros en NOTIFICACIONES + emite en tiempo real por dos canales:
  1. WebSocket (panel web Angular — admin_taller)
  2. FCM push (app Flutter — cliente y técnico)
"""
from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.notificacion import Notificacion
from app.models.usuario import Usuario

logger = logging.getLogger(__name__)

# Referencia al event loop principal (fijada en el lifespan de main.py).
# Permite que los endpoints síncronos (thread pool) emitan eventos WS.
_main_loop: asyncio.AbstractEventLoop | None = None


def _get_fcm_token(db: Session, usuario_id: UUID) -> str | None:
    u = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    return u.fcm_token if u else None


def _crear(
    db: Session,
    usuario_id: UUID,
    titulo: str,
    cuerpo: str,
    incidente_id: UUID | None = None,
    tipo: str = "in_app",
    evento: str | None = None,
) -> Notificacion:
    """Crea la notificación en BD y dispara WS + FCM."""
    notif = Notificacion(
        usuario_id=usuario_id,
        incidente_id=incidente_id,
        tipo=tipo,
        titulo=titulo,
        cuerpo=cuerpo,
    )
    db.add(notif)

    # ── WebSocket (panel web) ──────────────────────────────────────────────
    _emit_ws(str(usuario_id), titulo, cuerpo, str(incidente_id) if incidente_id else None, evento)

    # ── FCM push (app Flutter) ─────────────────────────────────────────────
    fcm_token = _get_fcm_token(db, usuario_id)
    if fcm_token:
        from app.services.fcm_service import send_push
        send_push(
            fcm_token,
            titulo,
            cuerpo,
            data={"incidente_id": str(incidente_id)} if incidente_id else {},
        )

    return notif


def _emit_ws(
    usuario_id: str,
    titulo: str,
    cuerpo: str,
    incidente_id: str | None,
    evento: str | None = None,
) -> None:
    """Emite el evento por WebSocket sin bloquear (fire-and-forget).

    Funciona tanto desde coroutines (async endpoints) como desde hilos del
    thread pool (sync endpoints de FastAPI), usando el loop guardado en startup.
    """
    try:
        from app.core.ws_manager import user_manager
        payload: dict = {"titulo": titulo, "cuerpo": cuerpo, "incidente_id": incidente_id}
        if evento:
            payload["evento"] = evento

        coro = user_manager.send(usuario_id, payload)

        # Intentar obtener el loop del hilo actual (async endpoint)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
            return
        except RuntimeError:
            pass  # Estamos en un hilo del thread pool

        # Fallback: usar el loop principal guardado en el lifespan
        if _main_loop is not None and _main_loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, _main_loop)
        else:
            logger.warning("WS notif: no hay event loop disponible para emitir.")
    except Exception as e:
        logger.warning(f"WS notif error: {e}")


# ---------------------------------------------------------------------------
# Eventos del flujo de emergencia
# ---------------------------------------------------------------------------

def notif_incidente_creado(db: Session, cliente_id: UUID, incidente_id: UUID) -> None:
    """Evento: cliente reportó una emergencia (CU-05)."""
    _crear(
        db,
        usuario_id=cliente_id,
        incidente_id=incidente_id,
        titulo="Emergencia reportada",
        cuerpo="Tu solicitud de asistencia fue recibida. Estamos buscando el taller más cercano.",
    )


def notif_taller_asignado(
    db: Session,
    cliente_id: UUID,
    admin_taller_id: UUID,
    incidente_id: UUID,
    nombre_taller: str,
) -> None:
    """Evento: se asignó un taller al incidente (CU-20)."""
    _crear(
        db,
        usuario_id=cliente_id,
        incidente_id=incidente_id,
        titulo="Taller asignado",
        cuerpo=f"El taller «{nombre_taller}» fue seleccionado para atender tu emergencia.",
    )
    _crear(
        db,
        usuario_id=admin_taller_id,
        incidente_id=incidente_id,
        titulo="Nueva solicitud de emergencia",
        cuerpo="Tienes una nueva solicitud de asistencia pendiente de respuesta.",
        evento="nueva_solicitud",
    )


def notif_taller_acepto(
    db: Session,
    cliente_id: UUID,
    incidente_id: UUID,
    nombre_taller: str,
    eta_minutos: int | None,
) -> None:
    """Evento: el taller aceptó la solicitud (CU-12)."""
    eta_text = f" Tiempo estimado: {eta_minutos} min." if eta_minutos else ""
    _crear(
        db,
        usuario_id=cliente_id,
        incidente_id=incidente_id,
        titulo="Taller confirmado",
        cuerpo=f"«{nombre_taller}» aceptó tu solicitud.{eta_text}",
    )


def notif_taller_rechazo(
    db: Session,
    cliente_id: UUID,
    incidente_id: UUID,
    nombre_taller: str,
) -> None:
    """Evento: el taller rechazó — se buscará el siguiente (CU-12 → CU-20)."""
    _crear(
        db,
        usuario_id=cliente_id,
        incidente_id=incidente_id,
        titulo="Reasignando taller",
        cuerpo=f"«{nombre_taller}» no puede atenderte en este momento. Buscando otro taller.",
    )


def notif_tecnico_asignado(
    db: Session,
    cliente_id: UUID,
    tecnico_usuario_id: UUID,
    incidente_id: UUID,
    nombre_tecnico: str,
) -> None:
    """Evento: el taller asignó un técnico a la orden (CU-13)."""
    _crear(
        db,
        usuario_id=cliente_id,
        incidente_id=incidente_id,
        titulo="Técnico en camino",
        cuerpo=f"{nombre_tecnico} fue asignado para atenderte.",
    )
    _crear(
        db,
        usuario_id=tecnico_usuario_id,
        incidente_id=incidente_id,
        titulo="Nueva orden asignada",
        cuerpo="Se te asignó una emergencia. Revisa los detalles en tu panel.",
    )


def notif_tecnico_en_sitio(
    db: Session,
    cliente_id: UUID,
    incidente_id: UUID,
    nombre_tecnico: str,
) -> None:
    """Evento: el técnico confirmó que llegó a la ubicación del cliente."""
    _crear(
        db,
        usuario_id=cliente_id,
        incidente_id=incidente_id,
        titulo="¡Tu técnico llegó!",
        cuerpo=f"{nombre_tecnico} ya está en tu ubicación y comenzará a atenderte.",
    )


def notif_servicio_completado(
    db: Session,
    cliente_id: UUID,
    incidente_id: UUID,
) -> None:
    """Evento: el técnico marcó el servicio como completado (CU-17)."""
    _crear(
        db,
        usuario_id=cliente_id,
        incidente_id=incidente_id,
        titulo="Servicio completado",
        cuerpo="Tu emergencia fue atendida exitosamente. El técnico registrará el monto a pagar en breve.",
    )


def notif_pago_efectivo_cliente(
    db: Session,
    cliente_id: UUID,
    incidente_id: UUID,
    monto: float,
) -> None:
    """Evento: el técnico registró cobro en efectivo — notificar al cliente (CU-07)."""
    _crear(
        db,
        usuario_id=cliente_id,
        incidente_id=incidente_id,
        titulo="Pago registrado en efectivo",
        cuerpo=f"El técnico registró el cobro de Bs. {monto:.2f} en efectivo. ¡Gracias por usar la plataforma!",
    )


def notif_pago_recibido_tecnico(
    db: Session,
    tecnico_usuario_id: UUID,
    incidente_id: UUID,
    cliente_nombre: str,
    monto: float,
) -> None:
    """Evento: el cliente confirmó el pago — notificar al técnico (CU-07)."""
    _crear(
        db,
        usuario_id=tecnico_usuario_id,
        incidente_id=incidente_id,
        titulo="¡Pago recibido!",
        cuerpo=f"{cliente_nombre} pagó Bs. {monto:.2f} por tu servicio.",
    )


def notif_nuevo_mensaje_chat(admin_taller_id: UUID, incidente_id: UUID) -> None:
    """Evento en tiempo real: nuevo mensaje en el chat — solo WS, sin persistir en BD.
    Permite que el panel Angular muestre un badge sin abrir el chat.
    """
    _emit_ws(
        str(admin_taller_id),
        titulo="",
        cuerpo="",
        incidente_id=str(incidente_id),
        evento="nuevo_mensaje_chat",
    )


def notif_pago_confirmado_admin(
    db: Session,
    admin_taller_id: UUID,
    incidente_id: UUID,
    monto: float,
    metodo: str = "stripe",
) -> None:
    """Evento: pago confirmado — notificar al admin_taller por WS (CU-07).
    Incluye evento='pago_confirmado' para que el panel Angular refresque el badge.
    """
    metodo_label = "efectivo" if metodo == "efectivo" else "Stripe"
    _crear(
        db,
        usuario_id=admin_taller_id,
        incidente_id=incidente_id,
        titulo="Pago recibido",
        cuerpo=f"El cliente pagó Bs. {monto:.2f} vía {metodo_label}.",
        evento="pago_confirmado",
    )

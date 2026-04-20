"""
Servicio de notificaciones — CU-21
Inserta registros en NOTIFICACIONES ante cada evento clave del flujo de emergencia.

Deuda técnica: En el futuro se debe integrar Firebase Cloud Messaging (FCM)
para enviar notificaciones push reales usando las credenciales en .env.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.notificacion import Notificacion


def _crear(
    db: Session,
    usuario_id: UUID,
    titulo: str,
    cuerpo: str,
    incidente_id: UUID | None = None,
    tipo: str = "in_app",
) -> Notificacion:
    """Crea una notificación en BD. El caller es responsable del commit."""
    notif = Notificacion(
        usuario_id=usuario_id,
        incidente_id=incidente_id,
        tipo=tipo,
        titulo=titulo,
        cuerpo=cuerpo,
    )
    db.add(notif)
    # TODO FCM: Enviar push real aquí cuando se integre Firebase
    # send_push(usuario_id, titulo, cuerpo)
    return notif


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
    """Evento: el taller rechazó la solicitud — se buscará el siguiente (CU-12 → CU-20)."""
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
    """Evento: el taller asignó un técnico a la orden (CU-13).
    Notifica al cliente Y al técnico asignado.
    """
    # Al cliente: le avisa que un técnico va en camino
    _crear(
        db,
        usuario_id=cliente_id,
        incidente_id=incidente_id,
        titulo="Técnico en camino",
        cuerpo=f"{nombre_tecnico} fue asignado para atenderte.",
    )
    # Al técnico: le avisa que tiene una nueva orden activa
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
        cuerpo="Tu emergencia fue atendida exitosamente. ¡Gracias por usar la plataforma!",
    )

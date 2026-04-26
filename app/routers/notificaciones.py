from app.core.timezone import now_bo
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.notificacion import Notificacion
from app.models.usuario import Usuario
from app.schemas.notificacion import NotificacionResponse

router = APIRouter(prefix="/notificaciones", tags=["Notificaciones"])


@router.get("", response_model=list[NotificacionResponse])
def listar_notificaciones(
    solo_no_leidas: bool = False,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    CU-21 / CU-09 — Lista todas las notificaciones del usuario autenticado.
    Parámetro opcional `solo_no_leidas=true` para filtrar solo las no leídas.
    """
    query = db.query(Notificacion).filter(Notificacion.usuario_id == current_user.id)
    if solo_no_leidas:
        query = query.filter(Notificacion.leida == False)  # noqa: E712
    return query.order_by(Notificacion.enviada_en.desc()).all()


@router.patch("/{notificacion_id}/leer", response_model=NotificacionResponse)
def marcar_leida(
    notificacion_id: UUID,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """CU-09 — Marca una notificación como leída."""
    notif = db.query(Notificacion).filter(
        Notificacion.id == notificacion_id,
        Notificacion.usuario_id == current_user.id,
    ).first()
    if not notif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notificación no encontrada")

    if not notif.leida:
        notif.leida = True
        notif.leida_en = now_bo()
        db.commit()
        db.refresh(notif)

    return notif


@router.patch("/leer-todas", response_model=dict)
def marcar_todas_leidas(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Marca todas las notificaciones no leídas del usuario como leídas."""
    ahora = now_bo()
    actualizadas = (
        db.query(Notificacion)
        .filter(Notificacion.usuario_id == current_user.id, Notificacion.leida == False)  # noqa: E712
        .all()
    )
    for n in actualizadas:
        n.leida = True
        n.leida_en = ahora
    db.commit()
    return {"actualizadas": len(actualizadas)}

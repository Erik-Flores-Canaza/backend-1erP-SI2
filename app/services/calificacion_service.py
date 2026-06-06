"""Servicio de calificaciones y reseñas post-servicio — CU-43 (aporte propio).

Reglas de negocio:
- Solo el cliente dueño de un incidente en estado `finalizado` puede calificar.
- Una sola calificación por incidente.
- La calificación se ancla al taller que efectivamente atendió (asignación aceptada).
- El promedio (solo reseñas NO ocultas) alimenta CU-35 y CU-39.
- El admin_tenant puede ocultar/mostrar reseñas de su tenant (moderación).
"""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core import estado_incidente as estado_machine
from app.core.tenant_context import aplicar_filtro_tenant, verificar_acceso_tenant
from app.models.asignacion import Asignacion
from app.models.calificacion import Calificacion
from app.models.incidente import Incidente
from app.models.taller import Taller
from app.models.usuario import Usuario


# ---------------------------------------------------------------------------
# Promedios (usado por CU-35 y para mostrar reseñas)
# ---------------------------------------------------------------------------

def promedio_taller(db: Session, taller_id: UUID) -> tuple[float | None, int]:
    """Devuelve (promedio, total) de las reseñas visibles de un taller."""
    row = (
        db.query(func.avg(Calificacion.puntuacion), func.count(Calificacion.id))
        .filter(
            Calificacion.taller_id == taller_id,
            Calificacion.oculta == False,  # noqa: E712
        )
        .first()
    )
    if not row or row[1] == 0:
        return None, 0
    return round(float(row[0]), 2), int(row[1])


def promedios_por_taller(db: Session, taller_ids: list[UUID]) -> dict[UUID, tuple[float, int]]:
    """Promedio + total de reseñas visibles para varios talleres en una query."""
    if not taller_ids:
        return {}
    filas = (
        db.query(
            Calificacion.taller_id,
            func.avg(Calificacion.puntuacion),
            func.count(Calificacion.id),
        )
        .filter(
            Calificacion.taller_id.in_(taller_ids),
            Calificacion.oculta == False,  # noqa: E712
        )
        .group_by(Calificacion.taller_id)
        .all()
    )
    return {tid: (round(float(avg), 2), int(cnt)) for tid, avg, cnt in filas}


# ---------------------------------------------------------------------------
# CU-43: cliente califica el servicio
# ---------------------------------------------------------------------------

def crear_calificacion(
    db: Session,
    incidente_id: UUID,
    puntuacion: int,
    comentario: str | None,
    cliente: Usuario,
) -> Calificacion:
    incidente = db.query(Incidente).filter(Incidente.id == incidente_id).first()
    if not incidente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incidente no encontrado")

    if incidente.cliente_id != cliente.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el dueño del incidente puede calificar el servicio",
        )

    if incidente.estado != estado_machine.FINALIZADO:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Solo puedes calificar un servicio finalizado",
        )

    # No permitir doble calificación
    if db.query(Calificacion).filter(Calificacion.incidente_id == incidente_id).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya calificaste este servicio",
        )

    # Taller que efectivamente atendió (asignación aceptada)
    asignacion = (
        db.query(Asignacion)
        .filter(
            Asignacion.incidente_id == incidente_id,
            Asignacion.accion_taller == "aceptado",
        )
        .first()
    )
    if not asignacion:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se encontró el taller que atendió este servicio",
        )

    calificacion = Calificacion(
        tenant_id=asignacion.tenant_id,
        incidente_id=incidente_id,
        taller_id=asignacion.taller_id,
        cliente_id=cliente.id,
        puntuacion=puntuacion,
        comentario=(comentario.strip() if comentario and comentario.strip() else None),
    )
    db.add(calificacion)
    db.commit()
    db.refresh(calificacion)
    return calificacion


def obtener_mi_calificacion(
    db: Session, incidente_id: UUID, cliente: Usuario
) -> Calificacion | None:
    """Devuelve la calificación que el cliente dejó para su incidente (o None)."""
    incidente = db.query(Incidente).filter(Incidente.id == incidente_id).first()
    if not incidente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incidente no encontrado")
    if incidente.cliente_id != cliente.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin acceso")
    return (
        db.query(Calificacion)
        .filter(Calificacion.incidente_id == incidente_id)
        .first()
    )


def listar_resenas_taller(db: Session, taller_id: UUID) -> list[Calificacion]:
    """Reseñas visibles de un taller, más recientes primero."""
    return (
        db.query(Calificacion)
        .filter(
            Calificacion.taller_id == taller_id,
            Calificacion.oculta == False,  # noqa: E712
        )
        .order_by(Calificacion.creado_en.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# Moderación (admin_tenant)
# ---------------------------------------------------------------------------

def listar_para_moderacion(db: Session, current_user: Usuario) -> list[dict]:
    """Todas las reseñas del tenant del admin (incluidas las ocultas)."""
    q = db.query(Calificacion)
    q = aplicar_filtro_tenant(q, Calificacion, current_user)
    calificaciones = q.order_by(Calificacion.creado_en.desc()).all()

    resultado: list[dict] = []
    for c in calificaciones:
        taller = db.query(Taller).filter(Taller.id == c.taller_id).first()
        cliente = db.query(Usuario).filter(Usuario.id == c.cliente_id).first()
        resultado.append({
            "id": c.id,
            "incidente_id": c.incidente_id,
            "taller_id": c.taller_id,
            "taller_nombre": taller.nombre if taller else "—",
            "cliente_nombre": cliente.nombre_completo if cliente else "—",
            "puntuacion": c.puntuacion,
            "comentario": c.comentario,
            "oculta": c.oculta,
            "creado_en": c.creado_en,
        })
    return resultado


def moderar(
    db: Session, calificacion_id: UUID, oculta: bool, current_user: Usuario
) -> Calificacion:
    """El admin_tenant oculta o muestra una reseña de su tenant."""
    calificacion = (
        db.query(Calificacion).filter(Calificacion.id == calificacion_id).first()
    )
    if not calificacion:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calificación no encontrada")

    # Aislamiento: la reseña debe pertenecer al tenant del admin
    verificar_acceso_tenant(calificacion.tenant_id, current_user)

    calificacion.oculta = oculta
    db.commit()
    db.refresh(calificacion)
    return calificacion

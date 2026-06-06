"""Rutas de calificaciones y reseñas post-servicio — CU-43 (aporte propio).

Endpoints:
  POST  /incidentes/{incidente_id}/calificacion          (cliente)  — calificar
  GET   /incidentes/{incidente_id}/calificacion          (cliente)  — ver mi calificación
  GET   /talleres/{taller_id}/calificaciones             (cliente)  — reseñas visibles
  GET   /admin/calificaciones                            (admin_tenant) — moderación
  PATCH /admin/calificaciones/{id}/ocultar               (admin_tenant) — ocultar
  PATCH /admin/calificaciones/{id}/mostrar               (admin_tenant) — mostrar
"""
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.dependencies import get_db, require_admin_tenant, require_cliente
from app.models.usuario import Usuario
from app.schemas.calificacion import (
    CalificacionCreate,
    CalificacionModeracion,
    CalificacionPublica,
    CalificacionResponse,
)
from app.services import calificacion_service

router = APIRouter(tags=["Calificaciones"])


# ════════════════════════════════════════════════════════════════════════════
# Cliente
# ════════════════════════════════════════════════════════════════════════════

@router.post(
    "/incidentes/{incidente_id}/calificacion",
    response_model=CalificacionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="CU-43 — Calificar el servicio (1-5 + reseña)",
)
def crear_calificacion(
    incidente_id: UUID,
    body: CalificacionCreate,
    db: Session = Depends(get_db),
    cliente: Usuario = Depends(require_cliente),
):
    """El cliente puntúa al taller que atendió su incidente `finalizado`."""
    return calificacion_service.crear_calificacion(
        db, incidente_id, body.puntuacion, body.comentario, cliente
    )


@router.get(
    "/incidentes/{incidente_id}/calificacion",
    response_model=CalificacionResponse | None,
    summary="CU-43 — Ver la calificación que dejé para mi incidente",
)
def obtener_mi_calificacion(
    incidente_id: UUID,
    db: Session = Depends(get_db),
    cliente: Usuario = Depends(require_cliente),
):
    return calificacion_service.obtener_mi_calificacion(db, incidente_id, cliente)


@router.get(
    "/talleres/{taller_id}/calificaciones",
    response_model=list[CalificacionPublica],
    summary="CU-43 — Reseñas visibles de un taller",
)
def listar_resenas_taller(
    taller_id: UUID,
    db: Session = Depends(get_db),
    cliente: Usuario = Depends(require_cliente),
):
    return calificacion_service.listar_resenas_taller(db, taller_id)


# ════════════════════════════════════════════════════════════════════════════
# Moderación (admin_tenant)
# ════════════════════════════════════════════════════════════════════════════

@router.get(
    "/admin/calificaciones",
    response_model=list[CalificacionModeracion],
    summary="CU-43 — Listar reseñas del tenant para moderar",
)
def listar_para_moderacion(
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_admin_tenant),
):
    return calificacion_service.listar_para_moderacion(db, admin)


@router.patch(
    "/admin/calificaciones/{calificacion_id}/ocultar",
    response_model=CalificacionResponse,
    summary="CU-43 — Ocultar una reseña abusiva",
)
def ocultar_calificacion(
    calificacion_id: UUID,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_admin_tenant),
):
    return calificacion_service.moderar(db, calificacion_id, True, admin)


@router.patch(
    "/admin/calificaciones/{calificacion_id}/mostrar",
    response_model=CalificacionResponse,
    summary="CU-43 — Volver a mostrar una reseña oculta",
)
def mostrar_calificacion(
    calificacion_id: UUID,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_admin_tenant),
):
    return calificacion_service.moderar(db, calificacion_id, False, admin)

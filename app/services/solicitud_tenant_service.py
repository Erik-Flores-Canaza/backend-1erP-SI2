"""Servicio de solicitudes públicas para crear nuevos tenants (CU-29)."""
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.solicitud_tenant import SolicitudTenant
from app.schemas.solicitud_tenant import SolicitudTenantCreate


def crear_solicitud(db: Session, body: SolicitudTenantCreate) -> SolicitudTenant:
    existe = (
        db.query(SolicitudTenant)
        .filter(
            SolicitudTenant.solicitante_correo == body.solicitante_correo,
            SolicitudTenant.estado == "pendiente",
        )
        .first()
    )
    if existe:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya tienes una solicitud pendiente con este correo",
        )
    solicitud = SolicitudTenant(**body.model_dump())
    db.add(solicitud)
    db.commit()
    db.refresh(solicitud)
    return solicitud


def listar_solicitudes(
    db: Session, estado: str | None = None
) -> list[SolicitudTenant]:
    q = db.query(SolicitudTenant)
    if estado:
        q = q.filter(SolicitudTenant.estado == estado)
    return q.order_by(SolicitudTenant.creado_en.desc()).all()


def obtener_solicitud(db: Session, solicitud_id: UUID) -> SolicitudTenant:
    s = (
        db.query(SolicitudTenant)
        .filter(SolicitudTenant.id == solicitud_id)
        .first()
    )
    if not s:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Solicitud no encontrada"
        )
    return s

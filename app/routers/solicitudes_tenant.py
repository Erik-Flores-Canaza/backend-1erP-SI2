"""Endpoint público para solicitar alta como tenant nuevo (CU-29).

No requiere JWT. Cualquiera puede enviar una solicitud desde la landing.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.schemas.solicitud_tenant import (
    SolicitudTenantCreate,
    SolicitudTenantResponse,
)
from app.services import solicitud_tenant_service as svc

router = APIRouter(tags=["Plataforma — Solicitudes (público)"])


@router.post(
    "/solicitudes-tenant",
    response_model=SolicitudTenantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="CU-29 — Solicitar alta como tenant nuevo (público)",
)
def crear_solicitud(body: SolicitudTenantCreate, db: Session = Depends(get_db)):
    return svc.crear_solicitud(db, body)

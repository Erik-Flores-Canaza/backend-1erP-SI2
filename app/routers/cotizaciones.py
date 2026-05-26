"""Rutas de cotizaciones — CU-34 (taller envía) y CU-35 (cliente elige).

Endpoints:
  POST   /incidentes/{incidente_id}/cotizaciones?taller_id=...  (admin_taller)
  GET    /incidentes/{incidente_id}/cotizaciones                (cliente owner)
  GET    /talleres/{taller_id}/cotizaciones-pendientes          (admin_taller)
  POST   /cotizaciones/{cotizacion_id}/aceptar                  (cliente)
  DELETE /cotizaciones/{cotizacion_id}                          (admin_taller)
"""
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.dependencies import get_db, require_admin_taller, require_cliente
from app.models.usuario import Usuario
from app.schemas.asignacion import AsignacionResponse
from app.schemas.cotizacion import (
    CotizacionConTallerResponse,
    CotizacionCreate,
    CotizacionResponse,
    IncidentePendienteParaCotizar,
)
from app.services import cotizacion_service

router = APIRouter(tags=["Cotizaciones"])


# ════════════════════════════════════════════════════════════════════════════
# CU-34 — Taller envía cotización
# ════════════════════════════════════════════════════════════════════════════

@router.post(
    "/incidentes/{incidente_id}/cotizaciones",
    response_model=CotizacionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="CU-34 — Enviar cotización a un incidente",
)
def crear_cotizacion(
    incidente_id: UUID,
    taller_id: UUID,
    body: CotizacionCreate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_admin_taller),
):
    """El admin_taller envía una cotización para un incidente en estado `buscando_taller`.

    Reglas:
    - Solo un cotización por taller-incidente (UNIQUE).
    - El incidente debe estar en estado `buscando_taller`.
    - La cotización expira en 15 minutos.
    """
    return cotizacion_service.crear_cotizacion(
        db, incidente_id, taller_id, body, admin
    )


@router.delete(
    "/cotizaciones/{cotizacion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="CU-34 — Retirar cotización (solo antes de ser aceptada)",
)
def retirar_cotizacion(
    cotizacion_id: UUID,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_admin_taller),
):
    cotizacion_service.retirar_cotizacion(db, cotizacion_id, admin)


@router.get(
    "/talleres/{taller_id}/cotizaciones-pendientes",
    response_model=list[IncidentePendienteParaCotizar],
    summary="CU-34 — Listar incidentes en `buscando_taller` que el taller puede cotizar",
)
def listar_pendientes(
    taller_id: UUID,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_admin_taller),
):
    return cotizacion_service.listar_incidentes_para_cotizar(db, taller_id, admin)


# ════════════════════════════════════════════════════════════════════════════
# CU-35 — Cliente ve cotizaciones y elige una
# ════════════════════════════════════════════════════════════════════════════

@router.get(
    "/incidentes/{incidente_id}/cotizaciones",
    response_model=list[CotizacionConTallerResponse],
    summary="CU-35 — Ver cotizaciones recibidas para mi incidente",
)
def listar_cotizaciones_cliente(
    incidente_id: UUID,
    db: Session = Depends(get_db),
    cliente: Usuario = Depends(require_cliente),
):
    return cotizacion_service.listar_cotizaciones_de_incidente(db, incidente_id, cliente)


@router.post(
    "/cotizaciones/{cotizacion_id}/aceptar",
    response_model=AsignacionResponse,
    summary="CU-35 — Aceptar una cotización (crea Asignación, transiciona incidente)",
)
def aceptar_cotizacion(
    cotizacion_id: UUID,
    db: Session = Depends(get_db),
    cliente: Usuario = Depends(require_cliente),
):
    """Cliente acepta UNA cotización.
    - La elegida pasa a `aceptada`.
    - Las otras del mismo incidente pasan a `expirada`.
    - Se crea la Asignacion con accion_taller=aceptado.
    - El incidente pasa al estado `taller_asignado`.
    - El taller queda no disponible para otras emergencias.
    """
    return cotizacion_service.aceptar_cotizacion(db, cotizacion_id, cliente)

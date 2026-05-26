"""Rutas del panel superadmin_plataforma (CU-28 y revisión de CU-29).

Todas las rutas requieren rol `superadmin_plataforma`.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.timezone import now_bo
from app.dependencies import get_db, require_superadmin_plataforma
from app.models.usuario import Usuario
from app.schemas.solicitud_tenant import (
    SolicitudTenantRechazar,
    SolicitudTenantResponse,
)
from app.schemas.tenant import (
    TenantCreate,
    TenantCreateConAdmin,
    TenantCreateResponse,
    TenantResponse,
    TenantUpdate,
)
from app.services import solicitud_tenant_service as solic
from app.services import tenant_service as tsvc

router = APIRouter(
    prefix="/plataforma",
    tags=["Superadmin Plataforma — Tenants"],
)


# ════════════════════════════════════════════════════════════════════════════
# CU-28 — Gestionar tenants
# ════════════════════════════════════════════════════════════════════════════

@router.get("/tenants", response_model=list[TenantResponse])
def listar(
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_superadmin_plataforma),
):
    return tsvc.listar_tenants(db)


@router.get("/tenants/{tenant_id}", response_model=TenantResponse)
def obtener(
    tenant_id: UUID,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_superadmin_plataforma),
):
    return tsvc.obtener_tenant(db, tenant_id)


@router.post(
    "/tenants",
    response_model=TenantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear tenant (sin admin asociado todavía)",
)
def crear(
    body: TenantCreate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_superadmin_plataforma),
):
    return tsvc.crear_tenant(db, body)


@router.post(
    "/tenants/con-admin",
    response_model=TenantCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear tenant + primer admin_tenant (1 paso)",
)
def crear_con_admin(
    body: TenantCreateConAdmin,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_superadmin_plataforma),
):
    tenant, _admin = tsvc.crear_tenant_con_admin(db, body)
    return TenantCreateResponse(
        tenant=TenantResponse.model_validate(tenant),
        admin_correo=body.admin_correo,
    )


@router.patch("/tenants/{tenant_id}", response_model=TenantResponse)
def actualizar(
    tenant_id: UUID,
    body: TenantUpdate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_superadmin_plataforma),
):
    return tsvc.actualizar_tenant(db, tenant_id, body)


@router.patch("/tenants/{tenant_id}/activar", response_model=TenantResponse)
def activar(
    tenant_id: UUID,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_superadmin_plataforma),
):
    return tsvc.activar_tenant(db, tenant_id)


@router.patch("/tenants/{tenant_id}/desactivar", response_model=TenantResponse)
def desactivar(
    tenant_id: UUID,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_superadmin_plataforma),
):
    return tsvc.desactivar_tenant(db, tenant_id)


# ════════════════════════════════════════════════════════════════════════════
# CU-29 — Revisar solicitudes de tenant (superadmin_plataforma)
# ════════════════════════════════════════════════════════════════════════════

@router.get(
    "/solicitudes-tenant",
    response_model=list[SolicitudTenantResponse],
)
def listar_solicitudes(
    estado: str | None = None,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_superadmin_plataforma),
):
    return solic.listar_solicitudes(db, estado=estado)


@router.patch(
    "/solicitudes-tenant/{solicitud_id}/aprobar",
    response_model=TenantCreateResponse,
    summary="Aprueba la solicitud → crea tenant + admin_tenant con contraseña temporal",
)
def aprobar_solicitud(
    solicitud_id: UUID,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_superadmin_plataforma),
):
    s = solic.obtener_solicitud(db, solicitud_id)
    if s.estado != "pendiente":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La solicitud ya fue revisada",
        )

    base_slug = tsvc.derivar_slug(s.nombre_red)
    slug = tsvc.slug_unico(db, base_slug)
    contrasena_temp = tsvc.generar_password_temporal()

    body = TenantCreateConAdmin(
        nombre=s.nombre_red,
        slug=slug,
        correo_contacto=s.solicitante_correo,
        telefono_contacto=s.solicitante_telefono,
        plan="basico",
        admin_nombre_completo=s.solicitante_nombre,
        admin_correo=s.solicitante_correo,
        admin_contrasena=contrasena_temp,
        admin_telefono=s.solicitante_telefono,
    )
    tenant, _admin = tsvc.crear_tenant_con_admin(db, body)

    s.estado = "aprobado"
    s.revisado_por = current_user.id
    s.revisado_en = now_bo()
    db.commit()

    return TenantCreateResponse(
        tenant=TenantResponse.model_validate(tenant),
        admin_correo=body.admin_correo,
        contrasena_temporal=contrasena_temp,
    )


@router.patch(
    "/solicitudes-tenant/{solicitud_id}/rechazar",
    response_model=SolicitudTenantResponse,
)
def rechazar_solicitud(
    solicitud_id: UUID,
    body: SolicitudTenantRechazar,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_superadmin_plataforma),
):
    s = solic.obtener_solicitud(db, solicitud_id)
    if s.estado != "pendiente":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La solicitud ya fue revisada",
        )
    s.estado = "rechazado"
    s.motivo_rechazo = body.motivo_rechazo
    s.revisado_por = current_user.id
    s.revisado_en = now_bo()
    db.commit()
    db.refresh(s)
    return s

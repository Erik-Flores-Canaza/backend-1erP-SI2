"""Servicio de gestión de tenants (CU-28)."""
import secrets
import string
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.rol import Rol
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.schemas.tenant import TenantCreate, TenantCreateConAdmin, TenantUpdate


def listar_tenants(db: Session) -> list[Tenant]:
    return db.query(Tenant).order_by(Tenant.creado_en.desc()).all()


def obtener_tenant(db: Session, tenant_id: UUID) -> Tenant:
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant no encontrado"
        )
    return tenant


def crear_tenant(db: Session, body: TenantCreate) -> Tenant:
    if db.query(Tenant).filter(Tenant.slug == body.slug).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un tenant con el slug '{body.slug}'",
        )
    tenant = Tenant(**body.model_dump())
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def crear_tenant_con_admin(
    db: Session, body: TenantCreateConAdmin
) -> tuple[Tenant, Usuario]:
    """Crea un tenant nuevo + su primer admin_tenant en la misma transacción."""
    if db.query(Tenant).filter(Tenant.slug == body.slug).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un tenant con el slug '{body.slug}'",
        )
    if db.query(Usuario).filter(Usuario.correo == body.admin_correo).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El correo '{body.admin_correo}' ya está registrado",
        )
    rol = db.query(Rol).filter(Rol.nombre == "admin_tenant").first()
    if not rol:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Rol 'admin_tenant' no encontrado. Reinicia la app para ejecutar el seed.",
        )

    tenant = Tenant(
        nombre=body.nombre,
        slug=body.slug,
        correo_contacto=body.correo_contacto,
        telefono_contacto=body.telefono_contacto,
        plan=body.plan,
    )
    db.add(tenant)
    db.flush()  # asigna ID sin commit todavía

    admin = Usuario(
        rol_id=rol.id,
        tenant_id=tenant.id,
        nombre_completo=body.admin_nombre_completo,
        correo=body.admin_correo,
        hash_contrasena=hash_password(body.admin_contrasena),
        telefono=body.admin_telefono,
    )
    db.add(admin)
    db.commit()
    db.refresh(tenant)
    db.refresh(admin)
    return tenant, admin


def actualizar_tenant(db: Session, tenant_id: UUID, body: TenantUpdate) -> Tenant:
    tenant = obtener_tenant(db, tenant_id)
    cambios = body.model_dump(exclude_unset=True)
    for clave, valor in cambios.items():
        setattr(tenant, clave, valor)
    db.commit()
    db.refresh(tenant)
    return tenant


def activar_tenant(db: Session, tenant_id: UUID) -> Tenant:
    tenant = obtener_tenant(db, tenant_id)
    tenant.activo = True
    db.commit()
    db.refresh(tenant)
    return tenant


def desactivar_tenant(db: Session, tenant_id: UUID) -> Tenant:
    tenant = obtener_tenant(db, tenant_id)
    tenant.activo = False
    db.commit()
    db.refresh(tenant)
    return tenant


def generar_password_temporal(longitud: int = 12) -> str:
    """Contraseña aleatoria segura para enviar al admin recién creado."""
    alfabeto = string.ascii_letters + string.digits
    return "".join(secrets.choice(alfabeto) for _ in range(longitud))


def derivar_slug(nombre: str) -> str:
    """Convierte 'Red de Talleres ABC' → 'red-de-talleres-abc'."""
    base = nombre.lower().strip()
    # Sustituye caracteres comunes hispanoparlantes
    for src, dst in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ñ", "n")):
        base = base.replace(src, dst)
    # Reemplaza no-alfanuméricos por guiones
    out = []
    for ch in base:
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "_"):
            out.append("-")
    slug = "".join(out).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "tenant"


def slug_unico(db: Session, base: str) -> str:
    """Devuelve un slug único agregando sufijo numérico si el base ya existe."""
    slug = base
    suf = 1
    while db.query(Tenant).filter(Tenant.slug == slug).first():
        suf += 1
        slug = f"{base}-{suf}"
    return slug

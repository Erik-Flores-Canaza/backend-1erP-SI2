from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class TenantBase(BaseModel):
    nombre: str = Field(min_length=2, max_length=150)
    slug: str = Field(min_length=2, max_length=60, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    correo_contacto: EmailStr | None = None
    telefono_contacto: str | None = Field(default=None, max_length=20)
    plan: str = Field(default="basico", max_length=20)


class TenantCreate(TenantBase):
    """Datos para crear un tenant (Superadmin plataforma)."""


class TenantUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=150)
    correo_contacto: EmailStr | None = None
    telefono_contacto: str | None = Field(default=None, max_length=20)
    plan: str | None = Field(default=None, max_length=20)


class TenantResponse(TenantBase):
    id: UUID
    activo: bool
    creado_en: datetime

    class Config:
        from_attributes = True


class TenantCreateConAdmin(TenantCreate):
    """Crea un tenant + su primer admin_tenant en un solo paso."""
    admin_nombre_completo: str = Field(min_length=2, max_length=150)
    admin_correo: EmailStr
    admin_contrasena: str = Field(min_length=6, max_length=100)
    admin_telefono: str | None = Field(default=None, max_length=20)


class TenantCreateResponse(BaseModel):
    """Devuelve el tenant + las credenciales temporales del admin recién creado."""
    tenant: TenantResponse
    admin_correo: EmailStr
    contrasena_temporal: str | None = None  # solo se devuelve si el sistema generó la contraseña

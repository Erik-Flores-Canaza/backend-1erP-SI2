from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class SolicitudTenantCreate(BaseModel):
    """Cuerpo del formulario público para solicitar alta como tenant. CU-29."""
    solicitante_nombre: str = Field(min_length=2, max_length=150)
    solicitante_correo: EmailStr
    solicitante_telefono: str | None = Field(default=None, max_length=20)
    nombre_red: str = Field(min_length=2, max_length=150)
    descripcion: str | None = None


class SolicitudTenantResponse(BaseModel):
    id: UUID
    solicitante_nombre: str
    solicitante_correo: EmailStr
    solicitante_telefono: str | None = None
    nombre_red: str
    descripcion: str | None = None
    estado: str
    motivo_rechazo: str | None = None
    revisado_por: UUID | None = None
    revisado_en: datetime | None = None
    creado_en: datetime

    class Config:
        from_attributes = True


class SolicitudTenantRechazar(BaseModel):
    motivo_rechazo: str = Field(min_length=3, max_length=500)

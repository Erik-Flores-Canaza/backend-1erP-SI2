from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


class UsuarioCreate(BaseModel):
    nombre_completo: str
    correo: EmailStr
    contrasena: str
    telefono: str | None = None


class RolInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nombre: str


class UsuarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rol_id: UUID
    rol: RolInfo
    nombre_completo: str
    correo: str
    telefono: str | None
    activo: bool
    creado_en: datetime


class UsuarioUpdate(BaseModel):
    nombre_completo: str | None = None
    telefono: str | None = None


class ChangePasswordRequest(BaseModel):
    contrasena_actual: str
    nueva_contrasena: str

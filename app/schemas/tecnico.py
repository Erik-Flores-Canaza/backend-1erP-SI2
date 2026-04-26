from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


class TecnicoCreate(BaseModel):
    nombre_completo: str
    correo: EmailStr
    contrasena: str
    telefono: str | None = None
    taller_id: UUID


class UsuarioInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nombre_completo: str
    correo: str
    telefono: str | None


class TecnicoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    usuario_id: UUID
    usuario: UsuarioInfo
    taller_id: UUID
    latitud_actual: float | None
    longitud_actual: float | None
    disponible: bool
    disponible_ahora: bool = False   # calculado: tiene turno activo en este momento


class TecnicoUpdate(BaseModel):
    disponible: bool | None = None

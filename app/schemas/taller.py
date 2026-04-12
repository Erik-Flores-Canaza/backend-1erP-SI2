from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TallerCreate(BaseModel):
    nombre: str
    direccion: str | None = None
    latitud: float | None = None
    longitud: float | None = None


class TallerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    administrador_id: UUID
    nombre: str
    direccion: str | None
    latitud: float | None
    longitud: float | None
    porcentaje_comision: float
    activo: bool
    disponible: bool
    creado_en: datetime


class TallerUpdate(BaseModel):
    nombre: str | None = None
    direccion: str | None = None
    latitud: float | None = None
    longitud: float | None = None
    disponible: bool | None = None

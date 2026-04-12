from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class VehiculoCreate(BaseModel):
    placa: str
    marca: str
    modelo: str
    anio: int | None = None
    color: str | None = None


class VehiculoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    propietario_id: UUID
    placa: str
    marca: str
    modelo: str
    anio: int | None
    color: str | None
    creado_en: datetime


class VehiculoUpdate(BaseModel):
    marca: str | None = None
    modelo: str | None = None
    anio: int | None = None
    color: str | None = None

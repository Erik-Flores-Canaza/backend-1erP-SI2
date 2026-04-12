from datetime import date, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TurnoCreate(BaseModel):
    fecha_turno: date
    hora_inicio: time
    hora_fin: time


class TurnoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tecnico_id: UUID
    fecha_turno: date
    hora_inicio: time
    hora_fin: time
    en_servicio: bool

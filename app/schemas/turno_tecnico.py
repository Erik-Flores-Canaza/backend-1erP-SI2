from datetime import time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


class TurnoCreate(BaseModel):
    dia_semana: int   # 0=Lun … 6=Dom
    hora_inicio: time
    hora_fin: time

    @field_validator('dia_semana')
    @classmethod
    def validar_dia(cls, v: int) -> int:
        if v < 0 or v > 6:
            raise ValueError('dia_semana debe ser entre 0 (Lunes) y 6 (Domingo)')
        return v


class TurnoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tecnico_id: UUID
    dia_semana: int
    dia_nombre: str | None = None   # calculado, no en DB
    hora_inicio: time
    hora_fin: time

    @classmethod
    def from_orm_with_nombre(cls, turno: object) -> "TurnoResponse":
        obj = cls.model_validate(turno)
        obj.dia_nombre = DIAS_SEMANA[obj.dia_semana]
        return obj

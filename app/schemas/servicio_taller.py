from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

TIPOS_VALIDOS = {"electrico", "neumatico", "remolque", "mecanica", "otro"}


class ServicioTallerCreate(BaseModel):
    tipo_servicio: str

    @field_validator("tipo_servicio")
    @classmethod
    def validar_tipo(cls, v: str) -> str:
        if v not in TIPOS_VALIDOS:
            raise ValueError(f"tipo_servicio debe ser uno de: {', '.join(TIPOS_VALIDOS)}")
        return v


class ServicioTallerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    taller_id: UUID
    tipo_servicio: str
    disponible: bool

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CalificacionCreate(BaseModel):
    """Body del cliente para calificar el servicio (CU-43)."""
    puntuacion: int = Field(ge=1, le=5)
    comentario: str | None = Field(default=None, max_length=1000)


class CalificacionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incidente_id: UUID
    taller_id: UUID
    puntuacion: int
    comentario: str | None
    oculta: bool
    creado_en: datetime


class CalificacionPublica(BaseModel):
    """Reseña visible de un taller (para mostrar a clientes)."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    puntuacion: int
    comentario: str | None
    creado_en: datetime


class CalificacionModeracion(BaseModel):
    """Reseña con datos para el panel de moderación del admin_tenant."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incidente_id: UUID
    taller_id: UUID
    taller_nombre: str
    cliente_nombre: str
    puntuacion: int
    comentario: str | None
    oculta: bool
    creado_en: datetime


class ResumenCalificacionTaller(BaseModel):
    """Promedio y total de reseñas visibles de un taller."""
    taller_id: UUID
    promedio: float | None
    total: int

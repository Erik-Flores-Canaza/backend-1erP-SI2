from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class NotificacionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    usuario_id: UUID
    incidente_id: UUID | None
    tipo: str
    titulo: str
    cuerpo: str | None
    leida: bool
    leida_en: datetime | None
    enviada_en: datetime

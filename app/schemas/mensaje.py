from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MensajeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incidente_id: UUID
    remitente_id: UUID
    rol_remitente: str
    nombre_remitente: str = "Desconocido"
    contenido: str
    leido: bool
    creado_en: datetime

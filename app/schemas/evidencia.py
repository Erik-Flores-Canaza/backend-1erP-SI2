from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EvidenciaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incidente_id: UUID
    tipo: str
    url_archivo: str | None
    transcripcion: str | None
    analisis_ia: str | None
    creado_en: datetime

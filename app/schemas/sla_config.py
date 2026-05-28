"""Schemas de configuración de SLA por tenant — CU-37."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


TipoServicio = Literal["bateria", "llanta", "motor", "choque", "otro"]


class SlaConfigBase(BaseModel):
    minutos_asignacion_objetivo: int = Field(gt=0, le=1440)
    minutos_llegada_objetivo: int = Field(gt=0, le=1440)
    minutos_resolucion_objetivo: int = Field(gt=0, le=1440)


class SlaConfigUpsert(SlaConfigBase):
    """Body de PUT /admin/sla/{tipo_servicio}. El tipo va en la URL."""


class SlaConfigResponse(SlaConfigBase):
    id: UUID
    tenant_id: UUID
    tipo_servicio: TipoServicio
    creado_en: datetime
    actualizado_en: datetime

    model_config = ConfigDict(from_attributes=True)

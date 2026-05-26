from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CotizacionCreate(BaseModel):
    """Body del taller para enviar cotización (CU-34)."""
    monto_estimado: float = Field(gt=0, le=99999.99)
    tiempo_estimado_horas: float | None = Field(default=None, gt=0, le=999.99)
    observaciones: str | None = Field(default=None, max_length=1000)


class CotizacionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incidente_id: UUID
    taller_id: UUID
    monto_estimado: float
    tiempo_estimado_horas: float | None
    observaciones: str | None
    estado: str
    enviado_en: datetime
    expira_en: datetime
    respondido_en: datetime | None


class CotizacionConTallerResponse(BaseModel):
    """Cotización + datos básicos del taller para que el cliente decida (CU-35)."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    taller_id: UUID
    taller_nombre: str
    taller_direccion: str | None
    monto_estimado: float
    tiempo_estimado_horas: float | None
    observaciones: str | None
    estado: str
    enviado_en: datetime
    expira_en: datetime


class IncidentePendienteParaCotizar(BaseModel):
    """Incidente pendiente que el taller puede cotizar (CU-34)."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    descripcion: str | None = None
    latitud: float | None = None
    longitud: float | None = None
    clasificacion_ia: str | None = None
    prioridad: str | None = None
    resumen_ia: str | None = None
    creado_en: datetime
    cotizacion_propia_id: UUID | None = None  # si el taller ya envió cotización

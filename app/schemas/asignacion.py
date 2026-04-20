from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Evidencia embebida en la orden activa del técnico
# ---------------------------------------------------------------------------
class EvidenciaEnOrden(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    tipo: str
    archivo_url: str | None = Field(None, validation_alias="url_archivo")


class AsignacionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incidente_id: UUID
    taller_id: UUID
    tecnico_id: UUID | None
    accion_taller: str | None
    taller_respondio_en: datetime | None
    eta_minutos: int | None
    asignado_en: datetime
    completado_en: datetime | None


class ResponderAsignacionBody(BaseModel):
    accion_taller: str  # 'aceptado' | 'rechazado'
    eta_minutos: int | None = None


class AsignarTecnicoBody(BaseModel):
    tecnico_id: UUID


# ---------------------------------------------------------------------------
# Schema extendido para GET /tecnicos/me/orden-activa
# Incluye datos del incidente y del cliente para la vista del técnico.
# ---------------------------------------------------------------------------

class ClienteEnOrden(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    nombre_completo: str = ""
    telefono: str | None = None


class IncidenteEnOrden(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    descripcion: str | None = Field(None, validation_alias="descripcion_texto")
    latitud: float | None = None
    longitud: float | None = None
    estado: str
    prioridad: str
    clasificacion_ia: str | None = None
    resumen_ia: str | None = None
    cliente: ClienteEnOrden | None = None
    evidencias: list[EvidenciaEnOrden] = []


class OrdenActivaTecnicoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incidente_id: UUID
    accion_taller: str | None = None
    eta_minutos: int | None = None
    asignado_en: datetime
    completado_en: datetime | None = None
    incidente: IncidenteEnOrden | None = None

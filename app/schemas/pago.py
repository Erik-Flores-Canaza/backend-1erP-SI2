from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CrearIntentBody(BaseModel):
    incidente_id: UUID
    monto: float = Field(..., gt=0, description="Monto en dólares (ej: 50.00)")


class CrearIntentResponse(BaseModel):
    client_secret: str
    publishable_key: str
    monto_total: float
    comision: float
    neto_taller: float


class ConfirmarPagoBody(BaseModel):
    incidente_id: UUID
    payment_intent_id: str
    metodo_pago: str


class PagoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incidente_id: UUID
    monto_total: float
    comision_plataforma: float
    neto_taller: float
    estado: str
    metodo_pago: str | None
    pagado_en: datetime | None
    creado_en: datetime

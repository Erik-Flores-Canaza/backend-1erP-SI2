from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── Técnico registra el monto ─────────────────────────────────────────────────

METODOS_PAGO = ('efectivo', 'stripe')

class RegistrarMontoBody(BaseModel):
    incidente_id: UUID
    monto: float = Field(..., gt=0, description="Monto cobrado por el servicio (Bs.)")
    metodo_pago: str | None = Field(
        None,
        description="'efectivo' cierra el pago en sitio. None o 'stripe' deja pendiente para pago online.",
    )


# ── Cliente crea el PaymentIntent ─────────────────────────────────────────────

class CrearIntentBody(BaseModel):
    incidente_id: UUID
    # El monto ya fue fijado por el técnico; no lo ingresa el cliente.


class CrearIntentResponse(BaseModel):
    client_secret: str
    publishable_key: str
    monto_total: float
    comision: float
    neto_taller: float


# ── Confirmación Stripe ───────────────────────────────────────────────────────

class ConfirmarPagoBody(BaseModel):
    incidente_id: UUID
    payment_intent_id: str
    metodo_pago: str


# ── Respuestas ────────────────────────────────────────────────────────────────

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


class ServicioTecnicoItem(BaseModel):
    """Un ítem del historial de servicios del técnico."""
    model_config = ConfigDict(from_attributes=True)

    incidente_id: UUID
    cliente_nombre: str
    clasificacion_ia: str | None
    prioridad: str | None
    completado_en: datetime | None
    pago_estado: str | None          # 'pendiente' | 'pagado' | None
    pago_monto: float | None
    pago_metodo: str | None          # 'efectivo' | 'stripe' | None

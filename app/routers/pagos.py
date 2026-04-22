from datetime import datetime, timezone
from uuid import UUID

import stripe
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.dependencies import get_current_user, get_db, require_cliente
from app.models.incidente import Incidente
from app.models.pago import Pago
from app.models.usuario import Usuario
from app.schemas.pago import (
    ConfirmarPagoBody,
    CrearIntentBody,
    CrearIntentResponse,
    PagoResponse,
)

router = APIRouter(prefix="/pagos", tags=["Pagos"])

COMISION_PORCENTAJE = 0.10


@router.post(
    "/crear-intent",
    response_model=CrearIntentResponse,
    status_code=status.HTTP_201_CREATED,
)
def crear_payment_intent(
    body: CrearIntentBody,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_cliente),
):
    """
    CU-07 — Paso 1: Crea un PaymentIntent en Stripe.
    Valida que el incidente esté 'atendido' y sin pago previo.
    Retorna client_secret para completar el pago desde el frontend.
    """
    incidente = db.query(Incidente).filter(
        Incidente.id == body.incidente_id,
        Incidente.cliente_id == current_user.id,
    ).first()
    if not incidente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incidente no encontrado",
        )
    if incidente.estado != "atendido":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El incidente debe estar en estado 'atendido'. Estado actual: '{incidente.estado}'",
        )

    pago_existente = db.query(Pago).filter(Pago.incidente_id == body.incidente_id).first()
    if pago_existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este incidente ya tiene un pago registrado",
        )

    monto_total = round(body.monto, 2)
    comision = round(monto_total * COMISION_PORCENTAJE, 2)
    neto_taller = round(monto_total - comision, 2)

    # Stripe espera el monto en centavos (entero)
    monto_centavos = int(round(monto_total * 100))

    try:
        intent = stripe.PaymentIntent.create(
            amount=monto_centavos,
            currency="usd",
            metadata={
                "incidente_id": str(body.incidente_id),
                "cliente_id": str(current_user.id),
            },
        )
    except stripe.StripeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error al crear PaymentIntent en Stripe: {exc.user_message}",
        )

    return CrearIntentResponse(
        client_secret=intent.client_secret,
        publishable_key=settings.STRIPE_PUBLISHABLE_KEY,
        monto_total=monto_total,
        comision=comision,
        neto_taller=neto_taller,
    )


@router.post("/confirmar", response_model=PagoResponse, status_code=status.HTTP_201_CREATED)
def confirmar_pago(
    body: ConfirmarPagoBody,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_cliente),
):
    """
    CU-07 — Paso 2: Confirma el pago verificando con Stripe.
    Si el PaymentIntent tiene status 'succeeded', registra el pago en BD.
    """
    incidente = db.query(Incidente).filter(
        Incidente.id == body.incidente_id,
        Incidente.cliente_id == current_user.id,
    ).first()
    if not incidente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incidente no encontrado",
        )
    if incidente.estado != "atendido":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El incidente debe estar en estado 'atendido'",
        )

    pago_existente = db.query(Pago).filter(Pago.incidente_id == body.incidente_id).first()
    if pago_existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este incidente ya tiene un pago registrado",
        )

    try:
        intent = stripe.PaymentIntent.retrieve(body.payment_intent_id)
    except stripe.StripeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error al consultar PaymentIntent en Stripe: {exc.user_message}",
        )

    if intent.status != "succeeded":
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"El pago aún no fue confirmado por Stripe (status: {intent.status})",
        )

    monto_total = round(intent.amount / 100, 2)
    comision = round(monto_total * COMISION_PORCENTAJE, 2)
    neto_taller = round(monto_total - comision, 2)

    pago = Pago(
        incidente_id=body.incidente_id,
        monto_total=monto_total,
        comision_plataforma=comision,
        neto_taller=neto_taller,
        estado="pagado",
        metodo_pago=body.metodo_pago,
        pagado_en=datetime.now(timezone.utc),
    )
    db.add(pago)
    db.commit()
    db.refresh(pago)
    return pago


@router.get("/{incidente_id}", response_model=PagoResponse)
def get_pago(
    incidente_id: UUID,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """CU-07 — Detalle del pago asociado a un incidente."""
    pago = db.query(Pago).filter(Pago.incidente_id == incidente_id).first()
    if not pago:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró pago para este incidente",
        )
    return pago

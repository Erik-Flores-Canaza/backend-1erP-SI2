from app.core.timezone import now_bo

import stripe
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.dependencies import get_current_user, get_db, require_cliente, require_tecnico
from app.models.asignacion import Asignacion
from app.models.incidente import Incidente
from app.models.pago import Pago
from app.models.tecnico import Tecnico
from app.models.usuario import Usuario
from app.schemas.pago import (
    ConfirmarPagoBody,
    CrearIntentBody,
    CrearIntentResponse,
    PagoResponse,
    RegistrarMontoBody,
)

router = APIRouter(prefix="/pagos", tags=["Pagos"])

COMISION_PORCENTAJE = 0.10


# ---------------------------------------------------------------------------
# Paso 0 (NUEVO): Técnico registra el monto tras completar el servicio
# ---------------------------------------------------------------------------

@router.post(
    "/registrar-monto",
    response_model=PagoResponse,
    status_code=status.HTTP_201_CREATED,
)
def registrar_monto(
    body: RegistrarMontoBody,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_tecnico),
):
    """
    CU-07 — Paso 0: El técnico fija el monto del servicio.
    Crea el registro de PAGO en estado 'pendiente'.
    Solo puede llamarlo el técnico asignado a esa orden.
    """
    incidente = db.query(Incidente).filter(Incidente.id == body.incidente_id).first()
    if not incidente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incidente no encontrado")

    if incidente.estado != "atendido":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El incidente debe estar en estado 'atendido'. Estado actual: '{incidente.estado}'",
        )

    # Verificar que el técnico autenticado es el asignado a este incidente
    tecnico = db.query(Tecnico).filter(Tecnico.usuario_id == current_user.id).first()
    if not tecnico:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes perfil de técnico")

    asignacion = (
        db.query(Asignacion)
        .filter(
            Asignacion.incidente_id == body.incidente_id,
            Asignacion.tecnico_id == tecnico.id,
            Asignacion.accion_taller == "aceptado",
        )
        .first()
    )
    if not asignacion:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el técnico asignado a esta orden puede registrar el monto",
        )

    if db.query(Pago).filter(Pago.incidente_id == body.incidente_id).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un pago registrado para este incidente",
        )

    monto_total = round(body.monto, 2)
    comision = round(monto_total * COMISION_PORCENTAJE, 2)
    neto_taller = round(monto_total - comision, 2)

    es_efectivo = (body.metodo_pago == "efectivo")

    pago = Pago(
        incidente_id=body.incidente_id,
        monto_total=monto_total,
        comision_plataforma=comision,
        neto_taller=neto_taller,
        metodo_pago=body.metodo_pago if es_efectivo else None,
        estado="pagado" if es_efectivo else "pendiente",
        pagado_en=now_bo() if es_efectivo else None,
    )
    db.add(pago)

    if es_efectivo:
        from app.services import notificacion_service
        from app.models.taller import Taller

        # Notificar al cliente que el técnico registró el cobro en efectivo
        notificacion_service.notif_pago_efectivo_cliente(
            db,
            cliente_id=incidente.cliente_id,
            incidente_id=incidente.id,
            monto=monto_total,
        )

        # Notificar al admin_taller (activa auto-refresh en Angular)
        taller = db.query(Taller).filter(Taller.id == asignacion.taller_id).first()
        if taller:
            notificacion_service.notif_pago_confirmado_admin(
                db,
                admin_taller_id=taller.administrador_id,
                incidente_id=incidente.id,
                monto=monto_total,
                metodo="efectivo",
            )

    db.commit()
    db.refresh(pago)
    return pago


# ---------------------------------------------------------------------------
# CU-07 — Paso 1: Cliente crea el PaymentIntent (monto ya fijado por técnico)
# ---------------------------------------------------------------------------

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
    El monto ya fue registrado por el técnico (estado 'pendiente').
    Retorna client_secret para que el cliente complete el pago.
    """
    incidente = db.query(Incidente).filter(
        Incidente.id == body.incidente_id,
        Incidente.cliente_id == current_user.id,
    ).first()
    if not incidente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incidente no encontrado")

    if incidente.estado != "atendido":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El incidente debe estar en estado 'atendido'. Estado actual: '{incidente.estado}'",
        )

    pago = db.query(Pago).filter(Pago.incidente_id == body.incidente_id).first()
    if not pago:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El técnico aún no ha registrado el monto del servicio",
        )
    if pago.estado == "pagado":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Este incidente ya fue pagado")

    monto_centavos = int(round(pago.monto_total * 100))

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
        monto_total=pago.monto_total,
        comision=pago.comision_plataforma,
        neto_taller=pago.neto_taller,
    )


# ---------------------------------------------------------------------------
# CU-07 — Paso 2: Cliente confirma el pago → notificar técnico
# ---------------------------------------------------------------------------

@router.post("/confirmar", response_model=PagoResponse, status_code=status.HTTP_201_CREATED)
def confirmar_pago(
    body: ConfirmarPagoBody,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_cliente),
):
    """
    CU-07 — Paso 2: Confirma el pago verificando con Stripe.
    Actualiza el Pago existente a estado 'pagado' y notifica al técnico.
    """
    incidente = db.query(Incidente).filter(
        Incidente.id == body.incidente_id,
        Incidente.cliente_id == current_user.id,
    ).first()
    if not incidente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incidente no encontrado")

    pago = db.query(Pago).filter(Pago.incidente_id == body.incidente_id).first()
    if not pago:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No se encontró pago pendiente")
    if pago.estado == "pagado":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Este incidente ya fue pagado")

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

    pago.estado = "pagado"
    pago.metodo_pago = body.metodo_pago
    pago.pagado_en = now_bo()
    db.commit()
    db.refresh(pago)

    # ── Notificar al técnico asignado y al admin_taller ──────────────────
    asignacion = (
        db.query(Asignacion)
        .filter(
            Asignacion.incidente_id == body.incidente_id,
            Asignacion.accion_taller == "aceptado",
        )
        .first()
    )
    if asignacion:
        from app.services import notificacion_service
        from app.models.taller import Taller

        # Notificar al técnico
        if asignacion.tecnico_id:
            tecnico = db.query(Tecnico).filter(Tecnico.id == asignacion.tecnico_id).first()
            if tecnico:
                notificacion_service.notif_pago_recibido_tecnico(
                    db,
                    tecnico_usuario_id=tecnico.usuario_id,
                    incidente_id=incidente.id,
                    cliente_nombre=current_user.nombre_completo,
                    monto=pago.monto_total,
                )

        # Notificar al admin_taller (activa auto-refresh en Angular)
        taller = db.query(Taller).filter(Taller.id == asignacion.taller_id).first()
        if taller:
            notificacion_service.notif_pago_confirmado_admin(
                db,
                admin_taller_id=taller.administrador_id,
                incidente_id=incidente.id,
                monto=pago.monto_total,
                metodo=pago.metodo_pago or "stripe",
            )

        db.commit()

    return pago


# ---------------------------------------------------------------------------
# GET: estado del pago de un incidente
# ---------------------------------------------------------------------------

@router.get("/{incidente_id}", response_model=PagoResponse)
def get_pago(
    incidente_id,
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

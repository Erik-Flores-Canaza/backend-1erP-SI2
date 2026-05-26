"""Servicio de cotizaciones — CU-34 (taller envía) y CU-35 (cliente acepta).

Reglas de negocio:
- Cada cotización tiene un TTL de 15 minutos desde su envío.
- Cuando un cliente acepta una cotización: la elegida pasa a 'aceptada', las demás
  del mismo incidente pasan a 'expirada', se crea la Asignación y el incidente
  pasa al estado 'taller_asignado' (CU-31).
- Un taller no puede enviar dos cotizaciones para el mismo incidente.
- Solo se puede cotizar mientras el incidente esté en estado 'buscando_taller'.
"""
from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core import estado_incidente as estado_machine
from app.core.timezone import now_bo
from app.models.asignacion import Asignacion
from app.models.cotizacion import Cotizacion
from app.models.incidente import Incidente
from app.models.taller import Taller
from app.models.usuario import Usuario
from app.schemas.cotizacion import CotizacionCreate
from app.services import incidente_service, notificacion_service

# TTL de cotización en minutos
COTIZACION_TTL_MINUTOS = 15


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _marcar_expiradas_si_corresponde(db: Session, incidente_id: UUID) -> None:
    """Marca como 'expirada' las cotizaciones del incidente cuyo expira_en ya pasó."""
    ahora = now_bo().replace(tzinfo=None)
    vencidas = (
        db.query(Cotizacion)
        .filter(
            Cotizacion.incidente_id == incidente_id,
            Cotizacion.estado == "enviada",
            Cotizacion.expira_en < ahora,
        )
        .all()
    )
    for c in vencidas:
        c.estado = "expirada"
    if vencidas:
        db.flush()


def _verificar_taller_del_admin(
    admin: Usuario, taller_id: UUID, db: Session
) -> Taller:
    """Verifica que el admin_taller es dueño del taller indicado."""
    taller = (
        db.query(Taller)
        .filter(
            Taller.id == taller_id,
            Taller.administrador_id == admin.id,
        )
        .first()
    )
    if not taller:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este taller",
        )
    return taller


# ---------------------------------------------------------------------------
# CU-34: taller envía cotización
# ---------------------------------------------------------------------------

def crear_cotizacion(
    db: Session,
    incidente_id: UUID,
    taller_id: UUID,
    body: CotizacionCreate,
    admin: Usuario,
) -> Cotizacion:
    taller = _verificar_taller_del_admin(admin, taller_id, db)

    incidente = (
        db.query(Incidente).filter(Incidente.id == incidente_id).first()
    )
    if not incidente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Incidente no encontrado"
        )

    if incidente.estado != estado_machine.BUSCANDO_TALLER:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Solo se puede cotizar mientras el incidente esté en estado "
                f"'buscando_taller'. Estado actual: '{incidente.estado}'."
            ),
        )

    # Evitar duplicado del mismo taller
    existente = (
        db.query(Cotizacion)
        .filter(
            Cotizacion.incidente_id == incidente_id,
            Cotizacion.taller_id == taller_id,
        )
        .first()
    )
    if existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tu taller ya envió una cotización para este incidente",
        )

    ahora = now_bo().replace(tzinfo=None)
    cotizacion = Cotizacion(
        tenant_id=taller.tenant_id,
        incidente_id=incidente_id,
        taller_id=taller_id,
        monto_estimado=body.monto_estimado,
        tiempo_estimado_horas=body.tiempo_estimado_horas,
        observaciones=body.observaciones,
        estado="enviada",
        enviado_en=ahora,
        expira_en=ahora + timedelta(minutes=COTIZACION_TTL_MINUTOS),
    )
    db.add(cotizacion)
    db.flush()

    # Notificar al cliente que llegó una cotización nueva
    notificacion_service.notif_cotizacion_recibida(
        db,
        cliente_id=incidente.cliente_id,
        incidente_id=incidente_id,
        nombre_taller=taller.nombre,
        monto=float(body.monto_estimado),
    )

    db.commit()
    db.refresh(cotizacion)
    return cotizacion


def retirar_cotizacion(
    db: Session, cotizacion_id: UUID, admin: Usuario
) -> None:
    cot = db.query(Cotizacion).filter(Cotizacion.id == cotizacion_id).first()
    if not cot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Cotización no encontrada"
        )

    _verificar_taller_del_admin(admin, cot.taller_id, db)

    if cot.estado != "enviada":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No se puede retirar una cotización en estado '{cot.estado}'",
        )

    db.delete(cot)
    db.commit()


def listar_incidentes_para_cotizar(
    db: Session, taller_id: UUID, admin: Usuario
) -> list[dict]:
    """CU-34 — Lista los incidentes en estado 'buscando_taller' candidatos a cotización
    para el taller del admin autenticado.

    Filtros:
    - incidente.estado == 'buscando_taller'
    - el taller ofrece un servicio compatible con la clasificación IA
    """
    taller = _verificar_taller_del_admin(admin, taller_id, db)

    # Importar el mapa de servicios compatibles del asignador
    from app.models.servicio_taller import ServicioTaller
    from app.services.asignacion_service import _CLASIFICACION_SERVICIOS

    servicios_taller = {
        s.tipo_servicio
        for s in db.query(ServicioTaller)
        .filter(
            ServicioTaller.taller_id == taller.id,
            ServicioTaller.disponible == True,  # noqa: E712
        )
        .all()
    }

    incidentes = (
        db.query(Incidente)
        .filter(Incidente.estado == estado_machine.BUSCANDO_TALLER)
        .order_by(Incidente.creado_en.desc())
        .all()
    )

    resultado = []
    for inc in incidentes:
        clasificacion = inc.clasificacion_ia or "otro"
        tipos_compatibles = set(
            _CLASIFICACION_SERVICIOS.get(clasificacion, ["otro"])
        )
        # Filtrar: el taller debe tener al menos un tipo de servicio compatible
        if not (servicios_taller & tipos_compatibles):
            continue

        # ¿el taller ya envió cotización para este incidente?
        cot_propia = (
            db.query(Cotizacion)
            .filter(
                Cotizacion.incidente_id == inc.id,
                Cotizacion.taller_id == taller.id,
            )
            .first()
        )

        resultado.append({
            "id": inc.id,
            "descripcion": inc.descripcion_texto,
            "latitud": float(inc.latitud) if inc.latitud is not None else None,
            "longitud": float(inc.longitud) if inc.longitud is not None else None,
            "clasificacion_ia": inc.clasificacion_ia,
            "prioridad": inc.prioridad,
            "resumen_ia": inc.resumen_ia,
            "creado_en": inc.creado_en,
            "cotizacion_propia_id": cot_propia.id if cot_propia else None,
        })
    return resultado


# ---------------------------------------------------------------------------
# CU-35: cliente ve cotizaciones y elige una
# ---------------------------------------------------------------------------

def listar_cotizaciones_de_incidente(
    db: Session, incidente_id: UUID, cliente: Usuario
) -> list[dict]:
    """Cliente lee las cotizaciones recibidas para SU incidente."""
    incidente = (
        db.query(Incidente).filter(Incidente.id == incidente_id).first()
    )
    if not incidente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Incidente no encontrado"
        )

    if incidente.cliente_id != cliente.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sin acceso a las cotizaciones de otro cliente",
        )

    # Marca expiradas si corresponde antes de listar
    _marcar_expiradas_si_corresponde(db, incidente_id)

    cotizaciones = (
        db.query(Cotizacion)
        .filter(Cotizacion.incidente_id == incidente_id)
        .order_by(Cotizacion.enviado_en.desc())
        .all()
    )

    resultado = []
    for c in cotizaciones:
        taller = db.query(Taller).filter(Taller.id == c.taller_id).first()
        resultado.append({
            "id": c.id,
            "taller_id": c.taller_id,
            "taller_nombre": taller.nombre if taller else "",
            "taller_direccion": taller.direccion if taller else None,
            "monto_estimado": float(c.monto_estimado),
            "tiempo_estimado_horas": (
                float(c.tiempo_estimado_horas) if c.tiempo_estimado_horas is not None else None
            ),
            "observaciones": c.observaciones,
            "estado": c.estado,
            "enviado_en": c.enviado_en,
            "expira_en": c.expira_en,
        })
    return resultado


def aceptar_cotizacion(
    db: Session, cotizacion_id: UUID, cliente: Usuario
) -> Asignacion:
    """CU-35 — Cliente acepta UNA cotización.

    Efectos en cascada:
    - La cotización elegida → estado 'aceptada' + respondido_en
    - Las demás cotizaciones del mismo incidente → 'expirada'
    - Crea Asignacion con accion_taller='aceptado' (taller ya se comprometió al cotizar)
    - Incidente: tenant_id ← taller.tenant_id; estado → taller_asignado
    - taller.disponible = False
    - Notifica al admin_taller del taller ganador
    """
    cot = db.query(Cotizacion).filter(Cotizacion.id == cotizacion_id).first()
    if not cot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Cotización no encontrada"
        )

    incidente = (
        db.query(Incidente).filter(Incidente.id == cot.incidente_id).first()
    )
    if not incidente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Incidente no encontrado"
        )
    if incidente.cliente_id != cliente.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el dueño del incidente puede aceptar cotizaciones",
        )

    # Validar estado de la cotización y el incidente
    _marcar_expiradas_si_corresponde(db, incidente.id)
    db.refresh(cot)

    if cot.estado != "enviada":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La cotización ya no está disponible (estado: {cot.estado})",
        )

    if incidente.estado != estado_machine.BUSCANDO_TALLER:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"No se puede aceptar cotización con incidente en estado "
                f"'{incidente.estado}'. Debe estar en 'buscando_taller'."
            ),
        )

    taller = db.query(Taller).filter(Taller.id == cot.taller_id).first()
    if not taller:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Taller no encontrado"
        )
    if not taller.disponible or not taller.activo:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El taller ya no está disponible. Elige otra cotización.",
        )

    ahora = now_bo().replace(tzinfo=None)

    # 1. Aceptar la cotización elegida
    cot.estado = "aceptada"
    cot.respondido_en = ahora

    # 2. Expirar las demás cotizaciones del mismo incidente
    otras = (
        db.query(Cotizacion)
        .filter(
            Cotizacion.incidente_id == incidente.id,
            Cotizacion.id != cot.id,
            Cotizacion.estado == "enviada",
        )
        .all()
    )
    for o in otras:
        o.estado = "expirada"
        o.respondido_en = ahora

    # 3. Crear la Asignación (taller ya se comprometió al cotizar)
    asignacion = Asignacion(
        tenant_id=taller.tenant_id,
        incidente_id=incidente.id,
        taller_id=taller.id,
        accion_taller="aceptado",
        taller_respondio_en=ahora,
        eta_minutos=(int(float(cot.tiempo_estimado_horas) * 60)
                     if cot.tiempo_estimado_horas else None),
    )
    db.add(asignacion)

    # 4. Anclar tenant_id al incidente + transicionar estado
    if incidente.tenant_id is None:
        incidente.tenant_id = taller.tenant_id

    incidente_service.registrar_cambio_estado(
        db, incidente, estado_machine.TALLER_ASIGNADO, cliente.id,
        notas=f"Cliente aceptó cotización del taller '{taller.nombre}' por Bs. {float(cot.monto_estimado):.2f}",
    )

    # 5. Marcar taller como ocupado
    taller.disponible = False

    # 6. Notificar al admin del taller ganador
    notificacion_service.notif_cotizacion_aceptada(
        db,
        admin_taller_id=taller.administrador_id,
        incidente_id=incidente.id,
        nombre_taller=taller.nombre,
    )

    db.commit()
    db.refresh(asignacion)
    return asignacion

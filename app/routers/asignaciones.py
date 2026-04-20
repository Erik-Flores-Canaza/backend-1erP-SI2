from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db, require_admin_taller, require_tecnico
from app.models.asignacion import Asignacion
from app.models.incidente import Incidente
from app.models.taller import Taller
from app.models.tecnico import Tecnico
from app.models.usuario import Usuario
from app.schemas.asignacion import (
    AsignacionResponse,
    AsignarTecnicoBody,
    ResponderAsignacionBody,
)
from app.schemas.incidente import IncidenteResponse
from app.services import asignacion_service, incidente_service, notificacion_service

router = APIRouter(tags=["Asignaciones"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_taller_del_admin(admin: Usuario, db: Session) -> Taller:
    taller = db.query(Taller).filter(Taller.administrador_id == admin.id).first()
    if not taller:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No tienes un taller registrado")
    return taller


def _get_asignacion(asignacion_id: UUID, db: Session) -> Asignacion:
    asignacion = db.query(Asignacion).filter(Asignacion.id == asignacion_id).first()
    if not asignacion:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asignación no encontrada")
    return asignacion


# ---------------------------------------------------------------------------
# CU-13: Órdenes activas del taller — asignaciones aceptadas aún sin completar
# ---------------------------------------------------------------------------

@router.get("/talleres/{taller_id}/ordenes-activas", response_model=list[IncidenteResponse])
def listar_ordenes_activas(
    taller_id: UUID,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin_taller),
):
    """
    Devuelve los incidentes cuya asignación al taller fue aceptada y
    aún no están completados ni cancelados.
    """
    taller = db.query(Taller).filter(
        Taller.id == taller_id, Taller.administrador_id == current_user.id
    ).first()
    if not taller:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Taller no encontrado")

    asignaciones_activas = (
        db.query(Asignacion)
        .join(Incidente, Asignacion.incidente_id == Incidente.id)
        .filter(
            Asignacion.taller_id == taller_id,
            Asignacion.accion_taller == "aceptado",
            Asignacion.completado_en == None,           # noqa: E711
            Incidente.estado.in_(["pendiente", "en_proceso"]),
        )
        .all()
    )

    incidente_ids = [a.incidente_id for a in asignaciones_activas]
    if not incidente_ids:
        return []

    return (
        db.query(Incidente)
        .filter(Incidente.id.in_(incidente_ids))
        .order_by(Incidente.creado_en.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# CU-12: Gestionar solicitudes — listar incidentes pendientes del taller
# ---------------------------------------------------------------------------

@router.get("/talleres/{taller_id}/solicitudes", response_model=list[IncidenteResponse])
def listar_solicitudes(
    taller_id: UUID,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin_taller),
):
    """
    CU-12 — Lista los incidentes asignados al taller donde accion_taller es NULL
    (aún no respondidos) o cuyo estado sea 'pendiente'.
    """
    taller = db.query(Taller).filter(
        Taller.id == taller_id, Taller.administrador_id == current_user.id
    ).first()
    if not taller:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Taller no encontrado")

    # Asignaciones pendientes de respuesta (accion_taller IS NULL)
    asignaciones_pendientes = (
        db.query(Asignacion)
        .filter(
            Asignacion.taller_id == taller_id,
            Asignacion.accion_taller == None,  # noqa: E711
        )
        .all()
    )
    incidente_ids = [a.incidente_id for a in asignaciones_pendientes]

    if not incidente_ids:
        return []

    return (
        db.query(Incidente)
        .filter(Incidente.id.in_(incidente_ids))
        .order_by(Incidente.creado_en.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# CU-12: Responder solicitud (aceptar / rechazar)
# ---------------------------------------------------------------------------

@router.patch("/asignaciones/{asignacion_id}/responder", response_model=AsignacionResponse)
def responder_asignacion(
    asignacion_id: UUID,
    body: ResponderAsignacionBody,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin_taller),
):
    """
    CU-12 — El taller acepta o rechaza la solicitud.
    Si rechaza, dispara CU-20 para reasignar al siguiente candidato.
    """
    if body.accion_taller not in ("aceptado", "rechazado"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="accion_taller debe ser 'aceptado' o 'rechazado'",
        )

    asignacion = _get_asignacion(asignacion_id, db)

    # Verificar que la asignación pertenece al taller del admin
    taller = _get_taller_del_admin(current_user, db)
    if asignacion.taller_id != taller.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin acceso a esta asignación")

    if asignacion.accion_taller is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La asignación ya fue respondida: {asignacion.accion_taller}",
        )

    asignacion.accion_taller = body.accion_taller
    asignacion.taller_respondio_en = datetime.now(timezone.utc)
    if body.eta_minutos:
        asignacion.eta_minutos = body.eta_minutos

    incidente: Incidente = asignacion.incidente

    if body.accion_taller == "aceptado":
        # Marcar taller como no disponible para nuevas asignaciones automáticas
        taller.disponible = False
        # Notificar al cliente
        notificacion_service.notif_taller_acepto(
            db,
            cliente_id=incidente.cliente_id,
            incidente_id=incidente.id,
            nombre_taller=taller.nombre,
            eta_minutos=body.eta_minutos,
        )
    else:
        # Rechazado → notificar y reasignar (CU-20)
        notificacion_service.notif_taller_rechazo(
            db,
            cliente_id=incidente.cliente_id,
            incidente_id=incidente.id,
            nombre_taller=taller.nombre,
        )
        try:
            asignacion_service.reasignar(asignacion, db)
        except HTTPException:
            pass  # Sin más candidatos — queda registrado el rechazo

    db.commit()
    db.refresh(asignacion)
    return asignacion


# ---------------------------------------------------------------------------
# CU-13: Asignar orden a técnico
# ---------------------------------------------------------------------------

@router.patch("/asignaciones/{asignacion_id}/asignar-tecnico", response_model=AsignacionResponse)
def asignar_tecnico(
    asignacion_id: UUID,
    body: AsignarTecnicoBody,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin_taller),
):
    """
    CU-13 — Asigna un técnico disponible del taller a la orden aceptada.
    Valida: técnico pertenece al taller, técnico disponible, sin orden activa.
    """
    asignacion = _get_asignacion(asignacion_id, db)
    taller = _get_taller_del_admin(current_user, db)

    if asignacion.taller_id != taller.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin acceso a esta asignación")

    if asignacion.accion_taller != "aceptado":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Solo se puede asignar técnico a solicitudes aceptadas",
        )

    tecnico = db.query(Tecnico).filter(
        Tecnico.id == body.tecnico_id,
        Tecnico.taller_id == taller.id,
    ).first()
    if not tecnico:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Técnico no encontrado o no pertenece a tu taller",
        )

    if not tecnico.disponible:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El técnico no está disponible",
        )

    # Regla de negocio: un técnico solo puede tener UNA orden activa
    orden_activa = (
        db.query(Asignacion)
        .join(Incidente, Asignacion.incidente_id == Incidente.id)
        .filter(
            Asignacion.tecnico_id == body.tecnico_id,
            Incidente.estado.in_(["pendiente", "en_proceso"]),
            Asignacion.completado_en == None,  # noqa: E711
        )
        .first()
    )
    if orden_activa:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El técnico ya tiene una orden activa asignada",
        )

    asignacion.tecnico_id = body.tecnico_id
    tecnico.disponible = False

    # Obtener el incidente antes de usarlo
    incidente: Incidente = asignacion.incidente

    # Calcular ETA automáticamente si el técnico tiene ubicación registrada
    if (tecnico.latitud_actual is not None and tecnico.longitud_actual is not None
            and incidente.latitud is not None and incidente.longitud is not None):
        import math
        lat1, lon1 = math.radians(float(tecnico.latitud_actual)), math.radians(float(tecnico.longitud_actual))
        lat2, lon2 = math.radians(float(incidente.latitud)),      math.radians(float(incidente.longitud))
        dlat, dlon = lat2 - lat1, lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        distancia_km = 6371 * 2 * math.asin(math.sqrt(a))
        # Velocidad promedio urbana: 30 km/h → 0.5 km/min. Mínimo 5 min.
        eta = max(5, math.ceil(distancia_km / 0.5))
        asignacion.eta_minutos = eta

    # Actualizar estado del incidente a 'en_proceso'
    incidente_service.registrar_cambio_estado(
        db, incidente, "en_proceso", current_user.id,
        notas=f"Técnico {tecnico.usuario.nombre_completo} asignado",
    )

    # CU-21: Notificar al cliente y al técnico
    notificacion_service.notif_tecnico_asignado(
        db,
        cliente_id=incidente.cliente_id,
        tecnico_usuario_id=tecnico.usuario_id,
        incidente_id=incidente.id,
        nombre_tecnico=tecnico.usuario.nombre_completo,
    )

    db.commit()
    db.refresh(asignacion)
    return asignacion


# ---------------------------------------------------------------------------
# Técnico en sitio — notifica al cliente que el técnico ya llegó
# ---------------------------------------------------------------------------

@router.post("/asignaciones/{asignacion_id}/tecnico-en-sitio")
def tecnico_en_sitio(
    asignacion_id: UUID,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_tecnico),
):
    """
    El técnico confirma que llegó a la ubicación del cliente.
    Envía una notificación al cliente sin cambiar el estado del incidente.
    """
    asignacion = _get_asignacion(asignacion_id, db)

    # Solo el técnico asignado puede confirmar llegada
    tecnico = db.query(Tecnico).filter(Tecnico.usuario_id == current_user.id).first()
    if not tecnico or asignacion.tecnico_id != tecnico.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el técnico asignado puede confirmar llegada.",
        )

    if asignacion.incidente.estado not in ("en_proceso",):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El incidente no está en proceso.",
        )

    notificacion_service.notif_tecnico_en_sitio(
        db,
        cliente_id=asignacion.incidente.cliente_id,
        incidente_id=asignacion.incidente_id,
        nombre_tecnico=tecnico.usuario.nombre_completo,
    )
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# CU-17: Marcar servicio como completado
# ---------------------------------------------------------------------------

@router.patch("/asignaciones/{asignacion_id}/completar", response_model=AsignacionResponse)
def completar_servicio(
    asignacion_id: UUID,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_tecnico),
):
    """
    CU-17 — El técnico marca la orden como completada.
    Cambia el incidente a 'atendido', libera al técnico y registra en HISTORIAL.
    """
    asignacion = _get_asignacion(asignacion_id, db)

    # Verificar que el técnico es el asignado a esta orden
    tecnico = (
        db.query(Tecnico)
        .filter(Tecnico.usuario_id == current_user.id)
        .first()
    )
    if not tecnico or asignacion.tecnico_id != tecnico.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el técnico asignado puede completar esta orden",
        )

    if asignacion.completado_en is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La orden ya fue marcada como completada",
        )

    asignacion.completado_en = datetime.now(timezone.utc)

    # Liberar técnico y taller
    tecnico.disponible = True
    if asignacion.taller:
        asignacion.taller.disponible = True

    # Actualizar estado del incidente
    incidente: Incidente = asignacion.incidente
    incidente_service.registrar_cambio_estado(
        db, incidente, "atendido", current_user.id,
        notas="Servicio completado por el técnico",
    )

    # CU-21: Notificar al cliente
    notificacion_service.notif_servicio_completado(
        db, cliente_id=incidente.cliente_id, incidente_id=incidente.id
    )

    db.commit()
    db.refresh(asignacion)
    return asignacion

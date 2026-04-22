from collections import defaultdict
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db, require_admin_taller
from app.models.asignacion import Asignacion
from app.models.incidente import Incidente
from app.models.servicio_taller import ServicioTaller
from app.models.taller import Taller
from app.models.tecnico import Tecnico
from app.models.usuario import Usuario
from app.schemas.servicio_taller import ServicioTallerCreate, ServicioTallerResponse
from app.schemas.taller import (
    AtencionesPorMes,
    AtencionesPorTipo,
    HistorialItemResponse,
    IngresosPorMes,
    MetricasTallerResponse,
    TallerCreate,
    TallerResponse,
    TallerUpdate,
    TecnicoEnHistorial,
)
from app.schemas.tecnico import TecnicoResponse
from app.services import asignacion_service

router = APIRouter(prefix="/talleres", tags=["Talleres"])


def sincronizar_disponible(taller: Taller, db: Session) -> None:
    """
    Recalcula taller.disponible según si existe alguna asignación activa
    (aceptada, no completada, incidente no cerrado). Persiste si cambia.
    Esto corrige cualquier desincronización producida por bugs anteriores
    o reinicios del servidor.
    """
    tiene_orden_activa = db.query(Asignacion).join(
        Incidente, Asignacion.incidente_id == Incidente.id
    ).filter(
        Asignacion.taller_id == taller.id,
        Asignacion.accion_taller == "aceptado",
        Asignacion.completado_en == None,           # noqa: E711
        Incidente.estado.in_(["pendiente", "en_proceso"]),
    ).first() is not None

    correcto = not tiene_orden_activa
    if taller.disponible != correcto:
        taller.disponible = correcto
        db.commit()


@router.get("/mine", response_model=TallerResponse)
def get_my_taller(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin_taller),
):
    """Devuelve el taller administrado por el usuario autenticado."""
    taller = db.query(Taller).filter(Taller.administrador_id == current_user.id).first()
    if not taller:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No tienes un taller registrado. Crea uno primero.",
        )
    sincronizar_disponible(taller, db)
    return taller


@router.post("", response_model=TallerResponse, status_code=status.HTTP_201_CREATED)
def create_taller(
    body: TallerCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin_taller),
):
    taller = Taller(administrador_id=current_user.id, **body.model_dump())
    db.add(taller)
    db.commit()
    db.refresh(taller)
    return taller


@router.get("/{taller_id}", response_model=TallerResponse)
def get_taller(
    taller_id: UUID,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    taller = db.query(Taller).filter(Taller.id == taller_id).first()
    if not taller:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Taller no encontrado")
    sincronizar_disponible(taller, db)
    return taller


@router.patch("/{taller_id}", response_model=TallerResponse)
def update_taller(
    taller_id: UUID,
    body: TallerUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin_taller),
):
    taller = db.query(Taller).filter(
        Taller.id == taller_id, Taller.administrador_id == current_user.id
    ).first()
    if not taller:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Taller no encontrado")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(taller, field, value)
    db.commit()
    db.refresh(taller)
    return taller


@router.post("/{taller_id}/servicios", response_model=ServicioTallerResponse, status_code=status.HTTP_201_CREATED)
def add_servicio(
    taller_id: UUID,
    body: ServicioTallerCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin_taller),
):
    taller = db.query(Taller).filter(
        Taller.id == taller_id, Taller.administrador_id == current_user.id
    ).first()
    if not taller:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Taller no encontrado")

    servicio = ServicioTaller(taller_id=taller_id, **body.model_dump())
    db.add(servicio)
    db.commit()
    db.refresh(servicio)

    # Al agregar un servicio, el taller ya puede atender emergencias:
    # intentar asignar incidentes pendientes que no tienen taller activo.
    asignacion_service.intentar_asignar_pendientes(db)
    db.commit()

    return servicio


@router.get("/{taller_id}/servicios", response_model=list[ServicioTallerResponse])
def list_servicios(
    taller_id: UUID,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    if not db.query(Taller).filter(Taller.id == taller_id).first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Taller no encontrado")
    return db.query(ServicioTaller).filter(ServicioTaller.taller_id == taller_id).all()


@router.get("/{taller_id}/historial", response_model=list[HistorialItemResponse])
def get_historial(
    taller_id: UUID,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin_taller),
):
    """
    CU-15 — Historial de atenciones completadas/canceladas del taller.
    Incluye: fecha, clasificacion_ia, prioridad, tecnico, duración y estado final.
    """
    taller = db.query(Taller).filter(
        Taller.id == taller_id, Taller.administrador_id == current_user.id
    ).first()
    if not taller:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Taller no encontrado")

    asignaciones = (
        db.query(Asignacion)
        .join(Incidente, Asignacion.incidente_id == Incidente.id)
        .filter(
            Asignacion.taller_id == taller_id,
            Asignacion.accion_taller == "aceptado",
            Incidente.estado.in_(["atendido", "cancelado"]),
        )
        .order_by(Asignacion.asignado_en.desc())
        .all()
    )

    resultado: list[HistorialItemResponse] = []
    for asig in asignaciones:
        inc: Incidente = asig.incidente
        duracion = None
        if asig.asignado_en and asig.completado_en:
            duracion = round(
                (asig.completado_en - asig.asignado_en).total_seconds() / 60, 1
            )
        tecnico_schema = None
        if asig.tecnico:
            tecnico_schema = TecnicoEnHistorial.from_tecnico(asig.tecnico)

        pago = inc.pago
        resultado.append(
            HistorialItemResponse(
                incidente_id=inc.id,
                fecha=asig.asignado_en,
                clasificacion_ia=inc.clasificacion_ia,
                prioridad=inc.prioridad,
                tecnico=tecnico_schema,
                duracion_minutos=duracion,
                estado_final=inc.estado,
                pago_monto_neto=float(pago.neto_taller) if pago else None,
                pago_estado=pago.estado if pago else None,
            )
        )
    return resultado


@router.get("/{taller_id}/metricas", response_model=MetricasTallerResponse)
def get_metricas(
    taller_id: UUID,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin_taller),
):
    """
    CU-15 — Métricas de rendimiento del taller:
    total_atenciones, tiempo_promedio_respuesta, tasa_aceptacion,
    atenciones_por_tipo y atenciones_por_mes (últimos 6 meses).
    """
    taller = db.query(Taller).filter(
        Taller.id == taller_id, Taller.administrador_id == current_user.id
    ).first()
    if not taller:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Taller no encontrado")

    # Todas las asignaciones del taller que tuvieron respuesta
    todas = (
        db.query(Asignacion)
        .filter(
            Asignacion.taller_id == taller_id,
            Asignacion.accion_taller.isnot(None),
        )
        .all()
    )

    aceptadas = [a for a in todas if a.accion_taller == "aceptado"]
    rechazadas = [a for a in todas if a.accion_taller == "rechazado"]
    completadas = [a for a in aceptadas if a.completado_en is not None]

    # total_atenciones = asignaciones completadas
    total_atenciones = len(completadas)

    # tiempo_promedio_respuesta: minutos entre asignado_en y taller_respondio_en
    tiempos = [
        (a.taller_respondio_en - a.asignado_en).total_seconds() / 60
        for a in todas
        if a.asignado_en and a.taller_respondio_en
    ]
    tiempo_promedio = round(sum(tiempos) / len(tiempos), 2) if tiempos else None

    # tasa_aceptacion: % aceptadas sobre el total con respuesta
    total_respondidas = len(aceptadas) + len(rechazadas)
    tasa_aceptacion = (
        round(len(aceptadas) / total_respondidas * 100, 2)
        if total_respondidas > 0
        else None
    )

    # atenciones_por_tipo: completadas agrupadas por clasificacion_ia
    conteo_tipo: dict[str, int] = defaultdict(int)
    for asig in completadas:
        clave = asig.incidente.clasificacion_ia or "sin_clasificar"
        conteo_tipo[clave] += 1
    atenciones_por_tipo = [
        AtencionesPorTipo(clasificacion=k, total=v)
        for k, v in sorted(conteo_tipo.items())
    ]

    # atenciones_por_mes: completadas en los últimos 6 meses
    hace_6_meses = datetime.now(timezone.utc) - timedelta(days=183)
    conteo_mes: dict[tuple[int, int], int] = defaultdict(int)
    for asig in completadas:
        fecha = asig.asignado_en
        if fecha and fecha.replace(tzinfo=timezone.utc) >= hace_6_meses:
            conteo_mes[(fecha.year, fecha.month)] += 1
    atenciones_por_mes = [
        AtencionesPorMes(anio=anio, mes=mes, total=total)
        for (anio, mes), total in sorted(conteo_mes.items())
    ]

    # ── Ingresos ──────────────────────────────────────────────────────────
    pagados = [a for a in completadas if a.incidente.pago and a.incidente.pago.estado == "pagado"]
    ingresos_neto_total = round(sum(float(a.incidente.pago.neto_taller) for a in pagados), 2)
    servicios_cobrados = len(pagados)
    servicios_pendientes_cobro = len([a for a in completadas if not a.incidente.pago])

    conteo_ingresos: dict[tuple[int, int], float] = defaultdict(float)
    for asig in pagados:
        fecha = asig.asignado_en
        if fecha:
            conteo_ingresos[(fecha.year, fecha.month)] += float(asig.incidente.pago.neto_taller)
    ingresos_por_mes = [
        IngresosPorMes(anio=anio, mes=mes, total=round(total, 2))
        for (anio, mes), total in sorted(conteo_ingresos.items())
    ]

    return MetricasTallerResponse(
        total_atenciones=total_atenciones,
        tiempo_promedio_respuesta=tiempo_promedio,
        tasa_aceptacion=tasa_aceptacion,
        atenciones_por_tipo=atenciones_por_tipo,
        atenciones_por_mes=atenciones_por_mes,
        ingresos_neto_total=ingresos_neto_total,
        servicios_cobrados=servicios_cobrados,
        servicios_pendientes_cobro=servicios_pendientes_cobro,
        ingresos_por_mes=ingresos_por_mes,
    )


@router.get("/{taller_id}/tecnicos", response_model=list[TecnicoResponse])
def list_tecnicos(
    taller_id: UUID,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    if not db.query(Taller).filter(Taller.id == taller_id).first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Taller no encontrado")
    return db.query(Tecnico).filter(Tecnico.taller_id == taller_id).all()

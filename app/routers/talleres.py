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
from app.schemas.incidente import IncidenteResponse
from app.schemas.servicio_taller import ServicioTallerCreate, ServicioTallerResponse
from app.schemas.taller import TallerCreate, TallerResponse, TallerUpdate
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


@router.get("/{taller_id}/historial", response_model=list[IncidenteResponse])
def get_historial(
    taller_id: UUID,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin_taller),
):
    """
    CU-15 — Historial de atenciones del taller: incidentes atendidos o cancelados,
    ordenados del más reciente al más antiguo.
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
        .all()
    )
    incidente_ids = [a.incidente_id for a in asignaciones]
    if not incidente_ids:
        return []

    return (
        db.query(Incidente)
        .filter(Incidente.id.in_(incidente_ids))
        .order_by(Incidente.actualizado_en.desc())
        .all()
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

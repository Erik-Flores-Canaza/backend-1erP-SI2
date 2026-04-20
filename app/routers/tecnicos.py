from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db, require_admin_taller, require_tecnico
from app.models.asignacion import Asignacion
from app.models.incidente import Incidente
from app.models.taller import Taller
from app.models.tecnico import Tecnico
from app.models.turno_tecnico import TurnoTecnico
from app.models.usuario import Usuario
from app.schemas.asignacion import AsignacionResponse, OrdenActivaTecnicoResponse
from app.schemas.tecnico import TecnicoCreate, TecnicoResponse, TecnicoUpdate
from app.schemas.turno_tecnico import TurnoCreate, TurnoResponse
from app.services.tecnico_service import crear_tecnico


class UbicacionUpdate(BaseModel):
    latitud: float
    longitud: float

router = APIRouter(prefix="/tecnicos", tags=["Técnicos"])


# ---------------------------------------------------------------------------
# GET /tecnicos/me — perfil del técnico autenticado + asignación activa
# IMPORTANTE: debe declararse ANTES que /{tecnico_id} para que FastAPI
# no interprete "me" como un UUID.
# ---------------------------------------------------------------------------

@router.get("/me", response_model=TecnicoResponse)
def get_my_perfil(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_tecnico),
):
    """Devuelve el perfil del técnico autenticado."""
    tecnico = db.query(Tecnico).filter(Tecnico.usuario_id == current_user.id).first()
    if not tecnico:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No tienes un perfil de técnico registrado.",
        )
    return tecnico


@router.get("/me/orden-activa", response_model=OrdenActivaTecnicoResponse | None)
def get_orden_activa(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_tecnico),
):
    """
    Devuelve la asignación activa del técnico autenticado
    (accion_taller='aceptado', completado_en IS NULL, incidente no atendido/cancelado).
    Retorna null si no hay orden activa.
    """
    tecnico = db.query(Tecnico).filter(Tecnico.usuario_id == current_user.id).first()
    if not tecnico:
        return None

    asignacion = (
        db.query(Asignacion)
        .join(Incidente, Asignacion.incidente_id == Incidente.id)
        .filter(
            Asignacion.tecnico_id == tecnico.id,
            Asignacion.accion_taller == "aceptado",
            Asignacion.completado_en == None,           # noqa: E711
            Incidente.estado.in_(["pendiente", "en_proceso"]),
        )
        .first()
    )
    return asignacion


def _get_tecnico_del_admin(tecnico_id: UUID, current_user: Usuario, db: Session) -> Tecnico:
    tecnico = (
        db.query(Tecnico)
        .join(Taller, Tecnico.taller_id == Taller.id)
        .filter(Tecnico.id == tecnico_id, Taller.administrador_id == current_user.id)
        .first()
    )
    if not tecnico:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Técnico no encontrado")
    return tecnico


@router.post("", response_model=TecnicoResponse, status_code=status.HTTP_201_CREATED)
def create_tecnico(
    body: TecnicoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin_taller),
):
    return crear_tecnico(db, body, current_user.id)


@router.patch("/{tecnico_id}", response_model=TecnicoResponse)
def update_tecnico(
    tecnico_id: UUID,
    body: TecnicoUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin_taller),
):
    tecnico = _get_tecnico_del_admin(tecnico_id, current_user, db)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(tecnico, field, value)
    db.commit()
    db.refresh(tecnico)
    return tecnico


@router.delete("/{tecnico_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tecnico(
    tecnico_id: UUID,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin_taller),
):
    tecnico = _get_tecnico_del_admin(tecnico_id, current_user, db)
    db.delete(tecnico)
    db.commit()


@router.post("/{tecnico_id}/turnos", response_model=TurnoResponse, status_code=status.HTTP_201_CREATED)
def create_turno(
    tecnico_id: UUID,
    body: TurnoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin_taller),
):
    tecnico = _get_tecnico_del_admin(tecnico_id, current_user, db)
    turno = TurnoTecnico(tecnico_id=tecnico.id, **body.model_dump())
    db.add(turno)
    db.commit()
    db.refresh(turno)
    return turno


@router.get("/{tecnico_id}/turnos", response_model=list[TurnoResponse])
def list_turnos(
    tecnico_id: UUID,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    if not db.query(Tecnico).filter(Tecnico.id == tecnico_id).first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Técnico no encontrado")
    return db.query(TurnoTecnico).filter(TurnoTecnico.tecnico_id == tecnico_id).all()


# ---------------------------------------------------------------------------
# Admin solicita al técnico que actualice su ubicación
# ---------------------------------------------------------------------------

@router.post("/{tecnico_id}/solicitar-ubicacion", status_code=status.HTTP_200_OK)
def solicitar_ubicacion(
    tecnico_id: UUID,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin_taller),
):
    """
    El admin le envía una notificación al técnico pidiéndole que
    abra la app y actualice su ubicación GPS.
    """
    tecnico = _get_tecnico_del_admin(tecnico_id, current_user, db)
    from app.services import notificacion_service
    from app.models.taller import Taller as TallerModel
    taller = db.query(TallerModel).filter(TallerModel.administrador_id == current_user.id).first()
    nombre_taller = taller.nombre if taller else "El taller"
    notificacion_service._crear(
        db,
        usuario_id=tecnico.usuario_id,
        titulo="Actualiza tu ubicación",
        cuerpo=f"{nombre_taller} necesita conocer tu ubicación. Abre la app y actualízala.",
    )
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# CU-16: Actualizar ubicación del técnico en tiempo real
# ---------------------------------------------------------------------------

@router.patch("/{tecnico_id}/ubicacion", response_model=TecnicoResponse)
def actualizar_ubicacion(
    tecnico_id: UUID,
    body: UbicacionUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_tecnico),
):
    """
    CU-16 — El técnico actualiza su ubicación GPS actual.
    Solo el técnico autenticado puede actualizar su propia ubicación.
    """
    tecnico = db.query(Tecnico).filter(Tecnico.id == tecnico_id).first()
    if not tecnico:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Técnico no encontrado")

    # El técnico solo puede actualizar su propia ubicación
    if tecnico.usuario_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo puedes actualizar tu propia ubicación",
        )

    tecnico.latitud_actual = body.latitud
    tecnico.longitud_actual = body.longitud
    tecnico.ubicacion_actualizada_en = datetime.now(timezone.utc)
    db.commit()
    db.refresh(tecnico)
    return tecnico

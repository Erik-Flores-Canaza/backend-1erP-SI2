from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db, require_admin_taller
from app.models.taller import Taller
from app.models.tecnico import Tecnico
from app.models.turno_tecnico import TurnoTecnico
from app.models.usuario import Usuario
from app.schemas.tecnico import TecnicoCreate, TecnicoResponse, TecnicoUpdate
from app.schemas.turno_tecnico import TurnoCreate, TurnoResponse
from app.services.tecnico_service import crear_tecnico

router = APIRouter(prefix="/tecnicos", tags=["Técnicos"])


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

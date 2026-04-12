from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_db, require_cliente
from app.models.usuario import Usuario
from app.models.vehiculo import Vehiculo
from app.schemas.vehiculo import VehiculoCreate, VehiculoResponse, VehiculoUpdate

router = APIRouter(prefix="/vehiculos", tags=["Vehículos"])


@router.post("", response_model=VehiculoResponse, status_code=status.HTTP_201_CREATED)
def create_vehiculo(
    body: VehiculoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_cliente),
):
    if db.query(Vehiculo).filter(Vehiculo.placa == body.placa).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La placa ya está registrada",
        )
    vehiculo = Vehiculo(propietario_id=current_user.id, **body.model_dump())
    db.add(vehiculo)
    db.commit()
    db.refresh(vehiculo)
    return vehiculo


@router.get("", response_model=list[VehiculoResponse])
def list_vehiculos(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_cliente),
):
    return db.query(Vehiculo).filter(Vehiculo.propietario_id == current_user.id).all()


@router.patch("/{vehiculo_id}", response_model=VehiculoResponse)
def update_vehiculo(
    vehiculo_id: UUID,
    body: VehiculoUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_cliente),
):
    vehiculo = db.query(Vehiculo).filter(
        Vehiculo.id == vehiculo_id,
        Vehiculo.propietario_id == current_user.id,
    ).first()
    if not vehiculo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehículo no encontrado")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(vehiculo, field, value)
    db.commit()
    db.refresh(vehiculo)
    return vehiculo


@router.delete("/{vehiculo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehiculo(
    vehiculo_id: UUID,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_cliente),
):
    vehiculo = db.query(Vehiculo).filter(
        Vehiculo.id == vehiculo_id,
        Vehiculo.propietario_id == current_user.id,
    ).first()
    if not vehiculo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehículo no encontrado")

    db.delete(vehiculo)
    db.commit()

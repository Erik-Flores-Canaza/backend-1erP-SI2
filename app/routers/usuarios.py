from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.dependencies import get_current_user, get_db
from app.models.usuario import Usuario
from app.schemas.usuario import ChangePasswordRequest, UsuarioResponse, UsuarioUpdate

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])


@router.get("/me", response_model=UsuarioResponse)
def get_me(current_user: Usuario = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UsuarioResponse)
def update_me(
    body: UsuarioUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(current_user, field, value)
    db.commit()
    db.refresh(current_user)
    return current_user


@router.patch("/me/contrasena", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    if not verify_password(body.contrasena_actual, current_user.hash_contrasena):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña actual es incorrecta",
        )
    current_user.hash_contrasena = hash_password(body.nueva_contrasena)
    db.commit()

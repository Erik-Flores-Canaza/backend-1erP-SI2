from typing import Generator
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import decode_token
from app.models.usuario import Usuario

bearer_scheme = HTTPBearer()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Usuario:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar el token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise credentials_exception
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(Usuario).filter(
        Usuario.id == UUID(user_id), Usuario.activo == True
    ).first()
    if user is None:
        raise credentials_exception
    return user


def _require_rol(nombre_rol: str, current_user: Usuario) -> Usuario:
    """Valida que el usuario autenticado tenga el rol esperado."""
    if not current_user.rol or current_user.rol.nombre != nombre_rol:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Se requiere rol {nombre_rol}",
        )
    return current_user


def require_cliente(current_user: Usuario = Depends(get_current_user)) -> Usuario:
    return _require_rol("cliente", current_user)


def require_admin_taller(current_user: Usuario = Depends(get_current_user)) -> Usuario:
    return _require_rol("admin_taller", current_user)


def require_tecnico(current_user: Usuario = Depends(get_current_user)) -> Usuario:
    return _require_rol("tecnico", current_user)

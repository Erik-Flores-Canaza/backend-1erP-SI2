from sqlalchemy.orm import Session

from app.core.security import create_access_token, create_refresh_token, verify_password
from app.models.usuario import Usuario


def authenticate_user(db: Session, correo: str, contrasena: str) -> Usuario | None:
    user = db.query(Usuario).filter(Usuario.correo == correo, Usuario.activo == True).first()
    if not user or not verify_password(contrasena, user.hash_contrasena):
        return None
    return user


def build_tokens(user: Usuario) -> dict:
    payload = {"sub": str(user.id)}
    return {
        "access_token": create_access_token(payload),
        "refresh_token": create_refresh_token(payload),
        "token_type": "bearer",
    }

from sqlalchemy.orm import Session, joinedload

from app.core.security import create_access_token, create_refresh_token, verify_password
from app.models.usuario import Usuario


def authenticate_user(db: Session, correo: str, contrasena: str) -> Usuario | None:
    user = (
        db.query(Usuario)
        .options(joinedload(Usuario.rol))
        .filter(Usuario.correo == correo, Usuario.activo == True)
        .first()
    )
    if not user or not verify_password(contrasena, user.hash_contrasena):
        return None
    return user


def build_tokens(user: Usuario) -> dict:
    """Construye access + refresh tokens incluyendo tenant_id y rol del usuario.

    `tenant_id` puede ser None (clientes globales y superadmin_plataforma).
    `rol` es el nombre del rol — la dependencia lo lee para autorizar sin tocar BD.
    """
    payload = {
        "sub": str(user.id),
        "tenant_id": str(user.tenant_id) if user.tenant_id else None,
        "rol": user.rol.nombre if user.rol else None,
    }
    return {
        "access_token": create_access_token(payload),
        "refresh_token": create_refresh_token(payload),
        "token_type": "bearer",
    }

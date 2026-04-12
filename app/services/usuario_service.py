from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.rol import Rol
from app.models.usuario import Usuario
from app.schemas.usuario import UsuarioCreate


def registrar_cliente(db: Session, body: UsuarioCreate) -> Usuario:
    if db.query(Usuario).filter(Usuario.correo == body.correo).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El correo ya está registrado",
        )

    rol = db.query(Rol).filter(Rol.nombre == "cliente").first()
    if not rol:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Rol 'cliente' no encontrado. Reinicia la app para ejecutar el seed.",
        )

    user = Usuario(
        rol_id=rol.id,
        nombre_completo=body.nombre_completo,
        correo=body.correo,
        hash_contrasena=hash_password(body.contrasena),
        telefono=body.telefono,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

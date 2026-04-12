from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.rol import Rol
from app.models.taller import Taller
from app.models.tecnico import Tecnico
from app.models.usuario import Usuario
from app.schemas.tecnico import TecnicoCreate


def crear_tecnico(db: Session, body: TecnicoCreate, admin_id) -> Tecnico:
    taller = db.query(Taller).filter(
        Taller.id == body.taller_id, Taller.administrador_id == admin_id
    ).first()
    if not taller:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Taller no encontrado")

    if db.query(Usuario).filter(Usuario.correo == body.correo).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El correo ya está registrado")

    rol = db.query(Rol).filter(Rol.nombre == "tecnico").first()
    if not rol:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Rol 'tecnico' no encontrado",
        )

    usuario = Usuario(
        rol_id=rol.id,
        nombre_completo=body.nombre_completo,
        correo=body.correo,
        hash_contrasena=hash_password(body.contrasena),
        telefono=body.telefono,
    )
    db.add(usuario)
    db.flush()  # obtiene el UUID antes del commit

    tecnico = Tecnico(usuario_id=usuario.id, taller_id=body.taller_id)
    db.add(tecnico)
    db.commit()
    db.refresh(tecnico)
    return tecnico

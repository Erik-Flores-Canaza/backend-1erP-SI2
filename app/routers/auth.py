from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.dependencies import get_db
from app.models.usuario import Usuario
from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse
from app.schemas.usuario import UsuarioCreate, UsuarioResponse
from app.services.auth_service import authenticate_user, build_tokens
from app.core.config import settings
from app.models.rol import Rol
from app.services.usuario_service import registrar_cliente

router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, body.correo, body.contrasena)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos",
        )
    return build_tokens(user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError("tipo de token incorrecto")
        user_id: str = payload["sub"]
    except (JWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido o expirado",
        )

    user = db.query(Usuario).filter(
        Usuario.id == UUID(user_id), Usuario.activo == True
    ).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado")
    return build_tokens(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout():
    # JWT es stateless: el cliente descarta los tokens localmente.
    return None


@router.post("/registro", response_model=UsuarioResponse, status_code=status.HTTP_201_CREATED)
def registro(body: UsuarioCreate, db: Session = Depends(get_db)):
    return registrar_cliente(db, body)


# ── SOLO PARA PRUEBAS — eliminar antes de producción ─────────────────────────
@router.post(
    "/dev/crear-admin",
    response_model=UsuarioResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Dev / Testing"],
    summary="[DEV] Crear admin_taller (solo pruebas)",
)
def dev_crear_admin(body: UsuarioCreate, db: Session = Depends(get_db)):
    """
    Crea un usuario con rol **admin_taller** directamente.
    **⚠ Eliminar este endpoint antes de ir a producción.**
    """
    if db.query(Usuario).filter(Usuario.correo == body.correo).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El correo ya está registrado",
        )
    rol = db.query(Rol).filter(Rol.nombre == "admin_taller").first()
    if not rol:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Rol 'admin_taller' no encontrado. Reinicia la app para ejecutar el seed.",
        )
    from app.core.security import hash_password
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

"""
Servicio de administración global (superadmin).

Responsabilidades:
  - Aprobar solicitud → crear Usuario (admin_taller) + Taller + enviar correo
  - Rechazar solicitud → actualizar estado + notificar por correo
  - Generación de contraseña temporal segura
"""

import secrets
import string
from app.core.timezone import now_bo
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.rol import Rol
from app.models.solicitud_registro_taller import SolicitudRegistroTaller
from app.models.taller import Taller
from app.models.usuario import Usuario
from app.services import email_service


# ── Utilidades ────────────────────────────────────────────────────────────────

def _generar_contrasena_temporal(longitud: int = 12) -> str:
    """Genera una contraseña aleatoria con letras, dígitos y símbolos básicos."""
    alfabeto = string.ascii_letters + string.digits + "!@#$%&*"
    # Garantizar al menos un carácter de cada categoría
    contrasena = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%&*"),
    ]
    contrasena += [secrets.choice(alfabeto) for _ in range(longitud - 4)]
    secrets.SystemRandom().shuffle(contrasena)
    return "".join(contrasena)


# ── Lógica de aprobación / rechazo ───────────────────────────────────────────

def aprobar_solicitud(
    db: Session,
    solicitud: SolicitudRegistroTaller,
    superadmin_id: UUID,
) -> tuple[Usuario, Taller, str]:
    """
    Aprueba una solicitud de registro de taller.

    Acciones:
      1. Valida que la solicitud esté pendiente.
      2. Verifica que el correo no esté ya registrado.
      3. Crea el Usuario con rol admin_taller.
      4. Crea el Taller con estado_aprobacion = 'aprobado'.
      5. Marca la solicitud como aprobada.
      6. Envía correo con credenciales (si Gmail OAuth configurado).

    Returns:
        (usuario_nuevo, taller_nuevo, contrasena_temporal)
    """
    if solicitud.estado != "pendiente":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La solicitud ya fue procesada (estado: {solicitud.estado})",
        )

    # Verificar correo único
    if db.query(Usuario).filter(Usuario.correo == solicitud.solicitante_correo).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El correo del solicitante ya tiene una cuenta registrada",
        )

    # Obtener rol admin_taller
    rol = db.query(Rol).filter(Rol.nombre == "admin_taller").first()
    if not rol:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Rol 'admin_taller' no encontrado. Reinicia la app para ejecutar el seed.",
        )

    # Generar contraseña temporal
    contrasena_temporal = _generar_contrasena_temporal()

    # Crear usuario
    nuevo_usuario = Usuario(
        rol_id=rol.id,
        nombre_completo=solicitud.solicitante_nombre,
        correo=solicitud.solicitante_correo,
        hash_contrasena=hash_password(contrasena_temporal),
        telefono=solicitud.solicitante_telefono,
        activo=True,
    )
    db.add(nuevo_usuario)
    db.flush()  # obtener nuevo_usuario.id sin commit

    # Crear taller
    nuevo_taller = Taller(
        administrador_id=nuevo_usuario.id,
        nombre=solicitud.nombre_taller,
        direccion=solicitud.direccion,
        latitud=float(solicitud.latitud) if solicitud.latitud is not None else None,
        longitud=float(solicitud.longitud) if solicitud.longitud is not None else None,
        activo=True,
        disponible=True,
        estado_aprobacion="aprobado",
    )
    db.add(nuevo_taller)

    # Actualizar solicitud
    solicitud.estado = "aprobado"
    solicitud.revisado_por = superadmin_id
    solicitud.revisado_en = now_bo()

    db.commit()
    db.refresh(nuevo_usuario)
    db.refresh(nuevo_taller)

    # Enviar correo (no bloquea si falla)
    email_service.enviar_credenciales_admin_taller(
        destinatario=nuevo_usuario.correo,
        nombre=nuevo_usuario.nombre_completo,
        nombre_taller=nuevo_taller.nombre,
        contrasena_temporal=contrasena_temporal,
    )

    return nuevo_usuario, nuevo_taller, contrasena_temporal


def rechazar_solicitud(
    db: Session,
    solicitud: SolicitudRegistroTaller,
    superadmin_id: UUID,
    motivo: str,
) -> SolicitudRegistroTaller:
    """
    Rechaza una solicitud de registro de taller.

    Acciones:
      1. Valida que la solicitud esté pendiente.
      2. Actualiza estado a 'rechazado' con motivo.
      3. Envía correo de notificación (si Gmail OAuth configurado).
    """
    if solicitud.estado != "pendiente":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La solicitud ya fue procesada (estado: {solicitud.estado})",
        )

    solicitud.estado = "rechazado"
    solicitud.motivo_rechazo = motivo
    solicitud.revisado_por = superadmin_id
    solicitud.revisado_en = now_bo()

    db.commit()
    db.refresh(solicitud)

    # Enviar correo de rechazo (no bloquea si falla)
    email_service.enviar_rechazo_solicitud(
        destinatario=solicitud.solicitante_correo,
        nombre=solicitud.solicitante_nombre,
        nombre_taller=solicitud.nombre_taller,
        motivo=motivo,
    )

    return solicitud

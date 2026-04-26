"""
Schemas Pydantic para SOLICITUDES_REGISTRO_TALLER.

CU-22: POST /solicitudes-taller   (público, sin JWT)
CU-23: GET/PATCH /admin/solicitudes-taller/*   (superadmin)
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


# ── Request ───────────────────────────────────────────────────────────────────

class SolicitudRegistroCreate(BaseModel):
    """Body de CU-22: cualquier persona puede enviar este formulario."""
    solicitante_nombre: str
    solicitante_correo: EmailStr
    solicitante_telefono: str | None = None
    nombre_taller: str
    direccion: str | None = None
    latitud: float | None = None
    longitud: float | None = None
    descripcion: str | None = None


class RechazarSolicitudRequest(BaseModel):
    """Body de PATCH /admin/solicitudes-taller/{id}/rechazar."""
    motivo_rechazo: str


# ── Response ──────────────────────────────────────────────────────────────────

class SolicitudRegistroResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    solicitante_nombre: str
    solicitante_correo: str
    solicitante_telefono: str | None
    nombre_taller: str
    direccion: str | None
    latitud: float | None
    longitud: float | None
    descripcion: str | None
    estado: str
    motivo_rechazo: str | None
    revisado_por: UUID | None
    revisado_en: datetime | None
    creado_en: datetime


# ── Response de aprobación (incluye contraseña temporal) ─────────────────────

class AprobacionResponse(BaseModel):
    """
    Respuesta de PATCH /admin/solicitudes-taller/{id}/aprobar.
    Devuelve la contraseña temporal en el body para que el superadmin
    la registre o la reenvíe si el correo no llegó.
    """
    mensaje: str
    solicitud_id: UUID
    usuario_id: UUID
    taller_id: UUID
    correo: str
    contrasena_temporal: str
    correo_enviado: bool

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SolicitudTenant(Base):
    """Solicitud pública para crear un nuevo tenant en la plataforma. CU-29."""

    __tablename__ = "solicitudes_tenant"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)

    # Datos del solicitante (aún no es usuario en el sistema)
    solicitante_nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    solicitante_correo: Mapped[str] = mapped_column(String(150), nullable=False)
    solicitante_telefono: Mapped[str | None] = mapped_column(String(20))

    # Datos de la red propuesta
    nombre_red: Mapped[str] = mapped_column(String(150), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)

    # Estado: 'pendiente' / 'aprobado' / 'rechazado'
    estado: Mapped[str] = mapped_column(String(20), default="pendiente", nullable=False)
    motivo_rechazo: Mapped[str | None] = mapped_column(Text)

    revisado_por: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("usuarios.id"))
    revisado_en: Mapped[datetime | None] = mapped_column()
    creado_en: Mapped[datetime] = mapped_column(default=func.now())

    revisor: Mapped["Usuario | None"] = relationship("Usuario", foreign_keys=[revisado_por])

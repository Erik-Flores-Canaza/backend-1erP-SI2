from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DECIMAL, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SolicitudRegistroTaller(Base):
    __tablename__ = "solicitudes_registro_taller"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)

    # Datos del solicitante (aún no es usuario en el sistema)
    solicitante_nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    solicitante_correo: Mapped[str] = mapped_column(String(150), nullable=False)
    solicitante_telefono: Mapped[str | None] = mapped_column(String(20))

    # Datos del taller propuesto
    nombre_taller: Mapped[str] = mapped_column(String(150), nullable=False)
    direccion: Mapped[str | None] = mapped_column(String(255))
    latitud: Mapped[float | None] = mapped_column(DECIMAL(10, 7))
    longitud: Mapped[float | None] = mapped_column(DECIMAL(10, 7))
    descripcion: Mapped[str | None] = mapped_column(Text)

    # Estado: 'pendiente' / 'aprobado' / 'rechazado'
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="pendiente")
    motivo_rechazo: Mapped[str | None] = mapped_column(Text)

    # Quién la revisó y cuándo (null hasta revisión)
    revisado_por: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("usuarios.id"))
    revisado_en: Mapped[datetime | None] = mapped_column()

    creado_en: Mapped[datetime] = mapped_column(default=func.now())

    # Relación con el superadmin que revisó
    revisor: Mapped["Usuario | None"] = relationship("Usuario", foreign_keys=[revisado_por])

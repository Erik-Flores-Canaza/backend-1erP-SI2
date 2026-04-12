from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Notificacion(Base):
    __tablename__ = "notificaciones"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    usuario_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    incidente_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("incidentes.id"))
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    titulo: Mapped[str] = mapped_column(String(150), nullable=False)
    cuerpo: Mapped[str | None] = mapped_column(Text)
    leida: Mapped[bool] = mapped_column(Boolean, default=False)
    leida_en: Mapped[datetime | None] = mapped_column()
    enviada_en: Mapped[datetime] = mapped_column(default=func.now())

    usuario: Mapped["Usuario"] = relationship("Usuario", back_populates="notificaciones")
    incidente: Mapped["Incidente | None"] = relationship("Incidente", back_populates="notificaciones")

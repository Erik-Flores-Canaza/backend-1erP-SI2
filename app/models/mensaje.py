from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Mensaje(Base):
    __tablename__ = "mensajes"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    incidente_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("incidentes.id"), nullable=False)
    remitente_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    rol_remitente: Mapped[str] = mapped_column(String(20), nullable=False)
    contenido: Mapped[str] = mapped_column(Text, nullable=False)
    leido: Mapped[bool] = mapped_column(Boolean, default=False)
    creado_en: Mapped[datetime] = mapped_column(default=func.now())

    incidente: Mapped["Incidente"] = relationship("Incidente", back_populates="mensajes")
    remitente: Mapped["Usuario"] = relationship("Usuario", back_populates="mensajes_enviados")

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class HistorialServicio(Base):
    __tablename__ = "historial_servicio"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    incidente_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("incidentes.id"), nullable=False)
    cambiado_por: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    estado_anterior: Mapped[str | None] = mapped_column(String(20))
    estado_nuevo: Mapped[str] = mapped_column(String(20), nullable=False)
    notas: Mapped[str | None] = mapped_column(Text)
    cambiado_en: Mapped[datetime] = mapped_column(default=func.now())

    incidente: Mapped["Incidente"] = relationship("Incidente", back_populates="historial")
    cambiado_por_usuario: Mapped["Usuario"] = relationship("Usuario", back_populates="historial_cambios")

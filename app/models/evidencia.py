from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Evidencia(Base):
    __tablename__ = "evidencias"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    incidente_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("incidentes.id"), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    url_archivo: Mapped[str | None] = mapped_column(String(500))
    transcripcion: Mapped[str | None] = mapped_column(Text)
    analisis_ia: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(default=func.now())

    incidente: Mapped["Incidente"] = relationship("Incidente", back_populates="evidencias")

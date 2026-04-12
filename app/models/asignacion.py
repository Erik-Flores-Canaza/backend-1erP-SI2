from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Asignacion(Base):
    __tablename__ = "asignaciones"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    incidente_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("incidentes.id"), nullable=False)
    taller_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("talleres.id"), nullable=False)
    tecnico_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("tecnicos.id"))
    accion_taller: Mapped[str | None] = mapped_column(String(20))
    taller_respondio_en: Mapped[datetime | None] = mapped_column()
    eta_minutos: Mapped[int | None] = mapped_column(Integer)
    asignado_en: Mapped[datetime] = mapped_column(default=func.now())
    completado_en: Mapped[datetime | None] = mapped_column()

    incidente: Mapped["Incidente"] = relationship("Incidente", back_populates="asignaciones")
    taller: Mapped["Taller"] = relationship("Taller", back_populates="asignaciones")
    tecnico: Mapped["Tecnico | None"] = relationship("Tecnico", back_populates="asignaciones")

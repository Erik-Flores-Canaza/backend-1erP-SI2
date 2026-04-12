from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import DECIMAL, Date, Float, ForeignKey, Integer, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MetricaTaller(Base):
    __tablename__ = "metricas_taller"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    taller_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("talleres.id"), nullable=False)
    fecha_metrica: Mapped[date] = mapped_column(Date, nullable=False)
    solicitudes_totales: Mapped[int] = mapped_column(Integer, default=0)
    solicitudes_aceptadas: Mapped[int] = mapped_column(Integer, default=0)
    solicitudes_completadas: Mapped[int] = mapped_column(Integer, default=0)
    tiempo_respuesta_prom_min: Mapped[float | None] = mapped_column(Float)
    ingresos_totales: Mapped[float | None] = mapped_column(DECIMAL(10, 2))

    taller: Mapped["Taller"] = relationship("Taller", back_populates="metricas")

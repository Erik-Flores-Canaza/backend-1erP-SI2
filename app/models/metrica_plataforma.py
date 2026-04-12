from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import DECIMAL, Date, Float, Integer, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MetricaPlataforma(Base):
    __tablename__ = "metricas_plataforma"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    fecha_metrica: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    incidentes_totales: Mapped[int] = mapped_column(Integer, default=0)
    incidentes_resueltos: Mapped[int] = mapped_column(Integer, default=0)
    tiempo_resolucion_prom_min: Mapped[float | None] = mapped_column(Float)
    ingresos_totales: Mapped[float | None] = mapped_column(DECIMAL(10, 2))
    comisiones_totales: Mapped[float | None] = mapped_column(DECIMAL(10, 2))
    talleres_activos: Mapped[int] = mapped_column(Integer, default=0)
    usuarios_activos: Mapped[int] = mapped_column(Integer, default=0)

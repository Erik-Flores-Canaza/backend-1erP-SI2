from datetime import date, time
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Date, ForeignKey, Time, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TurnoTecnico(Base):
    __tablename__ = "turnos_tecnico"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tecnico_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tecnicos.id"), nullable=False)
    fecha_turno: Mapped[date] = mapped_column(Date, nullable=False)
    hora_inicio: Mapped[time] = mapped_column(Time, nullable=False)
    hora_fin: Mapped[time] = mapped_column(Time, nullable=False)
    en_servicio: Mapped[bool] = mapped_column(Boolean, default=False)

    tecnico: Mapped["Tecnico"] = relationship("Tecnico", back_populates="turnos")

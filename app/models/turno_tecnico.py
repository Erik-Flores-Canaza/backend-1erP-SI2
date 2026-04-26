from datetime import time
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, SmallInteger, Time, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TurnoTecnico(Base):
    __tablename__ = "turnos_tecnico"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tecnico_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tecnicos.id"), nullable=False)

    # 0 = Lunes, 1 = Martes, … 6 = Domingo  (isoweekday()-1)
    dia_semana: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    hora_inicio: Mapped[time] = mapped_column(Time, nullable=False)
    hora_fin: Mapped[time] = mapped_column(Time, nullable=False)

    tecnico: Mapped["Tecnico"] = relationship("Tecnico", back_populates="turnos")

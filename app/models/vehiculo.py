from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Vehiculo(Base):
    __tablename__ = "vehiculos"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    propietario_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    placa: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    marca: Mapped[str] = mapped_column(String(60), nullable=False)
    modelo: Mapped[str] = mapped_column(String(60), nullable=False)
    anio: Mapped[int | None] = mapped_column(Integer)
    color: Mapped[str | None] = mapped_column(String(40))
    creado_en: Mapped[datetime] = mapped_column(default=func.now())

    propietario: Mapped["Usuario"] = relationship("Usuario", back_populates="vehiculos")
    incidentes: Mapped[list["Incidente"]] = relationship("Incidente", back_populates="vehiculo")

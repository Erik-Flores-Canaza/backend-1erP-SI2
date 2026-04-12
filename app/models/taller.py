from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DECIMAL, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Taller(Base):
    __tablename__ = "talleres"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    administrador_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    direccion: Mapped[str | None] = mapped_column(String(255))
    latitud: Mapped[float | None] = mapped_column(DECIMAL(10, 7))
    longitud: Mapped[float | None] = mapped_column(DECIMAL(10, 7))
    porcentaje_comision: Mapped[float] = mapped_column(DECIMAL(5, 2), default=10.00)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    disponible: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(default=func.now())

    administrador: Mapped["Usuario"] = relationship("Usuario", back_populates="taller_administrado")
    servicios: Mapped[list["ServicioTaller"]] = relationship("ServicioTaller", back_populates="taller")
    tecnicos: Mapped[list["Tecnico"]] = relationship("Tecnico", back_populates="taller")
    asignaciones: Mapped[list["Asignacion"]] = relationship("Asignacion", back_populates="taller")
    metricas: Mapped[list["MetricaTaller"]] = relationship("MetricaTaller", back_populates="taller")

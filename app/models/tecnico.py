from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DECIMAL, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Tecnico(Base):
    __tablename__ = "tecnicos"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    usuario_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    taller_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("talleres.id"), nullable=False)
    latitud_actual: Mapped[float | None] = mapped_column(DECIMAL(10, 7))
    longitud_actual: Mapped[float | None] = mapped_column(DECIMAL(10, 7))
    disponible: Mapped[bool] = mapped_column(Boolean, default=True)
    ubicacion_actualizada_en: Mapped[datetime | None] = mapped_column()

    usuario: Mapped["Usuario"] = relationship("Usuario", back_populates="tecnico_perfil")
    taller: Mapped["Taller"] = relationship("Taller", back_populates="tecnicos")
    turnos: Mapped[list["TurnoTecnico"]] = relationship("TurnoTecnico", back_populates="tecnico")
    asignaciones: Mapped[list["Asignacion"]] = relationship("Asignacion", back_populates="tecnico")

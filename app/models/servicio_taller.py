from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ServicioTaller(Base):
    __tablename__ = "servicios_taller"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    taller_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("talleres.id"), nullable=False)
    tipo_servicio: Mapped[str] = mapped_column(String(50), nullable=False)
    disponible: Mapped[bool] = mapped_column(Boolean, default=True)

    taller: Mapped["Taller"] = relationship("Taller", back_populates="servicios")

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DECIMAL, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Pago(Base):
    __tablename__ = "pagos"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    incidente_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("incidentes.id"), unique=True, nullable=False)
    monto_total: Mapped[float] = mapped_column(DECIMAL(10, 2), nullable=False)
    comision_plataforma: Mapped[float] = mapped_column(DECIMAL(10, 2), nullable=False)
    neto_taller: Mapped[float] = mapped_column(DECIMAL(10, 2), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default="pendiente", nullable=False)
    metodo_pago: Mapped[str | None] = mapped_column(String(50))
    pagado_en: Mapped[datetime | None] = mapped_column()
    creado_en: Mapped[datetime] = mapped_column(default=func.now())

    incidente: Mapped["Incidente"] = relationship("Incidente", back_populates="pago")

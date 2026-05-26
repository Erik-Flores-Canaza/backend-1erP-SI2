from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DECIMAL, ForeignKey, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Cotizacion(Base):
    """Cotización enviada por un taller para un incidente — CU-34 / CU-35 (R3).

    Estados:
      - enviada    : el taller la envió, esperando que el cliente decida.
      - aceptada   : el cliente la eligió; se crea la asignación y se cierra.
      - rechazada  : el cliente rechazó explícitamente (no usado por defecto).
      - expirada   : el TTL (15 min) venció o se aceptó otra cotización.
    """

    __tablename__ = "cotizaciones"
    __table_args__ = (
        UniqueConstraint("incidente_id", "taller_id", name="uq_cotizacion_incidente_taller"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)

    # Multi-tenant: la cotización siempre pertenece al tenant del taller que la envía.
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )

    incidente_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("incidentes.id"), nullable=False, index=True
    )
    taller_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("talleres.id"), nullable=False, index=True
    )

    monto_estimado: Mapped[float] = mapped_column(DECIMAL(10, 2), nullable=False)
    tiempo_estimado_horas: Mapped[float | None] = mapped_column(DECIMAL(5, 2))
    observaciones: Mapped[str | None] = mapped_column(Text)

    estado: Mapped[str] = mapped_column(String(20), default="enviada", nullable=False)

    enviado_en: Mapped[datetime] = mapped_column(default=func.now(), nullable=False)
    expira_en: Mapped[datetime] = mapped_column(nullable=False)
    respondido_en: Mapped[datetime | None] = mapped_column()

    incidente: Mapped["Incidente"] = relationship("Incidente")
    taller: Mapped["Taller"] = relationship("Taller")

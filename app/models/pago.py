from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DECIMAL, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Pago(Base):
    __tablename__ = "pagos"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    # NULLABLE en R1.5 — R3 propagará desde incidente.tenant_id
    tenant_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True
    )
    incidente_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("incidentes.id"), unique=True, nullable=False)

    # Desglose del cobro (decisión docente, 2026-05-28):
    # - monto_base: lo que el cliente aceptó en la cotización (CU-35).
    # - monto_adicional: ajuste que el técnico aplicó si el trabajo resultó
    #   más costoso de lo estimado.
    # - motivo_adicional: justificación visible para el cliente.
    # - monto_total: suma de los anteriores; lo que efectivamente se cobra.
    monto_base: Mapped[float] = mapped_column(DECIMAL(10, 2), nullable=False)
    monto_adicional: Mapped[float] = mapped_column(DECIMAL(10, 2), nullable=False, default=0)
    motivo_adicional: Mapped[str | None] = mapped_column(Text)

    monto_total: Mapped[float] = mapped_column(DECIMAL(10, 2), nullable=False)
    comision_plataforma: Mapped[float] = mapped_column(DECIMAL(10, 2), nullable=False)
    neto_taller: Mapped[float] = mapped_column(DECIMAL(10, 2), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default="pendiente", nullable=False)
    metodo_pago: Mapped[str | None] = mapped_column(String(50))
    pagado_en: Mapped[datetime | None] = mapped_column()
    creado_en: Mapped[datetime] = mapped_column(default=func.now())

    incidente: Mapped["Incidente"] = relationship("Incidente", back_populates="pago")

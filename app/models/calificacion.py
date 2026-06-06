from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Calificacion(Base):
    """Calificación y reseña del cliente al taller tras finalizar el servicio — CU-43 (aporte propio).

    Cierra el ciclo de atención: una vez el incidente está `finalizado`, el cliente
    puntúa al taller (1-5 estrellas) y deja un comentario opcional.

    Impacto en el flujo del sistema (no es decorativo):
      - CU-35: el promedio del taller se muestra y ordena las cotizaciones.
      - CU-39: alimenta el KPI de satisfacción promedio del tenant.
      - Moderación: el admin_tenant puede ocultar reseñas abusivas (`oculta=True`).

    Reglas:
      - Una sola calificación por incidente (UNIQUE incidente_id).
      - Solo el cliente dueño de un incidente `finalizado` puede calificar.
    """

    __tablename__ = "calificaciones"
    __table_args__ = (
        UniqueConstraint("incidente_id", name="uq_calificacion_incidente"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)

    # Multi-tenant: hereda el tenant del taller calificado (para scoping de KPIs y moderación).
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    incidente_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("incidentes.id"), nullable=False, index=True
    )
    taller_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("talleres.id"), nullable=False, index=True
    )
    cliente_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("usuarios.id"), nullable=False
    )

    puntuacion: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..5
    comentario: Mapped[str | None] = mapped_column(Text)

    # Moderación por admin_tenant: una reseña oculta no se muestra ni cuenta en KPIs.
    oculta: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    creado_en: Mapped[datetime] = mapped_column(default=func.now(), nullable=False)

    taller: Mapped["Taller"] = relationship("Taller")

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SlaConfig(Base):
    """Configuración de SLA por tenant y tipo de servicio — CU-37.

    Cada tenant define sus propios objetivos de tiempo (en minutos) para cada
    tipo de servicio. El dashboard de KPIs (CU-39) los usa para calcular el
    porcentaje de incidentes que cumplieron el SLA.

    Si un tenant no tiene fila para un tipo de servicio, el cumplimiento no se
    calcula para los incidentes de ese tipo (regla de negocio #9).
    """

    __tablename__ = "sla_config"
    __table_args__ = (
        UniqueConstraint("tenant_id", "tipo_servicio", name="uq_sla_config_tenant_tipo"),
    )

    TIPOS_VALIDOS = ("bateria", "llanta", "motor", "choque", "otro")

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    tipo_servicio: Mapped[str] = mapped_column(String(20), nullable=False)

    minutos_asignacion_objetivo: Mapped[int] = mapped_column(Integer, nullable=False)
    minutos_llegada_objetivo: Mapped[int] = mapped_column(Integer, nullable=False)
    minutos_resolucion_objetivo: Mapped[int] = mapped_column(Integer, nullable=False)

    creado_en: Mapped[datetime] = mapped_column(default=func.now(), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now(), nullable=False,
    )

    tenant: Mapped["Tenant"] = relationship("Tenant")

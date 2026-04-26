from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TallerFavorito(Base):
    """Relación cliente → taller favorito (CU-20 extendido)."""

    __tablename__ = "talleres_favoritos"
    __table_args__ = (
        UniqueConstraint("cliente_id", "taller_id", name="uq_favorito_cliente_taller"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    cliente_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("usuarios.id"), nullable=False, index=True
    )
    taller_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("talleres.id"), nullable=False
    )
    creado_en: Mapped[datetime] = mapped_column(default=func.now())

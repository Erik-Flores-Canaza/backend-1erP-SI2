from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Tenant(Base):
    """Red independiente de talleres (multi-tenant SaaS). CU-28."""

    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    correo_contacto: Mapped[str | None] = mapped_column(String(150))
    telefono_contacto: Mapped[str | None] = mapped_column(String(20))
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    plan: Mapped[str] = mapped_column(String(20), default="basico", nullable=False)
    creado_en: Mapped[datetime] = mapped_column(default=func.now())

    usuarios: Mapped[list["Usuario"]] = relationship("Usuario", back_populates="tenant")
    talleres: Mapped[list["Taller"]] = relationship("Taller", back_populates="tenant")

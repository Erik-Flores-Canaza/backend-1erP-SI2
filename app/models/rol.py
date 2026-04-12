from uuid import UUID, uuid4

from sqlalchemy import String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Rol(Base):
    __tablename__ = "roles"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    nombre: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)

    usuarios: Mapped[list["Usuario"]] = relationship("Usuario", back_populates="rol")

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DECIMAL, Float, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Incidente(Base):
    __tablename__ = "incidentes"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    cliente_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    vehiculo_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("vehiculos.id"), nullable=False)
    descripcion_texto: Mapped[str | None] = mapped_column(Text)
    latitud: Mapped[float | None] = mapped_column(DECIMAL(10, 7))
    longitud: Mapped[float | None] = mapped_column(DECIMAL(10, 7))
    estado: Mapped[str] = mapped_column(String(20), default="pendiente", nullable=False)
    prioridad: Mapped[str] = mapped_column(String(20), default="incierto", nullable=False)
    clasificacion_ia: Mapped[str | None] = mapped_column(String(50))
    confianza_ia: Mapped[float | None] = mapped_column(Float)
    resumen_ia: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(default=func.now())
    actualizado_en: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())

    cliente: Mapped["Usuario"] = relationship("Usuario", back_populates="incidentes")
    vehiculo: Mapped["Vehiculo"] = relationship("Vehiculo", back_populates="incidentes")
    evidencias: Mapped[list["Evidencia"]] = relationship("Evidencia", back_populates="incidente")
    asignaciones: Mapped[list["Asignacion"]] = relationship("Asignacion", back_populates="incidente")
    pago: Mapped["Pago | None"] = relationship("Pago", back_populates="incidente")
    historial: Mapped[list["HistorialServicio"]] = relationship("HistorialServicio", back_populates="incidente")
    notificaciones: Mapped[list["Notificacion"]] = relationship("Notificacion", back_populates="incidente")
    mensajes: Mapped[list["Mensaje"]] = relationship("Mensaje", back_populates="incidente")

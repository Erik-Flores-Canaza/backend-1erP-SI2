from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    rol_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("roles.id"), nullable=False)
    # NULL para rol 'cliente' (global cross-tenant) y 'superadmin_plataforma' (sin tenant)
    # NOT NULL en la práctica para 'admin_tenant', 'admin_taller', 'tecnico'
    tenant_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True
    )
    nombre_completo: Mapped[str] = mapped_column(String(150), nullable=False)
    correo: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    hash_contrasena: Mapped[str] = mapped_column(String(255), nullable=False)
    telefono: Mapped[str | None] = mapped_column(String(20))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    fcm_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(default=func.now())
    actualizado_en: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())

    rol: Mapped["Rol"] = relationship("Rol", back_populates="usuarios")
    tenant: Mapped["Tenant | None"] = relationship("Tenant", back_populates="usuarios")
    vehiculos: Mapped[list["Vehiculo"]] = relationship("Vehiculo", back_populates="propietario")
    # CU-26: un admin_taller puede tener múltiples talleres (sucursales)
    talleres_administrados: Mapped[list["Taller"]] = relationship("Taller", back_populates="administrador")
    tecnico_perfil: Mapped["Tecnico | None"] = relationship("Tecnico", back_populates="usuario")
    incidentes: Mapped[list["Incidente"]] = relationship("Incidente", back_populates="cliente")
    notificaciones: Mapped[list["Notificacion"]] = relationship("Notificacion", back_populates="usuario")
    mensajes_enviados: Mapped[list["Mensaje"]] = relationship("Mensaje", back_populates="remitente")
    historial_cambios: Mapped[list["HistorialServicio"]] = relationship("HistorialServicio", back_populates="cambiado_por_usuario")

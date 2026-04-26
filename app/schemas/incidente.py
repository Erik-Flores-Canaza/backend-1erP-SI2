from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


# ---------------------------------------------------------------------------
# Schemas embebidos (para respuestas anidadas)
# ---------------------------------------------------------------------------

class TallerResumen(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nombre: str
    direccion: str | None = None
    latitud: float | None = None
    longitud: float | None = None


class TecnicoResumen(BaseModel):
    """Técnico aplanado: nombre/teléfono vienen de tecnico.usuario."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nombre_completo: str = ""
    telefono: str | None = None
    latitud_actual: float | None = None
    longitud_actual: float | None = None

    @model_validator(mode="before")
    @classmethod
    def flatten_usuario(cls, data: Any) -> Any:
        if hasattr(data, "usuario") and data.usuario is not None:
            return {
                "id": data.id,
                "nombre_completo": data.usuario.nombre_completo,
                "telefono": data.usuario.telefono,
                "latitud_actual": data.latitud_actual,
                "longitud_actual": data.longitud_actual,
            }
        return data


class EvidenciaResumen(BaseModel):
    """Evidencia embebida en IncidenteResponse (archivo_url alineado con Flutter)."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    tipo: str
    archivo_url: str | None = Field(None, validation_alias="url_archivo")


# ---------------------------------------------------------------------------
# Solicitudes (entrada)
# ---------------------------------------------------------------------------

class IncidenteCreate(BaseModel):
    """
    Payload de creación desde Flutter.
    vehiculo_id es opcional (el cliente puede no tener vehículo registrado).
    descripcion mapea a descripcion_texto en la BD.
    """
    vehiculo_id: UUID | None = None
    descripcion: str | None = None
    latitud: float | None = None
    longitud: float | None = None


class IncidenteEstadoUpdate(BaseModel):
    estado: str   # 'pendiente' | 'en_proceso' | 'atendido' | 'cancelado'
    notas: str | None = None


# ---------------------------------------------------------------------------
# Asignación embebida en IncidenteResponse
# ---------------------------------------------------------------------------

class AsignacionEnIncidenteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    taller_id: UUID
    tecnico_id: UUID | None = None
    accion_taller: str | None = None
    eta_minutos: int | None = None
    asignado_en: datetime
    completado_en: datetime | None = None

    # Objetos anidados — Pydantic los resuelve via la relación SQLAlchemy
    taller: TallerResumen | None = None
    tecnico: TecnicoResumen | None = None


# ---------------------------------------------------------------------------
# Respuesta principal de incidente
# ---------------------------------------------------------------------------

class IncidenteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    cliente_id: UUID
    vehiculo_id: UUID | None = None

    # descripcion_texto en BD → descripcion en JSON (Flutter lo espera así)
    # validation_alias: lee de ORM como descripcion_texto, serializa como descripcion
    descripcion: str | None = Field(None, validation_alias="descripcion_texto")

    latitud: float | None = None
    longitud: float | None = None
    estado: str
    prioridad: str
    clasificacion_ia: str | None = None
    confianza_ia: float | None = None
    resumen_ia: str | None = None
    creado_en: datetime
    actualizado_en: datetime

    # Lista completa (cargada por ORM)
    asignaciones: list[AsignacionEnIncidenteResponse] = []

    # Evidencias
    evidencias: list[EvidenciaResumen] = []

    pagado: bool = False

    @model_validator(mode="before")
    @classmethod
    def extract_pagado(cls, data: Any) -> Any:
        # pagado = True solo cuando el pago existe Y ya está confirmado (estado='pagado')
        if not isinstance(data, dict):
            pago = getattr(data, "pago", None)
            data.__dict__["pagado"] = pago is not None and getattr(pago, "estado", None) == "pagado"
        return data

    @computed_field  # type: ignore[misc]
    @property
    def asignacion(self) -> AsignacionEnIncidenteResponse | None:
        """
        Devuelve la asignación activa (no rechazada) más reciente.
        Flutter lee este campo singular para mostrar taller/técnico.
        """
        if not self.asignaciones:
            return None
        return next(
            (
                a
                for a in sorted(
                    self.asignaciones, key=lambda x: x.asignado_en, reverse=True
                )
                if a.accion_taller != "rechazado"
            ),
            None,
        )

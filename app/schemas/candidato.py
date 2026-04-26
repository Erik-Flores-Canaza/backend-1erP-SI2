from uuid import UUID

from pydantic import BaseModel


class TallerCandidatoResponse(BaseModel):
    """Taller candidato para un incidente, tal como lo ve el cliente."""

    id: UUID
    nombre: str
    direccion: str | None
    distancia_km: float | None       # None si el taller no tiene coordenadas
    eta_minutos: int | None          # estimación: distancia / 30 km/h
    tipo_servicios: list[str]        # servicios compatibles con el incidente
    es_favorito: bool                # True si el cliente lo tiene como favorito


class SeleccionarTallerBody(BaseModel):
    taller_id: UUID


class FavoritoResponse(BaseModel):
    """Taller favorito del cliente con datos básicos."""

    id: UUID
    taller_id: UUID
    nombre: str
    direccion: str | None

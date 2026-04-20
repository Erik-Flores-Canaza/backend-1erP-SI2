"""
Servicio de asignación inteligente — CU-20
Selecciona el taller más adecuado para un incidente considerando:
  1. Distancia (Haversine) al incidente
  2. Tipo de servicio compatible con la clasificación IA
  3. Disponibilidad del taller (activo + disponible)

Si el taller rechaza la solicitud, la función reasignar() busca el siguiente
candidato de la lista ordenada por distancia, excluyendo talleres ya intentados.
"""
from __future__ import annotations

import math
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.asignacion import Asignacion
from app.models.incidente import Incidente
from app.models.servicio_taller import ServicioTaller
from app.models.taller import Taller
from app.services import notificacion_service

# ---------------------------------------------------------------------------
# Mapa clasificación IA → tipos de servicio compatibles
# ---------------------------------------------------------------------------
_CLASIFICACION_SERVICIOS: dict[str, list[str]] = {
    "bateria":   ["electrico"],
    "llanta":    ["neumatico"],
    "choque":    ["remolque", "mecanica"],
    "motor":     ["mecanica", "remolque"],
    "otro":      ["mecanica", "electrico", "neumatico", "remolque", "otro"],
    "incierto":  ["mecanica", "electrico", "neumatico", "remolque", "otro"],
}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en kilómetros entre dos coordenadas geográficas."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _talleres_candidatos(
    incidente: Incidente,
    db: Session,
    excluir_ids: list[UUID] | None = None,
) -> list[Taller]:
    """
    Devuelve la lista de talleres válidos ordenados de más cercano a más lejano.
    Filtra por disponibilidad y tipo de servicio compatible.
    """
    excluir_ids = excluir_ids or []
    clasificacion = incidente.clasificacion_ia or "otro"
    tipos_compatibles = _CLASIFICACION_SERVICIOS.get(clasificacion, ["otro"])

    # Talleres activos y disponibles, no excluidos
    talleres = (
        db.query(Taller)
        .filter(
            Taller.activo == True,
            Taller.disponible == True,
            Taller.id.notin_(excluir_ids),
        )
        .all()
    )

    # Filtrar por servicio compatible
    taller_ids_con_servicio = {
        s.taller_id
        for s in db.query(ServicioTaller)
        .filter(
            ServicioTaller.tipo_servicio.in_(tipos_compatibles),
            ServicioTaller.disponible == True,
        )
        .all()
    }
    talleres = [t for t in talleres if t.id in taller_ids_con_servicio]

    # Ordenar por distancia si el incidente tiene coordenadas
    if incidente.latitud is not None and incidente.longitud is not None:
        def _distancia(t: Taller) -> float:
            if t.latitud is None or t.longitud is None:
                return float("inf")
            return _haversine_km(
                float(incidente.latitud), float(incidente.longitud),
                float(t.latitud), float(t.longitud),
            )
        talleres.sort(key=_distancia)

    return talleres


def asignar(incidente: Incidente, db: Session) -> Asignacion | None:
    """
    Selecciona el taller más adecuado y crea el registro de ASIGNACION.
    Lanza excepción si no hay talleres disponibles.
    Retorna None si confianza_ia < 0.5 (prioridad 'incierto').
    """
    # Regla de negocio: no asignar si la IA no tiene confianza suficiente
    if (incidente.confianza_ia is not None) and (incidente.confianza_ia < 0.5):
        return None

    candidatos = _talleres_candidatos(incidente, db)
    if not candidatos:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No hay talleres disponibles para atender esta emergencia.",
        )

    taller = candidatos[0]
    asignacion = Asignacion(
        incidente_id=incidente.id,
        taller_id=taller.id,
    )
    db.add(asignacion)
    db.flush()  # Obtener id sin commit para que el caller pueda hacer commit junto con notificaciones

    # Notificación CU-21: taller asignado
    notificacion_service.notif_taller_asignado(
        db,
        cliente_id=incidente.cliente_id,
        admin_taller_id=taller.administrador_id,
        incidente_id=incidente.id,
        nombre_taller=taller.nombre,
    )

    return asignacion


def intentar_asignar_pendientes(db: Session) -> None:
    """
    Llamado cuando un nuevo taller o servicio queda disponible.
    Busca incidentes pendientes sin asignación activa y los asigna al taller
    más cercano disponible.
    """
    # Incidentes que ya tienen asignación pendiente o aceptada (activos)
    subq = (
        db.query(Asignacion.incidente_id)
        .filter(
            (Asignacion.accion_taller == None) | (Asignacion.accion_taller == "aceptado"),  # noqa: E711
            Asignacion.completado_en == None,  # noqa: E711
        )
    )

    pendientes = (
        db.query(Incidente)
        .filter(
            Incidente.estado == "pendiente",
            Incidente.confianza_ia >= 0.5,
            ~Incidente.id.in_(subq),
        )
        .all()
    )

    for incidente in pendientes:
        try:
            asignar(incidente, db)
        except HTTPException:
            pass  # Sin talleres compatibles — seguir con el siguiente


def reasignar(asignacion_rechazada: Asignacion, db: Session) -> Asignacion | None:
    """
    Llamado cuando un taller rechaza la solicitud (CU-12).
    Busca el siguiente candidato excluyendo los talleres ya intentados.
    """
    # Obtener todos los talleres ya intentados para este incidente
    talleres_intentados = [
        a.taller_id
        for a in db.query(Asignacion)
        .filter(Asignacion.incidente_id == asignacion_rechazada.incidente_id)
        .all()
    ]

    incidente: Incidente = asignacion_rechazada.incidente
    candidatos = _talleres_candidatos(incidente, db, excluir_ids=talleres_intentados)

    if not candidatos:
        # No hay más talleres — el incidente queda sin asignación activa
        return None

    taller = candidatos[0]
    nueva_asignacion = Asignacion(
        incidente_id=incidente.id,
        taller_id=taller.id,
    )
    db.add(nueva_asignacion)
    db.flush()

    # Notificación CU-21: nuevo taller asignado
    notificacion_service.notif_taller_asignado(
        db,
        cliente_id=incidente.cliente_id,
        admin_taller_id=taller.administrador_id,
        incidente_id=incidente.id,
        nombre_taller=taller.nombre,
    )

    return nueva_asignacion

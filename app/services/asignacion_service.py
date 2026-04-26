"""
Servicio de asignación inteligente — CU-20
Selecciona el taller más adecuado para un incidente considerando:
  1. Distancia (Haversine) al incidente
  2. Tipo de servicio compatible con la clasificación IA
  3. Disponibilidad del taller (activo + disponible)
  4. Cobertura de turno activo (al menos 1 técnico en turno ahora)
  5. Prioridad del incidente (alta > media > baja > incierto) en la cola pendiente

Si el taller rechaza la solicitud, la función reasignar() busca el siguiente
candidato de la lista ordenada por distancia, excluyendo talleres ya intentados.
"""
from __future__ import annotations

import math
from app.core.timezone import now_bo
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.asignacion import Asignacion
from app.models.incidente import Incidente
from app.models.servicio_taller import ServicioTaller
from app.models.taller import Taller
from app.models.tecnico import Tecnico
from app.models.turno_tecnico import TurnoTecnico
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


def _taller_tiene_cobertura(taller_id: UUID, db: Session) -> bool:
    """
    Un taller tiene cobertura si existe al menos un técnico que:
    - Tiene turno programado para el día de la semana actual
    - La hora actual está dentro del rango hora_inicio–hora_fin
    - No está ocupado (Tecnico.disponible = True)
    """
    ahora = now_bo()
    dia_hoy = ahora.weekday()          # 0=Lun … 6=Dom  (igual que dia_semana)
    hora_ahora = ahora.time().replace(tzinfo=None)

    tiene = (
        db.query(TurnoTecnico)
        .join(Tecnico, TurnoTecnico.tecnico_id == Tecnico.id)
        .filter(
            Tecnico.taller_id == taller_id,
            Tecnico.disponible == True,
            TurnoTecnico.dia_semana == dia_hoy,
            TurnoTecnico.hora_inicio <= hora_ahora,
            TurnoTecnico.hora_fin > hora_ahora,
        )
        .first()
    )
    return tiene is not None


def _talleres_candidatos(
    incidente: Incidente,
    db: Session,
    excluir_ids: list[UUID] | None = None,
) -> list[Taller]:
    """
    Devuelve la lista de talleres válidos ordenados de más cercano a más lejano.
    Filtra por:
      1. Activo + disponible + aprobado
      2. Tipo de servicio compatible con clasificación IA
      3. Cobertura de turno ahora mismo (al menos 1 técnico disponible)
    """
    excluir_ids = excluir_ids or []
    clasificacion = incidente.clasificacion_ia or "otro"
    tipos_compatibles = _CLASIFICACION_SERVICIOS.get(clasificacion, ["otro"])

    talleres = (
        db.query(Taller)
        .filter(
            Taller.activo == True,
            Taller.disponible == True,
            Taller.estado_aprobacion == "aprobado",
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

    # Filtrar por cobertura de turno activa ahora mismo
    talleres = [t for t in talleres if _taller_tiene_cobertura(t.id, db)]

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


def candidatos_para_incidente(
    incidente: Incidente,
    db: Session,
    cliente_id: "UUID | None" = None,
    excluir_ids: "list[UUID] | None" = None,
) -> list[dict]:
    """
    Devuelve la lista de talleres candidatos enriquecida con distancia, ETA,
    servicios compatibles y si es favorito del cliente.
    Usada por el endpoint GET /incidentes/{id}/candidatos.
    """
    from app.models.taller_favorito import TallerFavorito
    from app.models.servicio_taller import ServicioTaller as ST

    clasificacion = incidente.clasificacion_ia or "otro"
    tipos_compatibles = _CLASIFICACION_SERVICIOS.get(clasificacion, ["otro"])

    favoritos: set[UUID] = set()
    if cliente_id:
        favoritos = {
            f.taller_id
            for f in db.query(TallerFavorito)
            .filter(TallerFavorito.cliente_id == cliente_id)
            .all()
        }

    talleres = _talleres_candidatos(incidente, db, excluir_ids=excluir_ids)

    resultado = []
    for t in talleres:
        dist: float | None = None
        eta: int | None = None
        if (incidente.latitud is not None and incidente.longitud is not None
                and t.latitud is not None and t.longitud is not None):
            dist = round(_haversine_km(
                float(incidente.latitud), float(incidente.longitud),
                float(t.latitud), float(t.longitud),
            ), 2)
            # ETA: distancia / 30 km/h → minutos, mínimo 5
            eta = max(5, int(dist / 30 * 60))

        servicios = [
            s.tipo_servicio
            for s in db.query(ST)
            .filter(
                ST.taller_id == t.id,
                ST.tipo_servicio.in_(tipos_compatibles),
                ST.disponible == True,
            )
            .all()
        ]

        resultado.append({
            "id": t.id,
            "nombre": t.nombre,
            "direccion": t.direccion,
            "distancia_km": dist,
            "eta_minutos": eta,
            "tipo_servicios": servicios,
            "es_favorito": t.id in favoritos,
        })

    # Ordenar: favoritos primero, luego por distancia
    resultado.sort(key=lambda x: (not x["es_favorito"], x["distancia_km"] or 9999))
    return resultado


def asignar(incidente: Incidente, db: Session) -> Asignacion | None:
    """
    Selecciona automáticamente el taller más adecuado y crea el ASIGNACION.
    Lanza excepción si no hay talleres disponibles.
    """
    candidatos = _talleres_candidatos(incidente, db)
    if not candidatos:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No hay talleres disponibles para atender esta emergencia.",
        )

    return _crear_asignacion(incidente, candidatos[0], db)


def asignar_especifico(
    incidente: Incidente,
    taller_id: "UUID",
    db: Session,
) -> Asignacion:
    """
    El cliente eligió manualmente un taller de la lista de candidatos.
    Verifica que sigue siendo candidato válido y crea la asignación.
    """
    candidatos = _talleres_candidatos(incidente, db)
    taller = next((t for t in candidatos if t.id == taller_id), None)
    if not taller:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El taller seleccionado ya no está disponible. Elige otro.",
        )
    return _crear_asignacion(incidente, taller, db)


def _crear_asignacion(incidente: Incidente, taller: "Taller", db: Session) -> Asignacion:
    """Crea el registro Asignacion y emite la notificación al taller."""
    asignacion = Asignacion(
        incidente_id=incidente.id,
        taller_id=taller.id,
    )
    db.add(asignacion)
    db.flush()

    notificacion_service.notif_taller_asignado(
        db,
        cliente_id=incidente.cliente_id,
        admin_taller_id=taller.administrador_id,
        incidente_id=incidente.id,
        nombre_taller=taller.nombre,
    )
    return asignacion


_PRIORIDAD_ORDEN = {"alta": 0, "media": 1, "baja": 2, "incierto": 3}


def intentar_asignar_pendientes(db: Session) -> None:
    """
    Llamado cuando un nuevo taller o servicio queda disponible.
    Busca incidentes pendientes sin asignación activa y los asigna al taller
    más cercano disponible, priorizando los de mayor urgencia.
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
            ~Incidente.id.in_(subq),
        )
        .all()
    )

    # Ordenar por prioridad: alta → media → baja → incierto, luego por fecha
    pendientes.sort(key=lambda inc: (
        _PRIORIDAD_ORDEN.get(inc.prioridad or "incierto", 3),
        inc.creado_en,
    ))

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
    talleres_intentados = [
        a.taller_id
        for a in db.query(Asignacion)
        .filter(Asignacion.incidente_id == asignacion_rechazada.incidente_id)
        .all()
    ]

    incidente: Incidente = asignacion_rechazada.incidente
    candidatos = _talleres_candidatos(incidente, db, excluir_ids=talleres_intentados)

    if not candidatos:
        return None

    return _crear_asignacion(incidente, candidatos[0], db)

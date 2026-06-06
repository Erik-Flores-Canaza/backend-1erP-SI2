"""Jobs de mantenimiento de cotizaciones — R3 (CU-34 / CU-35).

Se ejecutan periódicamente desde un task de asyncio arrancado en el lifespan de
`main.py` (sin dependencias externas tipo APScheduler). Cubren dos reglas que
antes solo ocurrían en *read-time* (al consultar) o no ocurrían:

  1. EXPIRACIÓN PROACTIVA: marca como 'expirada' toda cotización 'enviada' cuyo
     TTL (15 min) ya venció, aunque nadie la haya consultado. Esto mantiene los
     KPIs y la UI consistentes sin depender de que el cliente abra la pantalla.

  2. FALLBACK SIN COTIZACIONES: si un incidente lleva >= UMBRAL minutos en estado
     'buscando_taller' y NO recibió ninguna cotización activa, amplía el alcance
     notificando a los talleres candidatos que NO estaban en el top-5 inicial.
     Mitiga el riesgo "todos los talleres del top-5 ignoran la solicitud".
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.core import estado_incidente as estado_machine
from app.core.timezone import now_bo
from app.models.cotizacion import Cotizacion
from app.models.incidente import Incidente
from app.services import asignacion_service, notificacion_service

logger = logging.getLogger(__name__)

# Minutos que un incidente puede pasar en 'buscando_taller' sin ninguna
# cotización antes de ampliar el alcance a más talleres.
FALLBACK_UMBRAL_MINUTOS = 5

# Talleres del top-N ya contactados en el disparo inicial (incidente_service).
# El fallback notifica a partir de este índice para "ampliar el radio".
TOP_INICIAL = 5

# Incidentes a los que ya se les amplió el alcance en esta corrida del servidor
# (evita re-notificar en cada ciclo del job). Es aceptable que se reinicie al
# reiniciar el proceso: re-notificar es inocuo (el taller solo ve otro aviso).
_fallback_ya_notificado: set[UUID] = set()


def expirar_cotizaciones_vencidas(db: Session) -> int:
    """Marca como 'expirada' todas las cotizaciones 'enviada' con TTL vencido.

    Devuelve la cantidad de cotizaciones expiradas.
    """
    ahora = now_bo().replace(tzinfo=None)
    vencidas = (
        db.query(Cotizacion)
        .filter(
            Cotizacion.estado == "enviada",
            Cotizacion.expira_en < ahora,
        )
        .all()
    )
    for c in vencidas:
        c.estado = "expirada"
        c.respondido_en = ahora
    if vencidas:
        db.commit()
        logger.info("Job cotizaciones: %d cotización(es) expirada(s) por TTL.", len(vencidas))
    return len(vencidas)


def notificar_fallback_sin_cotizaciones(db: Session) -> int:
    """Amplía el alcance de incidentes que llevan mucho tiempo sin cotizaciones.

    Para cada incidente en 'buscando_taller' con antigüedad >= UMBRAL y sin
    ninguna cotización activa ('enviada' o 'aceptada'), notifica a los talleres
    candidatos más allá del top-5 inicial. Devuelve cuántos incidentes amplió.
    """
    ahora = now_bo().replace(tzinfo=None)
    ampliados = 0

    buscando = (
        db.query(Incidente)
        .filter(Incidente.estado == estado_machine.BUSCANDO_TALLER)
        .all()
    )

    # Mantener acotado el set: descartar ids que ya no están buscando taller.
    ids_buscando = {inc.id for inc in buscando}
    _fallback_ya_notificado.intersection_update(ids_buscando)

    for inc in buscando:
        if inc.id in _fallback_ya_notificado:
            continue

        # Antigüedad en el estado (proxy: creado_en; el análisis IA es inmediato).
        creado = inc.creado_en
        if creado is None:
            continue
        edad_min = (ahora - creado.replace(tzinfo=None)).total_seconds() / 60.0
        if edad_min < FALLBACK_UMBRAL_MINUTOS:
            continue

        # ¿Ya tiene alguna cotización activa? Entonces no hace falta ampliar.
        tiene_cotizacion = (
            db.query(Cotizacion)
            .filter(
                Cotizacion.incidente_id == inc.id,
                Cotizacion.estado.in_(["enviada", "aceptada"]),
            )
            .first()
        )
        if tiene_cotizacion:
            _fallback_ya_notificado.add(inc.id)  # ya no necesita fallback
            continue

        # Ampliar: notificar a candidatos fuera del top-5 inicial.
        candidatos = asignacion_service._talleres_candidatos(inc, db)
        adicionales = candidatos[TOP_INICIAL:]

        if not adicionales:
            # No hay más talleres compatibles que el top inicial. Marcamos para
            # no re-evaluar en cada ciclo; el incidente seguirá esperando.
            _fallback_ya_notificado.add(inc.id)
            logger.info(
                "Job fallback: incidente %s sin cotizaciones y sin talleres "
                "adicionales que notificar.", inc.id,
            )
            continue

        for taller in adicionales:
            notificacion_service.notif_solicitud_cotizacion(
                db,
                admin_taller_id=taller.administrador_id,
                incidente_id=inc.id,
                clasificacion=inc.clasificacion_ia,
            )
        db.commit()
        _fallback_ya_notificado.add(inc.id)
        ampliados += 1
        logger.info(
            "Job fallback: incidente %s amplió alcance a %d taller(es) adicional(es).",
            inc.id, len(adicionales),
        )

    return ampliados


def ejecutar_ciclo(db: Session) -> None:
    """Una pasada completa del job. Cada paso aísla sus errores."""
    try:
        expirar_cotizaciones_vencidas(db)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("Job expiración de cotizaciones falló: %s", exc)

    try:
        notificar_fallback_sin_cotizaciones(db)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("Job fallback de cotizaciones falló: %s", exc)

"""
Servicio de incidentes — CU-05
Orquesta la creación del incidente y dispara internamente CU-18, CU-19 y CU-20.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core import estado_incidente as estado_machine
from app.models.incidente import Incidente
from app.models.historial_servicio import HistorialServicio
from app.models.vehiculo import Vehiculo
from app.schemas.incidente import IncidenteCreate
from app.services import asignacion_service, ia_service, notificacion_service


def crear_incidente(db: Session, body: IncidenteCreate, cliente_id: UUID) -> Incidente:
    """
    CU-05 — Paso 1: Crea el incidente y notifica al cliente.
    La IA y la asignación se disparan DESPUÉS en analizar_incidente(),
    una vez que las evidencias (imágenes/audio) ya fueron subidas.
    """
    vehiculo_id = None
    if body.vehiculo_id is not None:
        vehiculo = db.query(Vehiculo).filter(
            Vehiculo.id == body.vehiculo_id,
            Vehiculo.propietario_id == cliente_id,
        ).first()
        if not vehiculo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vehículo no encontrado o no pertenece al usuario autenticado.",
            )
        vehiculo_id = vehiculo.id

    incidente = Incidente(
        cliente_id=cliente_id,
        vehiculo_id=vehiculo_id,
        descripcion_texto=body.descripcion,
        latitud=body.latitud,
        longitud=body.longitud,
        estado=estado_machine.PENDIENTE,
        prioridad="incierto",
    )
    db.add(incidente)
    db.flush()

    # CU-21: notificar recepción
    notificacion_service.notif_incidente_creado(db, cliente_id=cliente_id, incidente_id=incidente.id)

    db.commit()
    db.refresh(incidente)
    return incidente


def analizar_incidente(incidente: Incidente, db: Session) -> Incidente:
    """
    CU-18 + CU-19 — Paso 2: Procesa evidencias con IA y genera clasificación.
    Al terminar, transiciona el incidente de `pendiente` a `buscando_taller`
    (CU-31 — máquina de estados R2).
    NO dispara asignación — el cliente verá la lista de candidatos y podrá elegir
    o dejar que el sistema asigne automáticamente.
    """
    # CU-18: procesar evidencias
    try:
        resultado_ia = ia_service.process_evidencias(incidente.id, db)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("CU-18 falló: %s", exc)
        resultado_ia = {"clasificacion": "otro", "confianza": 0.5, "resumen": "Error al procesar evidencias"}

    # CU-19: generar resumen estructurado
    resumen = ia_service.generate_resumen(incidente.id, resultado_ia, db)
    incidente.clasificacion_ia = resumen["clasificacion_ia"]
    incidente.confianza_ia     = resumen["confianza_ia"]
    incidente.resumen_ia       = resumen["resumen_ia"]
    incidente.prioridad        = resumen["prioridad"]

    # CU-31: pendiente → buscando_taller tras análisis IA
    if incidente.estado == estado_machine.PENDIENTE:
        registrar_cambio_estado(
            db, incidente, estado_machine.BUSCANDO_TALLER, incidente.cliente_id,
            notas="IA completó el análisis — buscando taller compatible",
        )
        notificacion_service.notif_buscando_taller(
            db, cliente_id=incidente.cliente_id, incidente_id=incidente.id,
        )
        # R3 (CU-34): notificar a los talleres candidatos para que envíen cotización
        try:
            candidatos = asignacion_service._talleres_candidatos(incidente, db)
            for taller in candidatos[:5]:  # top 5 candidatos
                notificacion_service.notif_solicitud_cotizacion(
                    db,
                    admin_taller_id=taller.administrador_id,
                    incidente_id=incidente.id,
                    clasificacion=incidente.clasificacion_ia,
                )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Notif candidatos falló: %s", exc)

    db.commit()
    db.refresh(incidente)
    return incidente


def registrar_cambio_estado(
    db: Session,
    incidente: Incidente,
    nuevo_estado: str,
    cambiado_por_id: UUID,
    notas: str | None = None,
) -> None:
    """
    CU-14 + CU-31: Registra en HISTORIAL_SERVICIO el cambio de estado del incidente.
    Valida la transición contra la máquina de estados de 7 estados (R2).
    El caller debe hacer db.commit() después.
    """
    if not estado_machine.es_estado_valido(nuevo_estado):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Estado inválido. Valores permitidos: {sorted(estado_machine.ESTADOS_VALIDOS)}",
        )

    if not estado_machine.es_transicion_valida(incidente.estado, nuevo_estado):
        permitidas = sorted(estado_machine.TRANSICIONES_PERMITIDAS.get(incidente.estado, set()))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Transición inválida: {incidente.estado} → {nuevo_estado}. "
                f"Desde '{incidente.estado}' solo se permite: {permitidas}"
            ),
        )

    historial = HistorialServicio(
        tenant_id=incidente.tenant_id,  # hereda tenant del incidente (puede ser NULL)
        incidente_id=incidente.id,
        cambiado_por=cambiado_por_id,
        estado_anterior=incidente.estado,
        estado_nuevo=nuevo_estado,
        notas=notas,
    )
    db.add(historial)
    incidente.estado = nuevo_estado

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db, require_cliente
from app.models.asignacion import Asignacion
from app.models.incidente import Incidente
from app.models.tecnico import Tecnico
from app.models.usuario import Usuario
from app.schemas.incidente import IncidenteCreate, IncidenteEstadoUpdate, IncidenteResponse
from app.services import incidente_service, notificacion_service

router = APIRouter(prefix="/incidentes", tags=["Incidentes"])


# ---------------------------------------------------------------------------
# CU-05: Reportar emergencia — Paso 1: crear incidente
# ---------------------------------------------------------------------------

@router.post("", response_model=IncidenteResponse, status_code=status.HTTP_201_CREATED)
def crear_incidente(
    body: IncidenteCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_cliente),
):
    """
    CU-05 — Reportar emergencia.
    Crea el incidente, procesa evidencias con IA (stub) y dispara la asignación inteligente.
    """
    return incidente_service.crear_incidente(db, body, current_user.id)


# ---------------------------------------------------------------------------
# CU-18+19+20: Analizar incidente tras subir evidencias — Paso 2
# ---------------------------------------------------------------------------

@router.post("/{incidente_id}/analizar", response_model=IncidenteResponse)
def analizar_incidente(
    incidente_id: UUID,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_cliente),
):
    """
    CU-18+19+20 — Dispara el pipeline de IA (Whisper + GPT-4o) sobre las
    evidencias ya subidas y luego ejecuta la asignación inteligente.
    Debe llamarse DESPUÉS de subir todas las evidencias del incidente.
    """
    incidente = db.query(Incidente).filter(
        Incidente.id == incidente_id,
        Incidente.cliente_id == current_user.id,
    ).first()
    if not incidente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Incidente no encontrado")

    # Requiere al menos una evidencia (imagen/audio) o descripción de texto.
    # Sin información suficiente no se puede clasificar ni asignar correctamente.
    from app.models.evidencia import Evidencia as EvidenciaModel
    tiene_evidencia = db.query(EvidenciaModel).filter(
        EvidenciaModel.incidente_id == incidente_id
    ).first() is not None

    if not tiene_evidencia and not incidente.descripcion_texto:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Agrega al menos una foto, nota de voz o descripción antes de solicitar asistencia.",
        )

    return incidente_service.analizar_incidente(incidente, db)


# ---------------------------------------------------------------------------
# CU-06: Monitorear solicitud — lista todos los incidentes del cliente
# ---------------------------------------------------------------------------

@router.get("/mis-incidentes", response_model=list[IncidenteResponse])
def mis_incidentes(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_cliente),
):
    """CU-06 — Lista todos los incidentes del cliente autenticado."""
    return (
        db.query(Incidente)
        .filter(Incidente.cliente_id == current_user.id)
        .order_by(Incidente.creado_en.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# CU-06: Monitorear solicitud — detalle de un incidente
# ---------------------------------------------------------------------------

@router.get("/{incidente_id}", response_model=IncidenteResponse)
def get_incidente(
    incidente_id: UUID,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    CU-06 — Estado actual del incidente con asignación y técnico.
    Accesible por el cliente dueño del incidente o por admin_taller/técnico autenticado.
    """
    incidente = db.query(Incidente).filter(Incidente.id == incidente_id).first()
    if not incidente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incidente no encontrado")

    rol = current_user.rol.nombre if current_user.rol else ""

    # El cliente solo puede ver sus propios incidentes
    if rol == "cliente" and incidente.cliente_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin acceso a este incidente")

    return incidente


# ---------------------------------------------------------------------------
# CU-05: Cancelar solicitud — acción del propio cliente
# ---------------------------------------------------------------------------

@router.post("/{incidente_id}/cancelar", response_model=IncidenteResponse)
def cancelar_incidente(
    incidente_id: UUID,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_cliente),
):
    """
    Permite al cliente cancelar su propio incidente mientras aún no fue atendido.
    Solo se puede cancelar en estado 'pendiente' o 'en_proceso'.
    """
    incidente = db.query(Incidente).filter(
        Incidente.id == incidente_id,
        Incidente.cliente_id == current_user.id,
    ).first()
    if not incidente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Incidente no encontrado")

    if incidente.estado in ("atendido", "cancelado"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Este incidente ya fue finalizado y no puede cancelarse.",
        )

    incidente_service.registrar_cambio_estado(
        db, incidente, "cancelado", current_user.id,
        notas="Cancelado por el cliente",
    )

    # Liberar taller y técnico si había asignación activa
    asignacion = (
        db.query(Asignacion)
        .filter(
            Asignacion.incidente_id == incidente.id,
            Asignacion.accion_taller == "aceptado",
            Asignacion.completado_en == None,  # noqa: E711
        )
        .first()
    )
    if asignacion:
        from datetime import datetime, timezone
        asignacion.completado_en = datetime.now(timezone.utc)
        if asignacion.taller:
            asignacion.taller.disponible = True
        if asignacion.tecnico_id:
            from app.models.tecnico import Tecnico
            tecnico = db.query(Tecnico).filter(
                Tecnico.id == asignacion.tecnico_id
            ).first()
            if tecnico:
                tecnico.disponible = True

    db.commit()
    db.refresh(incidente)
    return incidente


# ---------------------------------------------------------------------------
# CU-14: Actualizar estado del servicio
# ---------------------------------------------------------------------------

@router.patch("/{incidente_id}/estado", response_model=IncidenteResponse)
def actualizar_estado(
    incidente_id: UUID,
    body: IncidenteEstadoUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    CU-14 — Actualiza el estado del incidente y registra en HISTORIAL_SERVICIO.
    Accesible por admin_taller (del taller asignado) o técnico asignado.
    """
    incidente = db.query(Incidente).filter(Incidente.id == incidente_id).first()
    if not incidente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incidente no encontrado")

    rol = current_user.rol.nombre if current_user.rol else ""
    if rol not in ("admin_taller", "tecnico"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el taller o técnico asignado puede cambiar el estado.",
        )

    incidente_service.registrar_cambio_estado(
        db, incidente, body.estado, current_user.id, body.notas
    )

    # Al cerrar el incidente (atendido/cancelado) liberar taller y técnico
    if body.estado in ("atendido", "cancelado"):
        asignacion = (
            db.query(Asignacion)
            .filter(
                Asignacion.incidente_id == incidente.id,
                Asignacion.accion_taller == "aceptado",
                Asignacion.completado_en == None,  # noqa: E711
            )
            .first()
        )
        if asignacion:
            from datetime import datetime, timezone
            asignacion.completado_en = datetime.now(timezone.utc)
            if asignacion.taller:
                asignacion.taller.disponible = True
            if asignacion.tecnico_id:
                tecnico = db.query(Tecnico).filter(Tecnico.id == asignacion.tecnico_id).first()
                if tecnico:
                    tecnico.disponible = True
        # Notificar al cliente si fue atendido
        if body.estado == "atendido":
            notificacion_service.notif_servicio_completado(
                db, cliente_id=incidente.cliente_id, incidente_id=incidente.id
            )

    db.commit()
    db.refresh(incidente)
    return incidente

from uuid import UUID

from app.core.timezone import now_bo

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db, require_cliente
from app.models.asignacion import Asignacion
from app.models.incidente import Incidente
from app.models.tecnico import Tecnico
from app.models.usuario import Usuario
from app.schemas.candidato import TallerCandidatoResponse, SeleccionarTallerBody
from app.schemas.incidente import IncidenteCreate, IncidenteEstadoUpdate, IncidenteResponse
from app.services import asignacion_service, incidente_service, notificacion_service

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
# CU-20: Lista de candidatos — el cliente elige o deja que el sistema asigne
# ---------------------------------------------------------------------------

@router.get("/{incidente_id}/candidatos", response_model=list[TallerCandidatoResponse])
def listar_candidatos(
    incidente_id: UUID,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_cliente),
):
    """
    CU-20 — Lista los talleres candidatos para el incidente ordenados por:
    1. Favoritos del cliente primero
    2. Distancia al incidente

    El cliente puede elegir uno o dejar que el sistema asigne automáticamente.
    Solo disponible mientras el incidente esté en estado 'pendiente' sin asignación activa.
    """
    incidente = db.query(Incidente).filter(
        Incidente.id == incidente_id,
        Incidente.cliente_id == current_user.id,
    ).first()
    if not incidente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incidente no encontrado")

    if incidente.estado != "pendiente":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El incidente ya tiene un taller asignado.",
        )

    candidatos = asignacion_service.candidatos_para_incidente(
        incidente, db, cliente_id=current_user.id
    )
    return candidatos


@router.post("/{incidente_id}/seleccionar-taller", response_model=IncidenteResponse)
def seleccionar_taller(
    incidente_id: UUID,
    body: SeleccionarTallerBody,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_cliente),
):
    """
    CU-20 — El cliente elige manualmente un taller de la lista de candidatos.
    Crea la asignación y notifica al taller seleccionado.
    """
    incidente = db.query(Incidente).filter(
        Incidente.id == incidente_id,
        Incidente.cliente_id == current_user.id,
    ).first()
    if not incidente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incidente no encontrado")

    if incidente.estado != "pendiente":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El incidente ya tiene un taller asignado.",
        )

    ya_tiene = db.query(Asignacion).filter(
        Asignacion.incidente_id == incidente_id,
        Asignacion.accion_taller.in_([None, "aceptado"]),
        Asignacion.completado_en == None,  # noqa: E711
    ).first()
    if ya_tiene:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este incidente ya tiene una asignación activa.",
        )

    asignacion_service.asignar_especifico(incidente, body.taller_id, db)
    db.commit()
    db.refresh(incidente)
    return incidente


@router.post("/{incidente_id}/asignar-automatico", response_model=IncidenteResponse)
def asignar_automatico(
    incidente_id: UUID,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_cliente),
):
    """
    CU-20 — El cliente deja que el sistema elija el mejor taller automáticamente.
    El sistema intentará el más cercano y compatible; si rechaza, pasa al siguiente.
    """
    incidente = db.query(Incidente).filter(
        Incidente.id == incidente_id,
        Incidente.cliente_id == current_user.id,
    ).first()
    if not incidente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incidente no encontrado")

    if incidente.estado != "pendiente":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El incidente ya tiene un taller asignado.",
        )

    ya_tiene = db.query(Asignacion).filter(
        Asignacion.incidente_id == incidente_id,
        Asignacion.accion_taller.in_([None, "aceptado"]),
        Asignacion.completado_en == None,  # noqa: E711
    ).first()
    if ya_tiene:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este incidente ya tiene una asignación activa.",
        )

    try:
        asignacion_service.asignar(incidente, db)
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No hay talleres disponibles en este momento. Intenta de nuevo en unos minutos.",
        )

    db.commit()
    db.refresh(incidente)
    return incidente


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
        asignacion.completado_en = now_bo()
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
            asignacion.completado_en = now_bo()
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

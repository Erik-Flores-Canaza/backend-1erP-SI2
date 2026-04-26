from datetime import time as dtime
from app.core.timezone import now_bo
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db, require_admin_taller, require_tecnico
from app.models.asignacion import Asignacion
from app.models.incidente import Incidente
from app.models.taller import Taller
from app.models.tecnico import Tecnico
from app.models.turno_tecnico import TurnoTecnico
from app.models.usuario import Usuario
from app.schemas.asignacion import AsignacionResponse, OrdenActivaTecnicoResponse
from app.schemas.tecnico import TecnicoCreate, TecnicoResponse, TecnicoUpdate
from app.schemas.turno_tecnico import TurnoCreate, TurnoResponse, DIAS_SEMANA
from app.services.tecnico_service import crear_tecnico


class UbicacionUpdate(BaseModel):
    latitud: float
    longitud: float

router = APIRouter(prefix="/tecnicos", tags=["Técnicos"])


# ---------------------------------------------------------------------------
# GET /tecnicos/me — perfil del técnico autenticado + asignación activa
# IMPORTANTE: debe declararse ANTES que /{tecnico_id} para que FastAPI
# no interprete "me" como un UUID.
# ---------------------------------------------------------------------------

@router.get("/me", response_model=TecnicoResponse)
def get_my_perfil(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_tecnico),
):
    """Devuelve el perfil del técnico autenticado."""
    tecnico = db.query(Tecnico).filter(Tecnico.usuario_id == current_user.id).first()
    if not tecnico:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No tienes un perfil de técnico registrado.",
        )
    return tecnico


@router.get("/me/servicios", response_model=list)
def get_mis_servicios(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_tecnico),
):
    """
    Devuelve el historial de órdenes completadas por el técnico autenticado,
    incluyendo el estado e importe del pago asociado.
    """
    from app.models.pago import Pago
    from app.models.usuario import Usuario as UsuarioModel
    from app.schemas.pago import ServicioTecnicoItem

    tecnico = db.query(Tecnico).filter(Tecnico.usuario_id == current_user.id).first()
    if not tecnico:
        return []

    asignaciones = (
        db.query(Asignacion)
        .join(Incidente, Asignacion.incidente_id == Incidente.id)
        .filter(
            Asignacion.tecnico_id == tecnico.id,
            Asignacion.accion_taller == "aceptado",
            Asignacion.completado_en != None,  # noqa: E711
        )
        .order_by(Asignacion.completado_en.desc())
        .all()
    )

    resultado = []
    for asig in asignaciones:
        inc: Incidente = asig.incidente
        cliente = db.query(UsuarioModel).filter(UsuarioModel.id == inc.cliente_id).first()
        pago = db.query(Pago).filter(Pago.incidente_id == inc.id).first()
        resultado.append(
            ServicioTecnicoItem(
                incidente_id=inc.id,
                cliente_nombre=cliente.nombre_completo if cliente else "–",
                clasificacion_ia=inc.clasificacion_ia,
                prioridad=inc.prioridad,
                completado_en=asig.completado_en,
                pago_estado=pago.estado if pago else None,
                pago_monto=pago.monto_total if pago else None,
                pago_metodo=pago.metodo_pago if pago else None,
            )
        )
    return resultado


@router.get("/me/orden-activa", response_model=OrdenActivaTecnicoResponse | None)
def get_orden_activa(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_tecnico),
):
    """
    Devuelve la asignación activa del técnico autenticado
    (accion_taller='aceptado', completado_en IS NULL, incidente no atendido/cancelado).
    Retorna null si no hay orden activa.
    """
    tecnico = db.query(Tecnico).filter(Tecnico.usuario_id == current_user.id).first()
    if not tecnico:
        return None

    asignacion = (
        db.query(Asignacion)
        .join(Incidente, Asignacion.incidente_id == Incidente.id)
        .filter(
            Asignacion.tecnico_id == tecnico.id,
            Asignacion.accion_taller == "aceptado",
            Asignacion.completado_en == None,           # noqa: E711
            Incidente.estado.in_(["pendiente", "en_proceso"]),
        )
        .first()
    )
    return asignacion


def _get_tecnico_del_admin(tecnico_id: UUID, current_user: Usuario, db: Session) -> Tecnico:
    tecnico = (
        db.query(Tecnico)
        .join(Taller, Tecnico.taller_id == Taller.id)
        .filter(Tecnico.id == tecnico_id, Taller.administrador_id == current_user.id)
        .first()
    )
    if not tecnico:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Técnico no encontrado")
    return tecnico


@router.post("", response_model=TecnicoResponse, status_code=status.HTTP_201_CREATED)
def create_tecnico(
    body: TecnicoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin_taller),
):
    return crear_tecnico(db, body, current_user.id)


@router.patch("/{tecnico_id}", response_model=TecnicoResponse)
def update_tecnico(
    tecnico_id: UUID,
    body: TecnicoUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin_taller),
):
    tecnico = _get_tecnico_del_admin(tecnico_id, current_user, db)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(tecnico, field, value)
    db.commit()
    db.refresh(tecnico)
    return tecnico


@router.delete("/{tecnico_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tecnico(
    tecnico_id: UUID,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin_taller),
):
    tecnico = _get_tecnico_del_admin(tecnico_id, current_user, db)
    db.delete(tecnico)
    db.commit()


def _turno_to_response(turno: TurnoTecnico) -> TurnoResponse:
    return TurnoResponse.from_orm_with_nombre(turno)


@router.post("/{tecnico_id}/turnos", response_model=TurnoResponse, status_code=status.HTTP_201_CREATED)
def create_turno(
    tecnico_id: UUID,
    body: TurnoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin_taller),
):
    tecnico = _get_tecnico_del_admin(tecnico_id, current_user, db)
    # Evitar duplicado del mismo día
    existente = db.query(TurnoTecnico).filter(
        TurnoTecnico.tecnico_id == tecnico.id,
        TurnoTecnico.dia_semana == body.dia_semana,
    ).first()
    if existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un turno para {DIAS_SEMANA[body.dia_semana]}. Elimínalo primero.",
        )
    turno = TurnoTecnico(tecnico_id=tecnico.id, **body.model_dump())
    db.add(turno)
    db.commit()
    db.refresh(turno)
    return _turno_to_response(turno)


@router.get("/{tecnico_id}/turnos", response_model=list[TurnoResponse])
def list_turnos(
    tecnico_id: UUID,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    if not db.query(Tecnico).filter(Tecnico.id == tecnico_id).first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Técnico no encontrado")
    turnos = db.query(TurnoTecnico).filter(
        TurnoTecnico.tecnico_id == tecnico_id,
    ).order_by(TurnoTecnico.dia_semana).all()
    return [_turno_to_response(t) for t in turnos]


@router.delete("/{tecnico_id}/turnos/{turno_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_turno(
    tecnico_id: UUID,
    turno_id: UUID,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin_taller),
):
    tecnico = _get_tecnico_del_admin(tecnico_id, current_user, db)
    turno = db.query(TurnoTecnico).filter(
        TurnoTecnico.id == turno_id,
        TurnoTecnico.tecnico_id == tecnico.id,
    ).first()
    if not turno:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turno no encontrado")
    db.delete(turno)
    db.commit()


# ---------------------------------------------------------------------------
# Admin solicita al técnico que actualice su ubicación
# ---------------------------------------------------------------------------

@router.post("/{tecnico_id}/solicitar-ubicacion", status_code=status.HTTP_200_OK)
def solicitar_ubicacion(
    tecnico_id: UUID,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin_taller),
):
    """
    El admin le envía una notificación al técnico pidiéndole que
    abra la app y actualice su ubicación GPS.
    """
    tecnico = _get_tecnico_del_admin(tecnico_id, current_user, db)
    from app.services import notificacion_service
    from app.models.taller import Taller as TallerModel
    taller = db.query(TallerModel).filter(TallerModel.administrador_id == current_user.id).first()
    nombre_taller = taller.nombre if taller else "El taller"
    notificacion_service._crear(
        db,
        usuario_id=tecnico.usuario_id,
        titulo="Actualiza tu ubicación",
        cuerpo=f"{nombre_taller} necesita conocer tu ubicación. Abre la app y actualízala.",
    )
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# CU-16: Actualizar ubicación del técnico en tiempo real
# ---------------------------------------------------------------------------

@router.patch("/{tecnico_id}/ubicacion", response_model=TecnicoResponse)
def actualizar_ubicacion(
    tecnico_id: UUID,
    body: UbicacionUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_tecnico),
):
    """
    CU-16 — El técnico actualiza su ubicación GPS actual.
    Solo el técnico autenticado puede actualizar su propia ubicación.
    """
    tecnico = db.query(Tecnico).filter(Tecnico.id == tecnico_id).first()
    if not tecnico:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Técnico no encontrado")

    # El técnico solo puede actualizar su propia ubicación
    if tecnico.usuario_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo puedes actualizar tu propia ubicación",
        )

    tecnico.latitud_actual = body.latitud
    tecnico.longitud_actual = body.longitud
    tecnico.ubicacion_actualizada_en = now_bo()
    db.commit()
    db.refresh(tecnico)
    return tecnico

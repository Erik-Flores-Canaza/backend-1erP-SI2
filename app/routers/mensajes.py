from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from jose import JWTError
from sqlalchemy.orm import Session, joinedload

from app.core.database import SessionLocal
from app.core.security import decode_token
from app.core.ws_manager import manager
from app.dependencies import get_current_user, get_db
from app.models.asignacion import Asignacion
from app.models.incidente import Incidente
from app.models.mensaje import Mensaje
from app.models.taller import Taller
from app.models.tecnico import Tecnico
from app.models.usuario import Usuario
from app.schemas.mensaje import MensajeResponse

# ─── Router HTTP ──────────────────────────────────────────────────────────────
http_router = APIRouter(prefix="/mensajes", tags=["Mensajes"])

# ─── Router WebSocket (registrado con prefix /ws en main.py) ─────────────────
ws_router = APIRouter(tags=["Chat WebSocket"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_user_from_token(token: str, db: Session) -> Usuario | None:
    """Decodifica el JWT y retorna el usuario activo, o None si es inválido."""
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            return None
        user_id = payload.get("sub")
        if user_id is None:
            return None
    except JWTError:
        return None

    return db.query(Usuario).filter(
        Usuario.id == UUID(user_id), Usuario.activo == True  # noqa: E712
    ).first()


def _puede_acceder_chat(usuario: Usuario, incidente: Incidente, db: Session) -> bool:
    """
    Retorna True si el usuario es:
    - el cliente dueño del incidente, o
    - el admin_taller cuyo taller está asignado (y aceptado) al incidente, o
    - el técnico asignado al incidente.
    """
    nombre_rol = usuario.rol.nombre if usuario.rol else ""

    if nombre_rol == "cliente":
        return incidente.cliente_id == usuario.id

    if nombre_rol == "admin_taller":
        taller = db.query(Taller).filter(Taller.administrador_id == usuario.id).first()
        if not taller:
            return False
        asignacion = db.query(Asignacion).filter(
            Asignacion.incidente_id == incidente.id,
            Asignacion.taller_id == taller.id,
            Asignacion.accion_taller == "aceptado",
        ).first()
        return asignacion is not None

    if nombre_rol == "tecnico":
        tecnico = db.query(Tecnico).filter(Tecnico.usuario_id == usuario.id).first()
        if not tecnico:
            return False
        asignacion = db.query(Asignacion).filter(
            Asignacion.incidente_id == incidente.id,
            Asignacion.tecnico_id == tecnico.id,
        ).first()
        return asignacion is not None

    return False


def _rol_label(usuario: Usuario) -> str:
    nombre_rol = usuario.rol.nombre if usuario.rol else ""
    if nombre_rol == "admin_taller":
        return "taller"
    if nombre_rol == "tecnico":
        return "tecnico"
    return "cliente"


def _serializar(mensaje: Mensaje, nombre_remitente: str) -> dict:
    return {
        "id": str(mensaje.id),
        "incidente_id": str(mensaje.incidente_id),
        "remitente_id": str(mensaje.remitente_id),
        "rol_remitente": mensaje.rol_remitente,
        "nombre_remitente": nombre_remitente,
        "contenido": mensaje.contenido,
        "leido": mensaje.leido,
        "creado_en": mensaje.creado_en.isoformat(),
    }


# ---------------------------------------------------------------------------
# WS /ws/chat/{incidente_id}?token={jwt}
# ---------------------------------------------------------------------------

@ws_router.websocket("/chat/{incidente_id}")
async def websocket_chat(incidente_id: UUID, websocket: WebSocket, token: str = ""):
    """
    CU-08 — Chat en tiempo real entre cliente, taller y técnico.
    Autenticación: ?token={jwt_access_token}
    """
    db: Session = SessionLocal()
    try:
        usuario = _get_user_from_token(token, db)
        if not usuario:
            await websocket.close(code=1008)
            return

        incidente = db.query(Incidente).filter(Incidente.id == incidente_id).first()
        if not incidente:
            await websocket.close(code=1008)
            return

        if not _puede_acceder_chat(usuario, incidente, db):
            await websocket.close(code=1008)
            return

        room_id = str(incidente_id)
        await manager.connect(room_id, websocket)

        try:
            while True:
                data = await websocket.receive_json()
                contenido = str(data.get("contenido", "")).strip()
                if not contenido:
                    continue

                mensaje = Mensaje(
                    incidente_id=incidente_id,
                    remitente_id=usuario.id,
                    rol_remitente=_rol_label(usuario),
                    contenido=contenido,
                )
                db.add(mensaje)
                db.commit()
                db.refresh(mensaje)

                await manager.broadcast(
                    room_id,
                    _serializar(mensaje, usuario.nombre_completo),
                )

                # Notificar al admin_taller con badge cuando el cliente o técnico escribe
                if _rol_label(usuario) in ("cliente", "tecnico"):
                    asig = db.query(Asignacion).filter(
                        Asignacion.incidente_id == incidente_id,
                        Asignacion.accion_taller == "aceptado",
                    ).first()
                    if asig:
                        taller_obj = db.query(Taller).filter(Taller.id == asig.taller_id).first()
                        if taller_obj:
                            from app.services.notificacion_service import notif_nuevo_mensaje_chat
                            notif_nuevo_mensaje_chat(taller_obj.administrador_id, incidente_id)

        except WebSocketDisconnect:
            manager.disconnect(room_id, websocket)

    finally:
        db.close()


# ---------------------------------------------------------------------------
# GET /mensajes/{incidente_id} — historial de mensajes
# ---------------------------------------------------------------------------

@http_router.get("/{incidente_id}", response_model=list[MensajeResponse])
def listar_mensajes(
    incidente_id: UUID,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """CU-08 — Historial de mensajes de un incidente."""
    incidente = db.query(Incidente).filter(Incidente.id == incidente_id).first()
    if not incidente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incidente no encontrado")

    if not _puede_acceder_chat(current_user, incidente, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin acceso a este chat")

    mensajes = (
        db.query(Mensaje)
        .options(joinedload(Mensaje.remitente))
        .filter(Mensaje.incidente_id == incidente_id)
        .order_by(Mensaje.creado_en.asc())
        .all()
    )

    return [
        MensajeResponse(
            id=m.id,
            incidente_id=m.incidente_id,
            remitente_id=m.remitente_id,
            rol_remitente=m.rol_remitente,
            nombre_remitente=m.remitente.nombre_completo if m.remitente else "Desconocido",
            contenido=m.contenido,
            leido=m.leido,
            creado_en=m.creado_en,
        )
        for m in mensajes
    ]

"""WebSocket de tracking en vivo del técnico — CU-32 (R2).

Endpoint:  WS /ws/tracking/{incidente_id}?token={jwt_access_token}

Roles permitidos a CONECTARSE:
- `tecnico`: el técnico asignado a la asignación aceptada del incidente (EMISOR)
- `cliente`: el dueño del incidente (RECEPTOR)
- `admin_taller`: admin del taller asignado al incidente (RECEPTOR)

Flujo:
1. El técnico (emisor) envía periódicamente {"latitud": X, "longitud": Y}.
2. El backend valida que el incidente sigue en estado `en_camino`. Si cambió de
   estado, envía {"tipo": "fin", "razon": "estado_cambio"} y cierra.
3. El backend persiste la última ubicación en `TECNICOS` (latitud_actual,
   longitud_actual, ubicacion_actualizada_en).
4. El backend hace broadcast a TODOS los participantes del room
   (incluido el emisor) con:
   {"tipo": "ubicacion", "latitud": X, "longitud": Y,
    "tecnico_id": "...", "incidente_id": "...", "ts": "ISO datetime"}
5. Cliente y admin_taller solo reciben — cualquier mensaje que envíen se ignora.

Razones de cierre temprano (close code 1008):
- token inválido / usuario inactivo
- incidente no existe
- usuario sin acceso (otro tenant, no es cliente owner, no es técnico asignado)
"""
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError
from sqlalchemy.orm import Session

from app.core import estado_incidente as estado_machine
from app.core.database import SessionLocal
from app.core.security import decode_token
from app.core.timezone import now_bo
from app.core.ws_manager import manager
from app.models.asignacion import Asignacion
from app.models.incidente import Incidente
from app.models.taller import Taller
from app.models.tecnico import Tecnico
from app.models.usuario import Usuario

router = APIRouter(tags=["Tracking WebSocket"])


def _get_user_from_token(token: str, db: Session) -> Usuario | None:
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            return None
        user_id = payload.get("sub")
        if user_id is None:
            return None
    except JWTError:
        return None
    return (
        db.query(Usuario)
        .filter(Usuario.id == UUID(user_id), Usuario.activo == True)  # noqa: E712
        .first()
    )


def _resolver_acceso(
    usuario: Usuario, incidente: Incidente, db: Session
) -> tuple[bool, str]:
    """Determina si el usuario puede conectarse y bajo qué rol.

    Retorna (allow, role_label) donde role_label es:
      - "tecnico_emisor": el técnico asignado a este incidente (puede emitir)
      - "cliente": el dueño del incidente (solo recibe)
      - "admin_taller": admin del taller asignado (solo recibe)
      - "" si no autorizado
    """
    rol = usuario.rol.nombre if usuario.rol else ""

    if rol == "cliente":
        if incidente.cliente_id == usuario.id:
            return True, "cliente"
        return False, ""

    if rol == "tecnico":
        tecnico = (
            db.query(Tecnico).filter(Tecnico.usuario_id == usuario.id).first()
        )
        if not tecnico:
            return False, ""
        asignacion = (
            db.query(Asignacion)
            .filter(
                Asignacion.incidente_id == incidente.id,
                Asignacion.tecnico_id == tecnico.id,
                Asignacion.accion_taller == "aceptado",
            )
            .first()
        )
        if asignacion:
            return True, "tecnico_emisor"
        return False, ""

    if rol == "admin_taller":
        taller_ids = [
            r[0]
            for r in db.query(Taller.id)
            .filter(Taller.administrador_id == usuario.id)
            .all()
        ]
        if not taller_ids:
            return False, ""
        asignacion = (
            db.query(Asignacion)
            .filter(
                Asignacion.incidente_id == incidente.id,
                Asignacion.taller_id.in_(taller_ids),
                Asignacion.accion_taller == "aceptado",
            )
            .first()
        )
        if asignacion:
            return True, "admin_taller"
        return False, ""

    return False, ""


@router.websocket("/tracking/{incidente_id}")
async def websocket_tracking(
    incidente_id: UUID, websocket: WebSocket, token: str = ""
):
    """CU-32 — Tracking en vivo del técnico."""
    db: Session = SessionLocal()
    try:
        usuario = _get_user_from_token(token, db)
        if not usuario:
            await websocket.close(code=1008)
            return

        incidente = (
            db.query(Incidente).filter(Incidente.id == incidente_id).first()
        )
        if not incidente:
            await websocket.close(code=1008)
            return

        allowed, role = _resolver_acceso(usuario, incidente, db)
        if not allowed:
            await websocket.close(code=1008)
            return

        room_id = f"tracking:{incidente_id}"
        await manager.connect(room_id, websocket)

        try:
            while True:
                # Bloquea hasta recibir un mensaje O hasta WebSocketDisconnect
                data = await websocket.receive_json()

                # Cliente y admin_taller son solo receptores: cualquier mensaje
                # entrante se ignora (lo dejamos abierto para detectar disconnect).
                if role != "tecnico_emisor":
                    continue

                # Validar payload del técnico
                try:
                    lat = float(data["latitud"])
                    lng = float(data["longitud"])
                except (KeyError, TypeError, ValueError):
                    await websocket.send_json(
                        {"tipo": "error", "razon": "payload_invalido"}
                    )
                    continue

                # Recargar incidente — el estado puede haber cambiado
                inc = (
                    db.query(Incidente)
                    .filter(Incidente.id == incidente_id)
                    .first()
                )
                if not inc or inc.estado != estado_machine.EN_CAMINO:
                    await websocket.send_json(
                        {"tipo": "fin", "razon": "estado_cambio"}
                    )
                    break

                # Persistir última ubicación del técnico
                tecnico = (
                    db.query(Tecnico)
                    .filter(Tecnico.usuario_id == usuario.id)
                    .first()
                )
                tecnico_id_str = None
                if tecnico:
                    tecnico.latitud_actual = lat
                    tecnico.longitud_actual = lng
                    tecnico.ubicacion_actualizada_en = now_bo()
                    db.commit()
                    tecnico_id_str = str(tecnico.id)

                # Broadcast a todos los suscriptores del room
                await manager.broadcast(
                    room_id,
                    {
                        "tipo": "ubicacion",
                        "latitud": lat,
                        "longitud": lng,
                        "tecnico_id": tecnico_id_str,
                        "incidente_id": str(incidente_id),
                        "ts": now_bo().isoformat(),
                    },
                )

        except WebSocketDisconnect:
            manager.disconnect(room_id, websocket)

    finally:
        db.close()

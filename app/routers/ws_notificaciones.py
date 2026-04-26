"""
WebSocket de notificaciones por usuario — CU-21
Endpoint: /ws/notificaciones?token={jwt}

El cliente (panel web Angular) se conecta al autenticarse.
El backend emite eventos JSON cuando ocurre algo relevante para ese usuario.
"""
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from jose import JWTError
from app.core.security import decode_token
from app.core.ws_manager import user_manager

router = APIRouter(tags=["Notificaciones WebSocket"])


@router.websocket("/notificaciones")
async def ws_notificaciones(websocket: WebSocket, token: str = ""):
    """
    Conexión WebSocket autenticada por JWT via query param ?token=...
    Emite notificaciones en tiempo real al usuario conectado.
    """
    # Validar token
    if not token:
        await websocket.close(code=1008)
        return

    try:
        payload = decode_token(token)
    except JWTError:
        await websocket.close(code=1008)
        return

    usuario_id: str = payload.get("sub", "")
    if not usuario_id:
        await websocket.close(code=1008)
        return

    await user_manager.connect(usuario_id, websocket)
    try:
        # Mantener viva la conexión — el servidor solo envía, no recibe
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        user_manager.disconnect(usuario_id, websocket)

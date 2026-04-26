from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    """
    Gestor de conexiones WebSocket agrupadas por incidente_id.
    Singleton: importar la instancia `manager` en lugar de instanciar la clase.
    """

    def __init__(self) -> None:
        # incidente_id (int/UUID como str) → lista de websockets activos
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, incidente_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        if incidente_id not in self.active_connections:
            self.active_connections[incidente_id] = []
        self.active_connections[incidente_id].append(websocket)

    def disconnect(self, incidente_id: str, websocket: WebSocket) -> None:
        room = self.active_connections.get(incidente_id, [])
        if websocket in room:
            room.remove(websocket)
        if not room:
            self.active_connections.pop(incidente_id, None)

    async def broadcast(self, incidente_id: str, message: dict[str, Any]) -> None:
        """Envía un mensaje JSON a todos los participantes del incidente."""
        for ws in list(self.active_connections.get(incidente_id, [])):
            try:
                await ws.send_json(message)
            except Exception:
                # Si el envío falla, el cliente se desconectó; lo limpiamos
                self.disconnect(incidente_id, ws)


# Singleton compartido por toda la aplicación
manager = ConnectionManager()


class UserConnectionManager:
    """
    Gestor de conexiones WebSocket agrupadas por usuario_id.
    Usado para notificaciones en tiempo real al panel web (admin_taller).
    """

    def __init__(self) -> None:
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, usuario_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        if usuario_id not in self.active_connections:
            self.active_connections[usuario_id] = []
        self.active_connections[usuario_id].append(websocket)

    def disconnect(self, usuario_id: str, websocket: WebSocket) -> None:
        room = self.active_connections.get(usuario_id, [])
        if websocket in room:
            room.remove(websocket)
        if not room:
            self.active_connections.pop(usuario_id, None)

    async def send(self, usuario_id: str, message: dict[str, Any]) -> None:
        """Envía un mensaje JSON a todas las conexiones activas del usuario."""
        for ws in list(self.active_connections.get(usuario_id, [])):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(usuario_id, ws)


# Singleton para notificaciones por usuario
user_manager = UserConnectionManager()

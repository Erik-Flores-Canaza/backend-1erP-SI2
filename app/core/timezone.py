"""
Zona horaria oficial del sistema: Bolivia (UTC-4, sin horario de verano).
Usar `now_bo()` en todo el backend en lugar de `datetime.now(timezone.utc)`.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

TZ_BOLIVIA = ZoneInfo("America/La_Paz")


def now_bo() -> datetime:
    """Retorna la hora actual en zona horaria de Bolivia (UTC-4)."""
    return datetime.now(TZ_BOLIVIA)

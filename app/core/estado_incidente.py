"""Máquina de estados extendida del incidente — CU-31.

7 estados oficiales según el examen:

    pendiente → buscando_taller → taller_asignado → en_camino → en_atencion → finalizado
        |              |                |              |             |
        └──────────────┴────────────────┴──────────────┘             ╳ (no cancelable)
                                                                     │
                                                  cancelado ← ─ ─ ─ ─┘

Reglas:
- `pendiente`         : cliente acaba de reportar, sin taller aún.
- `buscando_taller`   : IA terminó, se notifica a candidatos (o sistema busca).
- `taller_asignado`   : un taller aceptó la solicitud y queda comprometido.
- `en_camino`         : el técnico salió del taller hacia el cliente.
- `en_atencion`       : el técnico llegó al sitio y está atendiendo.
- `finalizado`        : servicio completado.
- `cancelado`         : abortado antes de `en_atencion` (no se puede cancelar
                        un servicio ya iniciado en sitio).

Estados finales: `finalizado` y `cancelado` (sin salida).
"""

PENDIENTE = "pendiente"
BUSCANDO_TALLER = "buscando_taller"
TALLER_ASIGNADO = "taller_asignado"
EN_CAMINO = "en_camino"
EN_ATENCION = "en_atencion"
FINALIZADO = "finalizado"
CANCELADO = "cancelado"

ESTADOS_VALIDOS: frozenset[str] = frozenset({
    PENDIENTE, BUSCANDO_TALLER, TALLER_ASIGNADO,
    EN_CAMINO, EN_ATENCION, FINALIZADO, CANCELADO,
})

# Estados donde el incidente sigue vivo (puede recibir cambios). Útil para queries.
ESTADOS_ACTIVOS: frozenset[str] = frozenset({
    PENDIENTE, BUSCANDO_TALLER, TALLER_ASIGNADO, EN_CAMINO, EN_ATENCION,
})

# Estados terminales. No se pueden transicionar.
ESTADOS_CERRADOS: frozenset[str] = frozenset({FINALIZADO, CANCELADO})

# Mapa de transiciones permitidas: clave = estado actual, valor = conjunto de estados destino válidos.
TRANSICIONES_PERMITIDAS: dict[str, frozenset[str]] = {
    PENDIENTE:        frozenset({BUSCANDO_TALLER, CANCELADO}),
    BUSCANDO_TALLER:  frozenset({TALLER_ASIGNADO, CANCELADO}),
    TALLER_ASIGNADO:  frozenset({EN_CAMINO, CANCELADO}),
    EN_CAMINO:        frozenset({EN_ATENCION, CANCELADO}),
    EN_ATENCION:      frozenset({FINALIZADO}),  # ya no se puede cancelar
    FINALIZADO:       frozenset(),
    CANCELADO:        frozenset(),
}


def es_estado_valido(estado: str) -> bool:
    return estado in ESTADOS_VALIDOS


def es_transicion_valida(actual: str, nuevo: str) -> bool:
    """True si pasar de `actual` a `nuevo` está permitido por la máquina de estados."""
    if actual not in TRANSICIONES_PERMITIDAS:
        return False
    return nuevo in TRANSICIONES_PERMITIDAS[actual]


def puede_cancelar(estado: str) -> bool:
    """Indica si el incidente puede ser cancelado desde el estado actual."""
    return estado in {PENDIENTE, BUSCANDO_TALLER, TALLER_ASIGNADO, EN_CAMINO}


def es_estado_activo(estado: str) -> bool:
    return estado in ESTADOS_ACTIVOS


def es_estado_cerrado(estado: str) -> bool:
    return estado in ESTADOS_CERRADOS

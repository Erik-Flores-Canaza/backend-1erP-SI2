from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# CU-15: Historial enriquecido y métricas
# ---------------------------------------------------------------------------

class TecnicoEnHistorial(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nombre_completo: str = ""

    @classmethod
    def from_tecnico(cls, tecnico) -> "TecnicoEnHistorial":
        nombre = tecnico.usuario.nombre_completo if tecnico and tecnico.usuario else ""
        return cls(id=tecnico.id, nombre_completo=nombre)


class HistorialItemResponse(BaseModel):
    incidente_id: UUID
    fecha: datetime
    clasificacion_ia: str | None
    prioridad: str
    tecnico: TecnicoEnHistorial | None
    duracion_minutos: float | None
    estado_final: str
    pago_monto_neto: float | None   # neto que recibió el taller
    pago_estado: str | None         # 'pagado' | None


class AtencionesPorTipo(BaseModel):
    clasificacion: str
    total: int


class AtencionesPorMes(BaseModel):
    anio: int
    mes: int
    total: int


class IngresosPorMes(BaseModel):
    anio: int
    mes: int
    total: float


class MetricasTallerResponse(BaseModel):
    total_atenciones: int
    tiempo_promedio_respuesta: float | None
    tasa_aceptacion: float | None
    atenciones_por_tipo: list[AtencionesPorTipo]
    atenciones_por_mes: list[AtencionesPorMes]
    ingresos_neto_total: float
    servicios_cobrados: int
    servicios_pendientes_cobro: int
    ingresos_por_mes: list[IngresosPorMes]


# ---------------------------------------------------------------------------
# Schemas CRUD del taller
# ---------------------------------------------------------------------------

class TallerCreate(BaseModel):
    nombre: str
    direccion: str | None = None
    latitud: float | None = None
    longitud: float | None = None


class TallerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    administrador_id: UUID
    nombre: str
    direccion: str | None
    latitud: float | None
    longitud: float | None
    porcentaje_comision: float
    activo: bool
    disponible: bool
    # CU-23: estado de aprobación del taller
    estado_aprobacion: str | None
    motivo_rechazo: str | None
    creado_en: datetime


class TallerUpdate(BaseModel):
    nombre: str | None = None
    direccion: str | None = None
    latitud: float | None = None
    longitud: float | None = None
    disponible: bool | None = None


# ---------------------------------------------------------------------------
# CU-27: Métricas consolidadas de todas las sucursales de un admin_taller
# ---------------------------------------------------------------------------

class MetricasSucursalResumen(BaseModel):
    """Resumen de métricas de una sucursal individual dentro del consolidado."""
    taller_id: UUID
    nombre: str
    total_atenciones: int
    tasa_aceptacion: float | None
    ingresos_neto_total: float


class MetricasConsolidadasResponse(BaseModel):
    """Respuesta de GET /talleres/metricas — suma de todas las sucursales."""
    total_sucursales: int
    total_atenciones: int
    ingresos_neto_total: float
    tasa_aceptacion_global: float | None
    por_sucursal: list[MetricasSucursalResumen]

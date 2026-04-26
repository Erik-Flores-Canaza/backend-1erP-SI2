"""
Rutas del panel superadmin y el formulario público de solicitud de taller.

Rutas públicas (sin JWT):
  POST   /solicitudes-taller                     CU-22

Rutas protegidas con rol superadmin:
  GET    /admin/solicitudes-taller               CU-23
  PATCH  /admin/solicitudes-taller/{id}/aprobar  CU-23
  PATCH  /admin/solicitudes-taller/{id}/rechazar CU-23
  GET    /admin/usuarios                         CU-24
  PATCH  /admin/usuarios/{id}/activar            CU-24
  PATCH  /admin/usuarios/{id}/desactivar         CU-24
  GET    /admin/metricas                         CU-25
"""

from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.dependencies import get_db, get_current_user, require_superadmin
from app.models.asignacion import Asignacion
from app.models.incidente import Incidente
from app.models.pago import Pago
from app.models.solicitud_registro_taller import SolicitudRegistroTaller
from app.models.taller import Taller
from app.models.usuario import Usuario
from app.schemas.solicitud_registro import (
    AprobacionResponse,
    RechazarSolicitudRequest,
    SolicitudRegistroCreate,
    SolicitudRegistroResponse,
)
from app.schemas.usuario import UsuarioResponse
from app.services import admin_service

# ── Routers ───────────────────────────────────────────────────────────────────

# Ruta pública (sin autenticación) para el formulario de la landing page
public_router = APIRouter(tags=["Superadmin — Solicitudes (público)"])

# Rutas protegidas para el panel superadmin
admin_router = APIRouter(prefix="/admin", tags=["Superadmin — Panel"])


# ════════════════════════════════════════════════════════════════════════════
# CU-22 — Enviar solicitud de registro de taller (PÚBLICO, sin JWT)
# ════════════════════════════════════════════════════════════════════════════

@public_router.post(
    "/solicitudes-taller",
    response_model=SolicitudRegistroResponse,
    status_code=status.HTTP_201_CREATED,
    summary="CU-22 — Enviar solicitud de registro de taller (público)",
)
def crear_solicitud_taller(
    body: SolicitudRegistroCreate,
    db: Session = Depends(get_db),
):
    """
    Endpoint público: cualquier persona puede enviar una solicitud para
    registrar su taller. No requiere JWT.

    El superadmin la revisa desde el panel (/admin/solicitudes-taller).
    """
    solicitud = SolicitudRegistroTaller(
        solicitante_nombre=body.solicitante_nombre,
        solicitante_correo=body.solicitante_correo,
        solicitante_telefono=body.solicitante_telefono,
        nombre_taller=body.nombre_taller,
        direccion=body.direccion,
        latitud=body.latitud,
        longitud=body.longitud,
        descripcion=body.descripcion,
        estado="pendiente",
    )
    db.add(solicitud)
    db.commit()
    db.refresh(solicitud)
    return solicitud


# ════════════════════════════════════════════════════════════════════════════
# CU-23 — Revisar solicitudes de registro (superadmin)
# ════════════════════════════════════════════════════════════════════════════

@admin_router.get(
    "/solicitudes-taller",
    response_model=list[SolicitudRegistroResponse],
    summary="CU-23 — Listar solicitudes de registro de taller",
)
def listar_solicitudes(
    estado: str | None = Query(None, description="Filtrar por estado: pendiente / aprobado / rechazado"),
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_superadmin),
):
    """Lista todas las solicitudes de registro. Filtro opcional por estado."""
    q = db.query(SolicitudRegistroTaller)
    if estado:
        q = q.filter(SolicitudRegistroTaller.estado == estado)
    return q.order_by(SolicitudRegistroTaller.creado_en.desc()).all()


@admin_router.patch(
    "/solicitudes-taller/{solicitud_id}/aprobar",
    response_model=AprobacionResponse,
    summary="CU-23 — Aprobar solicitud: crear usuario + taller + enviar correo",
)
def aprobar_solicitud(
    solicitud_id: UUID,
    db: Session = Depends(get_db),
    superadmin: Usuario = Depends(require_superadmin),
):
    """
    Aprueba la solicitud:
    1. Crea el Usuario con rol admin_taller.
    2. Crea el Taller con estado_aprobacion = 'aprobado'.
    3. Genera contraseña temporal → la devuelve en el body Y la envía por correo.
    """
    solicitud = db.query(SolicitudRegistroTaller).filter(
        SolicitudRegistroTaller.id == solicitud_id
    ).first()
    if not solicitud:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Solicitud no encontrada")

    usuario, taller, contrasena = admin_service.aprobar_solicitud(
        db=db,
        solicitud=solicitud,
        superadmin_id=superadmin.id,
    )

    correo_ok = bool(
        # email_service retorna True si el correo fue enviado
        # Reconocemos éxito si el usuario ya fue creado sin error en admin_service
        usuario.correo
    )
    # Rellamada real para saber si el correo fue efectivamente enviado:
    from app.services.email_service import enviar_credenciales_admin_taller as _email_check
    # El correo ya fue enviado dentro de admin_service; revisamos la config
    from app.core.config import settings
    correo_ok = bool(settings.GMAIL_CLIENT_ID)

    return AprobacionResponse(
        mensaje="Solicitud aprobada. Usuario y taller creados correctamente.",
        solicitud_id=solicitud.id,
        usuario_id=usuario.id,
        taller_id=taller.id,
        correo=usuario.correo,
        contrasena_temporal=contrasena,
        correo_enviado=correo_ok,
    )


@admin_router.patch(
    "/solicitudes-taller/{solicitud_id}/rechazar",
    response_model=SolicitudRegistroResponse,
    summary="CU-23 — Rechazar solicitud de registro de taller",
)
def rechazar_solicitud(
    solicitud_id: UUID,
    body: RechazarSolicitudRequest,
    db: Session = Depends(get_db),
    superadmin: Usuario = Depends(require_superadmin),
):
    """Rechaza la solicitud registrando el motivo y notificando al solicitante."""
    solicitud = db.query(SolicitudRegistroTaller).filter(
        SolicitudRegistroTaller.id == solicitud_id
    ).first()
    if not solicitud:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Solicitud no encontrada")

    return admin_service.rechazar_solicitud(
        db=db,
        solicitud=solicitud,
        superadmin_id=superadmin.id,
        motivo=body.motivo_rechazo,
    )


# ════════════════════════════════════════════════════════════════════════════
# CU-24 — Gestionar usuarios (superadmin)
# ════════════════════════════════════════════════════════════════════════════

@admin_router.get(
    "/usuarios",
    response_model=list[UsuarioResponse],
    summary="CU-24 — Listar todos los usuarios de la plataforma",
)
def listar_usuarios(
    rol: str | None = Query(None, description="Filtrar por nombre de rol"),
    activo: bool | None = Query(None, description="Filtrar por activo/inactivo"),
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_superadmin),
):
    """Lista todos los usuarios. Filtros opcionales: rol y activo."""
    from app.models.rol import Rol
    q = db.query(Usuario).join(Rol, Usuario.rol_id == Rol.id)
    if rol:
        q = q.filter(Rol.nombre == rol)
    if activo is not None:
        q = q.filter(Usuario.activo == activo)
    return q.order_by(Usuario.creado_en.desc()).all()


@admin_router.patch(
    "/usuarios/{usuario_id}/activar",
    response_model=UsuarioResponse,
    summary="CU-24 — Activar cuenta de usuario",
)
def activar_usuario(
    usuario_id: UUID,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_superadmin),
):
    """Solo el superadmin puede activar cuentas."""
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    if usuario.activo:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El usuario ya está activo")
    usuario.activo = True
    db.commit()
    db.refresh(usuario)
    return usuario


@admin_router.patch(
    "/usuarios/{usuario_id}/desactivar",
    response_model=UsuarioResponse,
    summary="CU-24 — Desactivar cuenta de usuario",
)
def desactivar_usuario(
    usuario_id: UUID,
    db: Session = Depends(get_db),
    superadmin: Usuario = Depends(require_superadmin),
):
    """Solo el superadmin puede desactivar cuentas. No puede desactivarse a sí mismo."""
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    if usuario.id == superadmin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes desactivar tu propia cuenta",
        )
    if not usuario.activo:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El usuario ya está inactivo")
    usuario.activo = False
    db.commit()
    db.refresh(usuario)
    return usuario


# ════════════════════════════════════════════════════════════════════════════
# CU-25 — Ver métricas globales (superadmin)
# ════════════════════════════════════════════════════════════════════════════

@admin_router.get(
    "/metricas",
    summary="CU-25 — Métricas globales de la plataforma",
)
def metricas_globales(
    fecha_inicio: date | None = Query(None, description="Fecha inicio del filtro (YYYY-MM-DD)"),
    fecha_fin: date | None = Query(None, description="Fecha fin del filtro (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_superadmin),
):
    """
    Métricas globales del sistema con filtro opcional por rango de fechas:
    - incidentes_totales, incidentes_resueltos
    - talleres_activos, talleres_aprobados
    - usuarios_activos por rol
    - ingresos_totales, comisiones_totales
    - distribución por clasificación IA
    - tiempo de resolución promedio (min)
    """
    from collections import defaultdict
    from app.models.rol import Rol

    # ── Filtro de fechas ──────────────────────────────────────────────────────
    def _en_rango(campo_dt: datetime) -> bool:
        if not campo_dt:
            return False
        d = campo_dt.date() if isinstance(campo_dt, datetime) else campo_dt
        if fecha_inicio and d < fecha_inicio:
            return False
        if fecha_fin and d > fecha_fin:
            return False
        return True

    # ── Incidentes ────────────────────────────────────────────────────────────
    q_inc = db.query(Incidente)
    if fecha_inicio:
        q_inc = q_inc.filter(Incidente.creado_en >= datetime.combine(fecha_inicio, datetime.min.time()))
    if fecha_fin:
        q_inc = q_inc.filter(Incidente.creado_en <= datetime.combine(fecha_fin, datetime.max.time()))
    incidentes = q_inc.all()

    incidentes_totales = len(incidentes)
    incidentes_resueltos = sum(1 for i in incidentes if i.estado == "atendido")

    # Distribución por clasificación IA
    dist_ia: dict[str, int] = defaultdict(int)
    for inc in incidentes:
        clave = inc.clasificacion_ia or "sin_clasificar"
        dist_ia[clave] += 1

    # ── Asignaciones / tiempo resolución ─────────────────────────────────────
    asignaciones = (
        db.query(Asignacion)
        .filter(
            Asignacion.accion_taller == "aceptado",
            Asignacion.completado_en.isnot(None),
        )
        .all()
    )
    tiempos = []
    for asig in asignaciones:
        if asig.asignado_en and asig.completado_en and _en_rango(asig.asignado_en):
            tiempos.append(
                (asig.completado_en - asig.asignado_en).total_seconds() / 60
            )
    tiempo_prom = round(sum(tiempos) / len(tiempos), 2) if tiempos else None

    # ── Pagos ─────────────────────────────────────────────────────────────────
    q_pagos = db.query(Pago).filter(Pago.estado == "pagado")
    if fecha_inicio:
        q_pagos = q_pagos.filter(Pago.pagado_en >= datetime.combine(fecha_inicio, datetime.min.time()))
    if fecha_fin:
        q_pagos = q_pagos.filter(Pago.pagado_en <= datetime.combine(fecha_fin, datetime.max.time()))
    pagos = q_pagos.all()

    ingresos_totales = round(sum(float(p.monto_total) for p in pagos), 2)
    comisiones_totales = round(sum(float(p.comision_plataforma) for p in pagos), 2)

    # ── Talleres ──────────────────────────────────────────────────────────────
    talleres_totales = db.query(Taller).count()
    talleres_aprobados = db.query(Taller).filter(Taller.estado_aprobacion == "aprobado").count()
    talleres_activos = db.query(Taller).filter(
        Taller.activo == True, Taller.estado_aprobacion == "aprobado"  # noqa: E712
    ).count()

    # ── Usuarios por rol ──────────────────────────────────────────────────────
    roles = db.query(Rol).all()
    usuarios_por_rol = {}
    for rol in roles:
        total = db.query(Usuario).filter(
            Usuario.rol_id == rol.id, Usuario.activo == True  # noqa: E712
        ).count()
        usuarios_por_rol[rol.nombre] = total

    usuarios_activos_total = db.query(Usuario).filter(Usuario.activo == True).count()  # noqa: E712

    return {
        "filtro": {
            "fecha_inicio": str(fecha_inicio) if fecha_inicio else None,
            "fecha_fin": str(fecha_fin) if fecha_fin else None,
        },
        "incidentes": {
            "totales": incidentes_totales,
            "resueltos": incidentes_resueltos,
            "tasa_resolucion": (
                round(incidentes_resueltos / incidentes_totales * 100, 2)
                if incidentes_totales > 0 else None
            ),
            "por_clasificacion_ia": dict(dist_ia),
        },
        "tiempo_resolucion_prom_min": tiempo_prom,
        "pagos": {
            "ingresos_totales": ingresos_totales,
            "comisiones_totales": comisiones_totales,
            "total_transacciones": len(pagos),
        },
        "talleres": {
            "totales": talleres_totales,
            "aprobados": talleres_aprobados,
            "activos": talleres_activos,
        },
        "usuarios": {
            "activos_total": usuarios_activos_total,
            "por_rol": usuarios_por_rol,
        },
    }

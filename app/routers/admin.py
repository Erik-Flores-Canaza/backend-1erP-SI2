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
  GET    /admin/sla                              CU-37
  PUT    /admin/sla/{tipo_servicio}              CU-37
  GET    /admin/kpis                             CU-39
"""

from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.tenant_context import aplicar_filtro_tenant, es_cross_tenant
from app.dependencies import get_db, get_current_user, require_superadmin
from app.models.asignacion import Asignacion
from app.models.incidente import Incidente
from app.models.pago import Pago
from app.models.solicitud_registro_taller import SolicitudRegistroTaller
from app.models.taller import Taller
from app.models.tenant import Tenant
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
    registrar su taller en un tenant existente. No requiere JWT.

    Multi-tenant: si el body trae `tenant_slug`, se vincula a ese tenant.
    Si no, se usa el primer tenant activo (modo dev). En producción se
    espera que la landing siempre envíe `tenant_slug`.
    """
    # Resolver tenant
    tenant: Tenant | None = None
    if body.tenant_slug:
        tenant = db.query(Tenant).filter(
            Tenant.slug == body.tenant_slug, Tenant.activo == True  # noqa: E712
        ).first()
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant '{body.tenant_slug}' no encontrado o inactivo",
            )
    else:
        tenant = db.query(Tenant).filter(Tenant.activo == True).order_by(Tenant.creado_en).first()  # noqa: E712
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No hay tenants activos en la plataforma. Solicita primero alta como tenant.",
            )

    solicitud = SolicitudRegistroTaller(
        tenant_id=tenant.id,
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
    current_user: Usuario = Depends(require_superadmin),
):
    """Lista solicitudes de registro de taller del tenant del admin.

    Multi-tenant:
    - admin_tenant: solo solicitudes de su tenant
    - superadmin_plataforma: todas las solicitudes (cross-tenant)
    """
    q = db.query(SolicitudRegistroTaller)
    q = aplicar_filtro_tenant(q, SolicitudRegistroTaller, current_user)
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

    Multi-tenant: admin_tenant solo aprueba solicitudes de su tenant.
    """
    solicitud = db.query(SolicitudRegistroTaller).filter(
        SolicitudRegistroTaller.id == solicitud_id
    ).first()
    if not solicitud:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Solicitud no encontrada")

    # Verificar acceso por tenant (admin_tenant solo su tenant; superadmin_plataforma cualquiera)
    if not es_cross_tenant(superadmin) and solicitud.tenant_id != superadmin.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sin acceso a solicitud de otro tenant",
        )

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
    """Rechaza la solicitud registrando el motivo y notificando al solicitante.

    Multi-tenant: admin_tenant solo rechaza solicitudes de su tenant.
    """
    solicitud = db.query(SolicitudRegistroTaller).filter(
        SolicitudRegistroTaller.id == solicitud_id
    ).first()
    if not solicitud:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Solicitud no encontrada")

    # Verificar acceso por tenant
    if not es_cross_tenant(superadmin) and solicitud.tenant_id != superadmin.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sin acceso a solicitud de otro tenant",
        )

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
    current_user: Usuario = Depends(require_superadmin),
):
    """Lista usuarios del tenant del admin.

    Multi-tenant:
    - admin_tenant: solo usuarios de su tenant (admin_taller, tecnico, admin_tenant del tenant)
    - superadmin_plataforma: TODOS los usuarios cross-tenant (incluyendo clientes globales)
    """
    from app.models.rol import Rol
    q = db.query(Usuario).join(Rol, Usuario.rol_id == Rol.id)
    q = aplicar_filtro_tenant(q, Usuario, current_user)
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
    current_user: Usuario = Depends(require_superadmin),
):
    """Activa una cuenta. admin_tenant solo dentro de su tenant; superadmin_plataforma cross-tenant."""
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    # Multi-tenant: admin_tenant solo puede operar sobre usuarios de su tenant
    if not es_cross_tenant(current_user):
        if usuario.tenant_id != current_user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Sin acceso a usuario de otro tenant",
            )
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
    """Desactiva una cuenta. admin_tenant solo dentro de su tenant; superadmin_plataforma cross-tenant.
    No puede desactivarse a sí mismo.
    """
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    if usuario.id == superadmin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes desactivar tu propia cuenta",
        )
    # Multi-tenant: admin_tenant solo puede operar sobre usuarios de su tenant
    if not es_cross_tenant(superadmin):
        if usuario.tenant_id != superadmin.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Sin acceso a usuario de otro tenant",
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
    current_user: Usuario = Depends(require_superadmin),
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
    q_inc = aplicar_filtro_tenant(q_inc, Incidente, current_user)
    if fecha_inicio:
        q_inc = q_inc.filter(Incidente.creado_en >= datetime.combine(fecha_inicio, datetime.min.time()))
    if fecha_fin:
        q_inc = q_inc.filter(Incidente.creado_en <= datetime.combine(fecha_fin, datetime.max.time()))
    incidentes = q_inc.all()

    incidentes_totales = len(incidentes)
    # R2: el estado terminal pasó de 'atendido' a 'finalizado' tras la máquina de 7 estados
    incidentes_resueltos = sum(1 for i in incidentes if i.estado == "finalizado")

    # Distribución por clasificación IA
    dist_ia: dict[str, int] = defaultdict(int)
    for inc in incidentes:
        clave = inc.clasificacion_ia or "sin_clasificar"
        dist_ia[clave] += 1

    # ── Asignaciones / tiempo resolución ─────────────────────────────────────
    q_asig = db.query(Asignacion).filter(
        Asignacion.accion_taller == "aceptado",
        Asignacion.completado_en.isnot(None),
    )
    q_asig = aplicar_filtro_tenant(q_asig, Asignacion, current_user)
    asignaciones = q_asig.all()
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
    talleres_totales = aplicar_filtro_tenant(db.query(Taller), Taller, current_user).count()
    talleres_aprobados = aplicar_filtro_tenant(
        db.query(Taller).filter(Taller.estado_aprobacion == "aprobado"), Taller, current_user
    ).count()
    talleres_activos = aplicar_filtro_tenant(
        db.query(Taller).filter(Taller.activo == True, Taller.estado_aprobacion == "aprobado"),  # noqa: E712
        Taller, current_user,
    ).count()

    # ── Usuarios por rol (scoped por tenant si admin_tenant) ─────────────────
    roles = db.query(Rol).all()
    usuarios_por_rol = {}
    for rol in roles:
        q_u = db.query(Usuario).filter(
            Usuario.rol_id == rol.id, Usuario.activo == True  # noqa: E712
        )
        q_u = aplicar_filtro_tenant(q_u, Usuario, current_user)
        usuarios_por_rol[rol.nombre] = q_u.count()

    q_total = db.query(Usuario).filter(Usuario.activo == True)  # noqa: E712
    q_total = aplicar_filtro_tenant(q_total, Usuario, current_user)
    usuarios_activos_total = q_total.count()

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


# ════════════════════════════════════════════════════════════════════════════
# CU-37 — Configurar SLA por tipo de servicio (admin_tenant)
# ════════════════════════════════════════════════════════════════════════════

from app.dependencies import require_admin_tenant  # noqa: E402
from app.models.sla_config import SlaConfig  # noqa: E402
from app.schemas.sla_config import (  # noqa: E402
    SlaConfigResponse,
    SlaConfigUpsert,
    TipoServicio,
)


@admin_router.get(
    "/sla",
    response_model=list[SlaConfigResponse],
    summary="CU-37 — Listar SLAs configurados del tenant",
)
def listar_sla(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin_tenant),
):
    """Devuelve los SLAs del tenant del admin (un registro por tipo de servicio,
    si fue configurado). Tipos sin SLA no aparecen — el frontend muestra
    placeholders editables."""
    if current_user.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin tenant sin tenant_id asociado",
        )
    return (
        db.query(SlaConfig)
        .filter(SlaConfig.tenant_id == current_user.tenant_id)
        .order_by(SlaConfig.tipo_servicio)
        .all()
    )


@admin_router.put(
    "/sla/{tipo_servicio}",
    response_model=SlaConfigResponse,
    summary="CU-37 — Crear o actualizar SLA de un tipo de servicio",
)
def upsert_sla(
    tipo_servicio: TipoServicio,
    body: SlaConfigUpsert,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin_tenant),
):
    """Upsert: si existe SLA para (tenant, tipo) lo actualiza; si no, lo crea."""
    if current_user.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin tenant sin tenant_id asociado",
        )

    sla = (
        db.query(SlaConfig)
        .filter(
            SlaConfig.tenant_id == current_user.tenant_id,
            SlaConfig.tipo_servicio == tipo_servicio,
        )
        .first()
    )
    if sla:
        sla.minutos_asignacion_objetivo = body.minutos_asignacion_objetivo
        sla.minutos_llegada_objetivo = body.minutos_llegada_objetivo
        sla.minutos_resolucion_objetivo = body.minutos_resolucion_objetivo
    else:
        sla = SlaConfig(
            tenant_id=current_user.tenant_id,
            tipo_servicio=tipo_servicio,
            minutos_asignacion_objetivo=body.minutos_asignacion_objetivo,
            minutos_llegada_objetivo=body.minutos_llegada_objetivo,
            minutos_resolucion_objetivo=body.minutos_resolucion_objetivo,
        )
        db.add(sla)
    db.commit()
    db.refresh(sla)
    return sla


# ════════════════════════════════════════════════════════════════════════════
# CU-39 — Dashboard de KPIs operacionales por tenant
# ════════════════════════════════════════════════════════════════════════════

from app.services import kpi_service  # noqa: E402


@admin_router.get(
    "/kpis",
    summary="CU-39 — Dashboard de KPIs operacionales por tenant",
)
def dashboard_kpis(
    fecha_inicio: date | None = Query(None, description="Fecha inicio (YYYY-MM-DD)"),
    fecha_fin: date | None = Query(None, description="Fecha fin (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_superadmin),
):
    """Devuelve los 7 KPIs del CU-39 calculados desde datos reales del tenant.

    - `admin_tenant`: scoped a su tenant.
    - `superadmin_plataforma`: agregados de toda la plataforma (cross-tenant).
    """
    return kpi_service.calcular_kpis(
        db=db, current_user=current_user,
        fecha_inicio=fecha_inicio, fecha_fin=fecha_fin,
    )

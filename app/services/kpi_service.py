"""Cálculo de KPIs operacionales por tenant — CU-39.

Los 7 KPIs (calculados sobre incidentes anclados al tenant, filtrados opcionalmente
por rango de fechas):

  1. tiempo_promedio_asignacion_min   — creado_en  → primera cotización aceptada
  2. tiempo_promedio_llegada_min      — cotización aceptada → tecnico_llego_en
  3. incidentes_por_tipo              — agrupado por clasificacion_ia
  4. talleres_mas_eficientes          — ranking por tiempo de finalización
  5. zonas_con_mas_incidentes         — clusters por grilla geográfica (1 km)
  6. casos_cancelados                 — cantidad y tasa
  7. nivel_cumplimiento_sla           — % de incidentes dentro del objetivo del tenant

Regla de negocio #5: solo se cuenta tiempo de llegada cuando hay `tecnico_llego_en`.
Regla de negocio #9: si el tenant no tiene SLA para un tipo, ese tipo no entra al
                     cálculo de cumplimiento.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.tenant_context import aplicar_filtro_tenant
from app.models.asignacion import Asignacion
from app.models.cotizacion import Cotizacion
from app.models.incidente import Incidente
from app.models.sla_config import SlaConfig
from app.models.taller import Taller
from app.models.usuario import Usuario


# Tamaño de la grilla geográfica para el KPI #5 (zonas con más incidentes).
# 0.01° ≈ 1.1 km en latitud — suficiente para visualización urbana.
GRID_CELL_DEG = 0.01


def calcular_kpis(
    db: Session,
    current_user: Usuario,
    fecha_inicio: date | None = None,
    fecha_fin: date | None = None,
) -> dict:
    """Devuelve los 7 KPIs del CU-39 para el tenant del `current_user`.

    `superadmin_plataforma` recibe los KPIs agregados de todos los tenants.
    """
    # ── Universo de incidentes (filtrado por tenant + rango) ─────────────────
    q_inc = db.query(Incidente)
    q_inc = aplicar_filtro_tenant(q_inc, Incidente, current_user)
    if fecha_inicio:
        q_inc = q_inc.filter(
            Incidente.creado_en >= datetime.combine(fecha_inicio, datetime.min.time())
        )
    if fecha_fin:
        q_inc = q_inc.filter(
            Incidente.creado_en <= datetime.combine(fecha_fin, datetime.max.time())
        )
    incidentes: list[Incidente] = q_inc.all()

    total = len(incidentes)
    ids_incidentes = [inc.id for inc in incidentes]

    # ── KPI #6: casos cancelados ─────────────────────────────────────────────
    cancelados = sum(1 for inc in incidentes if inc.estado == "cancelado")
    tasa_cancelacion = round(cancelados / total * 100, 2) if total > 0 else 0.0

    # ── KPI #3: incidentes por tipo (clasificacion_ia) ───────────────────────
    por_tipo: dict[str, int] = defaultdict(int)
    for inc in incidentes:
        por_tipo[inc.clasificacion_ia or "sin_clasificar"] += 1

    # ── Asignaciones aceptadas dentro del universo ───────────────────────────
    asignaciones: list[Asignacion] = []
    if ids_incidentes:
        asignaciones = (
            db.query(Asignacion)
            .filter(
                Asignacion.incidente_id.in_(ids_incidentes),
                Asignacion.accion_taller == "aceptado",
            )
            .all()
        )

    # ── Cotizaciones aceptadas dentro del universo ───────────────────────────
    cotizaciones_aceptadas: dict[UUID, Cotizacion] = {}
    if ids_incidentes:
        for cot in (
            db.query(Cotizacion)
            .filter(
                Cotizacion.incidente_id.in_(ids_incidentes),
                Cotizacion.estado == "aceptada",
            )
            .all()
        ):
            cotizaciones_aceptadas[cot.incidente_id] = cot

    incidentes_por_id: dict[UUID, Incidente] = {inc.id: inc for inc in incidentes}

    # ── KPI #1: tiempo promedio de asignación ────────────────────────────────
    # creado_en → respondido_en de la cotización aceptada
    tiempos_asignacion: list[float] = []
    for inc_id, cot in cotizaciones_aceptadas.items():
        inc = incidentes_por_id.get(inc_id)
        if not inc or not cot.respondido_en:
            continue
        delta_min = (cot.respondido_en - inc.creado_en).total_seconds() / 60
        if delta_min >= 0:
            tiempos_asignacion.append(delta_min)
    tiempo_prom_asignacion = (
        round(sum(tiempos_asignacion) / len(tiempos_asignacion), 2)
        if tiempos_asignacion else None
    )

    # ── KPI #2: tiempo promedio de llegada ───────────────────────────────────
    # Asignación creada → tecnico_llego_en (regla de negocio #5: requiere timestamp)
    tiempos_llegada: list[float] = []
    for asig in asignaciones:
        if not asig.tecnico_llego_en or not asig.asignado_en:
            continue
        delta_min = (asig.tecnico_llego_en - asig.asignado_en).total_seconds() / 60
        if delta_min >= 0:
            tiempos_llegada.append(delta_min)
    tiempo_prom_llegada = (
        round(sum(tiempos_llegada) / len(tiempos_llegada), 2)
        if tiempos_llegada else None
    )

    # ── KPI #4: talleres más eficientes ──────────────────────────────────────
    # Ranking por tiempo promedio de finalización (asignado_en → completado_en)
    tiempos_por_taller: dict[UUID, list[float]] = defaultdict(list)
    completados_por_taller: dict[UUID, int] = defaultdict(int)
    for asig in asignaciones:
        if asig.completado_en and asig.asignado_en:
            delta_min = (asig.completado_en - asig.asignado_en).total_seconds() / 60
            if delta_min >= 0:
                tiempos_por_taller[asig.taller_id].append(delta_min)
                completados_por_taller[asig.taller_id] += 1

    talleres_ranking: list[dict] = []
    if tiempos_por_taller:
        # cargar nombres de talleres
        taller_ids = list(tiempos_por_taller.keys())
        talleres_db = (
            db.query(Taller).filter(Taller.id.in_(taller_ids)).all()
        )
        nombre_por_id = {t.id: t.nombre for t in talleres_db}
        for tid, tiempos in tiempos_por_taller.items():
            prom = sum(tiempos) / len(tiempos)
            talleres_ranking.append({
                "taller_id": str(tid),
                "nombre": nombre_por_id.get(tid, "—"),
                "incidentes_completados": completados_por_taller[tid],
                "tiempo_promedio_min": round(prom, 2),
            })
        # menor tiempo = más eficiente
        talleres_ranking.sort(key=lambda r: r["tiempo_promedio_min"])

    # ── KPI #5: zonas con más incidentes (grilla 0.01° ≈ 1.1 km) ─────────────
    zonas: dict[tuple[float, float], int] = defaultdict(int)
    for inc in incidentes:
        if inc.latitud is None or inc.longitud is None:
            continue
        lat_cell = round(float(inc.latitud) / GRID_CELL_DEG) * GRID_CELL_DEG
        lon_cell = round(float(inc.longitud) / GRID_CELL_DEG) * GRID_CELL_DEG
        zonas[(round(lat_cell, 4), round(lon_cell, 4))] += 1

    zonas_top = [
        {"latitud": lat, "longitud": lon, "incidentes": cnt}
        for (lat, lon), cnt in sorted(zonas.items(), key=lambda kv: kv[1], reverse=True)[:10]
    ]

    # ── KPI #7: nivel de cumplimiento de SLA ─────────────────────────────────
    # Carga SLAs del tenant: si el usuario es superadmin_plataforma traemos todos
    # los SLAs del sistema (pero la comparación queda por incidente.tenant_id).
    q_sla = db.query(SlaConfig)
    q_sla = aplicar_filtro_tenant(q_sla, SlaConfig, current_user)
    slas: list[SlaConfig] = q_sla.all()
    # índice (tenant_id, tipo_servicio) → SlaConfig
    sla_index: dict[tuple[UUID, str], SlaConfig] = {
        (sla.tenant_id, sla.tipo_servicio): sla for sla in slas
    }
    asig_por_incidente: dict[UUID, Asignacion] = {a.incidente_id: a for a in asignaciones}

    sla_aplicables = 0
    sla_cumplidos = 0
    detalle_sla: dict[str, dict[str, int]] = defaultdict(lambda: {"aplicables": 0, "cumplidos": 0})

    for inc in incidentes:
        if inc.tenant_id is None or not inc.clasificacion_ia:
            continue
        sla = sla_index.get((inc.tenant_id, inc.clasificacion_ia))
        if not sla:
            continue  # regla #9: sin SLA configurado, no se calcula
        asig = asig_por_incidente.get(inc.id)
        cot = cotizaciones_aceptadas.get(inc.id)
        if not asig or not cot or not cot.respondido_en:
            continue
        # Cumplimiento sólo de incidentes finalizados con timestamps completos
        if inc.estado != "finalizado" or not asig.completado_en or not asig.tecnico_llego_en:
            continue
        sla_aplicables += 1
        detalle_sla[inc.clasificacion_ia]["aplicables"] += 1

        min_asig = (cot.respondido_en - inc.creado_en).total_seconds() / 60
        min_llegada = (asig.tecnico_llego_en - cot.respondido_en).total_seconds() / 60
        min_resol = (asig.completado_en - inc.creado_en).total_seconds() / 60

        cumple = (
            min_asig <= sla.minutos_asignacion_objetivo
            and min_llegada <= sla.minutos_llegada_objetivo
            and min_resol <= sla.minutos_resolucion_objetivo
        )
        if cumple:
            sla_cumplidos += 1
            detalle_sla[inc.clasificacion_ia]["cumplidos"] += 1

    pct_cumplimiento = (
        round(sla_cumplidos / sla_aplicables * 100, 2) if sla_aplicables > 0 else None
    )

    return {
        "filtro": {
            "fecha_inicio": str(fecha_inicio) if fecha_inicio else None,
            "fecha_fin": str(fecha_fin) if fecha_fin else None,
        },
        "totales": {
            "incidentes": total,
            "cotizaciones_aceptadas": len(cotizaciones_aceptadas),
        },
        "tiempo_promedio_asignacion_min": tiempo_prom_asignacion,
        "tiempo_promedio_llegada_min": tiempo_prom_llegada,
        "incidentes_por_tipo": dict(por_tipo),
        "talleres_mas_eficientes": talleres_ranking[:10],
        "zonas_con_mas_incidentes": zonas_top,
        "casos_cancelados": {
            "cantidad": cancelados,
            "tasa_porcentaje": tasa_cancelacion,
        },
        "cumplimiento_sla": {
            "aplicables": sla_aplicables,
            "cumplidos": sla_cumplidos,
            "porcentaje": pct_cumplimiento,
            "por_tipo": {
                tipo: {
                    **vals,
                    "porcentaje": (
                        round(vals["cumplidos"] / vals["aplicables"] * 100, 2)
                        if vals["aplicables"] > 0 else None
                    ),
                }
                for tipo, vals in detalle_sla.items()
            },
        },
    }

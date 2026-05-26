"""multi-tenant R1: tablas tenants + solicitudes_tenant + tenant_id en tablas core

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-05-25

Resumen:
- Crea tabla `tenants` (CU-28) y `solicitudes_tenant` (CU-29).
- Agrega `tenant_id` a 12 tablas existentes con nullability segun el modelo Opción C
  (cliente global, incidente con tenant tras cotización aceptada).
- DB se asume vacía: no hay backfill.
"""
from alembic import op
import sqlalchemy as sa

revision = 'a6b7c8d9e0f1'
down_revision = 'f5a6b7c8d9e0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Tablas nuevas ────────────────────────────────────────────────────────
    op.create_table(
        'tenants',
        sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column('nombre', sa.String(150), nullable=False),
        sa.Column('slug', sa.String(60), nullable=False, unique=True),
        sa.Column('correo_contacto', sa.String(150), nullable=True),
        sa.Column('telefono_contacto', sa.String(20), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('plan', sa.String(20), nullable=False, server_default='basico'),
        sa.Column('creado_en', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_tenants_slug', 'tenants', ['slug'], unique=True)

    op.create_table(
        'solicitudes_tenant',
        sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column('solicitante_nombre', sa.String(150), nullable=False),
        sa.Column('solicitante_correo', sa.String(150), nullable=False),
        sa.Column('solicitante_telefono', sa.String(20), nullable=True),
        sa.Column('nombre_red', sa.String(150), nullable=False),
        sa.Column('descripcion', sa.Text(), nullable=True),
        sa.Column('estado', sa.String(20), nullable=False, server_default='pendiente'),
        sa.Column('motivo_rechazo', sa.Text(), nullable=True),
        sa.Column('revisado_por', sa.Uuid(as_uuid=True), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('revisado_en', sa.DateTime(), nullable=True),
        sa.Column('creado_en', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    )

    # ── tenant_id en tablas existentes ────────────────────────────────────────
    # NULLABLE: usuarios, incidentes, evidencias, notificaciones, historial_servicio
    # NOT NULL: talleres, tecnicos, asignaciones, pagos, mensajes, metricas_taller, solicitudes_registro_taller

    op.add_column('usuarios', sa.Column(
        'tenant_id', sa.Uuid(as_uuid=True),
        sa.ForeignKey('tenants.id'), nullable=True
    ))
    op.create_index('ix_usuarios_tenant_id', 'usuarios', ['tenant_id'])

    op.add_column('talleres', sa.Column(
        'tenant_id', sa.Uuid(as_uuid=True),
        sa.ForeignKey('tenants.id'), nullable=False
    ))
    op.create_index('ix_talleres_tenant_id', 'talleres', ['tenant_id'])

    op.add_column('incidentes', sa.Column(
        'tenant_id', sa.Uuid(as_uuid=True),
        sa.ForeignKey('tenants.id'), nullable=True
    ))
    op.create_index('ix_incidentes_tenant_id', 'incidentes', ['tenant_id'])

    op.add_column('tecnicos', sa.Column(
        'tenant_id', sa.Uuid(as_uuid=True),
        sa.ForeignKey('tenants.id'), nullable=False
    ))
    op.create_index('ix_tecnicos_tenant_id', 'tecnicos', ['tenant_id'])

    op.add_column('asignaciones', sa.Column(
        'tenant_id', sa.Uuid(as_uuid=True),
        sa.ForeignKey('tenants.id'), nullable=False
    ))
    op.create_index('ix_asignaciones_tenant_id', 'asignaciones', ['tenant_id'])

    op.add_column('evidencias', sa.Column(
        'tenant_id', sa.Uuid(as_uuid=True),
        sa.ForeignKey('tenants.id'), nullable=True
    ))
    op.create_index('ix_evidencias_tenant_id', 'evidencias', ['tenant_id'])

    op.add_column('pagos', sa.Column(
        'tenant_id', sa.Uuid(as_uuid=True),
        sa.ForeignKey('tenants.id'), nullable=False
    ))
    op.create_index('ix_pagos_tenant_id', 'pagos', ['tenant_id'])

    op.add_column('mensajes', sa.Column(
        'tenant_id', sa.Uuid(as_uuid=True),
        sa.ForeignKey('tenants.id'), nullable=False
    ))
    op.create_index('ix_mensajes_tenant_id', 'mensajes', ['tenant_id'])

    op.add_column('notificaciones', sa.Column(
        'tenant_id', sa.Uuid(as_uuid=True),
        sa.ForeignKey('tenants.id'), nullable=True
    ))
    op.create_index('ix_notificaciones_tenant_id', 'notificaciones', ['tenant_id'])

    op.add_column('historial_servicio', sa.Column(
        'tenant_id', sa.Uuid(as_uuid=True),
        sa.ForeignKey('tenants.id'), nullable=True
    ))
    op.create_index('ix_historial_servicio_tenant_id', 'historial_servicio', ['tenant_id'])

    op.add_column('metricas_taller', sa.Column(
        'tenant_id', sa.Uuid(as_uuid=True),
        sa.ForeignKey('tenants.id'), nullable=False
    ))
    op.create_index('ix_metricas_taller_tenant_id', 'metricas_taller', ['tenant_id'])

    op.add_column('solicitudes_registro_taller', sa.Column(
        'tenant_id', sa.Uuid(as_uuid=True),
        sa.ForeignKey('tenants.id'), nullable=False
    ))
    op.create_index('ix_solicitudes_registro_taller_tenant_id', 'solicitudes_registro_taller', ['tenant_id'])


def downgrade() -> None:
    # Indices + columnas tenant_id (reverso del upgrade)
    op.drop_index('ix_solicitudes_registro_taller_tenant_id', table_name='solicitudes_registro_taller')
    op.drop_column('solicitudes_registro_taller', 'tenant_id')

    op.drop_index('ix_metricas_taller_tenant_id', table_name='metricas_taller')
    op.drop_column('metricas_taller', 'tenant_id')

    op.drop_index('ix_historial_servicio_tenant_id', table_name='historial_servicio')
    op.drop_column('historial_servicio', 'tenant_id')

    op.drop_index('ix_notificaciones_tenant_id', table_name='notificaciones')
    op.drop_column('notificaciones', 'tenant_id')

    op.drop_index('ix_mensajes_tenant_id', table_name='mensajes')
    op.drop_column('mensajes', 'tenant_id')

    op.drop_index('ix_pagos_tenant_id', table_name='pagos')
    op.drop_column('pagos', 'tenant_id')

    op.drop_index('ix_evidencias_tenant_id', table_name='evidencias')
    op.drop_column('evidencias', 'tenant_id')

    op.drop_index('ix_asignaciones_tenant_id', table_name='asignaciones')
    op.drop_column('asignaciones', 'tenant_id')

    op.drop_index('ix_tecnicos_tenant_id', table_name='tecnicos')
    op.drop_column('tecnicos', 'tenant_id')

    op.drop_index('ix_incidentes_tenant_id', table_name='incidentes')
    op.drop_column('incidentes', 'tenant_id')

    op.drop_index('ix_talleres_tenant_id', table_name='talleres')
    op.drop_column('talleres', 'tenant_id')

    op.drop_index('ix_usuarios_tenant_id', table_name='usuarios')
    op.drop_column('usuarios', 'tenant_id')

    op.drop_table('solicitudes_tenant')

    op.drop_index('ix_tenants_slug', table_name='tenants')
    op.drop_table('tenants')

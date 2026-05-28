"""Ciclo 5: tabla sla_config + columna idempotency_key en incidentes

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
Create Date: 2026-05-27

Cambios:
- Nueva tabla `sla_config`: SLA por tenant + tipo de servicio (CU-37).
  Define los objetivos de tiempo (asignación, llegada, resolución) que el
  dashboard de KPIs (CU-39) usa para calcular el % de cumplimiento.
- Nueva columna `incidentes.idempotency_key` (UUID String, nullable, unique):
  garantiza que un POST /incidentes reintentado por la app Flutter offline
  (CU-40/CU-41) no cree incidentes duplicados.
"""
from alembic import op
import sqlalchemy as sa

revision = 'e0f1a2b3c4d5'
down_revision = 'd9e0f1a2b3c4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── CU-37: tabla sla_config ──────────────────────────────────────────────
    op.create_table(
        'sla_config',
        sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', sa.Uuid(as_uuid=True),
                  sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tipo_servicio', sa.String(20), nullable=False),
        sa.Column('minutos_asignacion_objetivo', sa.Integer(), nullable=False),
        sa.Column('minutos_llegada_objetivo', sa.Integer(), nullable=False),
        sa.Column('minutos_resolucion_objetivo', sa.Integer(), nullable=False),
        sa.Column('creado_en', sa.DateTime(),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('actualizado_en', sa.DateTime(),
                  server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('tenant_id', 'tipo_servicio',
                            name='uq_sla_config_tenant_tipo'),
    )
    op.create_index('ix_sla_config_tenant_id', 'sla_config', ['tenant_id'])

    # ── CU-40/CU-41: idempotency_key en incidentes ──────────────────────────
    op.add_column(
        'incidentes',
        sa.Column('idempotency_key', sa.String(64), nullable=True),
    )
    op.create_index(
        'uq_incidentes_idempotency_key',
        'incidentes',
        ['idempotency_key'],
        unique=True,
        postgresql_where=sa.text('idempotency_key IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index('uq_incidentes_idempotency_key', table_name='incidentes')
    op.drop_column('incidentes', 'idempotency_key')

    op.drop_index('ix_sla_config_tenant_id', table_name='sla_config')
    op.drop_table('sla_config')

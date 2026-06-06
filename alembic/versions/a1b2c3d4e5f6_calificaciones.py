"""CU-43 (aporte propio): tabla calificaciones (reseñas post-servicio)

Revision ID: a1b2c3d4e5f6
Revises: f6b7c8d9e0f1
Create Date: 2026-06-05

Cambios:
- Nueva tabla `calificaciones`: el cliente puntúa (1-5) y reseña al taller tras
  finalizar el servicio. Afecta CU-35 (orden de cotizaciones por promedio),
  CU-39 (KPI de satisfacción promedio) y permite moderación por el admin_tenant
  (columna `oculta`).
- UNIQUE(incidente_id): una sola calificación por incidente.
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = 'f6b7c8d9e0f1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'calificaciones',
        sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', sa.Uuid(as_uuid=True),
                  sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('incidente_id', sa.Uuid(as_uuid=True),
                  sa.ForeignKey('incidentes.id'), nullable=False),
        sa.Column('taller_id', sa.Uuid(as_uuid=True),
                  sa.ForeignKey('talleres.id'), nullable=False),
        sa.Column('cliente_id', sa.Uuid(as_uuid=True),
                  sa.ForeignKey('usuarios.id'), nullable=False),
        sa.Column('puntuacion', sa.Integer(), nullable=False),
        sa.Column('comentario', sa.Text(), nullable=True),
        sa.Column('oculta', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('creado_en', sa.DateTime(),
                  server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('incidente_id', name='uq_calificacion_incidente'),
    )
    op.create_index('ix_calificaciones_tenant_id', 'calificaciones', ['tenant_id'])
    op.create_index('ix_calificaciones_taller_id', 'calificaciones', ['taller_id'])
    op.create_index('ix_calificaciones_incidente_id', 'calificaciones', ['incidente_id'])


def downgrade() -> None:
    op.drop_index('ix_calificaciones_incidente_id', table_name='calificaciones')
    op.drop_index('ix_calificaciones_taller_id', table_name='calificaciones')
    op.drop_index('ix_calificaciones_tenant_id', table_name='calificaciones')
    op.drop_table('calificaciones')

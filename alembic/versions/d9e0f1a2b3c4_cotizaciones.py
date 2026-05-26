"""R3: tabla cotizaciones (CU-34 + CU-35)

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-05-26
"""
from alembic import op
import sqlalchemy as sa

revision = 'd9e0f1a2b3c4'
down_revision = 'c8d9e0f1a2b3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'cotizaciones',
        sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', sa.Uuid(as_uuid=True),
                  sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('incidente_id', sa.Uuid(as_uuid=True),
                  sa.ForeignKey('incidentes.id'), nullable=False),
        sa.Column('taller_id', sa.Uuid(as_uuid=True),
                  sa.ForeignKey('talleres.id'), nullable=False),
        sa.Column('monto_estimado', sa.DECIMAL(10, 2), nullable=False),
        sa.Column('tiempo_estimado_horas', sa.DECIMAL(5, 2), nullable=True),
        sa.Column('observaciones', sa.Text(), nullable=True),
        sa.Column('estado', sa.String(20), nullable=False, server_default='enviada'),
        sa.Column('enviado_en', sa.DateTime(),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('expira_en', sa.DateTime(), nullable=False),
        sa.Column('respondido_en', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('incidente_id', 'taller_id',
                            name='uq_cotizacion_incidente_taller'),
    )
    op.create_index('ix_cotizaciones_tenant_id', 'cotizaciones', ['tenant_id'])
    op.create_index('ix_cotizaciones_incidente_id', 'cotizaciones', ['incidente_id'])
    op.create_index('ix_cotizaciones_taller_id', 'cotizaciones', ['taller_id'])


def downgrade() -> None:
    op.drop_index('ix_cotizaciones_taller_id', table_name='cotizaciones')
    op.drop_index('ix_cotizaciones_incidente_id', table_name='cotizaciones')
    op.drop_index('ix_cotizaciones_tenant_id', table_name='cotizaciones')
    op.drop_table('cotizaciones')

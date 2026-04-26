"""turno_remove_en_servicio — elimina columna en_servicio de turnos_tecnico

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-04-24
"""
from alembic import op
import sqlalchemy as sa

revision = 'd3e4f5a6b7c8'
down_revision = 'c2d3e4f5a6b7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column('turnos_tecnico', 'en_servicio')


def downgrade() -> None:
    op.add_column('turnos_tecnico', sa.Column('en_servicio', sa.Boolean(), nullable=False, server_default='false'))
    op.alter_column('turnos_tecnico', 'en_servicio', server_default=None)

"""turnos_dia_semana — reemplaza fecha_turno por dia_semana (0=Lun … 6=Dom)

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-04-24
"""
from alembic import op
import sqlalchemy as sa

revision = 'c2d3e4f5a6b7'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Eliminar columna vieja y agregar la nueva
    op.drop_column('turnos_tecnico', 'fecha_turno')
    op.add_column('turnos_tecnico', sa.Column('dia_semana', sa.SmallInteger(), nullable=False, server_default='0'))
    # Quitar el server_default para que sea explícito en inserts futuros
    op.alter_column('turnos_tecnico', 'dia_semana', server_default=None)


def downgrade() -> None:
    op.drop_column('turnos_tecnico', 'dia_semana')
    op.add_column('turnos_tecnico', sa.Column('fecha_turno', sa.Date(), nullable=False, server_default='2000-01-01'))
    op.alter_column('turnos_tecnico', 'fecha_turno', server_default=None)

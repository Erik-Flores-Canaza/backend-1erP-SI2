"""ciclo3plus_superadmin

Revision ID: b1c2d3e4f5a6
Revises: a3f1c2d4e5b6
Create Date: 2026-04-23 00:00:00.000000

Cambios:
  - Agrega estado_aprobacion y motivo_rechazo a talleres
  - Crea tabla solicitudes_registro_taller
  - El rol 'superadmin' se inserta vía seed (no migración)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = 'a3f1c2d4e5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Campos nuevos en talleres ─────────────────────────────────────────────
    op.add_column(
        'talleres',
        sa.Column('estado_aprobacion', sa.String(length=20), nullable=True),
    )
    op.add_column(
        'talleres',
        sa.Column('motivo_rechazo', sa.Text(), nullable=True),
    )
    # Los talleres existentes (creados antes de CU-23) quedan como 'aprobado'
    op.execute("UPDATE talleres SET estado_aprobacion = 'aprobado' WHERE estado_aprobacion IS NULL")

    # ── Tabla solicitudes_registro_taller ─────────────────────────────────────
    op.create_table(
        'solicitudes_registro_taller',
        sa.Column('id', sa.Uuid(), nullable=False),
        # Datos del solicitante
        sa.Column('solicitante_nombre', sa.String(length=150), nullable=False),
        sa.Column('solicitante_correo', sa.String(length=150), nullable=False),
        sa.Column('solicitante_telefono', sa.String(length=20), nullable=True),
        # Datos del taller propuesto
        sa.Column('nombre_taller', sa.String(length=150), nullable=False),
        sa.Column('direccion', sa.String(length=255), nullable=True),
        sa.Column('latitud', sa.DECIMAL(precision=10, scale=7), nullable=True),
        sa.Column('longitud', sa.DECIMAL(precision=10, scale=7), nullable=True),
        sa.Column('descripcion', sa.Text(), nullable=True),
        # Estado de la solicitud
        sa.Column('estado', sa.String(length=20), nullable=False),
        sa.Column('motivo_rechazo', sa.Text(), nullable=True),
        # Revisión
        sa.Column('revisado_por', sa.Uuid(), nullable=True),
        sa.Column('revisado_en', sa.DateTime(), nullable=True),
        sa.Column('creado_en', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['revisado_por'], ['usuarios.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('solicitudes_registro_taller')
    op.drop_column('talleres', 'motivo_rechazo')
    op.drop_column('talleres', 'estado_aprobacion')

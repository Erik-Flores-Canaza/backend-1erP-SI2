"""vehiculo_id nullable en incidentes

Revision ID: a3f1c2d4e5b6
Revises: 149bc0e1eede
Create Date: 2026-04-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3f1c2d4e5b6'
down_revision: Union[str, None] = '149bc0e1eede'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'incidentes',
        'vehiculo_id',
        existing_type=sa.Uuid(),
        nullable=True,
    )


def downgrade() -> None:
    # Primero asegurarse de que no hay NULLs antes de revertir
    op.execute("UPDATE incidentes SET vehiculo_id = cliente_id WHERE vehiculo_id IS NULL")
    op.alter_column(
        'incidentes',
        'vehiculo_id',
        existing_type=sa.Uuid(),
        nullable=False,
    )

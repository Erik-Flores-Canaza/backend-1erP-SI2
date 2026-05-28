"""add monto_base, monto_adicional, motivo_adicional a pagos

Permite que el tecnico ajuste el cobro final si el trabajo resulto mas
costoso de lo cotizado (decision docente). El cliente debe ver el desglose
en su pantalla de pago.

monto_total se mantiene como suma: monto_base + monto_adicional. Asi todo
lo que ya leia monto_total sigue funcionando (Stripe, metricas, etc.).

Revision ID: f6b7c8d9e0f1
Revises: e0f1a2b3c4d5
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa

revision = 'f6b7c8d9e0f1'
down_revision = 'e0f1a2b3c4d5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Agregar columnas (nullable inicial para permitir backfill seguro)
    op.add_column('pagos', sa.Column('monto_base', sa.DECIMAL(10, 2), nullable=True))
    op.add_column('pagos', sa.Column('monto_adicional', sa.DECIMAL(10, 2), nullable=True))
    op.add_column('pagos', sa.Column('motivo_adicional', sa.Text(), nullable=True))

    # 2. Backfill: pagos existentes (sin cotizacion / sin adicional)
    #    monto_base = monto_total, monto_adicional = 0, motivo = NULL
    op.execute("""
        UPDATE pagos
        SET monto_base = monto_total,
            monto_adicional = 0
        WHERE monto_base IS NULL
    """)

    # 3. Forzar NOT NULL + default tras el backfill
    op.alter_column('pagos', 'monto_base', nullable=False)
    op.alter_column('pagos', 'monto_adicional', nullable=False, server_default='0')


def downgrade() -> None:
    op.drop_column('pagos', 'motivo_adicional')
    op.drop_column('pagos', 'monto_adicional')
    op.drop_column('pagos', 'monto_base')

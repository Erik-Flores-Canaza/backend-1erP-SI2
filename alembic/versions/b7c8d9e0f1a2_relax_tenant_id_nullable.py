"""Multi-tenant R1.5: relaja tenant_id a NULLABLE en pagos, mensajes y metricas_taller

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-05-26

Justificación:
- pagos, mensajes y metricas_taller los crea código existente que aún no propaga
  tenant_id (R3/CU-15 los aterrizará correctamente). Para no bloquear el flujo
  cliente → cotización → pago / chat, los volvemos nullable temporalmente.
- En R3 se propagará el tenant_id desde el incidente y se podrá volver NOT NULL.
"""
from alembic import op
import sqlalchemy as sa  # noqa: F401

revision = 'b7c8d9e0f1a2'
down_revision = 'a6b7c8d9e0f1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column('pagos', 'tenant_id', nullable=True)
    op.alter_column('mensajes', 'tenant_id', nullable=True)
    op.alter_column('metricas_taller', 'tenant_id', nullable=True)


def downgrade() -> None:
    op.alter_column('metricas_taller', 'tenant_id', nullable=False)
    op.alter_column('mensajes', 'tenant_id', nullable=False)
    op.alter_column('pagos', 'tenant_id', nullable=False)

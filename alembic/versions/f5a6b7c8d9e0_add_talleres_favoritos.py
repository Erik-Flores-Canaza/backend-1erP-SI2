"""add talleres_favoritos table

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-04-25
"""
from alembic import op
import sqlalchemy as sa

revision = 'f5a6b7c8d9e0'
down_revision = 'e4f5a6b7c8d9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'talleres_favoritos',
        sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column('cliente_id', sa.Uuid(as_uuid=True), sa.ForeignKey('usuarios.id'), nullable=False),
        sa.Column('taller_id', sa.Uuid(as_uuid=True), sa.ForeignKey('talleres.id'), nullable=False),
        sa.Column('creado_en', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('cliente_id', 'taller_id', name='uq_favorito_cliente_taller'),
    )
    op.create_index('ix_talleres_favoritos_cliente_id', 'talleres_favoritos', ['cliente_id'])


def downgrade() -> None:
    op.drop_index('ix_talleres_favoritos_cliente_id', table_name='talleres_favoritos')
    op.drop_table('talleres_favoritos')

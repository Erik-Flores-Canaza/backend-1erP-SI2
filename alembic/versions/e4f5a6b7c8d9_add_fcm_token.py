"""add fcm_token to usuarios

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-04-25
"""
from alembic import op
import sqlalchemy as sa

revision = 'e4f5a6b7c8d9'
down_revision = 'd3e4f5a6b7c8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('usuarios', sa.Column('fcm_token', sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column('usuarios', 'fcm_token')

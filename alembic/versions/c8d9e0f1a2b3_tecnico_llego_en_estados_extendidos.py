"""R2: agrega tecnico_llego_en a asignaciones + migra estados al esquema de 7 estados

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-05-26

Cambios:
- Nueva columna `asignaciones.tecnico_llego_en` (nullable DateTime). La setea CU-38
  cuando el técnico marca su llegada al sitio del cliente.
- Mapeo de datos del enum viejo al nuevo:
    'atendido'  → 'finalizado'
    'en_proceso' → 'taller_asignado'  (estado más conservador del split)
  La columna `incidentes.estado` sigue siendo String(20); no hay cambio de tipo.

Nuevos estados (sin migración de datos — son nuevos): buscando_taller, en_camino, en_atencion.
"""
from alembic import op
import sqlalchemy as sa

revision = 'c8d9e0f1a2b3'
down_revision = 'b7c8d9e0f1a2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('asignaciones', sa.Column('tecnico_llego_en', sa.DateTime(), nullable=True))

    # ── Mapeo de datos viejos → nuevos ────────────────────────────────────────
    op.execute("UPDATE incidentes SET estado = 'finalizado' WHERE estado = 'atendido'")
    op.execute("UPDATE incidentes SET estado = 'taller_asignado' WHERE estado = 'en_proceso'")

    # historial_servicio guarda estado_anterior y estado_nuevo — mismos mapeos
    op.execute("UPDATE historial_servicio SET estado_anterior = 'finalizado' WHERE estado_anterior = 'atendido'")
    op.execute("UPDATE historial_servicio SET estado_anterior = 'taller_asignado' WHERE estado_anterior = 'en_proceso'")
    op.execute("UPDATE historial_servicio SET estado_nuevo = 'finalizado' WHERE estado_nuevo = 'atendido'")
    op.execute("UPDATE historial_servicio SET estado_nuevo = 'taller_asignado' WHERE estado_nuevo = 'en_proceso'")


def downgrade() -> None:
    # Reverso conservador: 4 estados viejos del esquema anterior
    op.execute("UPDATE incidentes SET estado = 'atendido' WHERE estado = 'finalizado'")
    op.execute(
        "UPDATE incidentes SET estado = 'en_proceso' "
        "WHERE estado IN ('buscando_taller', 'taller_asignado', 'en_camino', 'en_atencion')"
    )

    op.execute("UPDATE historial_servicio SET estado_anterior = 'atendido' WHERE estado_anterior = 'finalizado'")
    op.execute(
        "UPDATE historial_servicio SET estado_anterior = 'en_proceso' "
        "WHERE estado_anterior IN ('buscando_taller', 'taller_asignado', 'en_camino', 'en_atencion')"
    )
    op.execute("UPDATE historial_servicio SET estado_nuevo = 'atendido' WHERE estado_nuevo = 'finalizado'")
    op.execute(
        "UPDATE historial_servicio SET estado_nuevo = 'en_proceso' "
        "WHERE estado_nuevo IN ('buscando_taller', 'taller_asignado', 'en_camino', 'en_atencion')"
    )

    op.drop_column('asignaciones', 'tecnico_llego_en')

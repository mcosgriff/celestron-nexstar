"""Expand eclipses with contact times and path

Revision ID: 20251219101000
Revises: 20251219090000
Create Date: 2025-12-19 10:10:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251219101000"
down_revision: str | Sequence[str] | None = "20251219090000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add new columns for richer eclipse data
    with op.batch_alter_table("eclipses", schema=None) as batch_op:
        batch_op.add_column(sa.Column("start_time", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("max_time", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("end_time", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("obscuration", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("central_duration_sec", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("path_geojson", sa.Text(), nullable=True))
        batch_op.create_index("idx_eclipse_max_time", ["max_time"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("eclipses", schema=None) as batch_op:
        batch_op.drop_index("idx_eclipse_max_time")
        batch_op.drop_column("path_geojson")
        batch_op.drop_column("central_duration_sec")
        batch_op.drop_column("obscuration")
        batch_op.drop_column("end_time")
        batch_op.drop_column("max_time")
        batch_op.drop_column("start_time")


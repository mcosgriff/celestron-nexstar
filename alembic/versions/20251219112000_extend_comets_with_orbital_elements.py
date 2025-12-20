"""extend comets with orbital elements and photometric params

Revision ID: 20251219112000
Revises: 20251219101000
Create Date: 2025-12-19 11:20:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20251219112000"
down_revision = "20251219101000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("comets", sa.Column("eccentricity", sa.Float(), nullable=True))
    op.add_column("comets", sa.Column("inclination_deg", sa.Float(), nullable=True))
    op.add_column("comets", sa.Column("arg_perihelion_deg", sa.Float(), nullable=True))
    op.add_column("comets", sa.Column("ascending_node_deg", sa.Float(), nullable=True))
    op.add_column("comets", sa.Column("semi_major_axis_au", sa.Float(), nullable=True))
    op.add_column("comets", sa.Column("perihelion_time", sa.DateTime(timezone=True), nullable=True))
    op.add_column("comets", sa.Column("absolute_magnitude_h", sa.Float(), nullable=True))
    op.add_column("comets", sa.Column("slope_g", sa.Float(), nullable=True))
    op.add_column("comets", sa.Column("source", sa.String(length=100), nullable=True))
    op.create_index("idx_comet_perihelion_time", "comets", ["perihelion_time"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_comet_perihelion_time", table_name="comets")
    op.drop_column("comets", "source")
    op.drop_column("comets", "slope_g")
    op.drop_column("comets", "absolute_magnitude_h")
    op.drop_column("comets", "perihelion_time")
    op.drop_column("comets", "semi_major_axis_au")
    op.drop_column("comets", "ascending_node_deg")
    op.drop_column("comets", "arg_perihelion_deg")
    op.drop_column("comets", "inclination_deg")
    op.drop_column("comets", "eccentricity")


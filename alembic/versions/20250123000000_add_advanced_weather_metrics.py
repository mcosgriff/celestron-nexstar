"""add_advanced_weather_metrics

Revision ID: 20250123000000
Revises: 20250118000000
Create Date: 2025-01-23 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20250123000000"
down_revision: str | Sequence[str] | None = "20251220150000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add advanced weather metrics to weather_forecast table."""
    with op.batch_alter_table("weather_forecast", schema=None) as batch_op:
        # Cloud layer breakdown
        batch_op.add_column(sa.Column("cloud_cover_low_percent", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("cloud_cover_mid_percent", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("cloud_cover_high_percent", sa.Float(), nullable=True))

        # Atmospheric quality
        batch_op.add_column(sa.Column("visibility_m", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("precipitation_probability", sa.Float(), nullable=True))

        # Atmospheric stability
        batch_op.add_column(sa.Column("cape", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("boundary_layer_height_m", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("freezing_level_height_m", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("vapour_pressure_deficit", sa.Float(), nullable=True))

        # Upper atmosphere winds
        batch_op.add_column(sa.Column("wind_speed_80m_mph", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("wind_speed_120m_mph", sa.Float(), nullable=True))

        # Precipitation & pressure
        batch_op.add_column(sa.Column("precipitation_mm", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("rain_mm", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("snowfall_cm", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("pressure_msl", sa.Float(), nullable=True))


def downgrade() -> None:
    """Remove advanced weather metrics columns from weather_forecast table."""
    with op.batch_alter_table("weather_forecast", schema=None) as batch_op:
        # Drop columns in reverse order
        batch_op.drop_column("pressure_msl")
        batch_op.drop_column("snowfall_cm")
        batch_op.drop_column("rain_mm")
        batch_op.drop_column("precipitation_mm")
        batch_op.drop_column("wind_speed_120m_mph")
        batch_op.drop_column("wind_speed_80m_mph")
        batch_op.drop_column("vapour_pressure_deficit")
        batch_op.drop_column("freezing_level_height_m")
        batch_op.drop_column("boundary_layer_height_m")
        batch_op.drop_column("cape")
        batch_op.drop_column("precipitation_probability")
        batch_op.drop_column("visibility_m")
        batch_op.drop_column("cloud_cover_high_percent")
        batch_op.drop_column("cloud_cover_mid_percent")
        batch_op.drop_column("cloud_cover_low_percent")

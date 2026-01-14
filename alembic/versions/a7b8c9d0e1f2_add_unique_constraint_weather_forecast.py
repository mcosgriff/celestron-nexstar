"""add_unique_constraint_weather_forecast

Revision ID: a7b8c9d0e1f2
Revises: 9c4f1e2d3b6a
Create Date: 2026-01-13 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "9c4f1e2d3b6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add unique constraint for weather_forecast and clean duplicates."""
    op.execute(
        """
        DELETE FROM weather_forecast
        WHERE id NOT IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY latitude, longitude, forecast_timestamp
                           ORDER BY fetched_at DESC, id DESC
                       ) AS rn
                FROM weather_forecast
            ) AS ranked
            WHERE rn = 1
        )
        """
    )

    with op.batch_alter_table("weather_forecast") as batch_op:
        batch_op.create_unique_constraint(
            "uq_weather_forecast_location_timestamp",
            ["latitude", "longitude", "forecast_timestamp"],
        )


def downgrade() -> None:
    """Drop unique constraint for weather_forecast."""
    with op.batch_alter_table("weather_forecast") as batch_op:
        batch_op.drop_constraint("uq_weather_forecast_location_timestamp", type_="unique")

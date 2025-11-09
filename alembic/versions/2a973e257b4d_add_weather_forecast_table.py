"""add_weather_forecast_table

Revision ID: 2a973e257b4d
Revises: 2fbc85dc151b
Create Date: 2025-11-08 15:57:02.567799

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "2a973e257b4d"
down_revision: str | Sequence[str] | None = "2fbc85dc151b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "weather_forecast",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("forecast_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("temperature_f", sa.Float(), nullable=True),
        sa.Column("dew_point_f", sa.Float(), nullable=True),
        sa.Column("humidity_percent", sa.Float(), nullable=True),
        sa.Column("cloud_cover_percent", sa.Float(), nullable=True),
        sa.Column("wind_speed_mph", sa.Float(), nullable=True),
        sa.Column("seeing_score", sa.Float(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("weather_forecast", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_weather_forecast_latitude"), ["latitude"], unique=False)
        batch_op.create_index(batch_op.f("ix_weather_forecast_longitude"), ["longitude"], unique=False)
        batch_op.create_index(batch_op.f("ix_weather_forecast_forecast_timestamp"), ["forecast_timestamp"], unique=False)
        batch_op.create_index(batch_op.f("ix_weather_forecast_fetched_at"), ["fetched_at"], unique=False)
        batch_op.create_index("idx_location_timestamp", ["latitude", "longitude", "forecast_timestamp"], unique=False)
        batch_op.create_index("idx_location_fetched", ["latitude", "longitude", "fetched_at"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("weather_forecast", schema=None) as batch_op:
        batch_op.drop_index("idx_location_fetched")
        batch_op.drop_index("idx_location_timestamp")
        batch_op.drop_index(batch_op.f("ix_weather_forecast_fetched_at"))
        batch_op.drop_index(batch_op.f("ix_weather_forecast_forecast_timestamp"))
        batch_op.drop_index(batch_op.f("ix_weather_forecast_longitude"))
        batch_op.drop_index(batch_op.f("ix_weather_forecast_latitude"))

    op.drop_table("weather_forecast")

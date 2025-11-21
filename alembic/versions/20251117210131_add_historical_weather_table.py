"""add_historical_weather_table

Revision ID: 20251117210131
Revises: 20250128010000
Create Date: 2025-11-17 21:01:31.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20251117210131"
down_revision: str | Sequence[str] | None = "20250128010000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add historical_weather table for storing monthly cloud cover climatology."""
    op.create_table(
        "historical_weather",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("geohash", sa.String(length=12), nullable=True),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("avg_cloud_cover_percent", sa.Float(), nullable=True),
        sa.Column("min_cloud_cover_percent", sa.Float(), nullable=True),
        sa.Column("max_cloud_cover_percent", sa.Float(), nullable=True),
        sa.Column("p25_cloud_cover_percent", sa.Float(), nullable=True),
        sa.Column("p75_cloud_cover_percent", sa.Float(), nullable=True),
        sa.Column("years_of_data", sa.Integer(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("historical_weather", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_historical_weather_latitude"), ["latitude"], unique=False)
        batch_op.create_index(batch_op.f("ix_historical_weather_longitude"), ["longitude"], unique=False)
        batch_op.create_index(batch_op.f("ix_historical_weather_geohash"), ["geohash"], unique=False)
        batch_op.create_index(batch_op.f("ix_historical_weather_month"), ["month"], unique=False)
        batch_op.create_index(batch_op.f("ix_historical_weather_fetched_at"), ["fetched_at"], unique=False)
        batch_op.create_index("idx_historical_location_month", ["latitude", "longitude", "month"], unique=False)
        batch_op.create_index("idx_historical_geohash_month", ["geohash", "month"], unique=False)


def downgrade() -> None:
    """Remove historical_weather table."""
    with op.batch_alter_table("historical_weather", schema=None) as batch_op:
        batch_op.drop_index("idx_historical_geohash_month")
        batch_op.drop_index("idx_historical_location_month")
        batch_op.drop_index(batch_op.f("ix_historical_weather_fetched_at"))
        batch_op.drop_index(batch_op.f("ix_historical_weather_month"))
        batch_op.drop_index(batch_op.f("ix_historical_weather_geohash"))
        batch_op.drop_index(batch_op.f("ix_historical_weather_longitude"))
        batch_op.drop_index(batch_op.f("ix_historical_weather_latitude"))

    op.drop_table("historical_weather")

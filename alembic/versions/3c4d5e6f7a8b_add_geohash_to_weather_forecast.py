"""add_geohash_to_weather_forecast

Revision ID: 3c4d5e6f7a8b
Revises: 1a2b3c4d5e6f
Create Date: 2025-01-27 17:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "3c4d5e6f7a8b"
down_revision: str | Sequence[str] | None = "1a2b3c4d5e6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add geohash column to weather_forecast table and populate from lat/lon."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if "weather_forecast" not in existing_tables:
        return

    existing_columns = [col["name"] for col in inspector.get_columns("weather_forecast")]
    if "geohash" in existing_columns:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("weather_forecast")]
        if "idx_weather_geohash" not in existing_indexes:
            op.create_index("idx_weather_geohash", "weather_forecast", ["geohash"], unique=False)
        return

    with op.batch_alter_table("weather_forecast", schema=None) as batch_op:
        batch_op.add_column(sa.Column("geohash", sa.String(length=12), nullable=True))

    from celestron_nexstar.api.geohash_utils import encode

    result = conn.execute(text("SELECT id, latitude, longitude FROM weather_forecast WHERE geohash IS NULL"))
    rows = result.fetchall()

    if rows:
        batch_size = 1000
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            for row in batch:
                row_id, lat, lon = row
                geohash_str = encode(float(lat), float(lon), precision=9)
                conn.execute(
                    text("UPDATE weather_forecast SET geohash = :geohash WHERE id = :id"),
                    {"geohash": geohash_str, "id": row_id},
                )
            conn.commit()

    # Create index on geohash
    op.create_index("idx_weather_geohash", "weather_forecast", ["geohash"], unique=False)

    conn.commit()


def downgrade() -> None:
    """Remove geohash column from weather_forecast table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if "weather_forecast" not in existing_tables:
        return

    existing_columns = [col["name"] for col in inspector.get_columns("weather_forecast")]
    if "geohash" not in existing_columns:
        return

    # Drop index first
    op.drop_index("idx_weather_geohash", table_name="weather_forecast")

    # Remove column
    with op.batch_alter_table("weather_forecast", schema=None) as batch_op:
        batch_op.drop_column("geohash")

    conn.commit()

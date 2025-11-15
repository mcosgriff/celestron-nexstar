"""add_geohash_to_iss_passes

Revision ID: 1a2b3c4d5e6f
Revises: 9a8b7c6d5e4f
Create Date: 2025-01-27 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "1a2b3c4d5e6f"
down_revision: str | Sequence[str] | None = "9a8b7c6d5e4f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add geohash column to iss_passes table and populate from lat/lon."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # Only proceed if the table exists
    if "iss_passes" not in existing_tables:
        # Table doesn't exist yet, it will be created with geohash by the model
        return

    # Check if geohash column already exists
    existing_columns = [col["name"] for col in inspector.get_columns("iss_passes")]
    if "geohash" in existing_columns:
        # Column already exists, just ensure index exists
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("iss_passes")]
        if "ix_iss_passes_geohash" not in existing_indexes:
            op.create_index("ix_iss_passes_geohash", "iss_passes", ["geohash"], unique=False)
        return

    # Add geohash column (nullable initially, will be populated)
    with op.batch_alter_table("iss_passes", schema=None) as batch_op:
        batch_op.add_column(sa.Column("geohash", sa.String(length=12), nullable=True))

    # Import geohash utility to calculate geohashes
    from celestron_nexstar.api.location.geohash_utils import encode

    # Populate geohash for all existing rows
    # Fetch all rows with lat/lon
    result = conn.execute(text("SELECT id, latitude, longitude FROM iss_passes WHERE geohash IS NULL"))
    rows = result.fetchall()

    if rows:
        # Update each row with its geohash (precision 9 for ~5m accuracy)
        # Process in batches for better performance
        batch_size = 1000
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            for row in batch:
                row_id, lat, lon = row
                geohash_str = encode(float(lat), float(lon), precision=9)
                conn.execute(
                    text("UPDATE iss_passes SET geohash = :geohash WHERE id = :id"),
                    {"geohash": geohash_str, "id": row_id},
                )
            # Commit in batches to avoid long transactions
            conn.commit()

    # Create index on geohash
    op.create_index("ix_iss_passes_geohash", "iss_passes", ["geohash"], unique=False)

    conn.commit()


def downgrade() -> None:
    """Remove geohash column from iss_passes table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if "iss_passes" not in existing_tables:
        return

    # Check if geohash column exists
    existing_columns = [col["name"] for col in inspector.get_columns("iss_passes")]
    if "geohash" not in existing_columns:
        return

    # Drop index first
    existing_indexes = [idx["name"] for idx in inspector.get_indexes("iss_passes")]
    if "ix_iss_passes_geohash" in existing_indexes:
        op.drop_index("ix_iss_passes_geohash", table_name="iss_passes")

    # Drop column
    with op.batch_alter_table("iss_passes", schema=None) as batch_op:
        batch_op.drop_column("geohash")

    conn.commit()

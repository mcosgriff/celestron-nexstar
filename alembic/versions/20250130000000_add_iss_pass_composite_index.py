"""Add composite index for ISS pass queries

Revision ID: 20250130000000
Revises: 20250129000000
Create Date: 2025-01-30 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20250130000000"
down_revision: str | Sequence[str] | None = "20250129000000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add composite index for ISS pass queries that filter on location, rise_time, and fetched_at."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "iss_passes" in existing_tables:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("iss_passes")]

        # Composite index for queries filtering on location, rise_time, and fetched_at
        if "idx_location_rise_fetched" not in existing_indexes:
            op.create_index(
                "idx_location_rise_fetched",
                "iss_passes",
                ["latitude", "longitude", "rise_time", "fetched_at"],
            )


def downgrade() -> None:
    """Remove composite index for ISS pass queries."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "iss_passes" in existing_tables:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("iss_passes")]

        if "idx_location_rise_fetched" in existing_indexes:
            op.drop_index("idx_location_rise_fetched", table_name="iss_passes")

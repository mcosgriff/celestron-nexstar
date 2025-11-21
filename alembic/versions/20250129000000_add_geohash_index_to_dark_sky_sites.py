"""add_geohash_index_to_dark_sky_sites

Revision ID: 20250129000000
Revises: 20250118000000
Create Date: 2025-01-29 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20250129000000"
down_revision: str | Sequence[str] | None = "20250118000000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add geohash index to dark_sky_sites table for efficient spatial proximity searches."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "dark_sky_sites" in existing_tables:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("dark_sky_sites")]

        # Add geohash index if it doesn't exist
        if "idx_dark_sky_geohash" not in existing_indexes:
            op.create_index("idx_dark_sky_geohash", "dark_sky_sites", ["geohash"])


def downgrade() -> None:
    """Remove geohash index from dark_sky_sites table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "dark_sky_sites" in existing_tables:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("dark_sky_sites")]

        if "idx_dark_sky_geohash" in existing_indexes:
            op.drop_index("idx_dark_sky_geohash", table_name="dark_sky_sites")

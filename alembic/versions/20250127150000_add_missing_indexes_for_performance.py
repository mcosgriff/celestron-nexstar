"""Add missing indexes for performance

Revision ID: 20250127150000
Revises: 20250127140000
Create Date: 2025-01-27 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20250127150000"
down_revision: str | Sequence[str] | None = "20250127140000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add missing indexes for improved query performance."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # Add indexes to objects table
    if "objects" in existing_tables:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("objects")]

        # Composite index for moon queries (parent_planet + object_type)
        if "idx_parent_planet_type" not in existing_indexes:
            op.execute("CREATE INDEX IF NOT EXISTS idx_parent_planet_type ON objects(parent_planet, object_type)")

        # Position index for position-based queries
        if "idx_position" not in existing_indexes:
            op.execute("CREATE INDEX IF NOT EXISTS idx_position ON objects(ra_hours, dec_degrees)")

        # Ephemeris name index for dynamic object lookups
        if "idx_ephemeris_name" not in existing_indexes:
            op.execute("CREATE INDEX IF NOT EXISTS idx_ephemeris_name ON objects(ephemeris_name)")

    # Add indexes to observations table
    if "observations" in existing_tables:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("observations")]

        # Composite index for querying observations by object and date
        if "idx_object_observed" not in existing_indexes:
            op.execute("CREATE INDEX IF NOT EXISTS idx_object_observed ON observations(object_id, observed_at)")

    # Add indexes to meteor_showers table
    if "meteor_showers" in existing_tables:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("meteor_showers")]

        # Index for filtering by constellation
        if "idx_radiant_constellation" not in existing_indexes:
            op.execute("CREATE INDEX IF NOT EXISTS idx_radiant_constellation ON meteor_showers(radiant_constellation)")

    # Add indexes to space_events table
    if "space_events" in existing_tables:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("space_events")]

        # Index for filtering by source
        if "idx_event_source" not in existing_indexes:
            op.execute("CREATE INDEX IF NOT EXISTS idx_event_source ON space_events(source)")

    # Add indexes to star_name_mappings table
    if "star_name_mappings" in existing_tables:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("star_name_mappings")]

        # Index for bayer designation searches
        if "idx_bayer_designation" not in existing_indexes:
            op.execute("CREATE INDEX IF NOT EXISTS idx_bayer_designation ON star_name_mappings(bayer_designation)")


def downgrade() -> None:
    """Remove indexes added for performance."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # Remove indexes from objects table
    if "objects" in existing_tables:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("objects")]

        if "idx_parent_planet_type" in existing_indexes:
            op.execute("DROP INDEX IF EXISTS idx_parent_planet_type")
        if "idx_position" in existing_indexes:
            op.execute("DROP INDEX IF EXISTS idx_position")
        if "idx_ephemeris_name" in existing_indexes:
            op.execute("DROP INDEX IF EXISTS idx_ephemeris_name")

    # Remove indexes from observations table
    if "observations" in existing_tables:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("observations")]

        if "idx_object_observed" in existing_indexes:
            op.execute("DROP INDEX IF EXISTS idx_object_observed")

    # Remove indexes from meteor_showers table
    if "meteor_showers" in existing_tables:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("meteor_showers")]

        if "idx_radiant_constellation" in existing_indexes:
            op.execute("DROP INDEX IF EXISTS idx_radiant_constellation")

    # Remove indexes from space_events table
    if "space_events" in existing_tables:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("space_events")]

        if "idx_event_source" in existing_indexes:
            op.execute("DROP INDEX IF EXISTS idx_event_source")

    # Remove indexes from star_name_mappings table
    if "star_name_mappings" in existing_tables:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("star_name_mappings")]

        if "idx_bayer_designation" in existing_indexes:
            op.execute("DROP INDEX IF EXISTS idx_bayer_designation")

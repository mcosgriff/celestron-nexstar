"""rename_sky_at_a_glance_to_rss_feeds

Revision ID: 20250128010000
Revises: 20250128000000
Create Date: 2025-01-28 01:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20250128010000"
down_revision: str | Sequence[str] | None = "20250128000000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename sky_at_a_glance table to rss_feeds."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "sky_at_a_glance" in existing_tables:
        # Get existing indexes before renaming
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("sky_at_a_glance")]

        # Drop indexes that will be recreated with new names
        indexes_to_drop = [
            "ix_sky_at_a_glance_guid",
            "ix_sky_at_a_glance_link",
            "ix_sky_at_a_glance_title",
        ]
        for index_name in indexes_to_drop:
            if index_name in existing_indexes:
                op.drop_index(index_name, table_name="sky_at_a_glance")

        # Rename the table
        op.rename_table("sky_at_a_glance", "rss_feeds")

        # Recreate indexes with new names
        op.create_index("ix_rss_feeds_guid", "rss_feeds", ["guid"], unique=True)
        op.create_index("ix_rss_feeds_link", "rss_feeds", ["link"], unique=True)
        op.create_index("ix_rss_feeds_title", "rss_feeds", ["title"], unique=False)

        # Note: Composite indexes (idx_published_date, idx_source_fetched) don't need renaming
        # as they don't have the table name in their identifier


def downgrade() -> None:
    """Rename rss_feeds table back to sky_at_a_glance."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "rss_feeds" in existing_tables:
        # Get existing indexes
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("rss_feeds")]

        # Drop indexes that will be recreated with old names
        indexes_to_drop = [
            "ix_rss_feeds_guid",
            "ix_rss_feeds_link",
            "ix_rss_feeds_title",
        ]
        for index_name in indexes_to_drop:
            if index_name in existing_indexes:
                op.drop_index(index_name, table_name="rss_feeds")

        # Rename the table back
        op.rename_table("rss_feeds", "sky_at_a_glance")

        # Recreate indexes with old names
        op.create_index("ix_sky_at_a_glance_guid", "sky_at_a_glance", ["guid"], unique=True)
        op.create_index("ix_sky_at_a_glance_link", "sky_at_a_glance", ["link"], unique=True)
        op.create_index("ix_sky_at_a_glance_title", "sky_at_a_glance", ["title"], unique=False)

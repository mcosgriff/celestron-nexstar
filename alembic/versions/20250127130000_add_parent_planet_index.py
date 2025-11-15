"""Add index on parent_planet for moons

Revision ID: 20250127130000
Revises: 20250127120000
Create Date: 2025-01-27 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20250127130000"
down_revision: str | Sequence[str] | None = "20250127120000"  # Add indexes for celestial_data imports
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add index on parent_planet column for efficient moon queries."""
    # Check if objects table exists
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "objects" in existing_tables:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("objects")]

        # Add index on parent_planet if it doesn't exist
        if "idx_parent_planet" not in existing_indexes:
            op.execute("CREATE INDEX IF NOT EXISTS idx_parent_planet ON objects(parent_planet)")


def downgrade() -> None:
    """Remove index on parent_planet column."""
    # Check if objects table exists
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "objects" in existing_tables:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("objects")]

        # Remove index if it exists
        if "idx_parent_planet" in existing_indexes:
            op.execute("DROP INDEX IF EXISTS idx_parent_planet")

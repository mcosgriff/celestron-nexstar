"""Add indexes for celestial_data imports

Revision ID: 20250127120000
Revises: 20251112195700
Create Date: 2025-01-27 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20250127120000"
down_revision: str | Sequence[str] | None = "20251112195700"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add indexes for constellations and asterisms tables."""
    # Check if tables exist
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # Add indexes for constellations table
    if "constellations" in existing_tables:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("constellations")]

        with op.batch_alter_table("constellations", schema=None) as batch_op:
            if "idx_constellation_position" not in existing_indexes:
                batch_op.create_index("idx_constellation_position", ["ra_hours", "dec_degrees"], unique=False)
            if "idx_constellation_bounds" not in existing_indexes:
                batch_op.create_index(
                    "idx_constellation_bounds",
                    ["ra_min_hours", "ra_max_hours", "dec_min_degrees", "dec_max_degrees"],
                    unique=False,
                )

    # Add indexes for asterisms table
    if "asterisms" in existing_tables:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("asterisms")]

        with op.batch_alter_table("asterisms", schema=None) as batch_op:
            if "idx_asterism_position" not in existing_indexes:
                batch_op.create_index("idx_asterism_position", ["ra_hours", "dec_degrees"], unique=False)
            if "idx_asterism_parent" not in existing_indexes:
                batch_op.create_index("idx_asterism_parent", ["parent_constellation"], unique=False)


def downgrade() -> None:
    """Remove indexes from constellations and asterisms tables."""
    # Check if tables exist
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # Remove indexes from constellations table
    if "constellations" in existing_tables:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("constellations")]

        with op.batch_alter_table("constellations", schema=None) as batch_op:
            if "idx_constellation_bounds" in existing_indexes:
                batch_op.drop_index("idx_constellation_bounds")
            if "idx_constellation_position" in existing_indexes:
                batch_op.drop_index("idx_constellation_position")

    # Remove indexes from asterisms table
    if "asterisms" in existing_tables:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("asterisms")]

        with op.batch_alter_table("asterisms", schema=None) as batch_op:
            if "idx_asterism_parent" in existing_indexes:
                batch_op.drop_index("idx_asterism_parent")
            if "idx_asterism_position" in existing_indexes:
                batch_op.drop_index("idx_asterism_position")

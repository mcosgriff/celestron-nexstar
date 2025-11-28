"""Add constellation + magnitude composite indexes for performance

Revision ID: 20251127220200
Revises: 20250201020002
Create Date: 2025-11-27 22:02:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20251127220200"
down_revision: str | Sequence[str] | None = "20250201020002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add composite indexes on (constellation, magnitude) for improved query performance."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # Tables that have constellation and magnitude columns
    tables_to_index = [
        "stars",
        "double_stars",
        "galaxies",
        "nebulae",
        "clusters",
    ]

    for table_name in tables_to_index:
        if table_name not in existing_tables:
            continue

        existing_indexes = [idx["name"] for idx in inspector.get_indexes(table_name)]
        index_name = f"idx_{table_name}_constellation_magnitude"

        if index_name not in existing_indexes:
            op.execute(
                f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name}(constellation, magnitude)"
            )


def downgrade() -> None:
    """Remove composite indexes on (constellation, magnitude)."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    tables_to_index = [
        "stars",
        "double_stars",
        "galaxies",
        "nebulae",
        "clusters",
    ]

    for table_name in tables_to_index:
        if table_name not in existing_tables:
            continue

        existing_indexes = [idx["name"] for idx in inspector.get_indexes(table_name)]
        index_name = f"idx_{table_name}_constellation_magnitude"

        if index_name in existing_indexes:
            op.execute(f"DROP INDEX IF EXISTS {index_name}")

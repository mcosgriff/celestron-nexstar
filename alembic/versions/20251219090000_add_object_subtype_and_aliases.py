"""Add object_subtype and aliases columns to celestial object tables

Revision ID: 20251219090000
Revises: 20251213000001
Create Date: 2025-12-19 09:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251219090000"
down_revision: str | Sequence[str] | None = "20251213000001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add subtype and aliases columns (nullable) to celestial object tables."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    target_tables = [
        "stars",
        "double_stars",
        "galaxies",
        "nebulae",
        "clusters",
        "planets",
        "moons",
    ]

    def _has_column(table: str, column: str) -> bool:
        return column in {col["name"] for col in inspector.get_columns(table)}

    def _has_index(table: str, index_name: str) -> bool:
        return any(idx["name"] == index_name for idx in inspector.get_indexes(table))

    for table in target_tables:
        if table not in existing_tables:
            continue

        # object_subtype column + index
        if not _has_column(table, "object_subtype"):
            op.add_column(table, sa.Column("object_subtype", sa.String(length=100), nullable=True))
        index_name = f"idx_{table}_object_subtype"
        if not _has_index(table, index_name):
            op.create_index(index_name, table, ["object_subtype"], unique=False)

        # aliases column
        if not _has_column(table, "aliases"):
            op.add_column(table, sa.Column("aliases", sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove subtype and aliases columns/indexes."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    target_tables = [
        "stars",
        "double_stars",
        "galaxies",
        "nebulae",
        "clusters",
        "planets",
        "moons",
    ]

    def _has_column(table: str, column: str) -> bool:
        return column in {col["name"] for col in inspector.get_columns(table)}

    def _has_index(table: str, index_name: str) -> bool:
        return any(idx["name"] == index_name for idx in inspector.get_indexes(table))

    for table in target_tables:
        if table not in existing_tables:
            continue

        index_name = f"idx_{table}_object_subtype"
        if _has_index(table, index_name):
            op.drop_index(index_name, table_name=table)

        if _has_column(table, "object_subtype"):
            op.drop_column(table, "object_subtype")
        if _has_column(table, "aliases"):
            op.drop_column(table, "aliases")


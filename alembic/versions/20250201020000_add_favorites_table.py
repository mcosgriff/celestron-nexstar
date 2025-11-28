"""Add favorites table

Revision ID: 20250201020000
Revises: 20250201010000
Create Date: 2025-02-01 02:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20250201020000"
down_revision: str | Sequence[str] | None = "20250201010000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add favorites table with indexes for fast lookups."""
    # Create favorites table
    op.create_table(
        "favorites",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("object_name", sa.String(length=255), nullable=False),
        sa.Column("object_type", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for fast lookups
    op.create_index("ix_favorites_object_name", "favorites", ["object_name"], unique=False)
    op.create_index("ix_favorites_object_type", "favorites", ["object_type"], unique=False)
    op.create_index("ix_favorites_created_at", "favorites", ["created_at"], unique=False)

    # Create unique constraint on object_name to prevent duplicates
    op.create_index("ix_favorites_object_name_unique", "favorites", ["object_name"], unique=True)


def downgrade() -> None:
    """Remove favorites table."""
    op.drop_index("ix_favorites_object_name_unique", table_name="favorites")
    op.drop_index("ix_favorites_created_at", table_name="favorites")
    op.drop_index("ix_favorites_object_type", table_name="favorites")
    op.drop_index("ix_favorites_object_name", table_name="favorites")
    op.drop_table("favorites")

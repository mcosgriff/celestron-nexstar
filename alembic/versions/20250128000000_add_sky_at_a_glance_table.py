"""add_sky_at_a_glance_table

Revision ID: 20250128000000
Revises: 20250127150000
Create Date: 2025-01-28 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20250128000000"
down_revision: str | Sequence[str] | None = "20250127150000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create sky_at_a_glance table for RSS feed articles."""
    op.create_table(
        "sky_at_a_glance",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("link", sa.String(length=1000), nullable=False),
        sa.Column("guid", sa.String(length=500), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("published_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("author", sa.String(length=255), nullable=True),
        sa.Column("categories", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=False, server_default="Sky & Telescope"),
        sa.Column("feed_url", sa.String(length=1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_published_date", "sky_at_a_glance", ["published_date"], unique=False)
    op.create_index("idx_source_fetched", "sky_at_a_glance", ["source", "fetched_at"], unique=False)
    op.create_index(op.f("ix_sky_at_a_glance_guid"), "sky_at_a_glance", ["guid"], unique=True)
    op.create_index(op.f("ix_sky_at_a_glance_link"), "sky_at_a_glance", ["link"], unique=True)
    op.create_index(op.f("ix_sky_at_a_glance_title"), "sky_at_a_glance", ["title"], unique=False)


def downgrade() -> None:
    """Drop sky_at_a_glance table."""
    op.drop_index(op.f("ix_sky_at_a_glance_title"), table_name="sky_at_a_glance")
    op.drop_index(op.f("ix_sky_at_a_glance_link"), table_name="sky_at_a_glance")
    op.drop_index(op.f("ix_sky_at_a_glance_guid"), table_name="sky_at_a_glance")
    op.drop_index("idx_source_fetched", table_name="sky_at_a_glance")
    op.drop_index("idx_published_date", table_name="sky_at_a_glance")
    op.drop_table("sky_at_a_glance")

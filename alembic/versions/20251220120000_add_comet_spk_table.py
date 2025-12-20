"""add comet spk table for Horizons SPK file tracking

Revision ID: 20251220120000
Revises: 20251219112000
Create Date: 2025-12-20 12:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20251220120000"
down_revision = "20251219112000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add comet_spks table for tracking SPK files."""
    op.create_table(
        "comet_spks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("comet_designation", sa.String(100), nullable=False),
        sa.Column("comet_name", sa.String(255), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(1024), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("coverage_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("coverage_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(100), nullable=False, server_default="JPL Horizons"),
        sa.Column("is_valid", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("last_verified", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index("idx_spk_designation", "comet_spks", ["comet_designation"], unique=True)
    op.create_index("idx_spk_coverage", "comet_spks", ["coverage_start", "coverage_end"])
    op.create_index("idx_spk_valid", "comet_spks", ["is_valid"])


def downgrade() -> None:
    """Remove comet_spks table."""
    op.drop_index("idx_spk_valid", table_name="comet_spks")
    op.drop_index("idx_spk_coverage", table_name="comet_spks")
    op.drop_index("idx_spk_designation", table_name="comet_spks")
    op.drop_table("comet_spks")


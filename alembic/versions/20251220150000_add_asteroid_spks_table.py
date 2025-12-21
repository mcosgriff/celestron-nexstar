"""add asteroid spks table for Horizons SPK file tracking

Revision ID: 20251220150000
Revises: 20251220140000
Create Date: 2025-12-20 15:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20251220150000"
down_revision = "20251220140000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add asteroid_spks table for tracking SPK files."""
    op.create_table(
        "asteroid_spks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("asteroid_designation", sa.String(100), nullable=False),
        sa.Column("asteroid_name", sa.String(255), nullable=True),
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
    op.create_index("idx_asteroid_spk_designation", "asteroid_spks", ["asteroid_designation"], unique=True)
    op.create_index("idx_asteroid_spk_coverage", "asteroid_spks", ["coverage_start", "coverage_end"])
    op.create_index("idx_asteroid_spk_valid", "asteroid_spks", ["is_valid"])


def downgrade() -> None:
    """Remove asteroid_spks table."""
    op.drop_index("idx_asteroid_spk_valid", table_name="asteroid_spks")
    op.drop_index("idx_asteroid_spk_coverage", table_name="asteroid_spks")
    op.drop_index("idx_asteroid_spk_designation", table_name="asteroid_spks")
    op.drop_table("asteroid_spks")

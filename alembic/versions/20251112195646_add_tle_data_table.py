"""add_tle_data_table

Revision ID: 20251112195646
Revises: 1a2b3c4d5e6f
Create Date: 2025-11-12 19:56:46.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20251112195646"
down_revision: str | Sequence[str] | None = "1a2b3c4d5e6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create tle_data table for storing satellite TLE data."""
    op.create_table(
        "tle_data",
        sa.Column("norad_id", sa.Integer(), nullable=False),
        sa.Column("satellite_name", sa.String(length=255), nullable=False),
        sa.Column("satellite_group", sa.String(length=50), nullable=True),
        sa.Column("line1", sa.Text(), nullable=False),
        sa.Column("line2", sa.Text(), nullable=False),
        sa.Column("epoch", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("norad_id"),
    )
    op.create_index("idx_satellite_group", "tle_data", ["satellite_group"], unique=False)
    op.create_index("idx_fetched_at", "tle_data", ["fetched_at"], unique=False)
    op.create_index("ix_tle_data_satellite_name", "tle_data", ["satellite_name"], unique=False)


def downgrade() -> None:
    """Drop tle_data table."""
    op.drop_index("ix_tle_data_satellite_name", table_name="tle_data")
    op.drop_index("idx_fetched_at", table_name="tle_data")
    op.drop_index("idx_satellite_group", table_name="tle_data")
    op.drop_table("tle_data")

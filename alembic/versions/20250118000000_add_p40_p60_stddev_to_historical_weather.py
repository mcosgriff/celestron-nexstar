"""add_p40_p60_stddev_to_historical_weather

Revision ID: 20250118000000
Revises: 20251117210131
Create Date: 2025-01-18 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20250118000000"
down_revision: str | Sequence[str] | None = "20251117210131"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add p40, p60, and std_dev columns to historical_weather table."""
    with op.batch_alter_table("historical_weather", schema=None) as batch_op:
        batch_op.add_column(sa.Column("p40_cloud_cover_percent", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("p60_cloud_cover_percent", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("std_dev_cloud_cover_percent", sa.Float(), nullable=True))


def downgrade() -> None:
    """Remove p40, p60, and std_dev columns from historical_weather table."""
    with op.batch_alter_table("historical_weather", schema=None) as batch_op:
        batch_op.drop_column("std_dev_cloud_cover_percent")
        batch_op.drop_column("p60_cloud_cover_percent")
        batch_op.drop_column("p40_cloud_cover_percent")

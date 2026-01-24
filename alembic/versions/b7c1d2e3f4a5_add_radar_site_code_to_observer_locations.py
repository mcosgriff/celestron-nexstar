"""Add radar site code to observer locations.

Revision ID: b7c1d2e3f4a5
Revises: 9c4f1e2d3b6a
Create Date: 2025-02-14 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b7c1d2e3f4a5"
down_revision = "9c4f1e2d3b6a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("observer_locations", sa.Column("radar_site_code", sa.String(length=10), nullable=True))


def downgrade() -> None:
    op.drop_column("observer_locations", "radar_site_code")

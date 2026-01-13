"""add_observer_locations_table

Revision ID: 8a1b2c3d4e5f
Revises: f1af6e2ecaf5
Create Date: 2026-01-05 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8a1b2c3d4e5f"
down_revision: Union[str, Sequence[str], None] = "f1af6e2ecaf5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "observer_locations",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("elevation", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_observer_locations_name", "observer_locations", ["name"], unique=False)
    op.create_index("ix_observer_locations_lat_lon", "observer_locations", ["latitude", "longitude"], unique=False)
    op.create_index("ix_observer_locations_is_active", "observer_locations", ["is_active"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_observer_locations_is_active", table_name="observer_locations")
    op.drop_index("ix_observer_locations_lat_lon", table_name="observer_locations")
    op.drop_index("ix_observer_locations_name", table_name="observer_locations")
    op.drop_table("observer_locations")

"""add_dark_sky_sites_table

Revision ID: 623f166524aa
Revises: a1b2c3d4e5f6
Create Date: 2025-11-09 18:21:39.253991

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "623f166524aa"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add dark_sky_sites table for offline dark sky location data."""
    op.create_table(
        "dark_sky_sites",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("bortle_class", sa.Integer(), nullable=False),
        sa.Column("sqm_value", sa.Float(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    with op.batch_alter_table("dark_sky_sites", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_dark_sky_sites_name"), ["name"], unique=False)
        batch_op.create_index(batch_op.f("ix_dark_sky_sites_latitude"), ["latitude"], unique=False)
        batch_op.create_index(batch_op.f("ix_dark_sky_sites_longitude"), ["longitude"], unique=False)
        batch_op.create_index(batch_op.f("ix_dark_sky_sites_bortle_class"), ["bortle_class"], unique=False)
        batch_op.create_index("idx_location", ["latitude", "longitude"], unique=False)


def downgrade() -> None:
    """Remove dark_sky_sites table."""
    with op.batch_alter_table("dark_sky_sites", schema=None) as batch_op:
        batch_op.drop_index("idx_location")
        batch_op.drop_index(batch_op.f("ix_dark_sky_sites_bortle_class"))
        batch_op.drop_index(batch_op.f("ix_dark_sky_sites_longitude"))
        batch_op.drop_index(batch_op.f("ix_dark_sky_sites_latitude"))
        batch_op.drop_index(batch_op.f("ix_dark_sky_sites_name"))
    op.drop_table("dark_sky_sites")

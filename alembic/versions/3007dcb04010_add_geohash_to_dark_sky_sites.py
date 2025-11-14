"""add_geohash_to_dark_sky_sites

Revision ID: 3007dcb04010
Revises: 20251112195700
Create Date: 2025-11-12 20:47:47.532055

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "3007dcb04010"
down_revision: str | Sequence[str] | None = "20251112195700"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add geohash column to dark_sky_sites table."""
    # Check if column already exists
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "dark_sky_sites" in inspector.get_table_names():
        existing_columns = [col["name"] for col in inspector.get_columns("dark_sky_sites")]
        if "geohash" not in existing_columns:
            with op.batch_alter_table("dark_sky_sites", schema=None) as batch_op:
                batch_op.add_column(sa.Column("geohash", sa.String(length=12), nullable=True))
                batch_op.create_index("ix_dark_sky_sites_geohash", ["geohash"], unique=False)


def downgrade() -> None:
    """Remove geohash column from dark_sky_sites table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "dark_sky_sites" in inspector.get_table_names():
        existing_columns = [col["name"] for col in inspector.get_columns("dark_sky_sites")]
        if "geohash" in existing_columns:
            with op.batch_alter_table("dark_sky_sites", schema=None) as batch_op:
                batch_op.drop_index("ix_dark_sky_sites_geohash")
                batch_op.drop_column("geohash")

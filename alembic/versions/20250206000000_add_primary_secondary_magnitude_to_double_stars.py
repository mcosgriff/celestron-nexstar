"""Add primary_magnitude and secondary_magnitude columns to double_stars table

Adds separate magnitude columns for primary and secondary stars in double star systems.
This allows storing both magnitudes separately instead of just the combined/brightest magnitude.

Revision ID: 20250206000000
Revises: 20250205000000
Create Date: 2025-02-06 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20250206000000"
down_revision: str | Sequence[str] | None = "20250205000000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add primary_magnitude and secondary_magnitude columns to double_stars table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "double_stars" in existing_tables:
        # Check if columns already exist
        columns = [col["name"] for col in inspector.get_columns("double_stars")]
        
        if "primary_magnitude" not in columns:
            op.add_column("double_stars", sa.Column("primary_magnitude", sa.Float(), nullable=True))
        
        if "secondary_magnitude" not in columns:
            op.add_column("double_stars", sa.Column("secondary_magnitude", sa.Float(), nullable=True))


def downgrade() -> None:
    """Remove primary_magnitude and secondary_magnitude columns from double_stars table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "double_stars" in existing_tables:
        columns = [col["name"] for col in inspector.get_columns("double_stars")]
        
        if "primary_magnitude" in columns:
            op.drop_column("double_stars", "primary_magnitude")
        
        if "secondary_magnitude" in columns:
            op.drop_column("double_stars", "secondary_magnitude")


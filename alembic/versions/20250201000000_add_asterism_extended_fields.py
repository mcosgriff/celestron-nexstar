"""Add extended information fields to asterisms table

Revision ID: 20250201000000
Revises: 20250131010000
Create Date: 2025-02-01 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20250201000000"
down_revision: str | Sequence[str] | None = "20250131010000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add extended information fields to asterisms table."""
    # Check if columns already exist (for idempotency)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if "asterisms" not in inspector.get_table_names():
        # Table doesn't exist, skip
        return
    
    existing_columns = {col["name"] for col in inspector.get_columns("asterisms")}
    
    # Add new columns if they don't exist
    if "wikipedia_url" not in existing_columns:
        op.add_column("asterisms", sa.Column("wikipedia_url", sa.String(500), nullable=True))
    
    if "cultural_info" not in existing_columns:
        op.add_column("asterisms", sa.Column("cultural_info", sa.Text(), nullable=True))
    
    if "guidepost_info" not in existing_columns:
        op.add_column("asterisms", sa.Column("guidepost_info", sa.Text(), nullable=True))
    
    if "historical_notes" not in existing_columns:
        op.add_column("asterisms", sa.Column("historical_notes", sa.Text(), nullable=True))
    
    if "shape_description" not in existing_columns:
        op.add_column("asterisms", sa.Column("shape_description", sa.String(255), nullable=True))


def downgrade() -> None:
    """Remove extended information fields from asterisms table."""
    # Check if table exists
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if "asterisms" not in inspector.get_table_names():
        return
    
    existing_columns = {col["name"] for col in inspector.get_columns("asterisms")}
    
    # Remove columns if they exist
    if "shape_description" in existing_columns:
        op.drop_column("asterisms", "shape_description")
    
    if "historical_notes" in existing_columns:
        op.drop_column("asterisms", "historical_notes")
    
    if "guidepost_info" in existing_columns:
        op.drop_column("asterisms", "guidepost_info")
    
    if "cultural_info" in existing_columns:
        op.drop_column("asterisms", "cultural_info")
    
    if "wikipedia_url" in existing_columns:
        op.drop_column("asterisms", "wikipedia_url")


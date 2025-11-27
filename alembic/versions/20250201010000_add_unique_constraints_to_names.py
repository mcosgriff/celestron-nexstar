"""Add unique constraints to name fields and clean up duplicates

Revision ID: 20250201010000
Revises: 20250201000000
Create Date: 2025-02-01 01:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20250201010000"
down_revision: str | Sequence[str] | None = "20250201000000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add unique constraints to name fields and clean up duplicates."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    # List of tables to add unique constraints to
    tables = ["stars", "double_stars", "galaxies", "nebulae", "clusters", "planets", "moons"]
    
    for table_name in tables:
        if table_name not in inspector.get_table_names():
            continue
        
        # First, clean up duplicates - keep the one with the lowest ID
        # SQLite doesn't support DELETE with JOIN, so we use a subquery
        conn.execute(sa.text(f"""
            DELETE FROM {table_name}
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM {table_name}
                GROUP BY name
            )
        """))
        
        # Check if unique constraint already exists
        existing_indexes = {idx["name"] for idx in inspector.get_indexes(table_name)}
        unique_index_name = f"uq_{table_name}_name"
        
        if unique_index_name not in existing_indexes:
            # Create unique index on name
            op.create_index(
                unique_index_name,
                table_name,
                ["name"],
                unique=True,
            )


def downgrade() -> None:
    """Remove unique constraints from name fields."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    # List of tables to remove unique constraints from
    tables = ["stars", "double_stars", "galaxies", "nebulae", "clusters", "planets", "moons"]
    
    for table_name in tables:
        if table_name not in inspector.get_table_names():
            continue
        
        unique_index_name = f"uq_{table_name}_name"
        existing_indexes = {idx["name"] for idx in inspector.get_indexes(table_name)}
        
        if unique_index_name in existing_indexes:
            op.drop_index(unique_index_name, table_name)


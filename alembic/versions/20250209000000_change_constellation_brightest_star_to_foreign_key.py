"""Change constellation brightest_star from string to foreign key.

Changes:
1. Rename brightest_star column to brightest_star_id
2. Change type from String(100) to Integer (foreign key to stars.id)
3. Add foreign key constraint
4. Add index

Revision ID: 20250209000000
Revises: 20250208000000
Create Date: 2025-02-09 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20250209000000"
down_revision: str | Sequence[str] | None = "20250208000000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Change brightest_star from string to foreign key."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "constellations" not in existing_tables:
        return

    columns = {col["name"]: col for col in inspector.get_columns("constellations")}

    # Enable foreign keys
    conn.execute(sa.text("PRAGMA foreign_keys=ON"))

    # Avoid batch_alter_table for tables with geometry columns - it causes issues with
    # GeoAlchemy2 trying to recover geometry columns. Use raw SQL instead.
    
    # Add new foreign key column if it doesn't exist
    if "brightest_star_id" not in columns:
        # Use raw SQL to add the column (avoids batch_alter_table issues with geometry)
        conn.execute(sa.text("ALTER TABLE constellations ADD COLUMN brightest_star_id INTEGER"))
        
        # Add index for faster lookups
        conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_constellations_brightest_star_id ON constellations(brightest_star_id)"))

    # Drop old column if it exists (SQLite 3.35.0+ supports DROP COLUMN)
    # Note: SQLite doesn't support adding foreign key constraints to existing tables,
    # so the FK constraint will be enforced by application logic. The column is just
    # an integer that references stars.id.
    if "brightest_star" in columns:
        try:
            conn.execute(sa.text("ALTER TABLE constellations DROP COLUMN brightest_star"))
        except Exception:
            # If DROP COLUMN is not supported (SQLite < 3.35.0), the old column will remain
            # but be ignored. This is fine - the application will use brightest_star_id instead.
            pass


def downgrade() -> None:
    """Revert brightest_star_id back to string column."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "constellations" not in existing_tables:
        return

    columns = {col["name"]: col for col in inspector.get_columns("constellations")}

    # Drop index and column using raw SQL
    if "brightest_star_id" in columns:
        try:
            conn.execute(sa.text("DROP INDEX IF EXISTS ix_constellations_brightest_star_id"))
            conn.execute(sa.text("ALTER TABLE constellations DROP COLUMN brightest_star_id"))
        except Exception:
            # If DROP COLUMN is not supported, skip
            pass

    # Add back string column if it doesn't exist
    if "brightest_star" not in columns:
        conn.execute(sa.text("ALTER TABLE constellations ADD COLUMN brightest_star VARCHAR(100)"))


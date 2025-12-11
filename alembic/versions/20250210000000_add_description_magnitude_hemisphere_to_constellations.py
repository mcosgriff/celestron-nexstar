"""Add description, magnitude, and hemisphere to constellations.

Adds three new columns to the constellations table:
1. description (Text, nullable) - Description of the constellation
2. magnitude (Float, nullable) - Magnitude of brightest star
3. hemisphere (String(20), nullable) - Hemisphere (Northern, Southern, Equatorial)

Revision ID: 20250210000000
Revises: 20250209000000
Create Date: 2025-02-10 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20250210000000"
down_revision: str | Sequence[str] | None = "20250209000000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add description, magnitude, and hemisphere columns to constellations."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "constellations" not in existing_tables:
        return

    columns = {col["name"]: col for col in inspector.get_columns("constellations")}

    # Use raw SQL to add columns (avoids batch_alter_table issues with geometry)
    if "description" not in columns:
        conn.execute(sa.text("ALTER TABLE constellations ADD COLUMN description TEXT"))

    if "magnitude" not in columns:
        conn.execute(sa.text("ALTER TABLE constellations ADD COLUMN magnitude REAL"))

    if "hemisphere" not in columns:
        conn.execute(sa.text("ALTER TABLE constellations ADD COLUMN hemisphere VARCHAR(20)"))


def downgrade() -> None:
    """Remove description, magnitude, and hemisphere columns from constellations."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "constellations" not in existing_tables:
        return

    columns = {col["name"]: col for col in inspector.get_columns("constellations")}

    # Drop columns using raw SQL
    if "description" in columns:
        try:
            conn.execute(sa.text("ALTER TABLE constellations DROP COLUMN description"))
        except Exception:
            # If DROP COLUMN is not supported (SQLite < 3.35.0), skip
            pass

    if "magnitude" in columns:
        try:
            conn.execute(sa.text("ALTER TABLE constellations DROP COLUMN magnitude"))
        except Exception:
            pass

    if "hemisphere" in columns:
        try:
            conn.execute(sa.text("ALTER TABLE constellations DROP COLUMN hemisphere"))
        except Exception:
            pass


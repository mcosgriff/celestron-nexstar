"""Add constellation_id and asterism_id to double_stars

Adds foreign key-style integer columns to support spatial relationships for
double star objects (WDS).

Revision ID: 20251213000000
Revises: 20250212000000
Create Date: 2025-12-13 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20251213000000"
down_revision: str | Sequence[str] | None = "20250212000000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add constellation_id and asterism_id columns to double_stars."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # Enable foreign keys (SQLite)
    conn.execute(sa.text("PRAGMA foreign_keys=ON"))

    if "double_stars" not in existing_tables:
        return

    columns = {col["name"]: col for col in inspector.get_columns("double_stars")}

    if "constellation_id" not in columns:
        conn.execute(sa.text("ALTER TABLE double_stars ADD COLUMN constellation_id INTEGER"))
        conn.execute(
            sa.text("CREATE INDEX IF NOT EXISTS ix_double_stars_constellation_id ON double_stars(constellation_id)")
        )

    if "asterism_id" not in columns:
        conn.execute(sa.text("ALTER TABLE double_stars ADD COLUMN asterism_id INTEGER"))
        conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_double_stars_asterism_id ON double_stars(asterism_id)"))


def downgrade() -> None:
    """Remove constellation_id and asterism_id columns (best-effort for SQLite)."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "double_stars" not in existing_tables:
        return

    columns = {col["name"]: col for col in inspector.get_columns("double_stars")}

    if "constellation_id" in columns:
        try:
            conn.execute(sa.text("DROP INDEX IF EXISTS ix_double_stars_constellation_id"))
            conn.execute(sa.text("ALTER TABLE double_stars DROP COLUMN constellation_id"))
        except Exception:
            pass

    if "asterism_id" in columns:
        try:
            conn.execute(sa.text("DROP INDEX IF EXISTS ix_double_stars_asterism_id"))
            conn.execute(sa.text("ALTER TABLE double_stars DROP COLUMN asterism_id"))
        except Exception:
            pass



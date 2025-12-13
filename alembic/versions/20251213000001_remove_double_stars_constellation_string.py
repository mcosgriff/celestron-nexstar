"""Remove legacy constellation string column from double_stars

Removes the old `double_stars.constellation` VARCHAR column and related indexes,
now that `double_stars.constellation_id` is available.

Revision ID: 20251213000001
Revises: 20251213000000
Create Date: 2025-12-13 00:00:01.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20251213000001"
down_revision: str | Sequence[str] | None = "20251213000000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop double_stars.constellation (string) and its indexes; add constellation_id composite index."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "double_stars" not in existing_tables:
        return

    cols = {col["name"] for col in inspector.get_columns("double_stars")}

    # Drop indexes that reference the legacy string constellation column (best-effort).
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_double_stars_constellation"))
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_double_star_constellation_magnitude"))
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_double_stars_constellation_magnitude"))

    # Prefer constellation_id-based composite index for performance.
    if "constellation_id" in cols and "magnitude" in cols:
        conn.execute(
            sa.text(
                "CREATE INDEX IF NOT EXISTS idx_double_star_constellation_id_magnitude "
                "ON double_stars(constellation_id, magnitude)"
            )
        )

    # Drop the legacy column (SQLite supports DROP COLUMN on recent versions; best-effort fallback).
    if "constellation" in cols:
        try:
            conn.execute(sa.text("ALTER TABLE double_stars DROP COLUMN constellation"))
        except Exception:
            # If the SQLite version doesn't support DROP COLUMN, we leave the column in place.
            # The ORM mapping excludes it, so the app will still function.
            pass


def downgrade() -> None:
    """Re-add the legacy constellation column (best-effort)."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "double_stars" not in existing_tables:
        return

    cols = {col["name"] for col in inspector.get_columns("double_stars")}

    if "constellation" not in cols:
        try:
            conn.execute(sa.text("ALTER TABLE double_stars ADD COLUMN constellation VARCHAR(50)"))
            conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_double_stars_constellation ON double_stars(constellation)"))
        except Exception:
            pass



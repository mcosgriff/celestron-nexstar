"""Remove constellation and asterism string columns from stars table.

Since we now use foreign keys (constellation_id and asterism_id) to track
relationships, we no longer need the string columns.

Revision ID: 20250212000000
Revises: 20250211000000
Create Date: 2025-02-12 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20250212000000"
down_revision: str | Sequence[str] | None = "20250211000000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Remove constellation and asterism string columns from stars table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "stars" not in existing_tables:
        return

    columns = {col["name"]: col for col in inspector.get_columns("stars")}

    # Drop index on constellation column if it exists
    if "constellation" in columns:
        try:
            conn.execute(sa.text("DROP INDEX IF EXISTS idx_star_constellation_magnitude"))
        except Exception:
            pass

    # Drop constellation column
    if "constellation" in columns:
        try:
            conn.execute(sa.text("ALTER TABLE stars DROP COLUMN constellation"))
        except Exception:
            # SQLite < 3.35.0 doesn't support DROP COLUMN
            # In that case, the column will remain but be ignored
            pass

    # Drop asterism column
    if "asterism" in columns:
        try:
            conn.execute(sa.text("DROP INDEX IF EXISTS ix_stars_asterism"))
        except Exception:
            pass
        try:
            conn.execute(sa.text("ALTER TABLE stars DROP COLUMN asterism"))
        except Exception:
            # SQLite < 3.35.0 doesn't support DROP COLUMN
            pass

    # Recreate index using constellation_id instead
    try:
        conn.execute(
            sa.text(
                "CREATE INDEX IF NOT EXISTS idx_star_constellation_id_magnitude ON stars(constellation_id, magnitude)"
            )
        )
    except Exception:
        pass


def downgrade() -> None:
    """Add back constellation and asterism string columns."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "stars" not in existing_tables:
        return

    columns = {col["name"]: col for col in inspector.get_columns("stars")}

    # Add back constellation column
    if "constellation" not in columns:
        conn.execute(sa.text("ALTER TABLE stars ADD COLUMN constellation VARCHAR(50)"))
        conn.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_star_constellation_magnitude ON stars(constellation, magnitude)"))

    # Add back asterism column
    if "asterism" not in columns:
        conn.execute(sa.text("ALTER TABLE stars ADD COLUMN asterism VARCHAR(255)"))
        conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_stars_asterism ON stars(asterism)"))

    # Drop the new index
    try:
        conn.execute(sa.text("DROP INDEX IF EXISTS idx_star_constellation_id_magnitude"))
    except Exception:
        pass



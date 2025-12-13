"""Add foreign keys for spatial relationships.

Adds foreign key columns for spatial relationships:
1. asterisms.parent_constellation_id - FK to constellations.id
2. stars.constellation_id - FK to constellations.id
3. stars.asterism_id - FK to asterisms.id
4. galaxies.constellation_id - FK to constellations.id
5. galaxies.asterism_id - FK to asterisms.id
6. nebulae.constellation_id - FK to constellations.id
7. nebulae.asterism_id - FK to asterisms.id
8. clusters.constellation_id - FK to constellations.id
9. clusters.asterism_id - FK to asterisms.id

These will be populated via spatial queries during import.

Revision ID: 20250211000000
Revises: 20250210000000
Create Date: 2025-02-11 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20250211000000"
down_revision: str | Sequence[str] | None = "20250210000000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add foreign key columns for spatial relationships."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # Enable foreign keys
    conn.execute(sa.text("PRAGMA foreign_keys=ON"))

    # 1. Add constellation_id and asterism_id to stars
    if "stars" in existing_tables:
        columns = {col["name"]: col for col in inspector.get_columns("stars")}
        if "constellation_id" not in columns:
            conn.execute(sa.text("ALTER TABLE stars ADD COLUMN constellation_id INTEGER"))
            conn.execute(
                sa.text("CREATE INDEX IF NOT EXISTS ix_stars_constellation_id ON stars(constellation_id)")
            )
        if "asterism_id" not in columns:
            conn.execute(sa.text("ALTER TABLE stars ADD COLUMN asterism_id INTEGER"))
            conn.execute(
                sa.text("CREATE INDEX IF NOT EXISTS ix_stars_asterism_id ON stars(asterism_id)")
            )

    # 2. Add parent_constellation_id to asterisms
    if "asterisms" in existing_tables:
        columns = {col["name"]: col for col in inspector.get_columns("asterisms")}
        if "parent_constellation_id" not in columns:
            conn.execute(sa.text("ALTER TABLE asterisms ADD COLUMN parent_constellation_id INTEGER"))
            conn.execute(
                sa.text("CREATE INDEX IF NOT EXISTS ix_asterisms_parent_constellation_id ON asterisms(parent_constellation_id)")
            )

    # 3. Add constellation_id and asterism_id to galaxies
    if "galaxies" in existing_tables:
        columns = {col["name"]: col for col in inspector.get_columns("galaxies")}
        if "constellation_id" not in columns:
            conn.execute(sa.text("ALTER TABLE galaxies ADD COLUMN constellation_id INTEGER"))
            conn.execute(
                sa.text("CREATE INDEX IF NOT EXISTS ix_galaxies_constellation_id ON galaxies(constellation_id)")
            )
        if "asterism_id" not in columns:
            conn.execute(sa.text("ALTER TABLE galaxies ADD COLUMN asterism_id INTEGER"))
            conn.execute(
                sa.text("CREATE INDEX IF NOT EXISTS ix_galaxies_asterism_id ON galaxies(asterism_id)")
            )

    # 4. Add constellation_id and asterism_id to nebulae
    if "nebulae" in existing_tables:
        columns = {col["name"]: col for col in inspector.get_columns("nebulae")}
        if "constellation_id" not in columns:
            conn.execute(sa.text("ALTER TABLE nebulae ADD COLUMN constellation_id INTEGER"))
            conn.execute(
                sa.text("CREATE INDEX IF NOT EXISTS ix_nebulae_constellation_id ON nebulae(constellation_id)")
            )
        if "asterism_id" not in columns:
            conn.execute(sa.text("ALTER TABLE nebulae ADD COLUMN asterism_id INTEGER"))
            conn.execute(
                sa.text("CREATE INDEX IF NOT EXISTS ix_nebulae_asterism_id ON nebulae(asterism_id)")
            )

    # 5. Add constellation_id and asterism_id to clusters
    if "clusters" in existing_tables:
        columns = {col["name"]: col for col in inspector.get_columns("clusters")}
        if "constellation_id" not in columns:
            conn.execute(sa.text("ALTER TABLE clusters ADD COLUMN constellation_id INTEGER"))
            conn.execute(
                sa.text("CREATE INDEX IF NOT EXISTS ix_clusters_constellation_id ON clusters(constellation_id)")
            )
        if "asterism_id" not in columns:
            conn.execute(sa.text("ALTER TABLE clusters ADD COLUMN asterism_id INTEGER"))
            conn.execute(
                sa.text("CREATE INDEX IF NOT EXISTS ix_clusters_asterism_id ON clusters(asterism_id)")
            )


def downgrade() -> None:
    """Remove foreign key columns."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # Remove indexes and columns
    if "stars" in existing_tables:
        columns = {col["name"]: col for col in inspector.get_columns("stars")}
        if "constellation_id" in columns:
            try:
                conn.execute(sa.text("DROP INDEX IF EXISTS ix_stars_constellation_id"))
                conn.execute(sa.text("ALTER TABLE stars DROP COLUMN constellation_id"))
            except Exception:
                pass
        if "asterism_id" in columns:
            try:
                conn.execute(sa.text("DROP INDEX IF EXISTS ix_stars_asterism_id"))
                conn.execute(sa.text("ALTER TABLE stars DROP COLUMN asterism_id"))
            except Exception:
                pass

    if "asterisms" in existing_tables:
        columns = {col["name"]: col for col in inspector.get_columns("asterisms")}
        if "parent_constellation_id" in columns:
            try:
                conn.execute(sa.text("DROP INDEX IF EXISTS ix_asterisms_parent_constellation_id"))
                conn.execute(sa.text("ALTER TABLE asterisms DROP COLUMN parent_constellation_id"))
            except Exception:
                pass

    if "galaxies" in existing_tables:
        columns = {col["name"]: col for col in inspector.get_columns("galaxies")}
        if "constellation_id" in columns:
            try:
                conn.execute(sa.text("DROP INDEX IF EXISTS ix_galaxies_constellation_id"))
                conn.execute(sa.text("ALTER TABLE galaxies DROP COLUMN constellation_id"))
            except Exception:
                pass
        if "asterism_id" in columns:
            try:
                conn.execute(sa.text("DROP INDEX IF EXISTS ix_galaxies_asterism_id"))
                conn.execute(sa.text("ALTER TABLE galaxies DROP COLUMN asterism_id"))
            except Exception:
                pass

    if "nebulae" in existing_tables:
        columns = {col["name"]: col for col in inspector.get_columns("nebulae")}
        if "constellation_id" in columns:
            try:
                conn.execute(sa.text("DROP INDEX IF EXISTS ix_nebulae_constellation_id"))
                conn.execute(sa.text("ALTER TABLE nebulae DROP COLUMN constellation_id"))
            except Exception:
                pass
        if "asterism_id" in columns:
            try:
                conn.execute(sa.text("DROP INDEX IF EXISTS ix_nebulae_asterism_id"))
                conn.execute(sa.text("ALTER TABLE nebulae DROP COLUMN asterism_id"))
            except Exception:
                pass

    if "clusters" in existing_tables:
        columns = {col["name"]: col for col in inspector.get_columns("clusters")}
        if "constellation_id" in columns:
            try:
                conn.execute(sa.text("DROP INDEX IF EXISTS ix_clusters_constellation_id"))
                conn.execute(sa.text("ALTER TABLE clusters DROP COLUMN constellation_id"))
            except Exception:
                pass
        if "asterism_id" in columns:
            try:
                conn.execute(sa.text("DROP INDEX IF EXISTS ix_clusters_asterism_id"))
                conn.execute(sa.text("ALTER TABLE clusters DROP COLUMN asterism_id"))
            except Exception:
                pass


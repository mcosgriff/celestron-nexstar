"""add_geohash_to_light_pollution_grid

Revision ID: 9a8b7c6d5e4f
Revises: f1e2d3c4b5a6
Create Date: 2025-01-27 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "9a8b7c6d5e4f"
down_revision: str | Sequence[str] | None = "f1e2d3c4b5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add geohash column to light_pollution_grid table and populate from lat/lon.
    If the table doesn't exist, create it with geohash column included.
    """
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # Create table if it doesn't exist
    if "light_pollution_grid" not in existing_tables:
        # Create the table with all columns including geohash
        op.execute(
            text(
                """
                CREATE TABLE light_pollution_grid (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    geohash TEXT NOT NULL,
                    sqm_value REAL NOT NULL,
                    region TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(latitude, longitude)
                )
                """
            )
        )
        # Create indexes
        op.execute(text("CREATE INDEX IF NOT EXISTS idx_lp_geohash ON light_pollution_grid(geohash)"))
        op.execute(text("CREATE INDEX IF NOT EXISTS idx_lp_lat_lon ON light_pollution_grid(latitude, longitude)"))
        op.execute(text("CREATE INDEX IF NOT EXISTS idx_lp_region ON light_pollution_grid(region)"))
        return

    # Check if geohash column already exists
    existing_columns = [col["name"] for col in inspector.get_columns("light_pollution_grid")]
    if "geohash" in existing_columns:
        # Column already exists, just ensure index exists
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("light_pollution_grid")]
        if "idx_lp_geohash" not in existing_indexes:
            op.create_index("idx_lp_geohash", "light_pollution_grid", ["geohash"], unique=False)
        return

    # Add geohash column (nullable initially, will be populated)
    with op.batch_alter_table("light_pollution_grid", schema=None) as batch_op:
        batch_op.add_column(sa.Column("geohash", sa.String(length=12), nullable=True))

    # Import geohash utility to calculate geohashes
    from celestron_nexstar.api.location.geohash_utils import encode

    # Populate geohash for all existing rows
    # Fetch all rows with lat/lon
    result = conn.execute(text("SELECT id, latitude, longitude FROM light_pollution_grid WHERE geohash IS NULL"))
    rows = result.fetchall()

    if rows:
        # Update each row with its geohash (precision 9 for ~5m accuracy)
        # Process in batches for better performance
        batch_size = 1000
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            for row in batch:
                row_id, lat, lon = row
                geohash_str = encode(float(lat), float(lon), precision=9)
                conn.execute(
                    text("UPDATE light_pollution_grid SET geohash = :geohash WHERE id = :id"),
                    {"geohash": geohash_str, "id": row_id},
                )
            # Commit in batches to avoid long transactions
            conn.commit()

    # Make geohash NOT NULL now that all rows are populated
    with op.batch_alter_table("light_pollution_grid", schema=None) as batch_op:
        # SQLite doesn't support ALTER COLUMN, so we need to recreate the table
        # But since we're using batch_alter_table, Alembic handles this
        # For SQLite, we'll need to do this manually
        pass

    # For SQLite, we need to recreate the table to make geohash NOT NULL
    # This is a limitation of SQLite's ALTER TABLE
    # We'll use a workaround: create a new table, copy data, drop old, rename new
    conn.execute(
        text(
            """
            CREATE TABLE light_pollution_grid_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                geohash TEXT NOT NULL,
                sqm_value REAL NOT NULL,
                region TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(latitude, longitude)
            )
            """
        )
    )

    # Copy data from old table to new table
    conn.execute(
        text(
            """
            INSERT INTO light_pollution_grid_new
            (id, latitude, longitude, geohash, sqm_value, region, created_at)
            SELECT id, latitude, longitude, geohash, sqm_value, region, created_at
            FROM light_pollution_grid
            """
        )
    )

    # Drop old table
    conn.execute(text("DROP TABLE light_pollution_grid"))

    # Rename new table
    conn.execute(text("ALTER TABLE light_pollution_grid_new RENAME TO light_pollution_grid"))

    # Recreate indexes
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_lp_geohash ON light_pollution_grid(geohash)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_lp_lat_lon ON light_pollution_grid(latitude, longitude)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_lp_region ON light_pollution_grid(region)"))

    conn.commit()


def downgrade() -> None:
    """Remove geohash column from light_pollution_grid table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if "light_pollution_grid" not in existing_tables:
        return

    # Drop geohash index if it exists
    existing_indexes = [idx["name"] for idx in inspector.get_indexes("light_pollution_grid")]
    if "idx_lp_geohash" in existing_indexes:
        op.drop_index("idx_lp_geohash", table_name="light_pollution_grid")

    # For SQLite, recreate table without geohash column
    conn.execute(
        text(
            """
            CREATE TABLE light_pollution_grid_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                sqm_value REAL NOT NULL,
                region TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(latitude, longitude)
            )
            """
        )
    )

    # Copy data (excluding geohash)
    conn.execute(
        text(
            """
            INSERT INTO light_pollution_grid_new
            (id, latitude, longitude, sqm_value, region, created_at)
            SELECT id, latitude, longitude, sqm_value, region, created_at
            FROM light_pollution_grid
            """
        )
    )

    # Drop old table
    conn.execute(text("DROP TABLE light_pollution_grid"))

    # Rename new table
    conn.execute(text("ALTER TABLE light_pollution_grid_new RENAME TO light_pollution_grid"))

    # Recreate indexes (without geohash)
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_lp_lat_lon ON light_pollution_grid(latitude, longitude)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_lp_region ON light_pollution_grid(region)"))

    conn.commit()

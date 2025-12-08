"""Add R-tree spatial indexes for celestial objects

Revision ID: 20250202000000
Revises: 20251127220200
Create Date: 2025-02-02 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "20250202000000"
down_revision: str | Sequence[str] | None = "20251127220200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create R-tree virtual tables for spatial indexing of celestial objects."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # R-tree tables for each object type table
    # R-tree format: id, minX, maxX, minY, maxY
    # For celestial coordinates:
    #   minX/maxX = RA in degrees (converted from hours: ra_hours * 15.0)
    #   minY/maxY = Dec in degrees
    rtree_tables = {
        "rtree_stars": "stars",
        "rtree_double_stars": "double_stars",
        "rtree_galaxies": "galaxies",
        "rtree_nebulae": "nebulae",
        "rtree_clusters": "clusters",
    }

    for rtree_table, source_table in rtree_tables.items():
        if source_table not in existing_tables:
            continue

        # Check if R-tree table already exists
        if rtree_table in existing_tables:
            continue

        # Create R-tree virtual table
        # R-tree stores bounding boxes: id, minX, maxX, minY, maxY
        # For stars, we use the same point for min/max (point objects)
        op.execute(
            text(
                f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS {rtree_table} USING rtree(
                    id,              -- Integer primary key (references source table)
                    minX, maxX,      -- RA in degrees (ra_hours * 15.0)
                    minY, maxY       -- Dec in degrees
                )
                """
            )
        )

        # Populate R-tree table with existing data
        # Convert RA from hours to degrees for R-tree
        # Handle RA wrap-around: convert to -180 to 180 range
        op.execute(
            text(
                f"""
                INSERT INTO {rtree_table} (id, minX, maxX, minY, maxY)
                SELECT 
                    id,
                    CASE 
                        WHEN ra_hours * 15.0 > 180 THEN (ra_hours * 15.0) - 360
                        ELSE ra_hours * 15.0
                    END AS minX,  -- Convert hours to degrees, handle wrap-around
                    CASE 
                        WHEN ra_hours * 15.0 > 180 THEN (ra_hours * 15.0) - 360
                        ELSE ra_hours * 15.0
                    END AS maxX,  -- Same for point objects
                    dec_degrees AS minY,
                    dec_degrees AS maxY
                FROM {source_table}
                WHERE ra_hours IS NOT NULL AND dec_degrees IS NOT NULL
                """
            )
        )

        # Create triggers to keep R-tree in sync with source table
        # Insert trigger
        op.execute(
            text(
                f"""
                CREATE TRIGGER IF NOT EXISTS {source_table}_rtree_insert AFTER INSERT ON {source_table}
                WHEN NEW.ra_hours IS NOT NULL AND NEW.dec_degrees IS NOT NULL
                BEGIN
                    INSERT INTO {rtree_table} (id, minX, maxX, minY, maxY)
                    VALUES (
                        NEW.id,
                        CASE 
                            WHEN NEW.ra_hours * 15.0 > 180 THEN (NEW.ra_hours * 15.0) - 360
                            ELSE NEW.ra_hours * 15.0
                        END,
                        CASE 
                            WHEN NEW.ra_hours * 15.0 > 180 THEN (NEW.ra_hours * 15.0) - 360
                            ELSE NEW.ra_hours * 15.0
                        END,
                        NEW.dec_degrees,
                        NEW.dec_degrees
                    );
                END
                """
            )
        )

        # Delete trigger
        op.execute(
            text(
                f"""
                CREATE TRIGGER IF NOT EXISTS {source_table}_rtree_delete AFTER DELETE ON {source_table}
                BEGIN
                    DELETE FROM {rtree_table} WHERE id = OLD.id;
                END
                """
            )
        )

        # Update trigger
        op.execute(
            text(
                f"""
                CREATE TRIGGER IF NOT EXISTS {source_table}_rtree_update AFTER UPDATE ON {source_table}
                WHEN NEW.ra_hours IS NOT NULL AND NEW.dec_degrees IS NOT NULL
                BEGIN
                    DELETE FROM {rtree_table} WHERE id = OLD.id;
                    INSERT INTO {rtree_table} (id, minX, maxX, minY, maxY)
                    VALUES (
                        NEW.id,
                        CASE 
                            WHEN NEW.ra_hours * 15.0 > 180 THEN (NEW.ra_hours * 15.0) - 360
                            ELSE NEW.ra_hours * 15.0
                        END,
                        CASE 
                            WHEN NEW.ra_hours * 15.0 > 180 THEN (NEW.ra_hours * 15.0) - 360
                            ELSE NEW.ra_hours * 15.0
                        END,
                        NEW.dec_degrees,
                        NEW.dec_degrees
                    );
                END
                """
            )
        )


def downgrade() -> None:
    """Remove R-tree virtual tables and triggers."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    rtree_tables = {
        "rtree_stars": "stars",
        "rtree_double_stars": "double_stars",
        "rtree_galaxies": "galaxies",
        "rtree_nebulae": "nebulae",
        "rtree_clusters": "clusters",
    }

    for rtree_table, source_table in rtree_tables.items():
        # Drop triggers
        op.execute(text(f"DROP TRIGGER IF EXISTS {source_table}_rtree_insert"))
        op.execute(text(f"DROP TRIGGER IF EXISTS {source_table}_rtree_delete"))
        op.execute(text(f"DROP TRIGGER IF EXISTS {source_table}_rtree_update"))

        # Drop R-tree table
        if rtree_table in existing_tables:
            op.execute(text(f"DROP TABLE IF EXISTS {rtree_table}"))


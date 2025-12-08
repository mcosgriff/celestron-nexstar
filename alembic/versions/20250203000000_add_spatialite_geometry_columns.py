"""Add SpatiaLite geometry columns for all spatial objects

Adds geometry columns to:
- Point objects: stars, double_stars, galaxies, nebulae, clusters (POINT geometry)
- Complex objects: constellations (POLYGON/MultiPolygon), asterisms (MultiLineString)

Revision ID: 20250203000000
Revises: 20250202000000
Create Date: 2025-02-03 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "20250203000000"
down_revision: str | Sequence[str] | None = "20250202000000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add geometry columns to all spatial object tables using SpatiaLite's AddGeometryColumn."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())
    
    # Load SpatiaLite extension (REQUIRED)
    try:
        # Try to enable extension loading
        dbapi_conn = conn.connection.dbapi_connection
        dbapi_conn.enable_load_extension(True)
        # Try common extension names
        spatialite_loaded = False
        for ext_name in ["mod_spatialite", "mod_spatialite.so", "mod_spatialite.dylib", "mod_spatialite.dll"]:
            try:
                dbapi_conn.load_extension(ext_name)
                spatialite_loaded = True
                break
            except Exception:
                continue
        if not spatialite_loaded:
            # Try system paths
            import platform
            import os
            system = platform.system()
            if system == "Darwin":
                paths = ["/opt/homebrew/lib/mod_spatialite.dylib", "/usr/local/lib/mod_spatialite.dylib"]
            elif system == "Linux":
                paths = ["/usr/lib/x86_64-linux-gnu/mod_spatialite.so", "/usr/local/lib/mod_spatialite.so"]
            else:
                paths = []
            for path in paths:
                if os.path.exists(path):
                    try:
                        dbapi_conn.load_extension(path)
                        spatialite_loaded = True
                        break
                    except Exception:
                        continue
        dbapi_conn.enable_load_extension(False)
        
        if not spatialite_loaded:
            raise RuntimeError(
                "SpatiaLite extension is required but could not be loaded. "
                "Please install SpatiaLite:\n"
                "  macOS: brew install spatialite-tools\n"
                "  Linux: apt-get install spatialite-bin libspatialite-dev\n"
                "  Or download from: https://www.gaia-gis.it/fossil/libspatialite/"
            )
        
        # Initialize SpatiaLite metadata if needed
        try:
            conn.execute(text("SELECT InitSpatialMetadata(1)"))
        except Exception:
            # Metadata might already exist - that's fine
            pass
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(
            f"Failed to load SpatiaLite extension: {e}. "
            "SpatiaLite is required for geometry columns."
        ) from e
    
    # Tables that need POINT geometry (stars, DSOs, etc.)
    point_geometry_tables = [
        "stars",
        "double_stars",
        "galaxies",
        "nebulae",
        "clusters",
    ]
    
    # Tables that need POLYGON/LINESTRING geometry (boundaries/patterns)
    complex_geometry_tables = {
        "constellations": "GEOMETRY",  # Polygon/MultiPolygon
        "asterisms": "GEOMETRY",  # MultiLineString/LineString
    }
    
    # Use SpatiaLite's AddGeometryColumn which:
    # 1. Creates the BLOB column
    # 2. Registers it in SpatiaLite metadata (geometry_columns table)
    # 3. Creates the spatial index automatically
    
    # Add POINT geometry columns to all spatial object tables
    for table_name in point_geometry_tables:
        if table_name in existing_tables:
            columns = [col["name"] for col in inspector.get_columns(table_name)]
            if "geometry" not in columns:
                # AddGeometryColumn(table, column, srid, type, dimension, not_null)
                # This creates the column, registers it, and creates the spatial index
                conn.execute(
                    text(
                        f"SELECT AddGeometryColumn('{table_name}', 'geometry', 0, 'POINT', 'XY', 0)"
                    )
                )
    
    # Add complex geometry columns (Polygon/LineString) to constellations and asterisms
    for table_name, geom_type in complex_geometry_tables.items():
        if table_name in existing_tables:
            columns = [col["name"] for col in inspector.get_columns(table_name)]
            if "geometry" not in columns:
                # AddGeometryColumn creates column, registers it, and creates spatial index
                conn.execute(
                    text(
                        f"SELECT AddGeometryColumn('{table_name}', 'geometry', 0, '{geom_type}', 'XY', 0)"
                    )
                )
    
    # Note: Don't commit here - Alembic manages transactions


def downgrade() -> None:
    """Remove geometry columns from all spatial object tables."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())
    
    # All tables with geometry columns
    geometry_tables = [
        "stars",
        "double_stars",
        "galaxies",
        "nebulae",
        "clusters",
        "constellations",
        "asterisms",
    ]
    
    # Try to use SpatiaLite to remove geometry columns properly
    for table_name in geometry_tables:
        if table_name in existing_tables:
            columns = [col["name"] for col in inspector.get_columns(table_name)]
            if "geometry" in columns:
                try:
                    # Try to remove using SpatiaLite's DiscardGeometryColumn
                    conn.execute(text(f"SELECT DiscardGeometryColumn('{table_name}', 'geometry')"))
                except Exception:
                    # Fallback to direct column drop
                    try:
                        op.drop_column(table_name, "geometry")
                    except Exception:
                        pass
    
    # Note: Don't commit here - Alembic manages transactions


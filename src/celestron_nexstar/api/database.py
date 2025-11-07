"""
SQLite-based Catalog Database

Provides efficient storage and querying for 40,000+ celestial objects
with full-text search, filtering, and offline capabilities.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .catalogs import CelestialObject
from .enums import CelestialObjectType
from .ephemeris import get_planetary_position, is_dynamic_object

logger = logging.getLogger(__name__)

__all__ = [
    "CatalogDatabase",
    "DatabaseStats",
    "get_database",
    "init_database",
]

# SQL Schema
SCHEMA_SQL = """
-- Main objects table
CREATE TABLE IF NOT EXISTS objects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    common_name TEXT,
    catalog TEXT NOT NULL,
    catalog_number INTEGER,

    -- Position (J2000 epoch for fixed objects)
    ra_hours REAL NOT NULL,
    dec_degrees REAL NOT NULL,

    -- Physical properties
    magnitude REAL,
    object_type TEXT NOT NULL,
    size_arcmin REAL,

    -- Metadata
    description TEXT,
    constellation TEXT,

    -- Dynamic object support (planets/moons)
    is_dynamic INTEGER DEFAULT 0,
    ephemeris_name TEXT,
    parent_planet TEXT,

    -- Timestamps
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_name ON objects(name);
CREATE INDEX IF NOT EXISTS idx_catalog ON objects(catalog);
CREATE INDEX IF NOT EXISTS idx_magnitude ON objects(magnitude);
CREATE INDEX IF NOT EXISTS idx_type ON objects(object_type);
CREATE INDEX IF NOT EXISTS idx_constellation ON objects(constellation);
CREATE INDEX IF NOT EXISTS idx_is_dynamic ON objects(is_dynamic);
CREATE INDEX IF NOT EXISTS idx_catalog_number ON objects(catalog, catalog_number);

-- Full-text search virtual table
CREATE VIRTUAL TABLE IF NOT EXISTS objects_fts USING fts5(
    name,
    common_name,
    description,
    content=objects,
    content_rowid=id
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS objects_ai AFTER INSERT ON objects BEGIN
    INSERT INTO objects_fts(rowid, name, common_name, description)
    VALUES (new.id, new.name, new.common_name, new.description);
END;

CREATE TRIGGER IF NOT EXISTS objects_ad AFTER DELETE ON objects BEGIN
    DELETE FROM objects_fts WHERE rowid = old.id;
END;

CREATE TRIGGER IF NOT EXISTS objects_au AFTER UPDATE ON objects BEGIN
    UPDATE objects_fts SET
        name = new.name,
        common_name = new.common_name,
        description = new.description
    WHERE rowid = new.id;
END;

-- Metadata table for database version and stats
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


@dataclass(frozen=True)
class DatabaseStats:
    """Statistics about the catalog database."""

    total_objects: int
    objects_by_catalog: dict[str, int]
    objects_by_type: dict[str, int]
    magnitude_range: tuple[float | None, float | None]
    dynamic_objects: int
    database_version: str
    last_updated: datetime | None


class CatalogDatabase:
    """Interface to the SQLite catalog database."""

    def __init__(self, db_path: Path | str | None = None):
        """
        Initialize database connection.

        Args:
            db_path: Path to database file (default: bundled catalogs.db)
        """
        if db_path is None:
            db_path = self._get_default_db_path()

        self.db_path = Path(db_path)
        self.conn: sqlite3.Connection | None = None
        self._connect()

    def _get_default_db_path(self) -> Path:
        """Get path to bundled database file."""
        # Same logic as catalogs.yaml path resolution
        module_path = Path(__file__).parent
        parent = module_path.parent
        db_path = parent / "cli" / "data" / "catalogs.db"

        if db_path.exists():
            return db_path

        # Fallback for installed package
        import sys

        if hasattr(sys, "_MEIPASS"):
            db_path = Path(sys._MEIPASS) / "celestron_nexstar" / "cli" / "data" / "catalogs.db"
            if db_path.exists():
                return db_path

        # If database doesn't exist yet, return expected path
        # (will be created during migration)
        return parent / "cli" / "data" / "catalogs.db"

    def _connect(self) -> None:
        """Connect to database and enable optimizations."""
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row

        # Enable optimizations
        self.conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging
        self.conn.execute("PRAGMA synchronous=NORMAL")  # Faster writes
        self.conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
        self.conn.execute("PRAGMA temp_store=MEMORY")  # Temp tables in RAM

    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self) -> CatalogDatabase:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: type, exc_val: Exception, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()

    def init_schema(self) -> None:
        """Initialize database schema."""
        if not self.conn:
            raise RuntimeError("Database not connected")

        self.conn.executescript(SCHEMA_SQL)
        self.conn.commit()
        logger.info("Database schema initialized")

    def insert_object(
        self,
        name: str,
        catalog: str,
        ra_hours: float,
        dec_degrees: float,
        object_type: CelestialObjectType | str,
        magnitude: float | None = None,
        common_name: str | None = None,
        catalog_number: int | None = None,
        size_arcmin: float | None = None,
        description: str | None = None,
        constellation: str | None = None,
        is_dynamic: bool = False,
        ephemeris_name: str | None = None,
        parent_planet: str | None = None,
    ) -> int:
        """
        Insert a celestial object into database.

        Args:
            name: Object name (e.g., "M31", "NGC 224")
            catalog: Catalog name (e.g., "messier", "ngc")
            ra_hours: Right ascension in hours
            dec_degrees: Declination in degrees
            object_type: Type of object
            magnitude: Apparent magnitude
            common_name: Common name (e.g., "Andromeda Galaxy")
            catalog_number: Numeric catalog number
            size_arcmin: Angular size in arcminutes
            description: Description text
            constellation: Constellation name
            is_dynamic: True for planets/moons
            ephemeris_name: Name for ephemeris lookup
            parent_planet: Parent planet for moons

        Returns:
            ID of inserted object
        """
        if not self.conn:
            raise RuntimeError("Database not connected")

        # Convert object_type to string if needed
        if isinstance(object_type, CelestialObjectType):
            object_type = object_type.value

        cursor = self.conn.execute(
            """
            INSERT INTO objects (
                name, common_name, catalog, catalog_number,
                ra_hours, dec_degrees, magnitude, object_type, size_arcmin,
                description, constellation,
                is_dynamic, ephemeris_name, parent_planet
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                common_name,
                catalog,
                catalog_number,
                ra_hours,
                dec_degrees,
                magnitude,
                object_type,
                size_arcmin,
                description,
                constellation,
                1 if is_dynamic else 0,
                ephemeris_name,
                parent_planet,
            ),
        )

        return cursor.lastrowid

    def get_by_id(self, object_id: int) -> CelestialObject | None:
        """Get object by ID."""
        if not self.conn:
            raise RuntimeError("Database not connected")

        cursor = self.conn.execute("SELECT * FROM objects WHERE id = ?", (object_id,))
        row = cursor.fetchone()

        if row is None:
            return None

        return self._row_to_object(row)

    def get_by_name(self, name: str) -> CelestialObject | None:
        """Get object by exact name match."""
        if not self.conn:
            raise RuntimeError("Database not connected")

        cursor = self.conn.execute("SELECT * FROM objects WHERE name = ? COLLATE NOCASE LIMIT 1", (name,))
        row = cursor.fetchone()

        if row is None:
            return None

        return self._row_to_object(row)

    def search(self, query: str, limit: int = 100) -> list[CelestialObject]:
        """
        Fuzzy search using FTS5.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of matching objects
        """
        if not self.conn:
            raise RuntimeError("Database not connected")

        # Use FTS5 MATCH for fuzzy search
        cursor = self.conn.execute(
            """
            SELECT objects.* FROM objects
            JOIN objects_fts ON objects.id = objects_fts.rowid
            WHERE objects_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, limit),
        )

        return [self._row_to_object(row) for row in cursor.fetchall()]

    def get_by_catalog(self, catalog: str, limit: int = 1000) -> list[CelestialObject]:
        """Get all objects from a specific catalog."""
        if not self.conn:
            raise RuntimeError("Database not connected")

        cursor = self.conn.execute(
            """
            SELECT * FROM objects
            WHERE catalog = ?
            ORDER BY catalog_number, name
            LIMIT ?
            """,
            (catalog, limit),
        )

        return [self._row_to_object(row) for row in cursor.fetchall()]

    def filter_objects(
        self,
        catalog: str | None = None,
        object_type: CelestialObjectType | str | None = None,
        max_magnitude: float | None = None,
        min_magnitude: float | None = None,
        constellation: str | None = None,
        is_dynamic: bool | None = None,
        limit: int = 1000,
    ) -> list[CelestialObject]:
        """
        Filter objects by various criteria.

        Args:
            catalog: Filter by catalog name
            object_type: Filter by object type
            max_magnitude: Maximum magnitude (fainter)
            min_magnitude: Minimum magnitude (brighter)
            constellation: Filter by constellation
            is_dynamic: Filter dynamic objects
            limit: Maximum results

        Returns:
            List of matching objects
        """
        if not self.conn:
            raise RuntimeError("Database not connected")

        # Build WHERE clause dynamically
        conditions = []
        params = []

        if catalog:
            conditions.append("catalog = ?")
            params.append(catalog)

        if object_type:
            if isinstance(object_type, CelestialObjectType):
                object_type = object_type.value
            conditions.append("object_type = ?")
            params.append(object_type)

        if max_magnitude is not None:
            conditions.append("magnitude <= ?")
            params.append(max_magnitude)

        if min_magnitude is not None:
            conditions.append("magnitude >= ?")
            params.append(min_magnitude)

        if constellation:
            conditions.append("constellation = ? COLLATE NOCASE")
            params.append(constellation)

        if is_dynamic is not None:
            conditions.append("is_dynamic = ?")
            params.append(1 if is_dynamic else 0)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)

        cursor = self.conn.execute(
            f"""
            SELECT * FROM objects
            WHERE {where_clause}
            ORDER BY magnitude ASC, name ASC
            LIMIT ?
            """,
            params,
        )

        return [self._row_to_object(row) for row in cursor.fetchall()]

    def get_all_catalogs(self) -> list[str]:
        """Get list of all catalog names."""
        if not self.conn:
            raise RuntimeError("Database not connected")

        cursor = self.conn.execute("SELECT DISTINCT catalog FROM objects ORDER BY catalog")
        return [row[0] for row in cursor.fetchall()]

    def get_stats(self) -> DatabaseStats:
        """Get database statistics."""
        if not self.conn:
            raise RuntimeError("Database not connected")

        # Total count
        total = self.conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0]

        # By catalog
        by_catalog = {}
        for row in self.conn.execute("SELECT catalog, COUNT(*) FROM objects GROUP BY catalog"):
            by_catalog[row[0]] = row[1]

        # By type
        by_type = {}
        for row in self.conn.execute("SELECT object_type, COUNT(*) FROM objects GROUP BY object_type"):
            by_type[row[0]] = row[1]

        # Magnitude range
        mag_row = self.conn.execute("SELECT MIN(magnitude), MAX(magnitude) FROM objects WHERE magnitude IS NOT NULL").fetchone()
        mag_range = (mag_row[0], mag_row[1]) if mag_row else (None, None)

        # Dynamic objects
        dynamic = self.conn.execute("SELECT COUNT(*) FROM objects WHERE is_dynamic = 1").fetchone()[0]

        # Version
        version_row = self.conn.execute("SELECT value FROM metadata WHERE key = 'version'").fetchone()
        version = version_row[0] if version_row else "unknown"

        # Last updated
        updated_row = self.conn.execute("SELECT value FROM metadata WHERE key = 'last_updated'").fetchone()
        last_updated = datetime.fromisoformat(updated_row[0]) if updated_row else None

        return DatabaseStats(
            total_objects=total,
            objects_by_catalog=by_catalog,
            objects_by_type=by_type,
            magnitude_range=mag_range,
            dynamic_objects=dynamic,
            database_version=version,
            last_updated=last_updated,
        )

    def _row_to_object(self, row: sqlite3.Row) -> CelestialObject:
        """Convert database row to CelestialObject."""
        obj = CelestialObject(
            name=row["name"],
            common_name=row["common_name"],
            ra_hours=row["ra_hours"],
            dec_degrees=row["dec_degrees"],
            magnitude=row["magnitude"],
            object_type=CelestialObjectType(row["object_type"]),
            catalog=row["catalog"],
            description=row["description"],
            parent_planet=row["parent_planet"],
        )

        # Handle dynamic objects
        if row["is_dynamic"] and is_dynamic_object(row["ephemeris_name"] or row["name"]):
            try:
                ra, dec = get_planetary_position(row["ephemeris_name"] or row["name"])
                from dataclasses import replace

                obj = replace(obj, ra_hours=ra, dec_degrees=dec)
            except (ValueError, KeyError):
                pass  # Use stored coordinates as fallback

        return obj

    def commit(self) -> None:
        """Commit pending transactions."""
        if self.conn:
            self.conn.commit()


# Global database instance
_database_instance: CatalogDatabase | None = None


def get_database() -> CatalogDatabase:
    """
    Get the global database instance.

    Returns:
        Singleton database instance
    """
    global _database_instance
    if _database_instance is None:
        _database_instance = CatalogDatabase()
    return _database_instance


def init_database(db_path: Path | str | None = None) -> CatalogDatabase:
    """
    Initialize a new database with schema.

    Args:
        db_path: Path to database file

    Returns:
        Initialized database
    """
    db = CatalogDatabase(db_path)
    db.init_schema()
    return db

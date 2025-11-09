"""
SQLite-based Catalog Database

Provides efficient storage and querying for 40,000+ celestial objects
with full-text search, filtering, and offline capabilities.

Uses SQLAlchemy ORM for type-safe database operations.
"""

from __future__ import annotations

import logging
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from .catalogs import CelestialObject
from .enums import CelestialObjectType
from .ephemeris import get_planetary_position, is_dynamic_object
from .models import CelestialObjectModel, MetadataModel


logger = logging.getLogger(__name__)

__all__ = [
    "CatalogDatabase",
    "DatabaseStats",
    "get_database",
    "init_database",
    "vacuum_database",
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
CREATE INDEX IF NOT EXISTS idx_common_name ON objects(common_name);
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
    """Interface to the SQLite catalog database using SQLAlchemy ORM."""

    def __init__(self, db_path: Path | str | None = None):
        """
        Initialize database connection.

        Args:
            db_path: Path to database file (default: bundled catalogs.db)
        """
        if db_path is None:
            db_path = self._get_default_db_path()

        self.db_path = Path(db_path)

        # Use pysqlite3 if available (supports SpatiaLite extensions)
        # Fall back to built-in sqlite3 if not available
        try:
            import pysqlite3  # type: ignore[import-untyped]
            dbapi = pysqlite3
        except ImportError:
            import sqlite3
            dbapi = sqlite3

        self._engine = create_engine(
            f"sqlite:///{self.db_path}",
            module=dbapi,  # Use pysqlite3 for extension support
            poolclass=None,  # No connection pooling for SQLite
            connect_args={
                "check_same_thread": False,  # Allow multi-threaded access
            },
            echo=False,  # Set to True for SQL debugging
        )
        self._Session = sessionmaker(bind=self._engine, expire_on_commit=False)
        self._configure_optimizations()

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

    def _configure_optimizations(self) -> None:
        """Configure SQLite optimizations via engine events."""
        from sqlalchemy import event

        @event.listens_for(self._engine, "connect")
        def set_sqlite_pragmas(dbapi_conn: Any, connection_record: Any) -> None:
            """Set SQLite pragmas for performance and enable extension loading."""
            cursor = dbapi_conn.cursor()

            # Enable extension loading if supported (for SpatiaLite)
            # Built-in sqlite3 may not support enable_load_extension
            # This is fine - SpatiaLite is optional
            with suppress(AttributeError):
                dbapi_conn.enable_load_extension(True)

            cursor.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging
            cursor.execute("PRAGMA synchronous=NORMAL")  # Faster writes
            cursor.execute("PRAGMA cache_size=-64000")  # 64MB cache
            cursor.execute("PRAGMA temp_store=MEMORY")  # Temp tables in RAM
            cursor.close()

    def _get_session(self) -> Session:
        """Get a new database session."""
        return self._Session()

    def close(self) -> None:
        """Close database connection."""
        self._engine.dispose()

    def __enter__(self) -> CatalogDatabase:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: type, exc_val: Exception, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()

    def init_schema(self) -> None:
        """
        Initialize database schema.

        Note: This method is kept for backwards compatibility.
        For new databases, use Alembic migrations instead.
        """
        from .models import Base

        # Create all tables
        Base.metadata.create_all(self._engine)

        # Create FTS5 table and triggers (not handled by SQLAlchemy)
        with self._get_session() as session:
            # Create FTS5 virtual table
            session.execute(
                text("""
                CREATE VIRTUAL TABLE IF NOT EXISTS objects_fts USING fts5(
                    name,
                    common_name,
                    description,
                    content=objects,
                    content_rowid=id
                )
            """)
            )

            # Create triggers
            session.execute(
                text("""
                CREATE TRIGGER IF NOT EXISTS objects_ai AFTER INSERT ON objects BEGIN
                    INSERT INTO objects_fts(rowid, name, common_name, description)
                    VALUES (new.id, new.name, new.common_name, new.description);
                END
            """)
            )

            session.execute(
                text("""
                CREATE TRIGGER IF NOT EXISTS objects_ad AFTER DELETE ON objects BEGIN
                    DELETE FROM objects_fts WHERE rowid = old.id;
                END
            """)
            )

            session.execute(
                text("""
                CREATE TRIGGER IF NOT EXISTS objects_au AFTER UPDATE ON objects BEGIN
                    UPDATE objects_fts SET
                        name = new.name,
                        common_name = new.common_name,
                        description = new.description
                    WHERE rowid = new.id;
                END
            """)
            )

            session.commit()

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
        # Convert object_type to string if needed
        if isinstance(object_type, CelestialObjectType):
            object_type = object_type.value

        model = CelestialObjectModel(
            name=name,
            common_name=common_name,
            catalog=catalog,
            catalog_number=catalog_number,
            ra_hours=ra_hours,
            dec_degrees=dec_degrees,
            magnitude=magnitude,
            object_type=object_type,
            size_arcmin=size_arcmin,
            description=description,
            constellation=constellation,
            is_dynamic=is_dynamic,
            ephemeris_name=ephemeris_name,
            parent_planet=parent_planet,
        )

        with self._get_session() as session:
            session.add(model)
            session.commit()
            session.refresh(model)
            return model.id

    def get_by_id(self, object_id: int) -> CelestialObject | None:
        """Get object by ID."""
        with self._get_session() as session:
            model = session.get(CelestialObjectModel, object_id)
            if model is None:
                return None
            return self._model_to_object(model)

    def get_by_name(self, name: str) -> CelestialObject | None:
        """Get object by exact name match."""
        # Ensure name is a string
        name = str(name) if name is not None else ""
        with self._get_session() as session:
            # Use ilike() which is SQLAlchemy's standard case-insensitive comparison
            # It handles type coercion automatically
            model = (
                session.query(CelestialObjectModel)
                .filter(CelestialObjectModel.name.ilike(name))
                .first()
            )
            if model is None:
                return None
            return self._model_to_object(model)

    def search(self, query: str, limit: int = 100) -> list[CelestialObject]:
        """
        Fuzzy search using FTS5.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of matching objects
        """
        # Ensure query is a string
        query = str(query) if query is not None else ""
        with self._get_session() as session:
            # FTS5 search requires raw SQL
            result = session.execute(
                text("""
                    SELECT objects.id FROM objects
                    JOIN objects_fts ON objects.id = objects_fts.rowid
                    WHERE objects_fts MATCH :query
                    ORDER BY rank
                    LIMIT :limit
                """),
                {"query": query, "limit": limit},
            )

            # Get IDs and fetch models
            object_ids = [row[0] for row in result]
            objects = []
            for obj_id in object_ids:
                model = session.get(CelestialObjectModel, obj_id)
                if model:
                    objects.append(self._model_to_object(model))

            return objects

    def get_by_catalog(self, catalog: str, limit: int = 1000) -> list[CelestialObject]:
        """Get all objects from a specific catalog."""
        with self._get_session() as session:
            models = (
                session.query(CelestialObjectModel)
                .filter(CelestialObjectModel.catalog == catalog)
                .order_by(CelestialObjectModel.catalog_number, CelestialObjectModel.name)
                .limit(limit)
                .all()
            )
            return [self._model_to_object(model) for model in models]

    def exists_by_catalog_number(self, catalog: str, catalog_number: int) -> bool:
        """
        Check if an object exists with the given catalog and catalog number.

        Args:
            catalog: Catalog name
            catalog_number: Catalog number

        Returns:
            True if object exists, False otherwise
        """
        with self._get_session() as session:
            count = (
                session.query(CelestialObjectModel)
                .filter(
                    CelestialObjectModel.catalog == catalog,
                    CelestialObjectModel.catalog_number == catalog_number,
                )
                .count()
            )
            return count > 0

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
        with self._get_session() as session:
            query = session.query(CelestialObjectModel)

            # Build filters
            if catalog:
                query = query.filter(CelestialObjectModel.catalog == catalog)

            if object_type:
                if isinstance(object_type, CelestialObjectType):
                    object_type = object_type.value
                query = query.filter(CelestialObjectModel.object_type == object_type)

            if max_magnitude is not None:
                query = query.filter(CelestialObjectModel.magnitude <= max_magnitude)

            if min_magnitude is not None:
                query = query.filter(CelestialObjectModel.magnitude >= min_magnitude)

            if constellation:
                query = query.filter(CelestialObjectModel.constellation.ilike(constellation))

            if is_dynamic is not None:
                query = query.filter(CelestialObjectModel.is_dynamic == is_dynamic)

            # Order and limit
            models = (
                query.order_by(CelestialObjectModel.magnitude.asc().nulls_last(), CelestialObjectModel.name.asc())
                .limit(limit)
                .all()
            )

            return [self._model_to_object(model) for model in models]

    def get_all_catalogs(self) -> list[str]:
        """Get list of all catalog names."""
        with self._get_session() as session:
            catalogs = (
                session.query(CelestialObjectModel.catalog).distinct().order_by(CelestialObjectModel.catalog).all()
            )
            return [catalog[0] for catalog in catalogs]

    def get_names_for_completion(self, prefix: str = "", limit: int = 50) -> list[str]:
        """
        Get object names for command-line autocompletion.

        Filters names that start with the given prefix (case-insensitive).
        Searches both the `name` and `common_name` fields.

        Args:
            prefix: Prefix to match (empty string returns all)
            limit: Maximum number of results to return

        Returns:
            List of unique names matching the prefix (case-insensitive)
        """
        from sqlalchemy import func, select

        with self._get_session() as session:
            # Build case-insensitive filter using LIKE for better compatibility
            prefix_lower = str(prefix).lower()

            # Query both name and common_name fields, returning the actual values
            # Use a UNION-like approach with separate queries, then combine
            names_set = set()

            # Query name field
            name_query = (
                select(CelestialObjectModel.name)
                .distinct()
                .filter(func.lower(CelestialObjectModel.name).like(f"{prefix_lower}%"))
                .order_by(func.lower(CelestialObjectModel.name))
                .limit(limit)
            )
            name_results = session.execute(name_query).fetchall()
            for row in name_results:
                if row[0]:
                    names_set.add(row[0])

            # Query common_name field
            common_name_query = (
                select(CelestialObjectModel.common_name)
                .distinct()
                .filter(
                    CelestialObjectModel.common_name.isnot(None),
                    func.lower(CelestialObjectModel.common_name).like(f"{prefix_lower}%"),
                )
                .order_by(func.lower(CelestialObjectModel.common_name))
                .limit(limit)
            )
            common_name_results = session.execute(common_name_query).fetchall()
            for row in common_name_results:
                if row[0]:
                    names_set.add(row[0])

            # Return sorted list, limited to requested limit
            return sorted(names_set, key=str.lower)[:limit]

    def get_all_names_for_completion(self, limit: int = 10000) -> list[str]:
        """
        Get all object names for command-line autocompletion.

        DEPRECATED: Use get_names_for_completion() with a prefix for better performance.

        Args:
            limit: Maximum number of results to return

        Returns:
            List of unique names (case-insensitive)
        """
        return self.get_names_for_completion(prefix="", limit=limit)

    def get_stats(self) -> DatabaseStats:
        """Get database statistics."""
        from sqlalchemy import func

        with self._get_session() as session:
            # Total count
            total = session.query(func.count(CelestialObjectModel.id)).scalar()

            # By catalog
            catalog_counts = (
                session.query(CelestialObjectModel.catalog, func.count(CelestialObjectModel.id))
                .group_by(CelestialObjectModel.catalog)
                .all()
            )
            by_catalog: dict[str, int] = {row[0]: row[1] for row in catalog_counts}

            # By type
            type_counts = (
                session.query(CelestialObjectModel.object_type, func.count(CelestialObjectModel.id))
                .group_by(CelestialObjectModel.object_type)
                .all()
            )
            by_type: dict[str, int] = {row[0]: row[1] for row in type_counts}

            # Magnitude range
            mag_result = (
                session.query(
                    func.min(CelestialObjectModel.magnitude),
                    func.max(CelestialObjectModel.magnitude),
                )
                .filter(CelestialObjectModel.magnitude.isnot(None))
                .first()
            )
            mag_range = (mag_result[0], mag_result[1]) if mag_result and mag_result[0] is not None else (None, None)

            # Dynamic objects
            dynamic = (
                session.query(func.count(CelestialObjectModel.id))
                .filter(CelestialObjectModel.is_dynamic.is_(True))
                .scalar()
            )

            # Version
            version_model = session.get(MetadataModel, "version")
            version = version_model.value if version_model else "unknown"

            # Last updated
            updated_model = session.get(MetadataModel, "last_updated")
            last_updated = (
                datetime.fromisoformat(updated_model.value) if updated_model and updated_model.value else None
            )

            return DatabaseStats(
                total_objects=total or 0,
                objects_by_catalog=by_catalog,
                objects_by_type=by_type,
                magnitude_range=mag_range,
                dynamic_objects=dynamic or 0,
                database_version=version,
                last_updated=last_updated,
            )

    def _model_to_object(self, model: CelestialObjectModel) -> CelestialObject:
        """Convert SQLAlchemy model to CelestialObject."""
        # Ensure name and common_name are strings (handle cases where DB has integers)
        name = str(model.name) if model.name is not None else None
        common_name = str(model.common_name) if model.common_name is not None else None

        obj = CelestialObject(
            name=name,
            common_name=common_name,
            ra_hours=model.ra_hours,
            dec_degrees=model.dec_degrees,
            magnitude=model.magnitude,
            object_type=CelestialObjectType(model.object_type),
            catalog=model.catalog,
            description=model.description,
            parent_planet=model.parent_planet,
        )

        # Handle dynamic objects
        ephemeris_name = str(model.ephemeris_name) if model.ephemeris_name else str(name) if name else ""
        if model.is_dynamic and is_dynamic_object(ephemeris_name):
            try:
                ra, dec = get_planetary_position(ephemeris_name)
                from dataclasses import replace

                obj = replace(obj, ra_hours=ra, dec_degrees=dec)
            except (ValueError, KeyError):
                pass  # Use stored coordinates as fallback

        return obj

    def commit(self) -> None:
        """
        Commit pending transactions.

        Note: With SQLAlchemy, commits are handled per-session.
        This method is kept for backwards compatibility but does nothing.
        """
        # Sessions handle their own commits
        pass


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


def vacuum_database(db: CatalogDatabase | None = None) -> tuple[int, int]:
    """
    Reclaim unused space in the database by running VACUUM.

    SQLite doesn't automatically reclaim space when data is deleted.
    VACUUM rebuilds the database file, removing free pages and reducing file size.

    Args:
        db: Database instance (default: uses get_database())

    Returns:
        Tuple of (size_before_bytes, size_after_bytes)
    """
    if db is None:
        db = get_database()

    # Get file size before vacuum
    size_before = db.db_path.stat().st_size if db.db_path.exists() else 0

    logger.info(f"Running VACUUM on database: {db.db_path}")
    logger.info(f"Database size before: {size_before / (1024 * 1024):.2f} MB")

    # Run VACUUM
    # Note: VACUUM rebuilds the entire database file, so we need to ensure
    # all connections are closed for the file size to update properly
    with db._get_session() as session:
        session.execute(text("VACUUM"))
        session.commit()

    # Close the engine to ensure all connections are released and file is written
    # This is important because VACUUM creates a new database file
    db._engine.dispose()

    # Small delay to ensure filesystem updates (some filesystems cache stat info)
    import time

    time.sleep(0.1)

    # Get file size after vacuum
    # Note: Some filesystems may cache file size, so the actual size on disk
    # may differ from what stat() reports immediately after VACUUM
    size_after = db.db_path.stat().st_size if db.db_path.exists() else 0

    size_reclaimed = size_before - size_after

    logger.info(f"Database size after: {size_after / (1024 * 1024):.2f} MB")
    logger.info(f"Space reclaimed: {size_reclaimed / (1024 * 1024):.2f} MB")
    logger.info(
        f"Note: If filesystem shows different size, it may be cached. "
        f"Actual size on disk: {size_after / (1024 * 1024):.2f} MB"
    )

    return (size_before, size_after)

"""
SQLite-based Catalog Database

Provides efficient storage and querying for 40,000+ celestial objects
with full-text search, filtering, and offline capabilities.

Uses SQLAlchemy ORM for type-safe database operations.
"""

from __future__ import annotations

import logging
import shutil
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import deal
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session, sessionmaker

from .catalogs import CelestialObject
from .enums import CelestialObjectType
from .ephemeris import get_planetary_position, is_dynamic_object
from .models import CelestialObjectModel, EphemerisFileModel, MetadataModel


logger = logging.getLogger(__name__)

__all__ = [
    "CatalogDatabase",
    "DatabaseStats",
    "backup_database",
    "get_database",
    "init_database",
    "list_ephemeris_files_from_naif",
    "rebuild_database",
    "restore_database",
    "sync_ephemeris_files_from_naif",
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
            db_path: Path to database file (default: ~/.config/celestron-nexstar/catalogs.db)
        """
        if db_path is None:
            db_path = self._get_default_db_path()

        self.db_path = Path(db_path)

        # Use built-in sqlite3 (no longer need pysqlite3 since SpatiaLite was removed)
        import sqlite3

        dbapi = sqlite3

        self._engine = create_engine(
            f"sqlite:///{self.db_path}",
            module=dbapi,
            poolclass=None,  # No connection pooling for SQLite
            connect_args={
                "check_same_thread": False,  # Allow multi-threaded access
            },
            echo=False,  # Set to True for SQL debugging
        )
        self._Session = sessionmaker(bind=self._engine, expire_on_commit=False)
        self._configure_optimizations()

    def _get_default_db_path(self) -> Path:
        """Get path to database file in user config directory."""
        # Store database in user's config directory (~/.config/celestron-nexstar/)
        config_dir = Path.home() / ".config" / "celestron-nexstar"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "catalogs.db"

    def _configure_optimizations(self) -> None:
        """Configure SQLite optimizations via engine events."""
        from sqlalchemy import event

        @event.listens_for(self._engine, "connect")
        def set_sqlite_pragmas(dbapi_conn: Any, connection_record: Any) -> None:
            """Set SQLite pragmas for performance."""
            cursor = dbapi_conn.cursor()

            cursor.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging
            cursor.execute("PRAGMA synchronous=NORMAL")  # Faster writes
            cursor.execute("PRAGMA cache_size=-64000")  # 64MB cache
            cursor.execute("PRAGMA temp_store=MEMORY")  # Temp tables in RAM
            cursor.close()

    def _get_session(self) -> Session:
        """Get a new database session."""
        return self._Session()

    @deal.post(lambda result: result is None, message="Close must complete")
    def close(self) -> None:
        """Close database connection."""
        self._engine.dispose()

    def __enter__(self) -> CatalogDatabase:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: type, exc_val: Exception, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()

    @deal.post(lambda result: result is None, message="Schema initialization must complete")
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

    @deal.post(lambda result: result is None, message="FTS table ensure must complete")
    def ensure_fts_table(self) -> None:
        """
        Ensure the FTS5 table exists. Creates it if missing.

        This is useful when the database was created without migrations
        or if the FTS table was accidentally dropped.
        """
        with self._get_session() as session:
            # Check if FTS table exists
            result = session.execute(
                text("""
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name='objects_fts'
                """)
            ).fetchone()

            if result is None:
                logger.info("Creating missing objects_fts table")
                # Create FTS5 virtual table
                session.execute(
                    text("""
                    CREATE VIRTUAL TABLE objects_fts USING fts5(
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

                # Populate FTS table with existing objects
                session.execute(
                    text("""
                    INSERT INTO objects_fts(rowid, name, common_name, description)
                    SELECT id, name, common_name, description FROM objects
                """)
                )

                session.commit()
                logger.info("FTS table created and populated")

    @deal.post(lambda result: result is None, message="FTS repopulation must complete")
    def repopulate_fts_table(self) -> None:
        """
        Repopulate the FTS table with all existing objects.

        Useful if objects were inserted before the FTS table was created,
        or if the FTS table got out of sync.

        Note: For external content tables (content=objects), we need to use
        INSERT OR REPLACE to properly sync the FTS table.
        """
        self.ensure_fts_table()  # Make sure table exists

        with self._get_session() as session:
            # For external content FTS tables, we need to rebuild the index
            # Delete all existing FTS data first
            try:
                session.execute(text("DELETE FROM objects_fts"))
                session.commit()
            except Exception:
                pass  # Table might be empty or not exist

            # Repopulate from objects table
            # For external content tables, use INSERT OR REPLACE
            session.execute(
                text("""
                    INSERT OR REPLACE INTO objects_fts(rowid, name, common_name, description)
                    SELECT id, name, common_name, description FROM objects
                    WHERE name IS NOT NULL
                """)
            )
            session.commit()

            # Verify the repopulation
            # FTS5 table requires raw SQL (virtual table)
            fts_count = session.execute(text("SELECT COUNT(*) FROM objects_fts")).scalar() or 0
            # Use SQLAlchemy for objects count
            from sqlalchemy import func, select

            objects_count = (
                session.scalar(select(func.count(CelestialObjectModel.id)).where(CelestialObjectModel.name.isnot(None)))
                or 0
            )

            logger.info(f"FTS table repopulated: {fts_count} entries (expected {objects_count})")

            if fts_count != objects_count:
                logger.warning(f"FTS table count mismatch: {fts_count} vs {objects_count} objects")

    @deal.pre(
        lambda self,
        name,
        catalog,
        ra_hours,
        dec_degrees,
        object_type,
        magnitude,
        common_name,
        catalog_number,
        size_arcmin,
        description,
        constellation,
        is_dynamic,
        ephemeris_name,
        parent_planet: name and len(name.strip()) > 0,
        message="Name must be non-empty",
    )  # type: ignore[misc,arg-type]
    @deal.pre(
        lambda self,
        name,
        catalog,
        ra_hours,
        dec_degrees,
        object_type,
        magnitude,
        common_name,
        catalog_number,
        size_arcmin,
        description,
        constellation,
        is_dynamic,
        ephemeris_name,
        parent_planet: catalog and len(catalog.strip()) > 0,
        message="Catalog must be non-empty",
    )  # type: ignore[misc,arg-type]
    @deal.pre(
        lambda self,
        name,
        catalog,
        ra_hours,
        dec_degrees,
        object_type,
        magnitude,
        common_name,
        catalog_number,
        size_arcmin,
        description,
        constellation,
        is_dynamic,
        ephemeris_name,
        parent_planet: 0 <= ra_hours < 24,
        message="RA must be 0-24 hours",
    )  # type: ignore[misc,arg-type]
    @deal.pre(
        lambda self,
        name,
        catalog,
        ra_hours,
        dec_degrees,
        object_type,
        magnitude,
        common_name,
        catalog_number,
        size_arcmin,
        description,
        constellation,
        is_dynamic,
        ephemeris_name,
        parent_planet: -90 <= dec_degrees <= 90,
        message="Dec must be -90 to +90 degrees",
    )  # type: ignore[misc,arg-type]
    @deal.post(lambda result: result > 0, message="Insert must return positive ID")
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
        # Ensure FTS table exists before inserting (triggers depend on it)
        self.ensure_fts_table()

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

    @deal.pre(lambda self, object_id: object_id > 0, message="Object ID must be positive")  # type: ignore[misc,arg-type]
    @deal.post(
        lambda result: result is None or isinstance(result, CelestialObject),
        message="Must return CelestialObject or None",
    )
    def get_by_id(self, object_id: int) -> CelestialObject | None:
        """Get object by ID."""
        with self._get_session() as session:
            model = session.get(CelestialObjectModel, object_id)
            if model is None:
                return None
            return self._model_to_object(model)

    @deal.pre(lambda self, name: name and len(name.strip()) > 0, message="Name must be non-empty")  # type: ignore[misc,arg-type]
    @deal.post(
        lambda result: result is None or isinstance(result, CelestialObject),
        message="Must return CelestialObject or None",
    )
    def get_by_name(self, name: str) -> CelestialObject | None:
        """
        Get object by exact name match (checks both name and common_name fields).

        Returns the first exact match found in either name or common_name field.
        This allows finding stars by common name (e.g., "Capella") even if stored
        as catalog number in name field (e.g., "HR 1708").
        """
        # Ensure name is a string
        name = str(name) if name is not None else ""
        if not name:
            return None

        with self._get_session() as session:
            # Check name field first (most common case)
            model = session.query(CelestialObjectModel).filter(CelestialObjectModel.name.ilike(name)).first()
            if model:
                return self._model_to_object(model)

            # If not found in name, check common_name field (exact match only)
            model = (
                session.query(CelestialObjectModel)
                .filter(
                    CelestialObjectModel.common_name.isnot(None),
                    CelestialObjectModel.common_name.ilike(name),
                )
                .first()
            )
            if model:
                return self._model_to_object(model)

            return None

    @deal.pre(lambda self, hr_number: hr_number > 0, message="HR number must be positive")  # type: ignore[misc,arg-type]
    @deal.post(lambda result: result is None or isinstance(result, str), message="Must return string or None")
    def get_common_name_by_hr(self, hr_number: int) -> str | None:
        """
        Get common name for a given HR number from star_name_mappings table.

        Args:
            hr_number: HR catalog number

        Returns:
            Common name if found, None otherwise
        """
        with self._get_session() as session:
            from .models import StarNameMappingModel

            mapping = session.query(StarNameMappingModel).filter(StarNameMappingModel.hr_number == hr_number).first()
            if mapping and mapping.common_name and mapping.common_name.strip():
                return mapping.common_name.strip()
            return None

    @deal.pre(lambda self, query, limit: query and len(query.strip()) > 0, message="Query must be non-empty")  # type: ignore[misc,arg-type]
    @deal.pre(lambda self, query, limit: limit > 0, message="Limit must be positive")  # type: ignore[misc,arg-type]
    @deal.post(lambda result: isinstance(result, list), message="Must return list of objects")
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
        if not query:
            return []

        # Ensure FTS table exists
        self.ensure_fts_table()

        with self._get_session() as session:
            # FTS5 search requires raw SQL
            # FTS5 query syntax: simple word queries work directly
            # For multi-word queries, FTS5 uses AND by default
            # Escape special characters that FTS5 treats as operators
            fts_query = query.strip()

            # FTS5 special characters: " AND OR NOT ( ) [ ] { } * : ^
            # If query contains these, we need to escape or quote them
            # For simple word searches, just use the word directly
            try:
                result = session.execute(
                    text("""
                        SELECT objects.id FROM objects
                        JOIN objects_fts ON objects.id = objects_fts.rowid
                        WHERE objects_fts MATCH :query
                        ORDER BY rank
                        LIMIT :limit
                    """),
                    {"query": fts_query, "limit": limit},
                )

                # Get IDs and fetch models
                object_ids = [row[0] for row in result]
                objects = []
                for obj_id in object_ids:
                    model = session.get(CelestialObjectModel, obj_id)
                    if model:
                        objects.append(self._model_to_object(model))

                return objects
            except Exception as e:
                logger.error(f"FTS5 search failed for query '{query}': {e}")
                # Return empty list - no fallback
                return []

    @deal.pre(lambda self, catalog, limit: catalog and len(catalog.strip()) > 0, message="Catalog must be non-empty")  # type: ignore[misc,arg-type]
    @deal.pre(lambda self, catalog, limit: limit > 0, message="Limit must be positive")  # type: ignore[misc,arg-type]
    @deal.post(lambda result: isinstance(result, list), message="Must return list of objects")
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

    @deal.pre(
        lambda self, catalog, catalog_number: catalog and len(catalog.strip()) > 0, message="Catalog must be non-empty"
    )  # type: ignore[misc,arg-type]
    @deal.pre(lambda self, catalog, catalog_number: catalog_number > 0, message="Catalog number must be positive")  # type: ignore[misc,arg-type]
    @deal.post(lambda result: isinstance(result, bool), message="Must return boolean")
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

    @deal.pre(
        lambda self, *args, **kwargs: kwargs.get("limit", 1000) > 0,
        message="Limit must be positive",
    )  # type: ignore[misc,arg-type]
    @deal.post(lambda result: isinstance(result, list), message="Must return list of objects")
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

    @deal.post(lambda result: isinstance(result, list), message="Must return list of catalog names")
    def get_all_catalogs(self) -> list[str]:
        """Get list of all catalog names."""
        with self._get_session() as session:
            catalogs = (
                session.query(CelestialObjectModel.catalog).distinct().order_by(CelestialObjectModel.catalog).all()
            )
            return [catalog[0] for catalog in catalogs]

    @deal.pre(lambda self, prefix, limit: limit > 0, message="Limit must be positive")  # type: ignore[misc,arg-type]
    @deal.post(lambda result: isinstance(result, list), message="Must return list of strings")
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
            # Fix type incompatibility: Row[tuple[str | None]], be explicit with Optional[str]
            common_name_results: Sequence[Row[tuple[str | None]]] = session.execute(common_name_query).fetchall()
            for common_name_row in common_name_results:
                # Use cast to help mypy understand the type (common_name can be None)
                val = cast(str | None, common_name_row[0])
                if val is not None:
                    names_set.add(val)
            return sorted(names_set, key=str.lower)[:limit]

    @deal.pre(lambda self, limit: limit > 0, message="Limit must be positive")  # type: ignore[misc,arg-type]
    @deal.post(lambda result: isinstance(result, list), message="Must return list of strings")
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

    @deal.post(lambda result: result is not None, message="Stats must be returned")
    @deal.post(lambda result: hasattr(result, "total_objects"), message="Stats must have total_objects")
    def get_stats(self) -> DatabaseStats:
        """Get database statistics."""
        from sqlalchemy import func, select

        with self._get_session() as session:
            # Total count
            total = session.execute(select(func.count(CelestialObjectModel.id))).scalar_one() or 0

            # By catalog
            catalog_rows = session.execute(
                select(CelestialObjectModel.catalog, func.count(CelestialObjectModel.id)).group_by(
                    CelestialObjectModel.catalog
                )
            ).all()
            by_catalog = {row[0]: row[1] for row in catalog_rows if row[0] and row[1] > 0}

            # By type
            type_rows = session.execute(
                select(CelestialObjectModel.object_type, func.count(CelestialObjectModel.id)).group_by(
                    CelestialObjectModel.object_type
                )
            ).all()
            by_type = {row[0]: row[1] for row in type_rows}

            # Magnitude range
            mag_row = session.execute(
                select(func.min(CelestialObjectModel.magnitude), func.max(CelestialObjectModel.magnitude)).where(
                    CelestialObjectModel.magnitude.isnot(None)
                )
            ).first()
            mag_range = (mag_row[0], mag_row[1]) if mag_row and mag_row[0] is not None else (None, None)

            # Dynamic objects
            dynamic = (
                session.execute(
                    select(func.count(CelestialObjectModel.id)).where(CelestialObjectModel.is_dynamic.is_(True))
                ).scalar_one()
                or 0
            )

            # Version and last updated from metadata table
            version_model = session.get(MetadataModel, "version")
            version = version_model.value if version_model else "unknown"

            updated_model = session.get(MetadataModel, "last_updated")
            last_updated = (
                datetime.fromisoformat(updated_model.value) if updated_model and updated_model.value else None
            )

            return DatabaseStats(
                total_objects=total,
                objects_by_catalog=by_catalog,
                objects_by_type=by_type,
                magnitude_range=mag_range,
                dynamic_objects=dynamic,
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
            constellation=model.constellation,
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

    @deal.post(lambda result: result is None, message="Commit must complete")
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


@deal.post(lambda result: result is not None, message="Database instance must be returned")
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


@deal.post(lambda result: result is not None, message="Database must be initialized")
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


@deal.post(
    lambda result: isinstance(result, tuple) and len(result) == 2,
    message="Must return tuple of (pages_freed, pages_used)",
)
@deal.post(lambda result: result[0] >= 0 and result[1] >= 0, message="Page counts must be non-negative")
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


@deal.post(lambda result: result.exists(), message="Backup file must be created")
@deal.raises(FileNotFoundError, OSError)
def backup_database(
    db: CatalogDatabase | None = None,
    backup_dir: Path | None = None,
    keep_backups: int = 5,
) -> Path:
    """
    Create a timestamped backup of the database.

    Args:
        db: Database instance (default: uses get_database())
        backup_dir: Directory to store backups (default: ~/.nexstar/backups)
        keep_backups: Number of backups to keep (default: 5)

    Returns:
        Path to the created backup file

    Raises:
        FileNotFoundError: If database doesn't exist
        OSError: If backup directory can't be created
    """
    if db is None:
        db = get_database()

    if not db.db_path.exists():
        raise FileNotFoundError(f"Database not found: {db.db_path}")

    # Determine backup directory
    backup_dir = Path.home() / ".nexstar" / "backups" if backup_dir is None else Path(backup_dir)

    # Create backup directory if it doesn't exist
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Create timestamped backup filename
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"catalogs.db.{timestamp}.backup"

    # Copy database file
    shutil.copy2(db.db_path, backup_path)

    logger.info(f"Backup created: {backup_path} ({backup_path.stat().st_size / (1024 * 1024):.2f} MB)")

    # Clean up old backups (keep only the most recent N)
    backups = sorted(backup_dir.glob("catalogs.db.*.backup"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old_backup in backups[keep_backups:]:
        old_backup.unlink()
        logger.info(f"Removed old backup: {old_backup.name}")

    return backup_path


@deal.pre(lambda backup_path, db: backup_path.exists(), message="Backup file must exist")  # type: ignore[misc,arg-type]
@deal.raises(FileNotFoundError)
def restore_database(backup_path: Path, db: CatalogDatabase | None = None) -> None:
    """
    Restore database from a backup file.

    Args:
        backup_path: Path to backup file
        db: Database instance (default: uses get_database())

    Raises:
        FileNotFoundError: If backup file doesn't exist
    """
    if db is None:
        db = get_database()

    backup_path = Path(backup_path)
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_path}")

    # Close any existing connections
    db._engine.dispose()

    # Copy backup to database location
    shutil.copy2(backup_path, db.db_path)

    logger.info(f"Database restored from: {backup_path}")


@deal.pre(
    lambda backup_dir, sources, mag_limit, skip_backup, dry_run: mag_limit > 0,
    message="Magnitude limit must be positive",
)  # type: ignore[misc,arg-type]
@deal.post(lambda result: result is not None, message="Rebuild must return statistics")
@deal.post(lambda result: "duration_seconds" in result, message="Result must include duration")
@deal.raises(RuntimeError)
def rebuild_database(
    backup_dir: Path | None = None,
    sources: list[str] | None = None,
    mag_limit: float = 15.0,
    skip_backup: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Rebuild database from scratch.

    Steps:
    1. Backup existing database (if exists and not skipped)
    2. Drop existing database
    3. Run Alembic migrations to create fresh schema
    4. Import all data sources
    5. Initialize static data

    Args:
        backup_dir: Directory to store backups (default: ~/.nexstar/backups)
        sources: List of sources to import (default: all available)
        mag_limit: Maximum magnitude to import (default: 15.0)
        skip_backup: Skip backup step (not recommended)
        dry_run: Show what would be done without actually doing it

    Returns:
        Dictionary with rebuild statistics:
        - backup_path: Path to backup (if created)
        - imported_counts: Dict mapping source to (imported, skipped) counts
        - static_data: Dict with static data counts
        - duration_seconds: Time taken for rebuild
        - database_size_mb: Final database size

    Raises:
        RuntimeError: If rebuild fails (backup will be restored if available)
    """
    start_time = time.time()
    db = get_database()
    backup_path: Path | None = None

    try:
        # Step 1: Backup existing database
        if not dry_run and not skip_backup and db.db_path.exists():
            backup_path = backup_database(db, backup_dir)
            logger.info(f"Backup created: {backup_path}")

        if dry_run:
            logger.info("[DRY RUN] Would backup database if it exists")
            return {
                "backup_path": None,
                "imported_counts": {},
                "static_data": {},
                "duration_seconds": 0,
                "database_size_mb": 0,
            }

        # Step 2: Drop existing database
        if db.db_path.exists():
            # Close all connections
            db._engine.dispose()
            # Remove database file
            db.db_path.unlink()
            logger.info("Database dropped")

        # Step 3: Run Alembic migrations to create fresh schema
        from alembic.config import Config

        from alembic import command  # type: ignore[attr-defined]

        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        logger.info("Schema created via Alembic migrations")

        # Get fresh database instance after rebuild
        db = get_database()

        # Ensure FTS table exists (migrations should create it, but ensure it's there)
        db.ensure_fts_table()

        # Step 4: Populate star name mappings BEFORE importing catalogs that need them
        # This ensures Yale BSC import can look up common names
        logger.info("Populating star name mappings...")
        from .models import get_db_session
        from .star_name_mappings import populate_star_name_mappings_database

        with get_db_session() as session:
            # Force refresh to ensure we have the latest mappings
            populate_star_name_mappings_database(session, force_refresh=True)
            from sqlalchemy import func, select

            from .models import StarNameMappingModel

            star_mapping_count = session.scalar(select(func.count(StarNameMappingModel.hr_number))) or 0
            logger.info(f"Added {star_mapping_count} star name mappings")
            if star_mapping_count == 0:
                logger.error("WARNING: No star name mappings were added! Yale BSC imports will not have common names.")

        # Step 5: Import data sources
        # Import here to avoid circular dependency
        from celestron_nexstar.cli.data_import import DATA_SOURCES, import_data_source

        if sources is None:
            sources = list(DATA_SOURCES.keys())

        imported_counts: dict[str, tuple[int, int]] = {}
        objects_before_import = 0

        for source_id in sources:
            if source_id not in DATA_SOURCES:
                logger.warning(f"Unknown source: {source_id}, skipping")
                continue

            logger.info(f"Importing {source_id}...")
            # Get count before import
            try:
                db_stats_before = db.get_stats()
                objects_before_import = db_stats_before.total_objects
            except Exception as e:
                logger.warning(f"Failed to get stats before import: {e}")
                objects_before_import = 0

            # Import the source
            try:
                logger.info(f"Calling import_data_source for {source_id}...")
                # import_data_source prints to console, so output should be visible
                success = import_data_source(source_id, mag_limit)
                logger.info(f"import_data_source returned: {success}")
                if success:
                    # Get count after import
                    try:
                        db_stats_after = db.get_stats()
                        imported = db_stats_after.total_objects - objects_before_import
                        imported_counts[source_id] = (imported, 0)  # Skipped count not easily available
                        objects_before_import = db_stats_after.total_objects
                        logger.info(f"Successfully imported {source_id}: {imported} objects")
                        if imported == 0:
                            logger.warning(f"Import reported success but no objects were added for {source_id}")
                    except Exception as e:
                        logger.warning(f"Failed to get stats after import: {e}")
                        imported_counts[source_id] = (0, 0)
                else:
                    imported_counts[source_id] = (0, 0)
                    logger.warning(f"import_data_source returned False for {source_id}")
            except Exception as e:
                logger.error(f"Exception importing {source_id}: {e}", exc_info=True)
                imported_counts[source_id] = (0, 0)
                # Continue with other sources even if one fails
                # Re-raise if it's a critical error
                if "database" in str(e).lower() or "schema" in str(e).lower():
                    raise

        # Repopulate FTS table after all imports to ensure all objects are searchable
        logger.info("Repopulating FTS search index...")
        try:
            db.repopulate_fts_table()
        except Exception as e:
            logger.warning(f"Failed to repopulate FTS table: {e}")
            # Continue - search will fall back to direct queries

        # Step 6: Initialize other static data
        from .constellations import populate_constellation_database
        from .meteor_showers import populate_meteor_shower_database
        from .space_events import populate_space_events_database
        from .vacation_planning import populate_dark_sky_sites_database

        logger.info("Initializing static reference data...")
        static_data: dict[str, int] = {}

        with get_db_session() as session:
            # Populate meteor showers
            logger.info("Populating meteor showers...")
            populate_meteor_shower_database(session)
            from sqlalchemy import func, select

            from .models import (
                AsterismModel,
                ConstellationModel,
                DarkSkySiteModel,
                MeteorShowerModel,
                SpaceEventModel,
            )

            meteor_count = session.scalar(select(func.count(MeteorShowerModel.id))) or 0
            static_data["meteor_showers"] = meteor_count
            logger.info(f"Added {meteor_count} meteor showers")

            # Populate constellations
            logger.info("Populating constellations and asterisms...")
            populate_constellation_database(session)
            constellation_count = session.scalar(select(func.count(ConstellationModel.id))) or 0
            asterism_count = session.scalar(select(func.count(AsterismModel.id))) or 0
            static_data["constellations"] = constellation_count
            static_data["asterisms"] = asterism_count
            logger.info(f"Added {constellation_count} constellations and {asterism_count} asterisms")

            # Populate dark sky sites
            logger.info("Populating dark sky sites...")
            populate_dark_sky_sites_database(session)
            dark_sky_count = session.scalar(select(func.count(DarkSkySiteModel.id))) or 0
            static_data["dark_sky_sites"] = dark_sky_count
            logger.info(f"Added {dark_sky_count} dark sky sites")

            # Populate space events
            logger.info("Populating space events...")
            populate_space_events_database(session)
            space_events_count = session.scalar(select(func.count(SpaceEventModel.id))) or 0
            static_data["space_events"] = space_events_count
            logger.info(f"Added {space_events_count} space events")

        # Step 6: Download and process World Atlas light pollution data
        logger.info("Downloading and processing World Atlas light pollution data...")
        try:
            import asyncio

            from .light_pollution_db import download_world_atlas_data

            # Download all regions (no state filter = all data)
            # Use a coarser grid resolution (0.2°) for faster processing during setup
            # Users can re-download with finer resolution later if needed
            logger.info("Downloading World Atlas PNG files (this may take a while)...")
            light_pollution_results = asyncio.run(
                download_world_atlas_data(
                    regions=None,  # All regions
                    grid_resolution=0.2,  # 0.2° ≈ 22km resolution for faster initial setup
                    force=False,  # Use cached files if available
                    state_filter=None,  # No filter - process all data
                )
            )

            total_grid_points = sum(light_pollution_results.values())
            logger.info(
                f"Processed {total_grid_points:,} light pollution grid points from {len(light_pollution_results)} regions"
            )
            static_data["light_pollution_grid_points"] = total_grid_points

            # Log per-region counts
            for region, count in light_pollution_results.items():
                logger.info(f"  {region}: {count:,} points")
        except Exception as e:
            logger.warning(f"Failed to download light pollution data: {e}")
            logger.warning(
                "Light pollution data can be downloaded later with: nexstar vacation download-light-pollution"
            )
            static_data["light_pollution_grid_points"] = 0

        # Step 7: Pre-fetch 3 days of weather forecast data (if location is configured)
        logger.info("Pre-fetching 3-day weather forecast data...")
        try:
            import asyncio

            from .observer import ObserverLocation, geocode_location, get_observer_location, set_observer_location
            from .weather import fetch_hourly_weather_forecast

            location: ObserverLocation | None = get_observer_location()

            # If no location is set, prompt user to set one
            if not location:
                logger.info("No observer location configured")
                # Try to get location interactively (only if running from CLI)
                # Check if we're in an interactive environment
                try:
                    import sys

                    if sys.stdin.isatty():
                        # We're in an interactive terminal, prompt for location
                        from rich.console import Console
                        from rich.prompt import Prompt

                        console = Console()
                        console.print("\n[cyan]Observer Location Required[/cyan]")
                        console.print(
                            "[dim]Your location is needed for weather forecasts and accurate calculations.[/dim]\n"
                        )

                        location_query = Prompt.ask("Enter your location", default="", console=console)

                        if location_query:
                            try:
                                console.print(f"[dim]Geocoding: {location_query}...[/dim]")
                                location = asyncio.run(geocode_location(location_query))
                                set_observer_location(location, save=True)
                                console.print(f"[green]✓[/green] Location set to: {location.name}")
                                console.print(
                                    f"[dim]  Coordinates: {location.latitude:.4f}°, {location.longitude:.4f}°[/dim]\n"
                                )
                            except ValueError as e:
                                logger.warning(f"Failed to geocode location '{location_query}': {e}")
                                logger.warning(
                                    "Skipping weather forecast pre-fetch. Set location later with: nexstar location set-observer <location>"
                                )
                                location = None
                        else:
                            logger.info("Location input skipped - weather forecast will be fetched on-demand")
                            location = None
                    else:
                        # Non-interactive environment, skip
                        logger.info("Non-interactive environment - skipping location prompt")
                        logger.info("Set your location with: nexstar location set-observer <location>")
                        location = None
                except Exception as e:
                    logger.debug(f"Could not prompt for location interactively: {e}")
                    logger.info("Set your location with: nexstar location set-observer <location>")
                    location = None

            if location:
                logger.info(
                    f"Fetching weather forecast for {location.name} ({location.latitude:.2f}°, {location.longitude:.2f}°)"
                )
                # Fetch 3 days = 72 hours of weather forecast
                weather_forecasts = fetch_hourly_weather_forecast(location, hours=72)
                if weather_forecasts:
                    logger.info(f"Pre-fetched {len(weather_forecasts)} hours of weather forecast data")
                    static_data["weather_forecast_hours"] = len(weather_forecasts)
                else:
                    logger.warning("No weather forecast data was fetched")
                    static_data["weather_forecast_hours"] = 0
            else:
                static_data["weather_forecast_hours"] = 0
        except Exception as e:
            logger.warning(f"Failed to pre-fetch weather forecast data: {e}")
            logger.warning("Weather forecasts will be fetched on-demand when needed")
            static_data["weather_forecast_hours"] = 0

        duration_seconds = time.time() - start_time
        database_size_mb = db.db_path.stat().st_size / (1024 * 1024) if db.db_path.exists() else 0

        logger.info(f"Database rebuild complete in {duration_seconds:.1f} seconds")
        logger.info(f"Final database size: {database_size_mb:.2f} MB")

        return {
            "backup_path": backup_path,
            "imported_counts": imported_counts,
            "static_data": static_data,
            "duration_seconds": duration_seconds,
            "database_size_mb": database_size_mb,
        }

    except Exception as e:
        # Restore backup if available
        if backup_path and backup_path.exists():
            logger.error(f"Rebuild failed: {e}. Restoring backup...")
            try:
                restore_database(backup_path, db)
                logger.info("Backup restored successfully")
            except Exception as restore_error:
                logger.error(f"Failed to restore backup: {restore_error}")
        raise RuntimeError(f"Database rebuild failed: {e}") from e


@deal.post(lambda result: isinstance(result, dict), message="Must return dictionary")
def get_ephemeris_files() -> dict[str, dict[str, Any]]:
    """
    Get all ephemeris files from the database.

    Returns:
        Dictionary mapping file_key to EphemerisFileInfo-like dict
    """
    db = get_database()
    with db._get_session() as session:
        files = session.query(EphemerisFileModel).all()
        result: dict[str, dict[str, Any]] = {}
        for file_model in files:
            result[file_model.file_key] = {
                "filename": file_model.filename,
                "display_name": file_model.display_name,
                "description": file_model.description,
                "coverage_start": file_model.coverage_start,
                "coverage_end": file_model.coverage_end,
                "size_mb": file_model.size_mb,
                "contents": tuple(file_model.contents.split(", ") if file_model.contents else ()),
                "use_case": file_model.use_case,
                "url": file_model.url,
            }
        return result


@deal.post(lambda result: isinstance(result, list), message="Must return list")
# Note: Postconditions on async functions check the coroutine, not the awaited result
async def list_ephemeris_files_from_naif() -> list[dict[str, Any]]:
    """
    Fetch ephemeris file information from NAIF and return as list (without syncing).

    Returns:
        List of dictionaries with ephemeris file information
    """
    from .ephemeris_manager import (
        NAIF_PLANETS_SUMMARY,
        NAIF_SATELLITES_SUMMARY,
        _fetch_summaries,
        _generate_file_info,
        _parse_summaries,
    )

    try:
        # Fetch and parse summaries
        logger.info("Fetching ephemeris file summaries from NAIF...")
        planets_content = await _fetch_summaries(NAIF_PLANETS_SUMMARY)
        satellites_content = await _fetch_summaries(NAIF_SATELLITES_SUMMARY)

        planets_summaries = _parse_summaries(planets_content, "planets")
        satellites_summaries = _parse_summaries(satellites_content, "satellites")
        all_summaries = planets_summaries + satellites_summaries

        # Convert to dict format for display
        files_list: list[dict[str, Any]] = []
        for summary in all_summaries:
            file_info = _generate_file_info(summary)
            file_key = summary.filename.replace(".bsp", "")

            files_list.append(
                {
                    "file_key": file_key,
                    "filename": file_info.filename,
                    "display_name": file_info.display_name,
                    "description": file_info.description,
                    "coverage_start": file_info.coverage_start,
                    "coverage_end": file_info.coverage_end,
                    "size_mb": file_info.size_mb,
                    "file_type": summary.file_type,
                    "url": file_info.url,
                    "contents": ", ".join(file_info.contents),
                    "use_case": file_info.use_case,
                }
            )

        return files_list

    except Exception as e:
        logger.error(f"Failed to fetch ephemeris files from NAIF: {e}")
        raise


# Note: Postconditions on async functions check the coroutine, not the awaited result
# Cannot use @deal.post here - deal checks coroutine object, not awaited result
@deal.pre(lambda force: isinstance(force, bool), message="Force must be boolean")  # type: ignore[misc,arg-type]
async def sync_ephemeris_files_from_naif(force: bool = False) -> int:
    """
    Fetch ephemeris file information from NAIF and sync to database.

    Args:
        force: If True, update even if recently synced

    Returns:
        Number of files synced
    """
    from .ephemeris_manager import (
        NAIF_PLANETS_SUMMARY,
        NAIF_SATELLITES_SUMMARY,
        _fetch_summaries,
        _generate_file_info,
        _parse_summaries,
    )

    db = get_database()

    # Check if we need to sync (check last sync time in metadata)
    if not force:
        with db._get_session() as session:
            last_sync = session.query(MetadataModel).filter(MetadataModel.key == "ephemeris_files_last_sync").first()
            if last_sync:
                last_sync_time = datetime.fromisoformat(last_sync.value)
                hours_since_sync = (datetime.now() - last_sync_time).total_seconds() / 3600
                if hours_since_sync < 24:  # Sync once per day max
                    logger.info("Ephemeris files recently synced, skipping")
                    return 0

    try:
        # Fetch and parse summaries
        logger.info("Fetching ephemeris file summaries from NAIF...")
        planets_content = await _fetch_summaries(NAIF_PLANETS_SUMMARY)
        satellites_content = await _fetch_summaries(NAIF_SATELLITES_SUMMARY)

        planets_summaries = _parse_summaries(planets_content, "planets")
        satellites_summaries = _parse_summaries(satellites_content, "satellites")
        all_summaries = planets_summaries + satellites_summaries

        # Convert to EphemerisFileInfo and then to database models
        files_to_sync: list[EphemerisFileModel] = []
        for summary in all_summaries:
            file_info = _generate_file_info(summary)
            file_key = summary.filename.replace(".bsp", "")

            files_to_sync.append(
                EphemerisFileModel(
                    file_key=file_key,
                    filename=file_info.filename,
                    display_name=file_info.display_name,
                    description=file_info.description,
                    coverage_start=file_info.coverage_start,
                    coverage_end=file_info.coverage_end,
                    size_mb=file_info.size_mb,
                    file_type=summary.file_type,
                    url=file_info.url,
                    contents=", ".join(file_info.contents),
                    use_case=file_info.use_case,
                )
            )

        # Upsert to database
        with db._get_session() as session:
            synced_count = 0
            for file_model in files_to_sync:
                # Check if exists
                existing = (
                    session.query(EphemerisFileModel).filter(EphemerisFileModel.file_key == file_model.file_key).first()
                )
                if existing:
                    # Update existing
                    for key, value in file_model.__dict__.items():
                        if key != "_sa_instance_state" and key != "file_key":
                            setattr(existing, key, value)
                    existing.updated_at = datetime.now(UTC)
                else:
                    # Insert new
                    session.add(file_model)
                synced_count += 1

            # Update sync timestamp
            sync_metadata = (
                session.query(MetadataModel).filter(MetadataModel.key == "ephemeris_files_last_sync").first()
            )
            if sync_metadata:
                sync_metadata.value = datetime.now(UTC).isoformat()
                sync_metadata.updated_at = datetime.now(UTC)
            else:
                session.add(
                    MetadataModel(
                        key="ephemeris_files_last_sync",
                        value=datetime.now(UTC).isoformat(),
                    )
                )

            session.commit()
            logger.info(f"Synced {synced_count} ephemeris files to database")
            return synced_count

    except Exception as e:
        logger.error(f"Failed to sync ephemeris files from NAIF: {e}")
        raise

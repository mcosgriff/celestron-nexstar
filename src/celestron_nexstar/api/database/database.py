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
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, TypeVar, cast

import deal
from rich.console import Console
from sqlalchemy import text
from sqlalchemy.engine import Row
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from celestron_nexstar.api.catalogs.catalogs import CelestialObject
from celestron_nexstar.api.core.enums import CelestialObjectType
from celestron_nexstar.api.core.exceptions import (
    DatabaseBackupError,
    DatabaseNotFoundError,
    DatabaseRebuildError,
    DatabaseRestoreError,
)
from celestron_nexstar.api.database.models import (
    CelestialObjectModel,
    CelestialObjectModelProtocol,
    ClusterModel,
    DoubleStarModel,
    EphemerisFileModel,
    GalaxyModel,
    MetadataModel,
    MoonModel,
    NebulaModel,
    PlanetModel,
    StarModel,
)
from celestron_nexstar.api.ephemeris.ephemeris import get_planetary_position, is_dynamic_object


# Type variable for model classes that have CelestialObjectMixin
_ModelType = TypeVar("_ModelType", bound=CelestialObjectModelProtocol)

console = Console()


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

    # Mapping from object_type to model class
    # Cast to Protocol type so mypy understands the attributes
    # These models all inherit from CelestialObjectMixin which matches the Protocol
    _TYPE_TO_MODEL: ClassVar[dict[CelestialObjectType, type[CelestialObjectModelProtocol]]] = {
        CelestialObjectType.STAR: cast(type[CelestialObjectModelProtocol], StarModel),
        CelestialObjectType.DOUBLE_STAR: cast(type[CelestialObjectModelProtocol], DoubleStarModel),
        CelestialObjectType.GALAXY: cast(type[CelestialObjectModelProtocol], GalaxyModel),
        CelestialObjectType.NEBULA: cast(type[CelestialObjectModelProtocol], NebulaModel),
        CelestialObjectType.CLUSTER: cast(type[CelestialObjectModelProtocol], ClusterModel),
        CelestialObjectType.PLANET: cast(type[CelestialObjectModelProtocol], PlanetModel),
        CelestialObjectType.MOON: cast(type[CelestialObjectModelProtocol], MoonModel),
    }

    @classmethod
    def _get_model_class(cls, object_type: CelestialObjectType | str) -> type[CelestialObjectModelProtocol]:
        """Get the model class for a given object type."""
        if isinstance(object_type, str):
            object_type = CelestialObjectType(object_type)
        # Don't fallback to CelestialObjectModel - the objects table no longer exists
        # Raise an error if object type is not found
        if object_type not in cls._TYPE_TO_MODEL:
            raise ValueError(f"Unknown object type: {object_type}. Supported types: {list(cls._TYPE_TO_MODEL.keys())}")
        return cls._TYPE_TO_MODEL[object_type]

    @classmethod
    def _get_table_name(cls, object_type: CelestialObjectType | str) -> str:
        """Get the table name for a given object type."""
        if isinstance(object_type, str):
            object_type = CelestialObjectType(object_type)
        model_class = cls._get_model_class(object_type)
        return str(model_class.__tablename__)

    def __init__(self, db_path: Path | str | None = None, use_memory: bool = False):
        """
        Initialize database connection.

        Args:
            db_path: Path to database file (default: ~/.config/celestron-nexstar/catalogs.db)
            use_memory: If True, load database into memory for faster queries (requires existing database)
        """
        if db_path is None:
            db_path = self._get_default_db_path()

        self.db_path = Path(db_path)
        self.use_memory = use_memory
        self._source_db_path = self.db_path if use_memory else None

        # Use aiosqlite for async SQLite support
        # SQLite URL format for async: sqlite+aiosqlite:///
        # For in-memory databases, use :memory: (see https://sqlite.org/inmemorydb.html)
        if use_memory:
            # Use shared cache for in-memory database so multiple connections can access it
            # See: https://sqlite.org/inmemorydb.html#sharedmemdb
            db_url = "sqlite+aiosqlite:///file:memdb1?mode=memory&cache=shared"
        else:
            db_url = f"sqlite+aiosqlite:///{self.db_path}"

        # Optimize connection pooling for SQLite:
        # - pool_size: SQLite doesn't use traditional pooling, but this sets max connections
        # - max_overflow: Additional connections beyond pool_size
        # - pool_pre_ping: Verify connections before using (prevents stale connections)
        # - pool_recycle: Recycle connections after this many seconds (not critical for SQLite)
        self._engine = create_async_engine(
            db_url,
            echo=False,  # Set to True for SQL debugging
            future=True,
            pool_size=10,  # Maximum number of connections to maintain
            max_overflow=5,  # Additional connections beyond pool_size
            pool_pre_ping=True,  # Verify connections before using (prevents stale connections)
            pool_recycle=3600,  # Recycle connections after 1 hour (not critical for SQLite)
        )
        self._AsyncSession = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._configure_optimizations()

        # If using memory mode, copy the existing database into memory
        if use_memory and self._source_db_path and self._source_db_path.exists():
            # This will be called asynchronously when needed
            self._memory_loaded = False
            self._memory_dirty = False  # Track if in-memory DB has been modified
        else:
            self._memory_loaded = True  # Not using memory or no source DB
            self._memory_dirty = False

    def _get_default_db_path(self) -> Path:
        """Get path to database file in user config directory."""
        # Store database in user's config directory (~/.config/celestron-nexstar/)
        config_dir = Path.home() / ".config" / "celestron-nexstar"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "catalogs.db"

    def _configure_optimizations(self) -> None:
        """Configure SQLite optimizations via engine events."""
        from sqlalchemy import event

        @event.listens_for(self._engine.sync_engine, "connect")
        def set_sqlite_pragmas(dbapi_conn: Any, connection_record: Any) -> None:
            """Set SQLite pragmas for performance."""
            cursor = dbapi_conn.cursor()

            cursor.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging
            cursor.execute("PRAGMA synchronous=NORMAL")  # Faster writes
            cursor.execute("PRAGMA cache_size=-64000")  # 64MB cache
            cursor.execute("PRAGMA temp_store=MEMORY")  # Temp tables in RAM
            cursor.close()

        # Hook into commit events to track writes when using in-memory mode
        # Note: This tracks commits on the sync engine (used by async engine under the hood)
        if self.use_memory:

            @event.listens_for(self._engine.sync_engine, "commit")
            def mark_dirty(conn: Any) -> None:
                """Mark in-memory database as dirty when commits occur."""
                self._memory_dirty = True

    async def _load_database_into_memory(self) -> None:
        """
        Load the source database into the in-memory database.

        Uses SQLite's backup API for efficient copying.
        See: https://sqlite.org/inmemorydb.html
        """
        if not self.use_memory or self._memory_loaded:
            return

        if not self._source_db_path or not self._source_db_path.exists():
            logger.warning(f"Source database not found: {self._source_db_path}, using empty in-memory database")
            self._memory_loaded = True
            return

        try:
            import aiosqlite

            # Connect to source database (file-based)
            async with (
                aiosqlite.connect(str(self._source_db_path)) as source_conn,
                # Connect to destination database (in-memory with shared cache)
                # Use the same shared memory name that SQLAlchemy uses
                aiosqlite.connect("file:memdb1?mode=memory&cache=shared") as dest_conn,
            ):
                # Use SQLite backup API to copy database
                # This is much faster than copying row by row
                await source_conn.backup(dest_conn)
                await dest_conn.commit()

            logger.info(f"Loaded database into memory from {self._source_db_path}")
            self._memory_loaded = True
            self._memory_dirty = False
        except Exception as e:
            logger.error(f"Failed to load database into memory: {e}", exc_info=True)
            # Fall back to file-based database
            self.use_memory = False
            self._memory_loaded = True

    async def _sync_memory_to_file(self) -> None:
        """
        Sync the in-memory database back to the file database.

        Uses SQLite's backup API in reverse to copy from memory to file.
        This should be called after write operations when using in-memory mode.
        See: https://sqlite.org/inmemorydb.html
        """
        if not self.use_memory or not self._memory_dirty or not self._source_db_path:
            return

        if not self._memory_loaded:
            # Database not loaded into memory yet, nothing to sync
            return

        try:
            import aiosqlite

            # Connect to source database (in-memory)
            async with (
                aiosqlite.connect("file:memdb1?mode=memory&cache=shared") as source_conn,
                # Connect to destination database (file-based)
                aiosqlite.connect(str(self._source_db_path)) as dest_conn,
            ):
                # Use SQLite backup API to copy from memory to file
                # This efficiently copies the entire database
                await source_conn.backup(dest_conn)
                await dest_conn.commit()

            logger.debug(f"Synced in-memory database to file: {self._source_db_path}")
            self._memory_dirty = False
        except Exception as e:
            logger.error(f"Failed to sync in-memory database to file: {e}", exc_info=True)

    async def sync_to_file(self) -> None:
        """
        Manually trigger a sync from in-memory database to file.

        This is useful if you want to ensure data is persisted immediately.
        """
        await self._sync_memory_to_file()

    async def _get_session(self) -> AsyncSession:
        """Get a new async database session."""
        # Ensure database is loaded into memory if using memory mode
        if self.use_memory and not self._memory_loaded:
            await self._load_database_into_memory()
        return self._AsyncSession()

    @contextmanager
    def _get_session_sync(self) -> Iterator[Session]:
        """
        Get a synchronous session (for backwards compatibility during migration).

        Note: This creates a sync engine temporarily. Use _get_session() for new code.

        Returns a context manager that yields a Session.
        """
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        # For sync engine, handle in-memory databases
        db_url = "sqlite:///file:memdb1?mode=memory&cache=shared" if self.use_memory else f"sqlite:///{self.db_path}"

        sync_engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False},
            echo=False,
        )
        session_factory = sessionmaker(bind=sync_engine, expire_on_commit=False)

        session = session_factory()
        try:
            yield session
            session.commit()
        except (SQLAlchemyError, RuntimeError, AttributeError, ValueError, TypeError):
            # SQLAlchemyError: database errors
            # RuntimeError: session errors
            # AttributeError: missing session attributes
            # ValueError: invalid data
            # TypeError: wrong argument types
            session.rollback()
            raise
        finally:
            session.close()

    @deal.post(lambda result: result is None, message="Close must complete")
    async def close(self) -> None:
        """Close database connection."""
        # If using in-memory mode and database has been modified, sync back to file
        if self.use_memory and self._memory_dirty:
            await self._sync_memory_to_file()
        await self._engine.dispose()

    def __enter__(self) -> CatalogDatabase:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: type, exc_val: Exception, exc_tb: Any) -> None:
        """Context manager exit."""
        # Note: close() is async, but __exit__ is sync
        # This is a limitation - proper cleanup would require async context manager
        # For now, we'll just log a warning if called
        import warnings

        warnings.warn(
            "CatalogDatabase.close() is async but called from sync context manager", RuntimeWarning, stacklevel=2
        )

    @deal.post(lambda result: result is None, message="Schema initialization must complete")
    async def init_schema(self) -> None:
        """
        Initialize database schema.

        Note: This method is kept for backwards compatibility.
        For new databases, use Alembic migrations instead.
        """
        from celestron_nexstar.api.database.models import Base

        # Create all tables (async)
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Create FTS5 table and triggers (not handled by SQLAlchemy)
        async with self._AsyncSession() as session:
            # Create FTS5 virtual table
            await session.execute(
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
            await session.execute(
                text("""
                CREATE TRIGGER IF NOT EXISTS objects_ai AFTER INSERT ON objects BEGIN
                    INSERT INTO objects_fts(rowid, name, common_name, description)
                    VALUES (new.id, new.name, new.common_name, new.description);
                END
            """)
            )

            await session.execute(
                text("""
                CREATE TRIGGER IF NOT EXISTS objects_ad AFTER DELETE ON objects BEGIN
                    DELETE FROM objects_fts WHERE rowid = old.id;
                END
            """)
            )

            await session.execute(
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

            await session.commit()

        logger.info("Database schema initialized")

    @deal.post(lambda result: result is None, message="FTS table ensure must complete")
    async def ensure_fts_table(self) -> None:
        """
        Ensure the FTS5 table exists. Creates it if missing.

        This is useful when the database was created without migrations
        or if the FTS table was accidentally dropped.
        """
        async with self._AsyncSession() as session:
            # Check if FTS table exists
            result = await session.execute(
                text("""
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name='objects_fts'
                """)
            )
            row = result.fetchone()

            if row is None:
                logger.info("Creating missing objects_fts table")
                # Create FTS5 virtual table
                await session.execute(
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
                await session.execute(
                    text("""
                    CREATE TRIGGER IF NOT EXISTS objects_ai AFTER INSERT ON objects BEGIN
                        INSERT INTO objects_fts(rowid, name, common_name, description)
                        VALUES (new.id, new.name, new.common_name, new.description);
                    END
                """)
                )

                await session.execute(
                    text("""
                    CREATE TRIGGER IF NOT EXISTS objects_ad AFTER DELETE ON objects BEGIN
                        DELETE FROM objects_fts WHERE rowid = old.id;
                    END
                """)
                )

                await session.execute(
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
                await session.execute(
                    text("""
                    INSERT INTO objects_fts(rowid, name, common_name, description)
                    SELECT id, name, common_name, description FROM objects
                """)
                )

                await session.commit()
                logger.info("FTS table created and populated")

    @deal.post(lambda result: result is None, message="FTS repopulation must complete")
    async def repopulate_fts_table(self) -> None:
        """
        Repopulate the FTS table with all existing objects.

        Useful if objects were inserted before the FTS table was created,
        or if the FTS table got out of sync.

        Note: For external content tables (content=objects), we need to use
        INSERT OR REPLACE to properly sync the FTS table.
        """
        await self.ensure_fts_table()  # Make sure table exists

        async with self._AsyncSession() as session:
            # For external content FTS tables, we need to rebuild the index
            # Delete all existing FTS data first
            try:
                await session.execute(text("DELETE FROM objects_fts"))
                await session.commit()
            except (SQLAlchemyError, RuntimeError, AttributeError) as e:
                # SQLAlchemyError: table doesn't exist or database errors
                # RuntimeError: async/await errors
                # AttributeError: missing session attributes
                # Table might be empty or not exist - ignore
                logger.debug(f"Could not delete from objects_fts (table may not exist): {e}")
                pass

            # Repopulate from objects table
            # For external content tables, use INSERT OR REPLACE
            await session.execute(
                text("""
                    INSERT OR REPLACE INTO objects_fts(rowid, name, common_name, description)
                    SELECT id, name, common_name, description FROM objects
                    WHERE name IS NOT NULL
                """)
            )
            await session.commit()

            # Verify the repopulation
            # FTS5 table requires raw SQL (virtual table)
            fts_result = await session.execute(text("SELECT COUNT(*) FROM objects_fts"))
            fts_count = fts_result.scalar() or 0
            # Use SQLAlchemy for objects count
            from sqlalchemy import func, select

            objects_result = await session.scalar(
                select(func.count(CelestialObjectModel.id)).where(CelestialObjectModel.name.isnot(None))
            )
            objects_count = objects_result or 0

            logger.info(f"FTS table repopulated: {fts_count} entries (expected {objects_count})")

            if fts_count != objects_count:
                logger.warning(f"FTS table count mismatch: {fts_count} vs {objects_count} objects")

    @deal.pre(
        lambda self, name, *args, **kwargs: name and len(name.strip()) > 0,
        message="Name must be non-empty",
    )  # type: ignore[misc,arg-type]
    @deal.pre(
        lambda self, name, catalog, *args, **kwargs: catalog and len(catalog.strip()) > 0,
        message="Catalog must be non-empty",
    )  # type: ignore[misc,arg-type]
    @deal.pre(
        lambda self, name, catalog, ra_hours, *args, **kwargs: 0 <= ra_hours < 24,
        message="RA must be 0-24 hours",
    )  # type: ignore[misc,arg-type]
    @deal.pre(
        lambda self, name, catalog, ra_hours, dec_degrees, *args, **kwargs: -90 <= dec_degrees <= 90,
        message="Dec must be -90 to +90 degrees",
    )  # type: ignore[misc,arg-type]
    @deal.post(lambda result: result > 0, message="Insert must return positive ID")  # type: ignore[misc,arg-type,operator]
    async def insert_object(
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
        await self.ensure_fts_table()

        # Get the correct model class for this object type
        object_type_enum = CelestialObjectType(object_type) if isinstance(object_type, str) else object_type
        model_class = self._get_model_class(object_type_enum)

        async with self._AsyncSession() as session:
            from sqlalchemy import select

            # Check if object with this name already exists
            existing = await session.scalar(select(model_class).where(model_class.name == name))
            if existing:
                # Object already exists, return its ID
                # At runtime, existing.id is an int, not Mapped[int]
                return existing.id  # type: ignore[return-value]

            # Create model instance with common fields
            model_kwargs = {
                "name": name,
                "common_name": common_name,
                "catalog": catalog,
                "catalog_number": catalog_number,
                "ra_hours": ra_hours,
                "dec_degrees": dec_degrees,
                "magnitude": magnitude,
                "size_arcmin": size_arcmin,
                "description": description,
                "constellation": constellation,
            }

            # Add dynamic fields for planets and moons
            if object_type_enum in (CelestialObjectType.PLANET, CelestialObjectType.MOON):
                model_kwargs["is_dynamic"] = is_dynamic
                model_kwargs["ephemeris_name"] = ephemeris_name
                if object_type_enum == CelestialObjectType.MOON:
                    model_kwargs["parent_planet"] = parent_planet

            model = model_class(**model_kwargs)
            session.add(model)
            await session.commit()
            await session.refresh(model)
            # At runtime, model.id is an int, not Mapped[int]
            return model.id  # type: ignore[return-value]

    async def insert_objects_batch(
        self,
        objects: list[dict[str, Any]],
    ) -> int:
        """
        Insert multiple celestial objects in a single batch operation.

        Args:
            objects: List of dictionaries with object data (same fields as insert_object)

        Returns:
            Number of objects inserted
        """
        # Ensure FTS table exists before inserting (triggers depend on it)
        await self.ensure_fts_table()

        if not objects:
            return 0

        async with self._AsyncSession() as session:
            from sqlalchemy import select

            # Pre-fetch existing names for each model type to avoid duplicates
            existing_names_by_type: dict[type, set[str]] = {}

            # Group objects by type first
            objects_by_type: dict[type, list[dict[str, Any]]] = {}
            for obj in objects:
                # Get object type and model class
                object_type = obj.get("object_type")
                if isinstance(object_type, str):
                    object_type_enum = CelestialObjectType(object_type)
                elif isinstance(object_type, CelestialObjectType):
                    object_type_enum = object_type
                else:
                    continue  # Skip invalid types

                model_class = self._get_model_class(object_type_enum)
                if model_class not in objects_by_type:
                    objects_by_type[model_class] = []
                objects_by_type[model_class].append(obj)

            # Pre-fetch existing names for each model type
            for model_class in objects_by_type:
                result = await session.execute(select(model_class.name))
                existing_names_by_type[model_class] = {row[0] for row in result.all()}

            # Group objects by type for batch insertion, skipping duplicates
            models_by_type: dict[type, list[Any]] = {}
            for model_class, obj_list in objects_by_type.items():
                existing_names = existing_names_by_type.get(model_class, set())
                for obj in obj_list:
                    obj_name = obj["name"]

                    # Skip if name already exists
                    if obj_name in existing_names:
                        continue

                    # Create model instance with common fields
                    model_kwargs = {
                        "name": obj_name,
                        "common_name": obj.get("common_name"),
                        "catalog": obj["catalog"],
                        "catalog_number": obj.get("catalog_number"),
                        "ra_hours": obj["ra_hours"],
                        "dec_degrees": obj["dec_degrees"],
                        "magnitude": obj.get("magnitude"),
                        "size_arcmin": obj.get("size_arcmin"),
                        "description": obj.get("description"),
                        "constellation": obj.get("constellation"),
                    }

                    # Get object type for dynamic fields
                    object_type = obj.get("object_type")
                    if isinstance(object_type, str):
                        object_type_enum = CelestialObjectType(object_type)
                    elif isinstance(object_type, CelestialObjectType):
                        object_type_enum = object_type
                    else:
                        continue

                    # Add dynamic fields for planets and moons
                    if object_type_enum in (CelestialObjectType.PLANET, CelestialObjectType.MOON):
                        model_kwargs["is_dynamic"] = obj.get("is_dynamic", True)  # Default to True for planets/moons
                        model_kwargs["ephemeris_name"] = obj.get("ephemeris_name")
                        if object_type_enum == CelestialObjectType.MOON:
                            model_kwargs["parent_planet"] = obj.get("parent_planet")

                    model = model_class(**model_kwargs)
                    if model_class not in models_by_type:
                        models_by_type[model_class] = []
                    models_by_type[model_class].append(model)
                    # Track this name as existing to avoid duplicates within the same batch
                    existing_names.add(obj_name)

            # Insert all models grouped by type
            total_inserted = 0
            for _model_class, models in models_by_type.items():
                if models:
                    session.add_all(models)
                    total_inserted += len(models)

            await session.commit()
            return total_inserted

    async def get_existing_objects_set(
        self,
        catalog: str | None = None,
    ) -> set[tuple[str, str | None, int | None]]:
        """
        Get a set of existing objects for deduplication.

        Returns a set of tuples: (name, common_name, catalog_number)
        This allows fast O(1) lookup for duplicates.

        Args:
            catalog: Optional catalog name to filter by

        Returns:
            Set of tuples (name, common_name, catalog_number)
        """
        async with self._AsyncSession() as session:
            from sqlalchemy import select

            existing_set: set[tuple[str, str | None, int | None]] = set()
            # Query all type-specific tables
            for model_class in self._TYPE_TO_MODEL.values():
                query = select(model_class.name, model_class.common_name, model_class.catalog_number)
                if catalog:
                    query = query.where(model_class.catalog == catalog)

                result = await session.execute(query)
                rows = result.all()

                # Build set of (name, common_name, catalog_number) tuples
                for name, common_name, catalog_number in rows:
                    existing_set.add((name, common_name, catalog_number))
                    # Also add common_name as a key if it exists
                    if common_name:
                        existing_set.add((common_name, common_name, catalog_number))

            return existing_set

    @deal.pre(lambda self, object_id: object_id > 0, message="Object ID must be positive")  # type: ignore[misc,arg-type]
    @deal.post(
        lambda result: result is None or isinstance(result, CelestialObject),
        message="Must return CelestialObject or None",
    )
    async def get_by_id(
        self, object_id: int, object_type: CelestialObjectType | str | None = None
    ) -> CelestialObject | None:
        """
        Get object by ID.

        Args:
            object_id: Object ID
            object_type: Optional object type to speed up lookup (searches all tables if not provided)
        """
        async with self._AsyncSession() as session:
            # If object_type is provided, query the specific table
            if object_type:
                if isinstance(object_type, str):
                    object_type = CelestialObjectType(object_type)
                model_class = self._get_model_class(object_type)
                model = await session.get(model_class, object_id)
                if model:
                    return self._model_to_object(model)
                return None

            # Otherwise, search across all tables
            for model_class in self._TYPE_TO_MODEL.values():
                model = await session.get(model_class, object_id)
                if model:
                    return self._model_to_object(model)

            # No fallback to old model - the objects table no longer exists
            return None

    @deal.pre(lambda self, name: name and len(name.strip()) > 0, message="Name must be non-empty")  # type: ignore[misc,arg-type]
    @deal.post(
        lambda result: result is None or isinstance(result, CelestialObject),
        message="Must return CelestialObject or None",
    )
    async def get_by_name(self, name: str) -> CelestialObject | None:
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

        async with self._AsyncSession() as session:
            from sqlalchemy import select

            # Search across all type-specific tables
            for model_class in self._TYPE_TO_MODEL.values():
                # Check name field first
                stmt = select(model_class).where(model_class.name.ilike(name)).limit(1)
                result = await session.execute(stmt)
                model = result.scalar_one_or_none()
                if model:
                    return self._model_to_object(model)

                # Check common_name field
                stmt = (
                    select(model_class)
                    .where(
                        model_class.common_name.isnot(None),
                        model_class.common_name.ilike(name),
                    )
                    .limit(1)
                )
                result = await session.execute(stmt)
                model = result.scalar_one_or_none()
                if model:
                    return self._model_to_object(model)

            # Check asterisms
            from celestron_nexstar.api.catalogs.catalogs import CelestialObject
            from celestron_nexstar.api.core.enums import CelestialObjectType
            from celestron_nexstar.api.database.models import AsterismModel

            asterism_stmt = select(AsterismModel).where(AsterismModel.name.ilike(name)).limit(1)
            result = await session.execute(asterism_stmt)
            asterism_model_raw = result.scalar_one_or_none()
            if asterism_model_raw:
                # Type cast: we know this is AsterismModel from the select
                asterism_model: AsterismModel = asterism_model_raw  # type: ignore[assignment]
                # Convert AsterismModel to CelestialObject
                alt_names_list = []
                if asterism_model.alt_names:
                    alt_names_list = [n.strip() for n in asterism_model.alt_names.split(",")]
                common_name = alt_names_list[0] if alt_names_list else None

                return CelestialObject(
                    name=asterism_model.name,
                    common_name=common_name,
                    ra_hours=asterism_model.ra_hours,
                    dec_degrees=asterism_model.dec_degrees,
                    magnitude=None,
                    object_type=CelestialObjectType.ASTERISM,
                    catalog="asterisms",
                    description=asterism_model.description,
                    parent_planet=None,
                    constellation=asterism_model.parent_constellation,
                )

            # Check asterism alt_names
            asterism_alt_stmt = (
                select(AsterismModel)
                .where(
                    AsterismModel.alt_names.isnot(None),
                    AsterismModel.alt_names.ilike(f"%{name}%"),
                )
                .limit(1)
            )
            result = await session.execute(asterism_alt_stmt)
            asterism_model_alt_raw = result.scalar_one_or_none()
            if asterism_model_alt_raw:
                # Type cast: we know this is AsterismModel from the select
                asterism_model_alt: AsterismModel = asterism_model_alt_raw  # type: ignore[assignment]
                alt_names_list = []
                if asterism_model_alt.alt_names:
                    alt_names_list = [n.strip() for n in asterism_model_alt.alt_names.split(",")]
                common_name = alt_names_list[0] if alt_names_list else None

                return CelestialObject(
                    name=asterism_model_alt.name,
                    common_name=common_name,
                    ra_hours=asterism_model_alt.ra_hours,
                    dec_degrees=asterism_model_alt.dec_degrees,
                    magnitude=None,
                    object_type=CelestialObjectType.ASTERISM,
                    catalog="asterisms",
                    description=asterism_model_alt.description,
                    parent_planet=None,
                    constellation=asterism_model_alt.parent_constellation,
                )

            # Check constellations
            from celestron_nexstar.api.database.models import ConstellationModel

            constellation_stmt = (
                select(ConstellationModel)
                .where(
                    (ConstellationModel.name.ilike(name))
                    | (ConstellationModel.abbreviation.ilike(name))
                    | (ConstellationModel.common_name.ilike(name))
                )
                .limit(1)
            )
            result = await session.execute(constellation_stmt)
            constellation_model_raw = result.scalar_one_or_none()
            if constellation_model_raw:
                # Type cast: we know this is ConstellationModel from the select
                constellation_model: ConstellationModel = constellation_model_raw  # type: ignore[assignment]
                return CelestialObject(
                    name=constellation_model.name,
                    common_name=constellation_model.common_name,
                    ra_hours=constellation_model.ra_hours,
                    dec_degrees=constellation_model.dec_degrees,
                    magnitude=None,
                    object_type=CelestialObjectType.CONSTELLATION,
                    catalog="constellations",
                    description=constellation_model.mythology,
                    parent_planet=None,
                    constellation=None,
                )

            return None

    @deal.pre(lambda self, hr_number: hr_number > 0, message="HR number must be positive")  # type: ignore[misc,arg-type]
    @deal.post(lambda result: result is None or isinstance(result, str), message="Must return string or None")
    async def get_common_name_by_hr(self, hr_number: int) -> str | None:
        """
        Get common name for a given HR number from star_name_mappings table.

        Args:
            hr_number: HR catalog number

        Returns:
            Common name if found, None otherwise
        """
        async with self._AsyncSession() as session:
            from sqlalchemy import select

            from celestron_nexstar.api.database.models import StarNameMappingModel

            stmt = select(StarNameMappingModel).where(StarNameMappingModel.hr_number == hr_number).limit(1)
            result = await session.execute(stmt)
            mapping = result.scalar_one_or_none()
            if mapping and mapping.common_name and mapping.common_name.strip():
                return mapping.common_name.strip()
            return None

    @deal.pre(lambda self, query, limit: query and len(query.strip()) > 0, message="Query must be non-empty")  # type: ignore[misc,arg-type]
    @deal.pre(lambda self, query, limit: limit > 0, message="Limit must be positive")  # type: ignore[misc,arg-type]
    @deal.post(lambda result: isinstance(result, list), message="Must return list of objects")
    async def search(self, query: str, limit: int = 100) -> list[CelestialObject]:
        """
        Search across all type-specific tables using LIKE queries.

        Note: FTS5 search is no longer available since we split the objects table.
        This method now performs case-insensitive LIKE searches across all tables.

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

        async with self._AsyncSession() as session:
            from sqlalchemy import select

            all_models: list[Any] = []
            query.lower()

            # Search across all type-specific tables
            for model_class in self._TYPE_TO_MODEL.values():
                # Search in name
                stmt = select(model_class).where(model_class.name.ilike(f"%{query}%")).limit(limit)
                result = await session.execute(stmt)
                models = result.scalars().all()
                all_models.extend(models)

                # Search in common_name
                stmt = (
                    select(model_class)
                    .where(
                        model_class.common_name.isnot(None),
                        model_class.common_name.ilike(f"%{query}%"),
                    )
                    .limit(limit)
                )
                result = await session.execute(stmt)
                models = result.scalars().all()
                all_models.extend(models)

                # Search in description
                stmt = (
                    select(model_class)
                    .where(
                        model_class.description.isnot(None),
                        model_class.description.ilike(f"%{query}%"),
                    )
                    .limit(limit)
                )
                result = await session.execute(stmt)
                models = result.scalars().all()
                all_models.extend(models)

            # Convert to objects and deduplicate by ID
            seen_ids = set()
            objects = []
            for model in all_models:
                if model.id not in seen_ids:
                    seen_ids.add(model.id)
                    objects.append(self._model_to_object(model))
                    if len(objects) >= limit:
                        break

            return objects

    @deal.pre(lambda self, ra_hours, dec_degrees, radius_arcmin: 0 <= ra_hours < 24, message="RA must be 0-24 hours")  # type: ignore[misc,arg-type]
    @deal.pre(
        lambda self, ra_hours, dec_degrees, radius_arcmin: -90 <= dec_degrees <= 90,
        message="Dec must be -90 to +90 degrees",
    )  # type: ignore[misc,arg-type]
    @deal.pre(lambda self, ra_hours, dec_degrees, radius_arcmin: radius_arcmin > 0, message="Radius must be positive")  # type: ignore[misc,arg-type]
    @deal.post(lambda result: isinstance(result, list), message="Must return list of objects")
    async def search_by_coordinates(
        self, ra_hours: float, dec_degrees: float, radius_arcmin: float = 5.0, limit: int = 50
    ) -> list[tuple[CelestialObject, float]]:
        """
        Search for objects near given coordinates.

        Args:
            ra_hours: Right ascension in hours (0-24)
            dec_degrees: Declination in degrees (-90 to +90)
            radius_arcmin: Search radius in arcminutes (default: 5.0)
            limit: Maximum number of results to return (default: 50)

        Returns:
            List of tuples (CelestialObject, angular_separation_arcmin) sorted by distance
        """
        from sqlalchemy import select

        from celestron_nexstar.api.core.utils import angular_separation

        # Convert radius from arcminutes to degrees
        radius_deg = radius_arcmin / 60.0

        # Approximate bounding box for initial filtering (faster than calculating separation for all objects)
        # Account for RA wrap-around and declination limits
        # RA range in degrees (approximate, accounting for declination)
        cos_dec = abs(max(0.1, abs(dec_degrees)))  # Avoid division by zero
        ra_range_deg = radius_deg / cos_dec if cos_dec > 0.1 else radius_deg
        ra_range_hours = ra_range_deg / 15.0

        ra_min = (ra_hours - ra_range_hours) % 24.0
        ra_max = (ra_hours + ra_range_hours) % 24.0
        dec_min = max(-90.0, dec_degrees - radius_deg)
        dec_max = min(90.0, dec_degrees + radius_deg)

        async with self._AsyncSession() as session:
            all_results: list[tuple[CelestialObject, float]] = []

            # Search across all type-specific tables
            for model_class in self._TYPE_TO_MODEL.values():
                # Use bounding box for initial filtering
                # Handle RA wrap-around (e.g., 23h to 1h)
                if ra_min <= ra_max:
                    # Normal case: no wrap-around
                    stmt = (
                        select(model_class)
                        .where(
                            model_class.ra_hours.between(ra_min, ra_max),
                            model_class.dec_degrees.between(dec_min, dec_max),
                        )
                        .limit(limit * 5)  # Get more candidates for accurate filtering
                    )
                else:
                    # Wrap-around case: RA range crosses 0h
                    stmt = (
                        select(model_class)
                        .where(
                            (model_class.ra_hours >= ra_min) | (model_class.ra_hours <= ra_max),
                            model_class.dec_degrees.between(dec_min, dec_max),
                        )
                        .limit(limit * 5)  # Get more candidates for accurate filtering
                    )

                result = await session.execute(stmt)
                models = result.scalars().all()

                # Calculate accurate angular separation and filter
                for model in models:
                    obj = self._model_to_object(model)
                    separation_deg = angular_separation(ra_hours, dec_degrees, obj.ra_hours, obj.dec_degrees)
                    separation_arcmin = separation_deg * 60.0

                    if separation_arcmin <= radius_arcmin:
                        all_results.append((obj, separation_arcmin))

            # Sort by angular separation (closest first)
            all_results.sort(key=lambda x: x[1])

            # Limit results
            return all_results[:limit]

    @deal.pre(lambda self, catalog, limit: catalog and len(catalog.strip()) > 0, message="Catalog must be non-empty")  # type: ignore[misc,arg-type]
    @deal.pre(lambda self, catalog, limit: limit > 0, message="Limit must be positive")  # type: ignore[misc,arg-type]
    @deal.post(lambda result: isinstance(result, list), message="Must return list of objects")
    async def get_by_catalog(self, catalog: str, limit: int = 1000) -> list[CelestialObject]:
        """Get all objects from a specific catalog."""
        async with self._AsyncSession() as session:
            from sqlalchemy import select

            all_models: list[Any] = []
            # Query all type-specific tables
            for model_class in self._TYPE_TO_MODEL.values():
                stmt = (
                    select(model_class)
                    .where(model_class.catalog == catalog)
                    .order_by(model_class.catalog_number, model_class.name)
                    .limit(limit)
                )
                result = await session.execute(stmt)
                models = result.scalars().all()
                all_models.extend(models)

            # Sort by catalog_number and name, then limit
            all_models.sort(
                key=lambda m: (m.catalog_number if m.catalog_number is not None else float("inf"), m.name or "")
            )
            return [self._model_to_object(model) for model in all_models[:limit]]

    @deal.pre(
        lambda self, catalog, catalog_number: catalog and len(catalog.strip()) > 0, message="Catalog must be non-empty"
    )  # type: ignore[misc,arg-type]
    @deal.pre(lambda self, catalog, catalog_number: catalog_number > 0, message="Catalog number must be positive")  # type: ignore[misc,arg-type]
    @deal.post(lambda result: isinstance(result, bool), message="Must return boolean")
    async def exists_by_catalog_number(self, catalog: str, catalog_number: int) -> bool:
        """
        Check if an object exists with the given catalog and catalog number.

        Args:
            catalog: Catalog name
            catalog_number: Catalog number

        Returns:
            True if object exists, False otherwise
        """
        async with self._AsyncSession() as session:
            from sqlalchemy import func, select

            # Check across all type-specific tables
            for model_class in self._TYPE_TO_MODEL.values():
                count = await session.scalar(
                    select(func.count(model_class.id)).where(
                        model_class.catalog == catalog,
                        model_class.catalog_number == catalog_number,
                    )
                )
                if (count or 0) > 0:
                    return True
            return False

    @deal.pre(
        lambda self, *args, **kwargs: kwargs.get("limit", 1000) > 0,
        message="Limit must be positive",
    )  # type: ignore[misc,arg-type]
    @deal.post(lambda result: isinstance(result, list), message="Must return list of objects")
    async def filter_objects(
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
        async with self._AsyncSession() as session:
            from sqlalchemy import select

            # Convert object_type to enum if string
            object_type_enum = CelestialObjectType(object_type) if isinstance(object_type, str) else object_type  # type: ignore[assignment]

            # Determine which tables to query
            model_classes: list[type[CelestialObjectModelProtocol]]
            if object_type_enum:
                # Query specific table
                model_classes = [self._get_model_class(object_type_enum)]
            elif is_dynamic is not None:
                # is_dynamic only applies to planets and moons
                if is_dynamic:
                    model_classes = [
                        cast(type[CelestialObjectModelProtocol], PlanetModel),
                        cast(type[CelestialObjectModelProtocol], MoonModel),
                    ]
                else:
                    # Query all non-dynamic tables
                    model_classes = [
                        cast(type[CelestialObjectModelProtocol], StarModel),
                        cast(type[CelestialObjectModelProtocol], DoubleStarModel),
                        cast(type[CelestialObjectModelProtocol], GalaxyModel),
                        cast(type[CelestialObjectModelProtocol], NebulaModel),
                        cast(type[CelestialObjectModelProtocol], ClusterModel),
                    ]
            else:
                # Query all tables
                model_classes = list(self._TYPE_TO_MODEL.values())

            all_models: list[Any] = []
            for model_class in model_classes:
                stmt = select(model_class)

                # Build filters
                if catalog:
                    stmt = stmt.where(model_class.catalog == catalog)

                if max_magnitude is not None:
                    # Include objects with NULL magnitude when filtering by specific object type
                    if object_type_enum:
                        stmt = stmt.where((model_class.magnitude <= max_magnitude) | (model_class.magnitude.is_(None)))
                    else:
                        stmt = stmt.where(model_class.magnitude <= max_magnitude)

                if min_magnitude is not None:
                    stmt = stmt.where(model_class.magnitude >= min_magnitude)

                if constellation:
                    stmt = stmt.where(model_class.constellation.ilike(constellation))

                # is_dynamic filter (only for planets and moons)
                # Type ignore: Protocol includes is_dynamic but mypy needs help with the check
                if is_dynamic is not None and model_class in (PlanetModel, MoonModel):  # type: ignore[comparison-overlap]
                    stmt = stmt.where(model_class.is_dynamic == is_dynamic)  # type: ignore[attr-defined]

                # Order and limit
                stmt = stmt.order_by(model_class.magnitude.asc().nulls_last(), model_class.name.asc()).limit(limit)

                result = await session.execute(stmt)
                models = result.scalars().all()
                all_models.extend(models)

            # Convert all models to objects
            objects = [self._model_to_object(model) for model in all_models]

            # Sort by magnitude and name, then limit
            objects.sort(key=lambda x: (x.magnitude if x.magnitude is not None else float("inf"), x.name or ""))
            return objects[:limit]

    async def get_moons_by_parent_planet(self, planet_name: str) -> list[CelestialObject]:
        """
        Get all moons for a given parent planet.

        Args:
            planet_name: Name of the parent planet (e.g., "Mars", "Jupiter")

        Returns:
            List of moon objects
        """
        async with self._AsyncSession() as session:
            from sqlalchemy import select

            stmt = (
                select(MoonModel)
                .where(MoonModel.parent_planet == planet_name)
                .order_by(MoonModel.magnitude.asc().nulls_last(), MoonModel.name.asc())
            )

            result = await session.execute(stmt)
            models = result.scalars().all()

            return [self._model_to_object(model) for model in models]

    @deal.post(lambda result: isinstance(result, list), message="Must return list of catalog names")
    async def get_all_catalogs(self) -> list[str]:
        """Get list of all catalog names."""
        async with self._AsyncSession() as session:
            from sqlalchemy import select

            catalog_set: set[str] = set()
            # Query all type-specific tables
            for model_class in self._TYPE_TO_MODEL.values():
                stmt = select(model_class.catalog).distinct()
                result = await session.execute(stmt)
                catalogs = result.scalars().all()
                catalog_set.update(catalogs)

            return sorted(catalog_set)

    @deal.pre(lambda self, prefix, limit: limit > 0, message="Limit must be positive")  # type: ignore[misc,arg-type]
    @deal.post(lambda result: isinstance(result, list), message="Must return list of strings")
    async def get_names_for_completion(self, prefix: str = "", limit: int = 50) -> list[str]:
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

        async with self._AsyncSession() as session:
            # Build case-insensitive filter using LIKE for better compatibility
            prefix_lower = str(prefix).lower()

            # Query both name and common_name fields, returning the actual values
            # Use a UNION-like approach with separate queries, then combine
            names_set = set()

            # Query across all type-specific tables
            for model_class in self._TYPE_TO_MODEL.values():
                # Query name field
                name_query = (
                    select(model_class.name)
                    .distinct()
                    .filter(func.lower(model_class.name).like(f"{prefix_lower}%"))
                    .order_by(func.lower(model_class.name))
                    .limit(limit)
                )
                name_result = await session.execute(name_query)
                name_results = name_result.fetchall()
                for row in name_results:
                    if row[0]:
                        names_set.add(row[0])

                # Query common_name field
                common_name_query = (
                    select(model_class.common_name)
                    .distinct()
                    .filter(
                        model_class.common_name.isnot(None),
                        func.lower(model_class.common_name).like(f"{prefix_lower}%"),
                    )
                    .order_by(func.lower(model_class.common_name))
                    .limit(limit)
                )
            # Fix type incompatibility: Row[tuple[str | None]], be explicit with Optional[str]
            common_name_result = await session.execute(common_name_query)
            common_name_results: Sequence[Row[tuple[str | None]]] = common_name_result.fetchall()
            for common_name_row in common_name_results:
                # Use cast to help mypy understand the type (common_name can be None)
                val = cast(str | None, common_name_row[0])
                if val is not None:
                    names_set.add(val)
            return sorted(names_set, key=str.lower)[:limit]

    @deal.pre(lambda self, limit: limit > 0, message="Limit must be positive")  # type: ignore[misc,arg-type]
    @deal.post(lambda result: isinstance(result, list), message="Must return list of strings")
    async def get_all_names_for_completion(self, limit: int = 10000) -> list[str]:
        """
        Get all object names for command-line autocompletion.

        DEPRECATED: Use get_names_for_completion() with a prefix for better performance.

        Args:
            limit: Maximum number of results to return

        Returns:
            List of unique names (case-insensitive)
        """
        return await self.get_names_for_completion(prefix="", limit=limit)

    @deal.post(lambda result: result is not None, message="Stats must be returned")
    @deal.post(lambda result: hasattr(result, "total_objects"), message="Stats must have total_objects")
    async def get_stats(self) -> DatabaseStats:
        """Get database statistics."""
        from sqlalchemy import func, select

        async with self._AsyncSession() as session:
            # Total count - sum across all tables
            total = 0
            for model_class in self._TYPE_TO_MODEL.values():
                result = await session.execute(select(func.count(model_class.id)))
                total += result.scalar_one() or 0

            # By catalog - query all tables
            by_catalog: dict[str, int] = {}
            for model_class in self._TYPE_TO_MODEL.values():
                result = await session.execute(
                    select(model_class.catalog, func.count(model_class.id)).group_by(model_class.catalog)
                )
                for row in result.all():
                    catalog_name = row[0]
                    count = row[1]
                    if catalog_name:
                        by_catalog[catalog_name] = by_catalog.get(catalog_name, 0) + count

            # By type - count each table
            by_type: dict[str, int] = {}
            for obj_type, model_class in self._TYPE_TO_MODEL.items():
                result = await session.execute(select(func.count(model_class.id)))
                count = result.scalar_one() or 0
                by_type[obj_type.value] = count

            # Magnitude range - get min/max across all tables
            min_mags: list[float] = []
            max_mags: list[float] = []
            for model_class in self._TYPE_TO_MODEL.values():
                result = await session.execute(
                    select(func.min(model_class.magnitude), func.max(model_class.magnitude)).where(
                        model_class.magnitude.isnot(None)
                    )
                )
                mag_row: Any = result.first()
                if mag_row is not None and mag_row[0] is not None and mag_row[1] is not None:
                    min_mags.append(float(mag_row[0]))
                    max_mags.append(float(mag_row[1]))

            mag_range = (min(min_mags) if min_mags else None, max(max_mags) if max_mags else None)

            # Dynamic objects - count from planets and moons
            dynamic = 0
            for model_class in (
                cast(type[CelestialObjectModelProtocol], PlanetModel),
                cast(type[CelestialObjectModelProtocol], MoonModel),
            ):
                result = await session.execute(
                    select(func.count(model_class.id)).where(model_class.is_dynamic.is_(True))  # type: ignore[attr-defined]
                )
                dynamic += result.scalar_one() or 0

            # Version and last updated from metadata table
            version_model = await session.get(MetadataModel, "version")
            version = version_model.value if version_model else "unknown"

            updated_model = await session.get(MetadataModel, "last_updated")
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

    def _model_to_object(self, model: Any) -> CelestialObject:
        """Convert SQLAlchemy model to CelestialObject."""
        # Determine object type from model class
        if isinstance(model, StarModel):
            object_type = CelestialObjectType.STAR
        elif isinstance(model, DoubleStarModel):
            object_type = CelestialObjectType.DOUBLE_STAR
        elif isinstance(model, GalaxyModel):
            object_type = CelestialObjectType.GALAXY
        elif isinstance(model, NebulaModel):
            object_type = CelestialObjectType.NEBULA
        elif isinstance(model, ClusterModel):
            object_type = CelestialObjectType.CLUSTER
        elif isinstance(model, PlanetModel):
            object_type = CelestialObjectType.PLANET
        elif isinstance(model, MoonModel):
            object_type = CelestialObjectType.MOON
        elif isinstance(model, CelestialObjectModel):
            # Fallback for old model
            object_type = CelestialObjectType(model.object_type)
        else:
            raise ValueError(f"Unknown model type: {type(model)}")

        # Ensure name and common_name are strings (handle cases where DB has integers)
        name = str(model.name) if model.name is not None else None
        common_name = str(model.common_name) if model.common_name is not None else None

        # Get parent_planet (only for moons, or from old model)
        parent_planet = None
        if isinstance(model, (MoonModel, CelestialObjectModel)):
            parent_planet = model.parent_planet

        obj = CelestialObject(
            name=name,
            common_name=common_name,
            ra_hours=model.ra_hours,
            dec_degrees=model.dec_degrees,
            magnitude=model.magnitude,
            object_type=object_type,
            catalog=model.catalog,
            description=model.description,
            parent_planet=parent_planet,
            constellation=model.constellation,
        )

        # Handle dynamic objects (planets and moons)
        is_dynamic = False
        ephemeris_name = None
        if isinstance(model, (PlanetModel, MoonModel, CelestialObjectModel)):
            is_dynamic = model.is_dynamic
            ephemeris_name = str(model.ephemeris_name) if model.ephemeris_name else str(name) if name else ""

        if is_dynamic and ephemeris_name and is_dynamic_object(ephemeris_name):
            try:
                # Convert to lowercase for get_planetary_position (it expects lowercase planet names)
                planet_name = ephemeris_name.lower()
                ra, dec = get_planetary_position(planet_name)
                from dataclasses import replace

                obj = replace(obj, ra_hours=ra, dec_degrees=dec)
            except (ValueError, KeyError, FileNotFoundError) as e:
                # Log the error but use stored coordinates as fallback
                logger.debug(f"Could not calculate position for {ephemeris_name}: {e}")
                pass  # Use stored coordinates as fallback
            except Exception as e:
                # Catch any other exceptions (e.g., UnknownEphemerisObjectError) and use stored coordinates
                from celestron_nexstar.api.core.exceptions import UnknownEphemerisObjectError

                if isinstance(e, UnknownEphemerisObjectError) or isinstance(e.__cause__, UnknownEphemerisObjectError):
                    logger.debug(f"Unknown ephemeris object {ephemeris_name}: {e}")
                else:
                    logger.debug(f"Could not calculate position for {ephemeris_name}: {e}")
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
def get_database(use_memory: bool | None = None) -> CatalogDatabase:
    """
    Get the global database instance.

    Args:
        use_memory: If True, load database into memory for faster queries.
                    Requires an existing database file. If None, checks
                    CELESTRON_USE_MEMORY_DB environment variable. Default: False.

    Returns:
        Singleton database instance
    """
    global _database_instance
    if _database_instance is None:
        # Check environment variable if use_memory not explicitly set
        if use_memory is None:
            import os

            use_memory = os.getenv("CELESTRON_USE_MEMORY_DB", "false").lower() in ("true", "1", "yes")

        _database_instance = CatalogDatabase(use_memory=use_memory)
    return _database_instance


@deal.post(lambda result: result is not None, message="Database must be initialized")
async def init_database(db_path: Path | str | None = None) -> CatalogDatabase:
    """
    Initialize a new database with schema.

    Args:
        db_path: Path to database file

    Returns:
        Initialized database
    """
    db = CatalogDatabase(db_path)
    await db.init_schema()
    return db


@deal.post(
    lambda result: isinstance(result, tuple) and len(result) == 2,
    message="Must return tuple of (pages_freed, pages_used)",
)
@deal.post(lambda result: result[0] >= 0 and result[1] >= 0, message="Page counts must be non-negative")  # type: ignore[misc,arg-type,index,operator]
async def vacuum_database(db: CatalogDatabase | None = None) -> tuple[int, int]:
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
    async with db._AsyncSession() as session:
        await session.execute(text("VACUUM"))
        await session.commit()

    # Close the engine to ensure all connections are released and file is written
    # This is important because VACUUM creates a new database file
    await db._engine.dispose()

    # Small delay to ensure filesystem updates (some filesystems cache stat info)
    import asyncio

    await asyncio.sleep(0.1)

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
@deal.raises(DatabaseNotFoundError, DatabaseBackupError, OSError)
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
        DatabaseNotFoundError: If database file doesn't exist
        DatabaseBackupError: If backup operation fails
        OSError: If backup directory can't be created
    """
    if db is None:
        db = get_database()

    if not db.db_path.exists():
        raise DatabaseNotFoundError(f"Database not found: {db.db_path}")

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
@deal.raises(DatabaseNotFoundError, DatabaseRestoreError)
def restore_database(backup_path: Path, db: CatalogDatabase | None = None) -> None:
    """
    Restore database from a backup file.

    Args:
        backup_path: Path to backup file
        db: Database instance (default: uses get_database())

    Raises:
        DatabaseNotFoundError: If backup file doesn't exist
        DatabaseRestoreError: If restore operation fails
    """
    if db is None:
        db = get_database()

    backup_path = Path(backup_path)
    if not backup_path.exists():
        raise DatabaseNotFoundError(f"Backup file not found: {backup_path}")

    # Close any existing connections
    # Run async dispose in sync context
    import asyncio

    async def _dispose_engine() -> None:
        await db._engine.dispose()

    asyncio.run(_dispose_engine())

    # Copy backup to database location
    shutil.copy2(backup_path, db.db_path)

    logger.info(f"Database restored from: {backup_path}")


@deal.pre(
    lambda backup_dir, sources, mag_limit, skip_backup, dry_run, force_download: mag_limit > 0,
    message="Magnitude limit must be positive",
)  # type: ignore[misc,arg-type]
@deal.post(lambda result: result is not None, message="Rebuild must return statistics")
@deal.post(lambda result: "duration_seconds" in result, message="Result must include duration")  # type: ignore[misc,arg-type,operator]
@deal.raises(DatabaseRebuildError)
async def rebuild_database(
    backup_dir: Path | None = None,
    sources: list[str] | None = None,
    mag_limit: float = 15.0,
    skip_backup: bool = False,
    dry_run: bool = False,
    force_download: bool = False,
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
            await db._engine.dispose()
            # Remove database file
            db.db_path.unlink()
            logger.info("Database dropped")

        # Step 3: Run Alembic migrations to create fresh schema
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        from alembic import command  # type: ignore[attr-defined]

        alembic_cfg = Config("alembic.ini")

        # Determine the target revision (handle multiple heads)
        script = ScriptDirectory.from_config(alembic_cfg)
        try:
            # Try to get single head first (works when there's no branching)
            target_rev = script.get_current_head()
        except (AttributeError, ValueError, RuntimeError):
            # AttributeError: missing script attributes
            # ValueError: invalid configuration
            # RuntimeError: multiple heads or script errors
            # Multiple heads detected - use get_heads() instead
            try:
                heads_list = script.get_heads()
                if len(heads_list) == 1:
                    target_rev = heads_list[0]
                elif len(heads_list) > 1:
                    # Multiple heads detected - look for a merge migration
                    logger.info(f"Multiple migration heads detected: {', '.join(heads_list)}")

                    # Search all revisions for a merge migration that combines these heads
                    merge_found = False
                    for rev in script.walk_revisions():
                        if hasattr(rev, "down_revision") and rev.down_revision:
                            down_rev = rev.down_revision
                            # Check if this is a merge migration (has tuple of down_revisions)
                            if isinstance(down_rev, tuple) and len(down_rev) > 1:
                                # Check if this merge migration combines all current heads
                                down_rev_set = set(down_rev) if isinstance(down_rev, tuple) else {down_rev}
                                heads_set = set(heads_list)
                                if down_rev_set == heads_set:
                                    merge_found = True
                                    target_rev = rev.revision
                                    logger.info(f"Found merge migration: {rev.revision}")
                                    break

                    if not merge_found:
                        logger.info("No merge migration found. Using 'heads' to upgrade all branches.")
                        # Use "heads" to upgrade all branches - Alembic will apply merge migrations if they exist
                        target_rev = "heads"
                else:
                    target_rev = "head"  # Fallback
            except (AttributeError, ValueError, RuntimeError, TypeError) as e:
                # AttributeError: missing script attributes
                # ValueError: invalid configuration
                # RuntimeError: script errors
                # TypeError: wrong argument types
                logger.warning(f"Error determining head revision: {e}, using 'head'")
                target_rev = "head"

        command.upgrade(alembic_cfg, target_rev)
        logger.info(f"Schema created via Alembic migrations (upgraded to {target_rev})")

        # Get fresh database instance after rebuild
        db = get_database()

        # Ensure FTS table exists (migrations should create it, but ensure it's there)
        await db.ensure_fts_table()

        # Step 4: Initialize static reference data (seed data)
        # This must happen before importing custom YAML and other data sources
        from celestron_nexstar.api.database.database_seeder import seed_all
        from celestron_nexstar.api.database.models import get_db_session

        logger.info("Initializing static reference data...")
        console.print("\n[cyan]Initializing static reference data...[/cyan]")
        console.print("[dim]  • Star name mappings[/dim]")
        console.print("[dim]  • Meteor showers[/dim]")
        console.print("[dim]  • Constellations[/dim]")
        console.print("[dim]  • Asterisms[/dim]")
        console.print("[dim]  • Dark sky sites[/dim]")
        console.print("[dim]  • Space events[/dim]")
        console.print("[dim]  • Variable stars[/dim]")
        console.print("[dim]  • Comets[/dim]")
        console.print("[dim]  • Eclipses[/dim]")
        console.print("[dim]  • Bortle characteristics[/dim]")
        console.print("[dim]  • Planets[/dim]")
        console.print("[dim]  • Moons[/dim]\n")

        static_data: dict[str, int] = {}

        async with get_db_session() as session:
            # Use seed_all which handles all static data seeding
            await seed_all(session, force=False)
            from sqlalchemy import func, select

            from celestron_nexstar.api.database.models import (
                AsterismModel,
                ConstellationModel,
                DarkSkySiteModel,
                MeteorShowerModel,
                SpaceEventModel,
            )

            meteor_result = await session.scalar(select(func.count(MeteorShowerModel.id)))
            meteor_count = meteor_result or 0
            static_data["meteor_showers"] = meteor_count
            logger.info(f"Added {meteor_count} meteor showers")

            constellation_result = await session.scalar(select(func.count(ConstellationModel.id)))
            constellation_count = constellation_result or 0
            asterism_result = await session.scalar(select(func.count(AsterismModel.id)))
            asterism_count = asterism_result or 0
            static_data["constellations"] = constellation_count
            static_data["asterisms"] = asterism_count
            logger.info(f"Added {constellation_count} constellations and {asterism_count} asterisms")

            dark_sky_result = await session.scalar(select(func.count(DarkSkySiteModel.id)))
            dark_sky_count = dark_sky_result or 0
            static_data["dark_sky_sites"] = dark_sky_count
            logger.info(f"Added {dark_sky_count} dark sky sites")

            space_event_result = await session.scalar(select(func.count(SpaceEventModel.id)))
            space_event_count = space_event_result or 0
            static_data["space_events"] = space_event_count
            logger.info(f"Added {space_event_count} space events")

        # Step 5: Import data sources
        # Import here to avoid circular dependency
        from celestron_nexstar.cli.data_import import DATA_SOURCES, import_data_source

        if sources is None:
            # Exclude "custom" from default sources - it's a separate action
            sources = [s for s in DATA_SOURCES if s != "custom"]

        imported_counts: dict[str, tuple[int, int]] = {}
        objects_before_import = 0

        for source_id in sources:
            if source_id not in DATA_SOURCES:
                logger.warning(f"Unknown source: {source_id}, skipping")
                continue

            logger.info(f"Importing {source_id}...")
            # Get count before import
            try:
                db_stats_before = await db.get_stats()
                objects_before_import = db_stats_before.total_objects
            except (SQLAlchemyError, RuntimeError, AttributeError, ValueError, TypeError) as e:
                # SQLAlchemyError: database errors
                # RuntimeError: async/await errors
                # AttributeError: missing database attributes
                # ValueError: invalid stats format
                # TypeError: wrong argument types
                logger.warning(f"Failed to get stats before import: {e}")
                objects_before_import = 0

            # Import the source
            try:
                logger.info(f"Calling import_data_source for {source_id}...")
                # import_data_source prints to console, so output should be visible
                from celestron_nexstar.cli.data_import import import_data_source

                success = import_data_source(source_id, mag_limit, force_download=force_download)
                logger.info(f"import_data_source returned: {success}")
                if success:
                    # Get count after import
                    try:
                        db_stats_after = await db.get_stats()
                        imported = db_stats_after.total_objects - objects_before_import
                        imported_counts[source_id] = (imported, 0)  # Skipped count not easily available
                        objects_before_import = db_stats_after.total_objects
                        logger.info(f"Successfully imported {source_id}: {imported} objects")
                        if imported == 0:
                            logger.warning(f"Import reported success but no objects were added for {source_id}")
                    except (SQLAlchemyError, RuntimeError, AttributeError, ValueError, TypeError) as e:
                        logger.warning(f"Failed to get stats after import: {e}")
                        imported_counts[source_id] = (0, 0)
                else:
                    imported_counts[source_id] = (0, 0)
                    logger.warning(f"import_data_source returned False for {source_id}")
            except (
                SQLAlchemyError,
                RuntimeError,
                AttributeError,
                ValueError,
                TypeError,
                OSError,
                FileNotFoundError,
                PermissionError,
            ) as e:
                # SQLAlchemyError: database errors
                # RuntimeError: async/await errors, import errors
                # AttributeError: missing attributes
                # ValueError: invalid data format
                # TypeError: wrong argument types
                # OSError: file I/O errors
                # FileNotFoundError: missing files
                # PermissionError: file permission errors
                logger.error(f"Exception importing {source_id}: {e}", exc_info=True)
                imported_counts[source_id] = (0, 0)
                # Continue with other sources even if one fails
                # Re-raise if it's a critical error
                if "database" in str(e).lower() or "schema" in str(e).lower():
                    raise

        # Repopulate FTS table after all imports to ensure all objects are searchable
        logger.info("Repopulating FTS search index...")
        try:
            await db.repopulate_fts_table()
        except (SQLAlchemyError, RuntimeError, AttributeError, ValueError, TypeError) as e:
            # SQLAlchemyError: database errors, FTS table issues
            # RuntimeError: async/await errors
            # AttributeError: missing database attributes
            # ValueError: invalid data format
            # TypeError: wrong argument types
            logger.warning(f"Failed to repopulate FTS table: {e}")
            # Continue - search will fall back to direct queries

        # Step 6: Download and process World Atlas light pollution data
        logger.info("Downloading and processing World Atlas light pollution data...")
        console.print("\n[cyan]Downloading light pollution data...[/cyan]")
        console.print("[dim]  • World Atlas 2024 PNG images[/dim]")
        console.print("[dim]  • Stored in ~/.cache/celestron-nexstar/light-pollution/[/dim]\n")
        try:
            from celestron_nexstar.api.database.light_pollution_db import (
                _create_light_pollution_table,
                download_world_atlas_data,
            )

            # Ensure light pollution table exists before downloading data
            logger.info("Ensuring light pollution grid table exists...")
            console.print("[dim]Ensuring light pollution grid table exists...[/dim]")
            await _create_light_pollution_table(db)

            # Download north_america region by default
            # Users can download other regions later with: nexstar data download-light-pollution --region <region>
            # Use 0.1° resolution for good balance of accuracy and processing time
            logger.info("Downloading World Atlas PNG files (this may take a while)...")
            console.print("[dim]Downloading World Atlas PNG files (this may take a while)...[/dim]")
            console.print(
                "[dim]Note: Downloading 'north_america' region by default. Use 'nexstar data download-light-pollution' to download other regions.[/dim]\n"
            )
            # We're already in an async context, so await directly
            light_pollution_results = await download_world_atlas_data(
                regions=["north_america"],  # North America by default
                grid_resolution=0.1,  # 0.1° ≈ 11km resolution
                force=force_download,  # Re-download if force_download is True
                state_filter=None,  # No filter - process all data
            )

            total_grid_points = sum(light_pollution_results.values())
            logger.info(
                f"Processed {total_grid_points:,} light pollution grid points from {len(light_pollution_results)} regions"
            )
            if total_grid_points > 0:
                console.print(
                    f"[green]✓[/green] Processed {total_grid_points:,} light pollution grid points from {len(light_pollution_results)} regions"
                )
            else:
                console.print("[yellow]⚠ Warning: No light pollution data was imported[/yellow]")
            static_data["light_pollution_grid_points"] = total_grid_points

            # Log per-region counts
            for region, count in light_pollution_results.items():
                logger.info(f"  {region}: {count:,} points")
                if count > 0:
                    console.print(f"[dim]  {region}: {count:,} points[/dim]")
        except (RuntimeError, OSError, FileNotFoundError, PermissionError, ValueError, TypeError, AttributeError) as e:
            # RuntimeError: download/processing errors
            # OSError: file I/O errors
            # FileNotFoundError: missing files
            # PermissionError: file permission errors
            # ValueError: invalid data format
            # TypeError: wrong argument types
            # AttributeError: missing attributes
            import traceback

            logger.warning(f"Failed to download light pollution data: {e}")
            logger.warning(
                "Light pollution data can be downloaded later with: nexstar vacation download-light-pollution"
            )
            # Also print to console for visibility
            console.print(f"[yellow]⚠ Warning: Failed to download light pollution data: {e}[/yellow]")
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(traceback.format_exc())
            static_data["light_pollution_grid_points"] = 0

        # Step 7: Pre-fetch 3 days of weather forecast data (if location is configured)
        logger.info("Pre-fetching 3-day weather forecast data...")
        try:
            import asyncio

            from celestron_nexstar.api.location.observer import (
                ObserverLocation,
                geocode_location,
                get_observer_location,
                set_observer_location,
            )
            from celestron_nexstar.api.location.weather import fetch_hourly_weather_forecast

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
                        from rich.prompt import Prompt

                        console.print("\n[cyan]Observer Location Required[/cyan]")
                        console.print(
                            "[dim]Your location is needed for weather forecasts and accurate calculations.[/dim]\n"
                        )

                        location_query = Prompt.ask("Enter your location", default="", console=console)

                        if location_query:
                            try:
                                console.print(f"[dim]Geocoding: {location_query}...[/dim]")
                                # Run async function - this is a sync entry point, so asyncio.run() is safe
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
                except (OSError, RuntimeError, AttributeError, ValueError, TypeError) as e:
                    # OSError: I/O errors (stdin/stdout)
                    # RuntimeError: prompt errors
                    # AttributeError: missing console attributes
                    # ValueError: invalid input
                    # TypeError: wrong argument types
                    logger.debug(f"Could not prompt for location interactively: {e}")
                    logger.info("Set your location with: nexstar location set-observer <location>")
                    location = None

            if location:
                logger.info(
                    f"Fetching weather forecast for {location.name} ({location.latitude:.2f}°, {location.longitude:.2f}°)"
                )
                # Fetch 3 days = 72 hours of weather forecast
                # We're already in an async context, so await directly
                weather_forecasts = await fetch_hourly_weather_forecast(location, hours=72)
                if weather_forecasts:
                    logger.info(f"Pre-fetched {len(weather_forecasts)} hours of weather forecast data")
                    static_data["weather_forecast_hours"] = len(weather_forecasts)
                else:
                    logger.warning("No weather forecast data was fetched")
                    static_data["weather_forecast_hours"] = 0
            else:
                static_data["weather_forecast_hours"] = 0
        except (RuntimeError, AttributeError, ValueError, TypeError, OSError, TimeoutError) as e:
            # RuntimeError: async/await errors, API errors
            # AttributeError: missing location/API attributes
            # ValueError: invalid location data
            # TypeError: wrong argument types
            # OSError: network I/O errors
            # TimeoutError: request timeout
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

    except (
        SQLAlchemyError,
        RuntimeError,
        AttributeError,
        ValueError,
        TypeError,
        OSError,
        FileNotFoundError,
        PermissionError,
    ) as e:
        # SQLAlchemyError: database errors
        # RuntimeError: async/await errors, import errors
        # AttributeError: missing attributes
        # ValueError: invalid data format
        # TypeError: wrong argument types
        # OSError: file I/O errors
        # FileNotFoundError: missing files
        # PermissionError: file permission errors
        # Restore backup if available
        if backup_path and backup_path.exists():
            logger.error(f"Rebuild failed: {e}. Restoring backup...")
            try:
                restore_database(backup_path, db)
                logger.info("Backup restored successfully")
            except (OSError, FileNotFoundError, PermissionError, RuntimeError, ValueError, TypeError) as restore_error:
                # OSError: file I/O errors
                # FileNotFoundError: backup file missing
                # PermissionError: file permission errors
                # RuntimeError: restore errors
                # ValueError: invalid backup format
                # TypeError: wrong argument types
                logger.error(f"Failed to restore backup: {restore_error}")
        raise DatabaseRebuildError(f"Database rebuild failed: {e}") from e


@deal.post(lambda result: isinstance(result, dict), message="Must return dictionary")
async def get_ephemeris_files() -> dict[str, dict[str, Any]]:
    """
    Get all ephemeris files from the database.

    Returns:
        Dictionary mapping file_key to EphemerisFileInfo-like dict
    """
    db = get_database()
    async with db._AsyncSession() as session:
        from sqlalchemy import select

        stmt = select(EphemerisFileModel)
        result = await session.execute(stmt)
        files = result.scalars().all()
        file_dict: dict[str, dict[str, Any]] = {}
        for file_model in files:
            file_dict[file_model.file_key] = {
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
        return file_dict


@deal.post(lambda result: isinstance(result, list), message="Must return list")
# Note: Postconditions on async functions check the coroutine, not the awaited result
async def list_ephemeris_files_from_naif() -> list[dict[str, Any]]:
    """
    Fetch ephemeris file information from NAIF and return as list (without syncing).

    Returns:
        List of dictionaries with ephemeris file information
    """
    from celestron_nexstar.api.ephemeris.ephemeris_manager import (
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

    except (RuntimeError, AttributeError, ValueError, TypeError, OSError, TimeoutError, KeyError, IndexError) as e:
        # RuntimeError: async/await errors, API errors
        # AttributeError: missing attributes in summaries
        # ValueError: invalid data format
        # TypeError: wrong argument types
        # OSError: network I/O errors
        # TimeoutError: request timeout
        # KeyError: missing keys in data
        # IndexError: missing array indices
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
    from celestron_nexstar.api.ephemeris.ephemeris_manager import (
        NAIF_PLANETS_SUMMARY,
        NAIF_SATELLITES_SUMMARY,
        _fetch_summaries,
        _generate_file_info,
        _parse_summaries,
    )

    db = get_database()

    # Check if we need to sync (check last sync time in metadata)
    if not force:
        async with db._AsyncSession() as session:
            from sqlalchemy import select

            result = await session.execute(
                select(MetadataModel).filter(MetadataModel.key == "ephemeris_files_last_sync")
            )
            last_sync = result.scalar_one_or_none()
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
        async with db._AsyncSession() as session:
            from sqlalchemy import select

            synced_count = 0
            for file_model in files_to_sync:
                # Check if exists
                result = await session.execute(
                    select(EphemerisFileModel).filter(EphemerisFileModel.file_key == file_model.file_key)
                )
                existing = result.scalar_one_or_none()
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
            sync_result = await session.execute(
                select(MetadataModel).filter(MetadataModel.key == "ephemeris_files_last_sync")
            )
            sync_metadata = sync_result.scalar_one_or_none()
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

            await session.commit()
            logger.info(f"Synced {synced_count} ephemeris files to database")
            return synced_count

    except (
        SQLAlchemyError,
        RuntimeError,
        AttributeError,
        ValueError,
        TypeError,
        OSError,
        TimeoutError,
        KeyError,
        IndexError,
    ) as e:
        # SQLAlchemyError: database errors
        # RuntimeError: async/await errors, API errors
        # AttributeError: missing attributes
        # ValueError: invalid data format
        # TypeError: wrong argument types
        # OSError: network I/O errors
        # TimeoutError: request timeout
        # KeyError: missing keys in data
        # IndexError: missing array indices
        logger.error(f"Failed to sync ephemeris files from NAIF: {e}")
        raise

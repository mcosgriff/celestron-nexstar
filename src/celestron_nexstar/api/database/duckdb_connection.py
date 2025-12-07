"""
Central DuckDB Connection Manager

Provides thread-safe DuckDB connections for all database operations.
Each thread gets its own connection to avoid thread-safety issues.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from pathlib import Path
from typing import Any

import duckdb

from celestron_nexstar.api.database.duckdb_migrations import run_migrations


logger = logging.getLogger(__name__)

__all__ = ["DuckDBConnection", "get_duckdb_connection"]


class DuckDBConnection:
    """
    Central DuckDB connection manager.

    Provides thread-local connections to the DuckDB database.
    Each thread gets its own connection to ensure thread safety.
    Ensures migrations are run and connections are properly configured.
    """

    _instance: DuckDBConnection | None = None
    _db_path: Path | None = None
    _local = threading.local()  # Thread-local storage for connections
    _migrations_run = False
    _lock = threading.Lock()  # Lock for migrations

    def __init__(self, db_path: Path | str | None = None):
        """
        Initialize DuckDB connection manager.

        Args:
            db_path: Path to DuckDB database file (default: ~/.config/celestron-nexstar/catalogs.duckdb)
        """
        if db_path is None:
            db_path = self._get_default_db_path()

        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _get_default_db_path() -> Path:
        """Get path to DuckDB database file in user config directory."""
        from pathlib import Path

        config_dir = Path.home() / ".config" / "celestron-nexstar"
        return config_dir / "catalogs.duckdb"

    def _get_thread_connection(self) -> duckdb.DuckDBPyConnection:
        """Get or create a thread-local DuckDB connection."""
        # Check if this thread already has a connection
        if not hasattr(self._local, "connection") or self._local.connection is None:
            # Create a new connection for this thread
            self._local.connection = duckdb.connect(str(self._db_path))

            # Configure for performance
            self._local.connection.execute("SET threads TO 1")  # Single thread per connection for thread safety
            self._local.connection.execute("SET memory_limit = '2GB'")  # Allow more memory for queries

            # Load extensions for enhanced functionality
            # Note: This requires network access to download extensions from DuckDB's repository
            extensions_to_load = [
                ("fts", "Full-text search"),
                ("spatial", "Geospatial data types and functions"),
            ]

            for ext_name, ext_description in extensions_to_load:
                try:
                    self._local.connection.execute(f"INSTALL {ext_name};")
                    self._local.connection.execute(f"LOAD {ext_name};")
                    logger.debug(f"Loaded {ext_name} extension ({ext_description})")
                except Exception as e:
                    if ext_name == "fts":
                        logger.warning(
                            f"Could not load fts extension: {e}. "
                            "Full-text search will fall back to LIKE queries. "
                            "The fts extension requires network access to download from DuckDB's extension repository. "
                            "If you need full-text search, ensure you have internet connectivity and try again."
                        )
                    elif ext_name == "spatial":
                        logger.warning(
                            f"Could not load spatial extension: {e}. "
                            "Spatial queries will use fallback methods. "
                            "The spatial extension requires network access to download from DuckDB's extension repository."
                        )

            # Run migrations only once (thread-safe)
            with self._lock:
                if not self._migrations_run:
                    run_migrations(self._local.connection)
                    self._migrations_run = True

        return self._local.connection

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        """Get the thread-local DuckDB connection."""
        return self._get_thread_connection()

    @property
    def db_path(self) -> Path:
        """Get the database file path."""
        if self._db_path is None:
            raise RuntimeError("DuckDB connection not initialized")
        return self._db_path

    def close(self) -> None:
        """Close all thread-local connections."""
        # Close the current thread's connection
        if hasattr(self._local, "connection") and self._local.connection:
            with contextlib.suppress(Exception):
                self._local.connection.close()
            self._local.connection = None

    def __enter__(self) -> duckdb.DuckDBPyConnection:
        """Context manager entry."""
        return self.connection

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        # Don't close the connection in context manager - it's thread-local
        pass


def get_duckdb_connection(db_path: Path | str | None = None) -> duckdb.DuckDBPyConnection:
    """
    Get a thread-local DuckDB connection.

    This function returns a connection that is specific to the current thread.
    Each thread gets its own connection to ensure thread safety.

    Args:
        db_path: Optional path to database file (only used on first call)

    Returns:
        DuckDB connection object (thread-local)
    """
    if DuckDBConnection._instance is None:
        DuckDBConnection._instance = DuckDBConnection(db_path)

    return DuckDBConnection._instance.connection

"""
High-performance DuckDB-based catalog database.

Uses DuckDB native API for maximum performance, queries starplot's parquet files directly,
and stores only custom data (planets, moons, asterisms, constellations) in the database.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from celestron_nexstar.api.catalogs.catalogs import CelestialObject
from celestron_nexstar.api.core.enums import CelestialObjectType
from celestron_nexstar.api.data.starplot_config import get_starplot_data_directory


logger = logging.getLogger(__name__)

__all__ = ["DuckDBCatalogDatabase"]


# Type alias for database compatibility
# Both CatalogDatabase and DuckDBCatalogDatabase implement the same interface
CatalogDatabaseProtocol = Any  # Protocol would be better, but Any works for now


class DuckDBCatalogDatabase:
    """
    High-performance DuckDB-based catalog database.

    Uses DuckDB native API for direct parquet queries and fts_main extension for full-text search.
    Only stores custom data (planets, moons, asterisms, constellations) in the database.
    Stars and DSOs are queried directly from starplot's parquet files.
    """

    def __init__(self, db_path: Path | str | None = None):
        """
        Initialize DuckDB database connection.

        Args:
            db_path: Path to DuckDB database file (default: ~/.config/celestron-nexstar/catalogs.duckdb)
        """
        if db_path is None:
            db_path = self._get_default_db_path()

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Get starplot data directory
        self.starplot_data_dir = get_starplot_data_directory()

        # Use shared DuckDB connection
        from celestron_nexstar.api.database.duckdb_connection import get_duckdb_connection

        self.con = get_duckdb_connection(db_path)

        # Check if extensions are available
        self._fts_available = False
        self._spatial_available = False
        try:
            # Check if extensions are loaded by querying the extensions list
            extensions = self.con.execute("SELECT * FROM duckdb_extensions() WHERE loaded = true").fetchall()
            extension_names = [ext[0] for ext in extensions]
            self._fts_available = "fts" in extension_names
            self._spatial_available = "spatial" in extension_names
            if not self._fts_available:
                logger.warning("FTS extension not available. Falling back to LIKE queries.")
            if not self._spatial_available:
                logger.debug("Spatial extension not available. Using fallback methods for spatial queries.")
        except Exception:
            logger.warning("Could not check extension availability. Using fallback methods.")

        # Cache parquet file paths
        self._star_parquet_path = self._find_star_parquet_file()
        self._dso_db_path = self._find_dso_database()

        # Alias for starplot database (used for both star_designations and deep_sky_objects)
        self._starplot_db_alias = "starplot_db"

        # Track FTS index creation status
        self._fts_indexes_created = False
        if self._fts_available:
            self._ensure_fts_indexes()

    def _get_default_db_path(self) -> Path:
        """Get path to DuckDB database file in user config directory."""
        config_dir = Path.home() / ".config" / "celestron-nexstar"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "catalogs.duckdb"

    def _find_star_parquet_file(self) -> Path | None:
        """Find starplot's star parquet file."""
        # Check for abridged version first (included with starplot)
        try:
            from starplot.data import DataFiles

            if DataFiles.BIG_SKY_MAG11.exists():
                return DataFiles.BIG_SKY_MAG11
        except Exception:
            pass

        # Check in starplot data directory
        parquet_files = list(self.starplot_data_dir.glob("*.parquet"))
        if parquet_files:
            # Prefer abridged version
            for f in parquet_files:
                if "mag11" in f.name.lower():
                    return f
            return parquet_files[0]

        return None

    def _find_dso_database(self) -> Path | None:
        """Find starplot's DSO database."""
        try:
            from starplot.data import DataFiles

            if DataFiles.DATABASE.exists():
                return DataFiles.DATABASE
        except Exception:
            pass

        # Check in starplot data directory
        dso_db = self.starplot_data_dir / "sky.db"
        if dso_db.exists():
            return dso_db

        return None

    def _ensure_starplot_db_attached(self) -> None:
        """Ensure starplot database is attached with consistent alias."""
        if not self._dso_db_path or not self._dso_db_path.exists():
            raise FileNotFoundError(
                f"Starplot database not found at {self._dso_db_path}. "
                "Starplot data is required. Please ensure starplot is properly installed and configured."
            )

        # Check if already attached
        try:
            # Try to query the attached databases
            attached = self.con.execute(
                "SELECT database_name FROM pragma_database_list() WHERE database_name = ?", [self._starplot_db_alias]
            ).fetchone()
            if attached:
                return  # Already attached
        except Exception:
            pass  # If query fails, try to attach

        # Attach the database
        try:
            self.con.execute(f"ATTACH '{self._dso_db_path}' AS {self._starplot_db_alias} (READ_ONLY)")
        except Exception as e:
            error_msg = str(e).lower()
            # Check if it's already attached (different error messages for this)
            if (
                "already exists" in error_msg
                or "already attached" in error_msg
                or "unique file handle conflict" in error_msg
                or "database with name" in error_msg
            ):
                # Already attached, that's fine - just return
                return
            else:
                # Some other error, re-raise it
                raise

    def _check_starplot_constellations_table(self) -> bool:
        """Check if starplot's database has a constellations table."""
        if not self._dso_db_path or not self._dso_db_path.exists():
            return False

        try:
            # Try to query for constellations table in starplot's database
            result = self.con.execute(
                f"SELECT table_name FROM information_schema.tables WHERE database_name = '{self._dso_db_path}' AND table_name = 'constellations'"
            ).fetchone()
            if result:
                return True

            # Alternative: try to query the table directly
            self.con.execute(f"SELECT COUNT(*) FROM '{self._dso_db_path}'.constellations LIMIT 1").fetchone()
            return True
        except Exception:
            return False

    def _ensure_fts_indexes(self) -> None:
        """Create FTS indexes on tables and views for efficient full-text search."""
        if self._fts_indexes_created:
            logger.debug("FTS indexes already created, skipping")
            return

        if not self._fts_available:
            logger.warning("FTS extension not available, cannot create indexes")
            return

        logger.info("Creating FTS indexes...")

        try:
            # Ensure starplot database is attached
            self._ensure_starplot_db_attached()

            # Create FTS indexes on DuckDB tables (planets, moons, asterisms, constellations)
            # These work directly on tables
            try:
                # Check if indexes already exist by trying to query them
                self.con.execute("SELECT * FROM fts_main_planets LIMIT 1").fetchone()
                logger.debug("FTS index on planets table already exists")
            except Exception:
                # Index doesn't exist, create it
                try:
                    self.con.execute("PRAGMA create_fts_index('planets', 'id', 'name', 'common_name')")
                    logger.info("Created FTS index on planets table")
                except Exception as e:
                    error_msg = str(e).lower()
                    if "already exists" in error_msg:
                        logger.debug("FTS index on planets table already exists")
                    else:
                        logger.warning(f"Could not create FTS index on planets: {e}")

            try:
                self.con.execute("SELECT * FROM fts_main_moons LIMIT 1").fetchone()
                logger.debug("FTS index on moons table already exists")
            except Exception:
                try:
                    self.con.execute("PRAGMA create_fts_index('moons', 'id', 'name', 'common_name', 'description')")
                    logger.info("Created FTS index on moons table")
                except Exception as e:
                    error_msg = str(e).lower()
                    if "already exists" in error_msg:
                        logger.debug("FTS index on moons table already exists")
                    else:
                        logger.warning(f"Could not create FTS index on moons: {e}")

            try:
                self.con.execute("SELECT * FROM fts_main_asterisms LIMIT 1").fetchone()
                logger.debug("FTS index on asterisms table already exists")
            except Exception:
                try:
                    self.con.execute("PRAGMA create_fts_index('asterisms', 'id', 'name', 'alt_names', 'description')")
                    logger.info("Created FTS index on asterisms table")
                except Exception as e:
                    error_msg = str(e).lower()
                    if "already exists" in error_msg:
                        logger.debug("FTS index on asterisms table already exists")
                    else:
                        logger.warning(f"Could not create FTS index on asterisms: {e}")

            try:
                self.con.execute("SELECT * FROM fts_main_constellations LIMIT 1").fetchone()
                logger.debug("FTS index on constellations table already exists")
            except Exception:
                try:
                    self.con.execute(
                        "PRAGMA create_fts_index('constellations', 'id', 'name', 'abbreviation', 'common_name')"
                    )
                    logger.info("Created FTS index on constellations table")
                except Exception as e:
                    error_msg = str(e).lower()
                    if "already exists" in error_msg:
                        logger.debug("FTS index on constellations table already exists")
                    else:
                        logger.warning(f"Could not create FTS index on constellations: {e}")

            # Create materialized tables for stars and DSOs from parquet/attached database
            # FTS indexes require tables, not views
            if self._star_parquet_path and self._star_parquet_path.exists():
                try:
                    # Check if table already exists and is up to date
                    table_exists = False
                    try:
                        result = self.con.execute(
                            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'stars_fts_table'"
                        ).fetchone()
                        table_exists = result and result[0] > 0
                    except Exception:
                        pass

                    if not table_exists:
                        logger.info("Creating materialized table for stars FTS (this may take a moment)...")
                        # Create materialized table for stars (from parquet + star_designations)
                        # We need a unique ID for FTS, so we'll use ROW_NUMBER
                        stars_table_sql = f"""
                            CREATE TABLE stars_fts_table AS
                            SELECT
                                ROW_NUMBER() OVER (ORDER BY s.hip, s.tyc_id) as id,
                                COALESCE(NULLIF(sd.name, ''), NULLIF(sd.bayer, ''), CAST(s.hip AS VARCHAR), s.tyc_id) as name,
                                NULLIF(sd.name, '') as common_name,
                                NULLIF(sd.bayer, '') as bayer,
                                CAST(s.hip AS VARCHAR) as hip_str,
                                s.tyc_id,
                                s.ra_degrees / 15.0 as ra_hours,
                                s.dec_degrees,
                                s.magnitude,
                                s.constellation
                            FROM read_parquet(?) s
                            LEFT JOIN {self._starplot_db_alias}.star_designations sd ON s.hip = sd.hip
                        """
                        self.con.execute(stars_table_sql, [str(self._star_parquet_path)])
                        logger.info("Created stars_fts_table")

                    # Try to create FTS index on the table
                    try:
                        self.con.execute("SELECT * FROM fts_main_stars_fts_table LIMIT 1").fetchone()
                        logger.debug("FTS index on stars_fts_table already exists")
                    except Exception:
                        try:
                            logger.info("Creating FTS index on stars_fts_table (this may take a moment)...")
                            self.con.execute(
                                "PRAGMA create_fts_index('stars_fts_table', 'id', 'name', 'common_name', 'bayer', 'hip_str', 'tyc_id')"
                            )
                            logger.info("Created FTS index on stars_fts_table")
                        except Exception as e:
                            error_msg = str(e).lower()
                            if "already exists" in error_msg:
                                logger.debug("FTS index on stars_fts_table already exists")
                            else:
                                logger.warning(f"Could not create FTS index on stars_fts_table: {e}")
                except Exception as e:
                    logger.warning(f"Could not create stars_fts_table: {e}")

            # Create materialized table for DSOs from attached database
            try:
                # Check if table already exists
                table_exists = False
                try:
                    result = self.con.execute(
                        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'dsos_fts_table'"
                    ).fetchone()
                    table_exists = result and result[0] > 0
                except Exception:
                    pass

                if not table_exists:
                    logger.info("Creating materialized table for DSOs FTS (this may take a moment)...")
                    dso_table_sql = f"""
                        CREATE TABLE dsos_fts_table AS
                        SELECT
                            ROW_NUMBER() OVER (ORDER BY name) as id,
                            name,
                            ra_degrees / 15.0 as ra_hours,
                            dec_degrees,
                            COALESCE(mag_v, mag_b) as magnitude,
                            type,
                            constellation
                        FROM {self._starplot_db_alias}.deep_sky_objects
                    """
                    self.con.execute(dso_table_sql)
                    logger.info("Created dsos_fts_table")

                # Try to create FTS index on the table
                try:
                    self.con.execute("SELECT * FROM fts_main_dsos_fts_table LIMIT 1").fetchone()
                    logger.debug("FTS index on dsos_fts_table already exists")
                except Exception:
                    try:
                        logger.info("Creating FTS index on dsos_fts_table (this may take a moment)...")
                        self.con.execute("PRAGMA create_fts_index('dsos_fts_table', 'id', 'name')")
                        logger.info("Created FTS index on dsos_fts_table")
                    except Exception as e:
                        error_msg = str(e).lower()
                        if "already exists" in error_msg:
                            logger.debug("FTS index on dsos_fts_table already exists")
                        else:
                            logger.warning(f"Could not create FTS index on dsos_fts_table: {e}")
            except Exception as e:
                logger.warning(f"Could not create dsos_fts_table: {e}")

            self._fts_indexes_created = True
            logger.info("FTS indexes created successfully")

        except Exception as e:
            logger.warning(f"Error creating FTS indexes: {e}. Falling back to LIKE queries.")
            self._fts_indexes_created = False

    def _row_to_celestial_object(self, row: dict[str, Any], object_type: CelestialObjectType) -> CelestialObject:
        """Convert a database row to CelestialObject."""
        return CelestialObject(
            name=str(row.get("name", "")),
            common_name=str(row["common_name"]) if row.get("common_name") else None,
            ra_hours=float(row["ra_hours"]),
            dec_degrees=float(row["dec_degrees"]),
            magnitude=float(row["magnitude"]) if row.get("magnitude") is not None else None,
            object_type=object_type,
            catalog=str(row.get("catalog", "")),
            description=str(row["description"]) if row.get("description") else None,
            parent_planet=str(row["parent_planet"]) if row.get("parent_planet") else None,
            constellation=str(row["constellation"]) if row.get("constellation") else None,
        )

    async def search(self, query: str, limit: int = 100) -> list[CelestialObject]:
        """
        Search for objects by name, common_name, or description.

        Uses full-text search if available, otherwise falls back to LIKE queries.
        Searches across all data sources: stars (parquet), DSOs (starplot DB), and custom data.

        Args:
            query: Search query string
            limit: Maximum number of results

        Returns:
            List of matching CelestialObject instances
        """
        if not query or not query.strip():
            return []

        # Use parameterized queries to prevent SQL injection
        query_lower = query.lower().strip()
        query_len = len(query_lower)

        # Performance optimization: For very short queries (1-2 characters), reduce the search scope
        # Note: We don't skip searches for common words like "and" because they appear in many object names
        # (e.g., "Andromeda", "Andromedae", etc.)

        # Adjust limits based on query length
        if query_len <= 2:
            # Very short queries: use smaller limits and skip expensive searches
            per_type_limit = min(10, limit // 4)  # Much smaller limit per type
            skip_stars = True  # Skip star search for very short queries
            skip_dsos = True  # Skip DSO search for very short queries
        elif query_len <= 3:
            # Short queries (like "and"): use higher limits to find more matches
            # Common words like "and" appear in many object names (Andromeda, Anderson, etc.)
            per_type_limit = min(100, limit)  # Use full limit per type for better coverage
            skip_stars = False
            skip_dsos = False
        else:
            # Normal queries: use full limits
            per_type_limit = limit
            skip_stars = False
            skip_dsos = False

        results: list[CelestialObject] = []

        import pandas as pd

        custom_results = pd.DataFrame()
        pattern = f"%{query_lower}%"

        # Log search method being used
        if self._fts_available and self._fts_indexes_created:
            logger.debug(f"Using FTS search for query: '{query}'")
        else:
            logger.debug(
                f"Using LIKE search for query: '{query}' (FTS available: {self._fts_available}, indexes created: {self._fts_indexes_created})"
            )

        # Use FTS if available, otherwise fall back to LIKE queries
        if self._fts_available and self._fts_indexes_created:
            try:
                # Use FTS queries for tables with indexes
                # Wrap each SELECT in a subquery to allow ORDER BY and LIMIT before UNION ALL
                custom_query = f"""
                    SELECT * FROM (
                        SELECT 'planet' as object_type, name, common_name, ra_hours, dec_degrees,
                               magnitude, catalog, description, NULL as parent_planet, constellation
                        FROM (
                            SELECT p.name, p.common_name, p.ra_hours, p.dec_degrees,
                                   p.magnitude, p.catalog, p.description, p.constellation,
                                   fts_main_planets.match_bm25(p.id, ?) as score
                            FROM planets p
                            WHERE score IS NOT NULL
                            ORDER BY score DESC
                            LIMIT {per_type_limit}
                        )
                        UNION ALL
                        SELECT 'moon' as object_type, name, common_name, ra_hours, dec_degrees,
                               magnitude, catalog, description, parent_planet, constellation
                        FROM (
                            SELECT m.name, m.common_name, m.ra_hours, m.dec_degrees,
                                   m.magnitude, m.catalog, m.description, m.parent_planet, m.constellation,
                                   fts_main_moons.match_bm25(m.id, ?) as score
                            FROM moons m
                            WHERE score IS NOT NULL
                            ORDER BY score DESC
                            LIMIT {per_type_limit}
                        )
                        UNION ALL
                        SELECT 'asterism' as object_type, name, NULL as common_name, ra_hours, dec_degrees,
                               NULL as magnitude, 'custom' as catalog, description, NULL as parent_planet, parent_constellation as constellation
                        FROM (
                            SELECT a.name, a.ra_hours, a.dec_degrees, a.description, a.parent_constellation,
                                   fts_main_asterisms.match_bm25(a.id, ?) as score
                            FROM asterisms a
                            WHERE score IS NOT NULL
                            ORDER BY score DESC
                            LIMIT {per_type_limit}
                        )
                        UNION ALL
                        SELECT 'constellation' as object_type, name, common_name, ra_hours, dec_degrees,
                               NULL as magnitude, 'starplot' as catalog, NULL as description, NULL as parent_planet, NULL as constellation
                        FROM (
                            SELECT c.name, c.common_name, c.ra_hours, c.dec_degrees,
                                   fts_main_constellations.match_bm25(c.id, ?) as score
                            FROM constellations c
                            WHERE score IS NOT NULL
                            ORDER BY score DESC
                            LIMIT {per_type_limit}
                        )
                    ) LIMIT {limit}
                """
                custom_results = self.con.execute(
                    custom_query,
                    [query_lower, query_lower, query_lower, query_lower],
                ).fetchdf()
                logger.debug(f"FTS search for custom data returned {len(custom_results)} results")
            except Exception as e:
                logger.warning(f"Error executing FTS search query, falling back to LIKE: {e}", exc_info=True)
                # Fall through to LIKE queries
                custom_results = pd.DataFrame()

        if not self._fts_available or custom_results.empty:
            import pandas as pd

            custom_results = pd.DataFrame()
            # Use LIKE queries with parameterized queries for planets, moons, asterisms, and constellations
            # Query from DuckDB tables for fast database-side filtering with indexes
            # Apply LIMIT to each SELECT to get per_type_limit results from each type
            pattern = f"%{query_lower}%"
            try:
                # Use subqueries with LIMIT, then wrap in outer query to apply overall limit
                custom_query = f"""
                    SELECT * FROM (
                        SELECT 'planet' as object_type, name, common_name, ra_hours, dec_degrees,
                               magnitude, catalog, description, NULL as parent_planet, constellation
                        FROM planets
                        WHERE name ILIKE ? OR common_name ILIKE ?
                        LIMIT {per_type_limit}
                        UNION ALL
                        SELECT 'moon' as object_type, name, common_name, ra_hours, dec_degrees,
                               magnitude, catalog, description, parent_planet, constellation
                        FROM moons
                        WHERE name ILIKE ? OR common_name ILIKE ? OR description ILIKE ?
                        LIMIT {per_type_limit}
                        UNION ALL
                        SELECT 'asterism' as object_type, name, NULL as common_name, ra_hours, dec_degrees,
                               NULL as magnitude, 'custom' as catalog, description, NULL as parent_planet, parent_constellation as constellation
                        FROM asterisms
                        WHERE name ILIKE ? OR alt_names ILIKE ? OR description ILIKE ?
                        LIMIT {per_type_limit}
                        UNION ALL
                        SELECT 'constellation' as object_type, name, common_name, ra_hours, dec_degrees,
                               NULL as magnitude, 'starplot' as catalog, NULL as description, NULL as parent_planet, NULL as constellation
                        FROM constellations
                        WHERE name ILIKE ? OR abbreviation ILIKE ? OR common_name ILIKE ?
                        LIMIT {per_type_limit}
                    ) LIMIT {limit}
                """
                custom_results = self.con.execute(
                    custom_query,
                    [
                        pattern,
                        pattern,
                        pattern,
                        pattern,
                        pattern,
                        pattern,
                        pattern,
                        pattern,
                        pattern,
                        pattern,
                        pattern,
                        pattern,
                    ],
                ).fetchdf()
            except Exception as e:
                logger.debug(f"Error executing custom search query: {e}", exc_info=True)
                custom_results = pd.DataFrame()

            # Search comets from starplot
            from starplot.models import Comet as StarplotComet

            matching_comets = []
            try:
                all_comets = StarplotComet.all()
                for comet in all_comets:
                    comet_name = comet.name if hasattr(comet, "name") and comet.name else ""
                    if query_lower in comet_name.lower():
                        matching_comets.append(comet)
                    if len(matching_comets) >= per_type_limit:
                        break

                if matching_comets:
                    comet_data = []
                    for comet in matching_comets:
                        comet_data.append(
                            {
                                "object_type": "star",  # Use STAR as closest match
                                "name": comet.name if hasattr(comet, "name") and comet.name else "Unknown",
                                "common_name": None,
                                "ra_hours": comet.ra / 15.0 if hasattr(comet, "ra") and comet.ra else 0.0,
                                "dec_degrees": comet.dec if hasattr(comet, "dec") and comet.dec else 0.0,
                                "magnitude": None,
                                "catalog": "starplot",
                                "description": "Comet",
                                "parent_planet": None,
                                "constellation": None,
                            }
                        )
                    comet_results = pd.DataFrame(comet_data)
                    if not custom_results.empty and not comet_results.empty:
                        # Ensure both DataFrames have the same columns in the same order to avoid FutureWarning
                        all_columns = sorted(set(custom_results.columns) | set(comet_results.columns))
                        for col in all_columns:
                            if col not in custom_results.columns:
                                custom_results[col] = None
                            if col not in comet_results.columns:
                                comet_results[col] = None
                        # Reorder columns to match
                        custom_results = custom_results[all_columns]
                        comet_results = comet_results[all_columns]
                        custom_results = pd.concat([custom_results, comet_results], ignore_index=True, sort=False)
                    elif not comet_results.empty:
                        custom_results = comet_results
                    # If both are empty, custom_results stays as is
            except Exception as e:
                logger.debug(f"Error querying comets from starplot: {e}")

            # Constellations are now included in custom_results from the DuckDB query above

        # Convert custom results
        for _, row in custom_results.iterrows():
            try:
                obj_type = CelestialObjectType(row["object_type"])
                results.append(self._row_to_celestial_object(row.to_dict(), obj_type))
            except Exception as e:
                logger.debug(f"Error converting custom result: {e}")

        # Search stars from parquet file (skip for very short queries)
        if not skip_stars:
            if not self._star_parquet_path or not self._star_parquet_path.exists():
                raise FileNotFoundError(
                    f"Star catalog parquet file not found at {self._star_parquet_path}. "
                    "Starplot data is required. Please ensure starplot is properly installed and configured."
                )
            # Attach the starplot database to access star_designations table
            self._ensure_starplot_db_attached()
            pattern = f"%{query_lower}%"

            # Try FTS first if available
            star_results = pd.DataFrame()
            if self._fts_available and self._fts_indexes_created:
                try:
                    # Check if stars_fts_table FTS index exists
                    # Use subquery to exclude score from final result
                    star_fts_query = """
                        SELECT
                            name,
                            common_name,
                            ra_hours,
                            dec_degrees,
                            magnitude,
                            'big_sky' as catalog,
                            NULL as description,
                            NULL as parent_planet,
                            constellation
                        FROM (
                            SELECT
                                name,
                                common_name,
                                ra_hours,
                                dec_degrees,
                                magnitude,
                                constellation,
                                fts_main_stars_fts_table.match_bm25(id, ?) as score
                            FROM stars_fts_table
                            WHERE score IS NOT NULL
                            ORDER BY score DESC, magnitude NULLS LAST
                            LIMIT ?
                        )
                    """
                    star_results = self.con.execute(star_fts_query, [query_lower, per_type_limit]).fetchdf()
                    logger.debug(f"FTS search for stars returned {len(star_results)} results")
                except Exception as e:
                    logger.debug(f"FTS search for stars failed, falling back to LIKE: {e}")

            # Fall back to LIKE if FTS didn't work or returned no results
            if star_results.empty:
                star_query = f"""
                    SELECT
                        COALESCE(NULLIF(sd.name, ''), NULLIF(sd.bayer, ''), CAST(s.hip AS VARCHAR), s.tyc_id) as name,
                        NULLIF(sd.name, '') as common_name,
                        s.ra_degrees / 15.0 as ra_hours,
                        s.dec_degrees,
                        s.magnitude,
                        'big_sky' as catalog,
                        NULL as description,
                        NULL as parent_planet,
                        s.constellation
                    FROM read_parquet(?) s
                    LEFT JOIN {self._starplot_db_alias}.star_designations sd ON s.hip = sd.hip
                    WHERE NULLIF(sd.name, '') ILIKE ?
                       OR NULLIF(sd.bayer, '') ILIKE ?
                       OR CAST(s.hip AS VARCHAR) ILIKE ?
                       OR s.tyc_id ILIKE ?
                    ORDER BY s.magnitude NULLS LAST
                    LIMIT ?
                """
                star_results = self.con.execute(
                    star_query, [str(self._star_parquet_path), pattern, pattern, pattern, pattern, per_type_limit]
                ).fetchdf()
            for _, row in star_results.iterrows():
                results.append(
                    CelestialObject(
                        name=str(row["name"]),
                        common_name=None,
                        ra_hours=float(row["ra_hours"]),
                        dec_degrees=float(row["dec_degrees"]),
                        magnitude=float(row["magnitude"]) if row.get("magnitude") is not None else None,
                        object_type=CelestialObjectType.STAR,
                        catalog=str(row["catalog"]),
                        description=None,
                        parent_planet=None,
                        constellation=str(row["constellation"]) if row.get("constellation") else None,
                    )
                )

        # Search DSOs from starplot database (skip for very short queries)
        if not skip_dsos:
            self._ensure_starplot_db_attached()
            pattern = f"%{query_lower}%"

            # Try FTS first if available
            dso_results = pd.DataFrame()
            if self._fts_available and self._fts_indexes_created:
                try:
                    # Check if dsos_fts_table FTS index exists
                    # Use subquery to exclude score from final result
                    dso_fts_query = """
                        SELECT
                            name,
                            NULL as common_name,
                            ra_hours,
                            dec_degrees,
                            magnitude,
                            CASE
                                WHEN type = 'G' THEN 'galaxy'
                                WHEN type IN ('Neb', 'PN', 'EmN', 'RfN', 'DrkN') THEN 'nebula'
                                WHEN type IN ('OCl', 'GCl') THEN 'cluster'
                                ELSE 'dso'
                            END as object_type,
                            'openngc' as catalog,
                            NULL as description,
                            NULL as parent_planet,
                            constellation
                        FROM (
                            SELECT
                                name,
                                ra_hours,
                                dec_degrees,
                                magnitude,
                                type,
                                constellation,
                                fts_main_dsos_fts_table.match_bm25(id, ?) as score
                            FROM dsos_fts_table
                            WHERE score IS NOT NULL
                            ORDER BY score DESC, magnitude NULLS LAST
                            LIMIT ?
                        )
                    """
                    dso_results = self.con.execute(dso_fts_query, [query_lower, per_type_limit]).fetchdf()
                    logger.debug(f"FTS search for DSOs returned {len(dso_results)} results")
                except Exception as e:
                    logger.debug(f"FTS search for DSOs failed, falling back to LIKE: {e}")

            # Fall back to LIKE if FTS didn't work or returned no results
            if dso_results.empty:
                dso_query_attached = f"""
                    SELECT
                        name,
                        NULL as common_name,
                        ra_degrees / 15.0 as ra_hours,
                        dec_degrees,
                        COALESCE(mag_v, mag_b) as magnitude,
                        CASE
                            WHEN type = 'G' THEN 'galaxy'
                            WHEN type IN ('Neb', 'PN', 'EmN', 'RfN', 'DrkN') THEN 'nebula'
                            WHEN type IN ('OCl', 'GCl') THEN 'cluster'
                            ELSE 'dso'
                        END as object_type,
                        'openngc' as catalog,
                        NULL as description,
                        NULL as parent_planet,
                        constellation
                    FROM {self._starplot_db_alias}.deep_sky_objects
                    WHERE name ILIKE ?
                    ORDER BY COALESCE(mag_v, mag_b) NULLS LAST
                    LIMIT ?
                """
                dso_results = self.con.execute(dso_query_attached, [pattern, per_type_limit]).fetchdf()
            for _, row in dso_results.iterrows():
                obj_type_str = str(row["object_type"])
                if obj_type_str == "galaxy":
                    obj_type = CelestialObjectType.GALAXY
                elif obj_type_str == "nebula":
                    obj_type = CelestialObjectType.NEBULA
                elif obj_type_str == "cluster":
                    obj_type = CelestialObjectType.CLUSTER
                else:
                    continue  # Skip unknown types

                results.append(
                    CelestialObject(
                        name=str(row["name"]),
                        common_name=None,
                        ra_hours=float(row["ra_hours"]),
                        dec_degrees=float(row["dec_degrees"]),
                        magnitude=float(row["magnitude"]) if row.get("magnitude") is not None else None,
                        object_type=obj_type,
                        catalog=str(row["catalog"]),
                        description=None,
                        parent_planet=None,
                        constellation=None,
                    )
                )

        # Sort by magnitude and limit
        results.sort(key=lambda x: (x.magnitude if x.magnitude is not None else float("inf"), x.name or ""))
        return results[:limit]

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
            is_dynamic: Filter dynamic objects (only applies to planets/moons)
            limit: Maximum results

        Returns:
            List of matching CelestialObject instances
        """
        results: list[CelestialObject] = []

        # Convert object_type to enum if string
        if isinstance(object_type, str):
            try:
                object_type = CelestialObjectType(object_type)
            except ValueError:
                object_type = None

        # Build WHERE clause
        where_clauses = []
        if catalog:
            escaped_catalog = catalog.replace("'", "''")
            where_clauses.append(f"catalog = '{escaped_catalog}'")
        if max_magnitude is not None:
            where_clauses.append(f"(magnitude <= {max_magnitude} OR magnitude IS NULL)")
        if min_magnitude is not None:
            where_clauses.append(f"magnitude >= {min_magnitude}")
        if constellation:
            escaped_constellation = constellation.replace("'", "''")
            where_clauses.append(f"constellation ILIKE '%{escaped_constellation}%'")

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        # Query custom data based on object_type
        if object_type is None or object_type in [
            CelestialObjectType.PLANET,
            CelestialObjectType.MOON,
            CelestialObjectType.ASTERISM,
            CelestialObjectType.CONSTELLATION,
        ]:
            queries = []

            if object_type is None or (object_type == CelestialObjectType.PLANET and is_dynamic is None) or is_dynamic:
                # Query planets from DuckDB table (seeded from starplot)
                planet_where = []
                if catalog and catalog != "starplot":
                    planet_where.append("1=0")  # No results if catalog doesn't match
                # Planets don't have fixed magnitude, so skip magnitude filters
                # Note: constellation filter for planets would require position calculation, so we skip it
                planet_where_sql = " AND ".join(planet_where) if planet_where else "1=1"

                queries.append(f"""
                    SELECT 'planet' as object_type, name, common_name, ra_hours, dec_degrees,
                           magnitude, catalog, description, NULL as parent_planet, constellation
                    FROM planets
                    WHERE {planet_where_sql}
                """)

            if object_type is None or (object_type == CelestialObjectType.MOON and is_dynamic is None) or is_dynamic:
                queries.append(f"""
                    SELECT 'moon' as object_type, name, common_name, ra_hours, dec_degrees,
                            magnitude, catalog, description, parent_planet, constellation
                    FROM moons
                    WHERE {where_sql}
                """)

            if object_type is None or object_type == CelestialObjectType.ASTERISM:
                # Build WHERE clause for asterisms (they don't have magnitude, catalog, or constellation columns)
                asterism_where = []
                if constellation:
                    # Use parent_constellation instead of constellation
                    escaped_constellation = constellation.replace("'", "''")
                    asterism_where.append(f"parent_constellation ILIKE '%{escaped_constellation}%'")
                # Skip magnitude and catalog filters for asterisms
                asterism_where_sql = " AND ".join(asterism_where) if asterism_where else "1=1"
                queries.append(f"""
                    SELECT 'asterism' as object_type, name, NULL as common_name, ra_hours, dec_degrees,
                           NULL as magnitude, 'custom' as catalog, description, NULL as parent_planet, parent_constellation as constellation
                    FROM asterisms
                    WHERE {asterism_where_sql}
                """)

            if object_type is None or object_type == CelestialObjectType.CONSTELLATION:
                # Query constellations from DuckDB table (seeded from starplot)
                const_where = []
                if catalog and catalog != "starplot":
                    const_where.append("1=0")  # No results if catalog doesn't match
                const_where_sql = " AND ".join(const_where) if const_where else "1=1"

                queries.append(f"""
                    SELECT 'constellation' as object_type, name, common_name, ra_hours, dec_degrees,
                           NULL as magnitude, 'starplot' as catalog, NULL as description, NULL as parent_planet, NULL as constellation
                    FROM constellations
                    WHERE {const_where_sql}
                """)

            if queries:
                custom_query = " UNION ALL ".join(queries) + f" ORDER BY magnitude NULLS LAST, name LIMIT {limit}"
                custom_results = self.con.execute(custom_query).fetchdf()
                for _, row in custom_results.iterrows():
                    try:
                        obj_type = CelestialObjectType(row["object_type"])
                        results.append(self._row_to_celestial_object(row.to_dict(), obj_type))
                    except Exception as e:
                        logger.debug(f"Error converting custom result: {e}")

        # Query stars from parquet if requested
        if object_type is None or object_type == CelestialObjectType.STAR:
            if not self._star_parquet_path or not self._star_parquet_path.exists():
                raise FileNotFoundError(
                    f"Star catalog parquet file not found at {self._star_parquet_path}. "
                    "Starplot data is required. Please ensure starplot is properly installed and configured."
                )
            star_where = []
            if max_magnitude is not None:
                star_where.append(f"(s.magnitude <= {max_magnitude} OR s.magnitude IS NULL)")
            if min_magnitude is not None:
                star_where.append(f"s.magnitude >= {min_magnitude}")
            if constellation:
                # Escape single quotes for SQL
                escaped_constellation = constellation.replace("'", "''")
                # Try to get constellation abbreviation from the constellations table
                # Starplot parquet files use 3-letter abbreviations (e.g., "And" for "Andromeda")
                # So we need to match both the full name and abbreviation
                constellation_filters = []
                try:
                    # Try exact match first, then case-insensitive match
                    abbrev_result = self.con.execute(
                        "SELECT abbreviation FROM constellations WHERE name = ? OR name ILIKE ? OR common_name ILIKE ? LIMIT 1",
                        [constellation, constellation, f"%{constellation}%"],
                    ).fetchone()
                    if abbrev_result:
                        abbrev = abbrev_result[0]
                        escaped_abbrev = abbrev.replace("'", "''")
                        # Match the abbreviation exactly (most likely format in parquet)
                        # Use = for exact match, which is faster and more accurate
                        constellation_filters.append(f"s.constellation = '{escaped_abbrev}'")
                        # Also try case-insensitive exact match
                        constellation_filters.append(f"s.constellation ILIKE '{escaped_abbrev}'")
                        # Also try matching the full name (in case parquet has full names)
                        constellation_filters.append(f"s.constellation ILIKE '%{escaped_constellation}%'")
                    else:
                        # Fallback: try to match the name directly
                        constellation_filters.append(f"s.constellation ILIKE '%{escaped_constellation}%'")
                        # Also try first 3 letters as abbreviation
                        if len(constellation) >= 3:
                            abbrev_guess = constellation[:3].upper()
                            constellation_filters.append(f"s.constellation ILIKE '{abbrev_guess}'")
                except Exception as e:
                    logger.debug(f"Error looking up constellation abbreviation for {constellation}: {e}")
                    # If lookup fails, try multiple approaches
                    constellation_filters.append(f"s.constellation ILIKE '%{escaped_constellation}%'")
                    if len(constellation) >= 3:
                        abbrev_guess = constellation[:3].upper()
                        constellation_filters.append(f"s.constellation ILIKE '{abbrev_guess}'")

                if constellation_filters:
                    star_where.append(f"({' OR '.join(constellation_filters)})")

            star_where_sql = " AND ".join(star_where) if star_where else "1=1"

            # Attach starplot database for star_designations if not already attached
            self._ensure_starplot_db_attached()

            star_query = f"""
                SELECT
                    star_name as name,
                    common_name,
                    ra_hours,
                    dec_degrees,
                    magnitude,
                    catalog,
                    description,
                    parent_planet,
                    constellation
                FROM (
                    SELECT
                        COALESCE(NULLIF(sd.name, ''), NULLIF(sd.bayer, ''), CAST(s.hip AS VARCHAR), s.tyc_id) as star_name,
                        NULLIF(sd.name, '') as common_name,
                        s.ra_degrees / 15.0 as ra_hours,
                        s.dec_degrees,
                        s.magnitude,
                        'big_sky' as catalog,
                        NULL as description,
                        NULL as parent_planet,
                        s.constellation
                    FROM read_parquet('{self._star_parquet_path}') s
                    LEFT JOIN starplot_db.star_designations sd ON s.hip = sd.hip
                    WHERE {star_where_sql}
                )
                ORDER BY magnitude NULLS LAST, star_name
                LIMIT {limit}
            """
            star_results = self.con.execute(star_query).fetchdf()
            for _, row in star_results.iterrows():
                results.append(
                    CelestialObject(
                        name=str(row["name"]),
                        common_name=None,
                        ra_hours=float(row["ra_hours"]),
                        dec_degrees=float(row["dec_degrees"]),
                        magnitude=float(row["magnitude"]) if row.get("magnitude") is not None else None,
                        object_type=CelestialObjectType.STAR,
                        catalog=str(row["catalog"]),
                        description=None,
                        parent_planet=None,
                        constellation=str(row["constellation"]) if row.get("constellation") else None,
                    )
                )

        # Query DSOs if requested
        dso_types = [CelestialObjectType.GALAXY, CelestialObjectType.NEBULA, CelestialObjectType.CLUSTER]
        if object_type is None or object_type in dso_types:
            if not self._dso_db_path or not self._dso_db_path.exists():
                raise FileNotFoundError(
                    f"DSO database not found at {self._dso_db_path}. "
                    "Starplot data is required. Please ensure starplot is properly installed and configured."
                )
            dso_where = []
            if max_magnitude is not None:
                dso_where.append(f"(COALESCE(mag_v, mag_b) <= {max_magnitude} OR (mag_v IS NULL AND mag_b IS NULL))")
            if min_magnitude is not None:
                dso_where.append(f"COALESCE(mag_v, mag_b) >= {min_magnitude}")

            # Filter by DSO type
            if object_type == CelestialObjectType.GALAXY:
                dso_where.append("type = 'G'")
            elif object_type == CelestialObjectType.NEBULA:
                dso_where.append("type IN ('Neb', 'PN', 'EmN', 'RfN', 'DrkN')")
            elif object_type == CelestialObjectType.CLUSTER:
                dso_where.append("type IN ('OCl', 'GCl')")

            dso_where_sql = " AND ".join(dso_where) if dso_where else "1=1"

            # Attach DSO database
            self._ensure_starplot_db_attached()
            dso_query = f"""
                SELECT
                    name,
                    NULL as common_name,
                    ra_degrees / 15.0 as ra_hours,
                    dec_degrees,
                    COALESCE(mag_v, mag_b) as magnitude,
                    CASE
                        WHEN type = 'G' THEN 'galaxy'
                        WHEN type IN ('Neb', 'PN', 'EmN', 'RfN', 'DrkN') THEN 'nebula'
                        WHEN type IN ('OCl', 'GCl') THEN 'cluster'
                        ELSE 'dso'
                    END as object_type,
                    'openngc' as catalog,
                    NULL as description,
                    NULL as parent_planet,
                    constellation
                FROM {self._starplot_db_alias}.deep_sky_objects
                WHERE {dso_where_sql}
                ORDER BY COALESCE(mag_v, mag_b) NULLS LAST, name
                LIMIT {limit}
            """
            dso_results = self.con.execute(dso_query).fetchdf()
            for _, row in dso_results.iterrows():
                obj_type_str = str(row["object_type"])
                if obj_type_str == "galaxy":
                    obj_type = CelestialObjectType.GALAXY
                elif obj_type_str == "nebula":
                    obj_type = CelestialObjectType.NEBULA
                elif obj_type_str == "cluster":
                    obj_type = CelestialObjectType.CLUSTER
                else:
                    continue

                results.append(
                    CelestialObject(
                        name=str(row["name"]),
                        common_name=None,
                        ra_hours=float(row["ra_hours"]),
                        dec_degrees=float(row["dec_degrees"]),
                        magnitude=float(row["magnitude"]) if row.get("magnitude") is not None else None,
                        object_type=obj_type,
                        catalog=str(row["catalog"]),
                        description=None,
                        parent_planet=None,
                        constellation=None,
                    )
                )

        # Sort and limit final results
        results.sort(key=lambda x: (x.magnitude if x.magnitude is not None else float("inf"), x.name or ""))
        return results[:limit]

    async def get_by_name(self, name: str) -> CelestialObject | None:
        """
        Get a single object by exact name match.

        Args:
            name: Object name

        Returns:
            CelestialObject if found, None otherwise
        """
        # Search planets from DuckDB table first
        try:
            planet_query = """
                SELECT name, common_name, ra_hours, dec_degrees, magnitude, catalog, description, parent_planet, constellation
                FROM planets
                WHERE name = ?
                LIMIT 1
            """
            planet_result = self.con.execute(planet_query, [name]).fetchdf()
            if not planet_result.empty:
                row = planet_result.iloc[0]
                return self._row_to_celestial_object(row.to_dict(), CelestialObjectType.PLANET)
        except Exception as e:
            logger.debug(f"Error querying planet from DuckDB: {e}")

        # Search Moon from starplot
        try:
            from starplot.models import Moon

            if name.lower() in ("moon", "luna"):
                moon = Moon.get()
                if moon:
                    return CelestialObject(
                        name="Moon",
                        common_name="Luna",
                        ra_hours=moon.ra / 15.0 if hasattr(moon, "ra") and moon.ra else 0.0,
                        dec_degrees=moon.dec if hasattr(moon, "dec") and moon.dec else 0.0,
                        magnitude=None,
                        object_type=CelestialObjectType.MOON,
                        catalog="starplot",
                        description=None,
                        parent_planet="Earth",
                        constellation=None,
                    )
        except Exception:
            pass

        # Search custom moons (planet moons - starplot doesn't have these yet, coming in 0.19+)
        moon_query = """
            SELECT 'moon' as object_type, name, common_name, ra_hours, dec_degrees,
                   magnitude, catalog, description, parent_planet, constellation
            FROM moons
            WHERE name = ?
            LIMIT 1
        """
        moon_result = self.con.execute(moon_query, [name]).fetchdf()
        if not moon_result.empty:
            row = moon_result.iloc[0]
            return self._row_to_celestial_object(row.to_dict(), CelestialObjectType.MOON)

        # Search asterisms (custom data)
        asterism_query = """
            SELECT 'asterism' as object_type, name, NULL as common_name, ra_hours, dec_degrees,
                   NULL as magnitude, 'custom' as catalog, description, NULL as parent_planet, parent_constellation as constellation
            FROM asterisms
            WHERE name = ?
            LIMIT 1
        """
        asterism_result = self.con.execute(asterism_query, [name]).fetchdf()
        if not asterism_result.empty:
            row = asterism_result.iloc[0]
            return self._row_to_celestial_object(row.to_dict(), CelestialObjectType.ASTERISM)

        # Search stars using parameterized query
        if not self._star_parquet_path or not self._star_parquet_path.exists():
            raise FileNotFoundError(
                f"Star catalog parquet file not found at {self._star_parquet_path}. "
                "Starplot data is required. Please ensure starplot is properly installed and configured."
            )
        # Attach starplot database for star_designations if not already attached
        self._ensure_starplot_db_attached()

        star_query = f"""
            SELECT
                COALESCE(NULLIF(sd.name, ''), NULLIF(sd.bayer, ''), CAST(s.hip AS VARCHAR), s.tyc_id) as name,
                NULLIF(sd.name, '') as common_name,
                s.ra_degrees / 15.0 as ra_hours,
                s.dec_degrees,
                s.magnitude,
                'big_sky' as catalog
            FROM read_parquet(?) s
            LEFT JOIN {self._starplot_db_alias}.star_designations sd ON s.hip = sd.hip
            WHERE NULLIF(sd.name, '') = ?
               OR NULLIF(sd.bayer, '') = ?
               OR CAST(s.hip AS VARCHAR) = ?
               OR s.tyc_id = ?
            LIMIT 1
        """
        star_result = self.con.execute(star_query, [str(self._star_parquet_path), name, name, name, name]).fetchdf()
        if not star_result.empty:
            row = star_result.iloc[0]
            return CelestialObject(
                name=str(row["name"]),
                common_name=None,
                ra_hours=float(row["ra_hours"]),
                dec_degrees=float(row["dec_degrees"]),
                magnitude=float(row["magnitude"]) if row.get("magnitude") is not None else None,
                object_type=CelestialObjectType.STAR,
                catalog=str(row["catalog"]),
                description=None,
                parent_planet=None,
                constellation=None,
            )

        # Search comets from starplot
        try:
            from starplot.models import Comet as StarplotComet

            comet = StarplotComet.get(name=name)
            if comet:
                return CelestialObject(
                    name=comet.name if hasattr(comet, "name") and comet.name else name,
                    common_name=None,
                    ra_hours=comet.ra / 15.0 if hasattr(comet, "ra") and comet.ra else 0.0,
                    dec_degrees=comet.dec if hasattr(comet, "dec") and comet.dec else 0.0,
                    magnitude=None,  # Comets don't have fixed magnitude
                    object_type=CelestialObjectType.STAR,  # Use STAR as closest match, or we could add COMET type
                    catalog="starplot",
                    description="Comet",
                    parent_planet=None,
                    constellation=None,
                )
        except Exception:
            pass

        # Search constellations from DuckDB table
        try:
            const_query = """
                SELECT name, common_name, ra_hours, dec_degrees
                FROM constellations
                WHERE name = ? OR abbreviation = ? OR common_name = ?
                LIMIT 1
            """
            const_result = self.con.execute(const_query, [name, name, name]).fetchdf()
            if not const_result.empty:
                row = const_result.iloc[0]
                return CelestialObject(
                    name=str(row["name"]),
                    common_name=str(row["common_name"]) if row.get("common_name") else None,
                    ra_hours=float(row["ra_hours"]),
                    dec_degrees=float(row["dec_degrees"]),
                    magnitude=None,
                    object_type=CelestialObjectType.CONSTELLATION,
                    catalog="starplot",
                    description=None,
                    parent_planet=None,
                    constellation=None,
                )
        except Exception as e:
            logger.debug(f"Error querying constellation from DuckDB: {e}")

        # Search DSOs using parameterized query
        if not self._dso_db_path or not self._dso_db_path.exists():
            raise FileNotFoundError(
                f"DSO database not found at {self._dso_db_path}. "
                "Starplot data is required. Please ensure starplot is properly installed and configured."
            )
        # Attach DSO database
        self._ensure_starplot_db_attached()
        dso_query = f"""
            SELECT
                name,
                ra_degrees / 15.0 as ra_hours,
                dec_degrees,
                COALESCE(mag_v, mag_b) as magnitude,
                CASE
                    WHEN type = 'G' THEN 'galaxy'
                    WHEN type IN ('Neb', 'PN', 'EmN', 'RfN', 'DrkN') THEN 'nebula'
                    WHEN type IN ('OCl', 'GCl') THEN 'cluster'
                    ELSE 'dso'
                END as object_type,
                'openngc' as catalog,
                NULL as common_name,
                NULL as description,
                NULL as parent_planet,
                constellation
            FROM {self._starplot_db_alias}.deep_sky_objects
            WHERE name = ?
            LIMIT 1
        """
        dso_result = self.con.execute(dso_query, [name]).fetchdf()
        if not dso_result.empty:
            row = dso_result.iloc[0]
            obj_type_str = str(row["object_type"])
            if obj_type_str == "galaxy":
                obj_type = CelestialObjectType.GALAXY
            elif obj_type_str == "nebula":
                obj_type = CelestialObjectType.NEBULA
            elif obj_type_str == "cluster":
                obj_type = CelestialObjectType.CLUSTER
            else:
                return None

            return CelestialObject(
                name=str(row["name"]),
                common_name=None,
                ra_hours=float(row["ra_hours"]),
                dec_degrees=float(row["dec_degrees"]),
                magnitude=float(row["magnitude"]) if row.get("magnitude") is not None else None,
                object_type=obj_type,
                catalog=str(row["catalog"]),
                description=None,
                parent_planet=None,
                constellation=None,
            )

        return None

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
        from celestron_nexstar.api.core.utils import angular_separation

        # Convert radius from arcminutes to degrees
        radius_deg = radius_arcmin / 60.0

        # Approximate bounding box for initial filtering
        cos_dec = abs(max(0.1, abs(dec_degrees)))
        ra_range_deg = radius_deg / cos_dec if cos_dec > 0.1 else radius_deg
        ra_range_hours = ra_range_deg / 15.0

        ra_min = (ra_hours - ra_range_hours) % 24.0
        ra_max = (ra_hours + ra_range_hours) % 24.0
        dec_min = max(-90.0, dec_degrees - radius_deg)
        dec_max = min(90.0, dec_degrees + radius_deg)

        all_results: list[tuple[CelestialObject, float]] = []

        # Search custom data (moons, asterisms) - planets and constellations come from starplot
        if ra_min <= ra_max:
            coord_query = """
                SELECT 'moon' as object_type, name, common_name, ra_hours, dec_degrees,
                       magnitude, catalog, description, parent_planet, constellation
                FROM moons
                WHERE ra_hours BETWEEN ? AND ? AND dec_degrees BETWEEN ? AND ?
                UNION ALL
                SELECT 'asterism' as object_type, name, NULL as common_name, ra_hours, dec_degrees,
                       NULL as magnitude, 'custom' as catalog, description, NULL as parent_planet, parent_constellation as constellation
                FROM asterisms
                WHERE ra_hours BETWEEN ? AND ? AND dec_degrees BETWEEN ? AND ?
                LIMIT ?
            """
            coord_results = self.con.execute(
                coord_query,
                [ra_min, ra_max, dec_min, dec_max] * 2 + [limit * 5],  # 2 tables, get more candidates
            ).fetchdf()
        else:
            # Handle RA wrap-around
            coord_query = """
                SELECT 'moon' as object_type, name, common_name, ra_hours, dec_degrees,
                       magnitude, catalog, description, parent_planet, constellation
                FROM moons
                WHERE (ra_hours >= ? OR ra_hours <= ?) AND dec_degrees BETWEEN ? AND ?
                UNION ALL
                SELECT 'asterism' as object_type, name, NULL as common_name, ra_hours, dec_degrees,
                       NULL as magnitude, 'custom' as catalog, description, NULL as parent_planet, parent_constellation as constellation
                FROM asterisms
                WHERE (ra_hours >= ? OR ra_hours <= ?) AND dec_degrees BETWEEN ? AND ?
                LIMIT ?
            """
            coord_results = self.con.execute(
                coord_query,
                [ra_min, ra_max, dec_min, dec_max] * 2 + [limit * 5],
            ).fetchdf()

        # Search planets from DuckDB table (seeded from starplot)
        try:
            planet_ra_where = (
                f"(ra_hours >= {ra_min} AND ra_hours <= {ra_max})"
                if ra_min <= ra_max
                else f"(ra_hours >= {ra_min} OR ra_hours <= {ra_max})"
            )
            planet_coord_query = f"""
                SELECT name, common_name, ra_hours, dec_degrees, magnitude, catalog, description, parent_planet, constellation
                FROM planets
                WHERE {planet_ra_where} AND dec_degrees >= {dec_min} AND dec_degrees <= {dec_max}
            """
            planet_coord_results = self.con.execute(planet_coord_query).fetchdf()
            for _, row in planet_coord_results.iterrows():
                planet_ra = float(row["ra_hours"])
                planet_dec = float(row["dec_degrees"])
                separation_deg = angular_separation(ra_hours, dec_degrees, planet_ra, planet_dec)
                separation_arcmin = separation_deg * 60.0
                if separation_arcmin <= radius_arcmin:
                    all_results.append(
                        (
                            CelestialObject(
                                name=str(row["name"]),
                                common_name=str(row["common_name"]) if row.get("common_name") else None,
                                ra_hours=planet_ra,
                                dec_degrees=planet_dec,
                                magnitude=float(row["magnitude"]) if row.get("magnitude") is not None else None,
                                object_type=CelestialObjectType.PLANET,
                                catalog=str(row["catalog"]),
                                description=str(row["description"]) if row.get("description") else None,
                                parent_planet=str(row["parent_planet"]) if row.get("parent_planet") else None,
                                constellation=str(row["constellation"]) if row.get("constellation") else None,
                            ),
                            separation_arcmin,
                        )
                    )
        except Exception as e:
            logger.debug(f"Error querying planets from DuckDB in coordinate search: {e}")

        # Search constellations from DuckDB table (seeded from starplot)
        try:
            const_ra_where = (
                f"(ra_hours >= {ra_min} AND ra_hours <= {ra_max})"
                if ra_min <= ra_max
                else f"(ra_hours >= {ra_min} OR ra_hours <= {ra_max})"
            )
            const_coord_query = f"""
                SELECT name, common_name, ra_hours, dec_degrees
                FROM constellations
                WHERE {const_ra_where} AND dec_degrees >= {dec_min} AND dec_degrees <= {dec_max}
            """
            const_coord_results = self.con.execute(const_coord_query).fetchdf()
            for _, row in const_coord_results.iterrows():
                const_ra = float(row["ra_hours"])
                const_dec = float(row["dec_degrees"])
                separation_deg = angular_separation(ra_hours, dec_degrees, const_ra, const_dec)
                separation_arcmin = separation_deg * 60.0
                if separation_arcmin <= radius_arcmin:
                    all_results.append(
                        (
                            CelestialObject(
                                name=str(row["name"]),
                                common_name=str(row["common_name"]) if row.get("common_name") else None,
                                ra_hours=const_ra,
                                dec_degrees=const_dec,
                                magnitude=None,
                                object_type=CelestialObjectType.CONSTELLATION,
                                catalog="starplot",
                                description=None,
                                parent_planet=None,
                                constellation=None,
                            ),
                            separation_arcmin,
                        )
                    )
        except Exception as e:
            logger.debug(f"Error querying constellations from DuckDB in coordinate search: {e}")

        # Calculate accurate angular separation
        for _, row in coord_results.iterrows():
            try:
                obj_type = CelestialObjectType(row["object_type"])
                obj = self._row_to_celestial_object(row.to_dict(), obj_type)
                separation_deg = angular_separation(ra_hours, dec_degrees, obj.ra_hours, obj.dec_degrees)
                separation_arcmin = separation_deg * 60.0

                if separation_arcmin <= radius_arcmin:
                    all_results.append((obj, separation_arcmin))
            except Exception as e:
                logger.debug(f"Error processing coordinate result: {e}")

        # Search stars from parquet
        if not self._star_parquet_path or not self._star_parquet_path.exists():
            raise FileNotFoundError(
                f"Star catalog parquet file not found at {self._star_parquet_path}. "
                "Starplot data is required. Please ensure starplot is properly installed and configured."
            )
        ra_hours * 15.0
        ra_min_deg = ra_min * 15.0
        ra_max_deg = ra_max * 15.0

        if ra_min <= ra_max:
            star_coord_query = """
                SELECT
                    COALESCE(name, CAST(hip AS VARCHAR), CAST(tyc_id AS VARCHAR)) as name,
                    NULL as common_name,
                    ra_degrees / 15.0 as ra_hours,
                    dec_degrees,
                    magnitude,
                    'big_sky' as catalog
                FROM read_parquet(?)
                WHERE ra_degrees BETWEEN ? AND ? AND dec_degrees BETWEEN ? AND ?
                LIMIT ?
            """
            star_coord_results = self.con.execute(
                star_coord_query,
                [str(self._star_parquet_path), ra_min_deg, ra_max_deg, dec_min, dec_max, limit * 5],
            ).fetchdf()
        else:
            star_coord_query = """
                SELECT
                    COALESCE(name, CAST(hip AS VARCHAR), CAST(tyc_id AS VARCHAR)) as name,
                    NULL as common_name,
                    ra_degrees / 15.0 as ra_hours,
                    dec_degrees,
                    magnitude,
                    'big_sky' as catalog
                FROM read_parquet(?)
                WHERE (ra_degrees >= ? OR ra_degrees <= ?) AND dec_degrees BETWEEN ? AND ?
                LIMIT ?
            """
            star_coord_results = self.con.execute(
                star_coord_query,
                [str(self._star_parquet_path), ra_min_deg, ra_max_deg, dec_min, dec_max, limit * 5],
            ).fetchdf()

        for _, row in star_coord_results.iterrows():
            obj = CelestialObject(
                name=str(row["name"]),
                common_name=None,
                ra_hours=float(row["ra_hours"]),
                dec_degrees=float(row["dec_degrees"]),
                magnitude=float(row["magnitude"]) if row.get("magnitude") is not None else None,
                object_type=CelestialObjectType.STAR,
                catalog=str(row["catalog"]),
                description=None,
                parent_planet=None,
                constellation=None,
            )
            separation_deg = angular_separation(ra_hours, dec_degrees, obj.ra_hours, obj.dec_degrees)
            separation_arcmin = separation_deg * 60.0

            if separation_arcmin <= radius_arcmin:
                all_results.append((obj, separation_arcmin))

        # Sort by angular separation
        all_results.sort(key=lambda x: x[1])
        return all_results[:limit]

    async def get_by_catalog(self, catalog: str, limit: int = 1000) -> list[CelestialObject]:
        """
        Get all objects from a specific catalog.

        Args:
            catalog: Catalog name
            limit: Maximum results

        Returns:
            List of CelestialObject instances
        """
        results: list[CelestialObject] = []

        # Handle starplot catalogs - query from DuckDB tables
        if catalog.lower() in ("starplot", "planets"):
            try:
                planet_catalog_query = """
                    SELECT 'planet' as object_type, name, common_name, ra_hours, dec_degrees,
                           magnitude, catalog, description, NULL as parent_planet, constellation
                    FROM planets
                    ORDER BY name
                    LIMIT ?
                """
                planet_catalog_results = self.con.execute(planet_catalog_query, [limit]).fetchdf()
                for _, row in planet_catalog_results.iterrows():
                    results.append(self._row_to_celestial_object(row.to_dict(), CelestialObjectType.PLANET))
            except Exception as e:
                logger.debug(f"Error querying planets from DuckDB: {e}")

        if catalog.lower() in ("starplot", "constellations"):
            try:
                const_catalog_query = """
                    SELECT 'constellation' as object_type, name, common_name, ra_hours, dec_degrees,
                           NULL as magnitude, 'starplot' as catalog, NULL as description, NULL as parent_planet, NULL as constellation
                    FROM constellations
                    ORDER BY name
                    LIMIT ?
                """
                const_catalog_results = self.con.execute(const_catalog_query, [limit]).fetchdf()
                for _, row in const_catalog_results.iterrows():
                    results.append(self._row_to_celestial_object(row.to_dict(), CelestialObjectType.CONSTELLATION))
            except Exception as e:
                logger.debug(f"Error querying constellations from DuckDB: {e}")

        # Query custom data (moons, asterisms)
        # Note: asterisms don't have a catalog column, so only include them if catalog is 'custom' or None
        if catalog == "custom" or catalog is None:
            catalog_query = """
                SELECT 'moon' as object_type, name, common_name, ra_hours, dec_degrees,
                       magnitude, catalog, description, parent_planet, constellation
                FROM moons
                WHERE catalog = ?
                UNION ALL
                SELECT 'asterism' as object_type, name, NULL as common_name, ra_hours, dec_degrees,
                       NULL as magnitude, 'custom' as catalog, description, NULL as parent_planet, parent_constellation as constellation
                FROM asterisms
                ORDER BY name
                LIMIT ?
            """
            catalog_results = self.con.execute(catalog_query, [catalog, limit]).fetchdf()
        else:
            # Only query moons if catalog is specified and not 'custom'
            catalog_query = """
                SELECT 'moon' as object_type, name, common_name, ra_hours, dec_degrees,
                       magnitude, catalog, description, parent_planet, constellation
                FROM moons
                WHERE catalog = ?
                ORDER BY name
                LIMIT ?
            """
            catalog_results = self.con.execute(catalog_query, [catalog, limit]).fetchdf()

        for _, row in catalog_results.iterrows():
            try:
                obj_type = CelestialObjectType(row["object_type"])
                results.append(self._row_to_celestial_object(row.to_dict(), obj_type))
            except Exception as e:
                logger.debug(f"Error converting catalog result: {e}")

        # Query stars if catalog matches
        if catalog.lower() in ("big_sky", "bigsky", "stars") and self._star_parquet_path:
            try:
                star_catalog_query = """
                    SELECT
                        COALESCE(name, CAST(hip AS VARCHAR), CAST(tyc_id AS VARCHAR)) as name,
                        NULL as common_name,
                        ra_degrees / 15.0 as ra_hours,
                        dec_degrees,
                        magnitude,
                        'big_sky' as catalog
                    FROM read_parquet(?)
                    ORDER BY magnitude NULLS LAST, name
                    LIMIT ?
                """
                star_catalog_results = self.con.execute(
                    star_catalog_query, [str(self._star_parquet_path), limit]
                ).fetchdf()
                for _, row in star_catalog_results.iterrows():
                    try:
                        results.append(
                            CelestialObject(
                                name=str(row["name"]),
                                common_name=None,
                                ra_hours=float(row["ra_hours"]),
                                dec_degrees=float(row["dec_degrees"]),
                                magnitude=float(row["magnitude"]) if row.get("magnitude") is not None else None,
                                object_type=CelestialObjectType.STAR,
                                catalog=str(row["catalog"]),
                                description=None,
                                parent_planet=None,
                                constellation=None,
                            )
                        )
                    except Exception as e:
                        logger.debug(f"Error converting star catalog result: {e}")
            except Exception as e:
                logger.warning(f"Error querying star parquet for catalog: {e}")

        # Query DSOs if catalog matches
        if catalog.lower() in ("openngc", "ngc", "messier", "m") and self._dso_db_path:
            try:
                self._ensure_starplot_db_attached()
                dso_catalog_query = f"""
                    SELECT
                        name,
                        NULL as common_name,
                        ra_degrees / 15.0 as ra_hours,
                        dec_degrees,
                        COALESCE(mag_v, mag_b) as magnitude,
                        CASE
                            WHEN type = 'G' THEN 'galaxy'
                            WHEN type IN ('Neb', 'PN', 'EmN', 'RfN', 'DrkN') THEN 'nebula'
                            WHEN type IN ('OCl', 'GCl') THEN 'cluster'
                            ELSE 'dso'
                        END as object_type,
                        'openngc' as catalog,
                        NULL as description,
                        NULL as parent_planet,
                        constellation
                    FROM {self._starplot_db_alias}.deep_sky_objects
                    ORDER BY COALESCE(mag_v, mag_b) NULLS LAST, name
                    LIMIT ?
                """
                dso_catalog_results = self.con.execute(dso_catalog_query, [limit]).fetchdf()
                for _, row in dso_catalog_results.iterrows():
                    try:
                        obj_type_str = str(row["object_type"])
                        if obj_type_str == "galaxy":
                            obj_type = CelestialObjectType.GALAXY
                        elif obj_type_str == "nebula":
                            obj_type = CelestialObjectType.NEBULA
                        elif obj_type_str == "cluster":
                            obj_type = CelestialObjectType.CLUSTER
                        else:
                            continue

                        results.append(
                            CelestialObject(
                                name=str(row["name"]),
                                common_name=None,
                                ra_hours=float(row["ra_hours"]),
                                dec_degrees=float(row["dec_degrees"]),
                                magnitude=float(row["magnitude"]) if row.get("magnitude") is not None else None,
                                object_type=obj_type,
                                catalog=str(row["catalog"]),
                                description=None,
                                parent_planet=None,
                                constellation=None,
                            )
                        )
                    except Exception as e:
                        logger.debug(f"Error converting DSO catalog result: {e}")
            except Exception as e:
                logger.warning(f"Error querying DSO database for catalog: {e}")

        return results[:limit]

    async def get_moons_by_parent_planet(self, planet_name: str) -> list[CelestialObject]:
        """
        Get all moons for a given parent planet.

        Args:
            planet_name: Name of the parent planet

        Returns:
            List of moon CelestialObject instances
        """
        moon_query = """
            SELECT 'moon' as object_type, name, common_name, ra_hours, dec_degrees,
                   magnitude, catalog, description, parent_planet, constellation
            FROM moons
            WHERE parent_planet = ?
            ORDER BY name
        """
        moon_results = self.con.execute(moon_query, [planet_name]).fetchdf()

        results: list[CelestialObject] = []
        for _, row in moon_results.iterrows():
            try:
                results.append(self._row_to_celestial_object(row.to_dict(), CelestialObjectType.MOON))
            except Exception as e:
                logger.debug(f"Error converting moon result: {e}")

        return results

    def close(self) -> None:
        """Close database connection."""
        if self.con:
            self.con.close()

    def __enter__(self) -> DuckDBCatalogDatabase:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()

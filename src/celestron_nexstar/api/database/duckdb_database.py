"""
High-performance DuckDB-based catalog database.

Uses DuckDB native API for maximum performance, queries starplot's parquet files directly,
and stores only custom data (planets, moons, asterisms, constellations) in the database.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from celestron_nexstar.api.catalogs.catalogs import CelestialObject
from celestron_nexstar.api.core.enums import CelestialObjectType
from celestron_nexstar.api.data.starplot_config import get_starplot_data_directory
from celestron_nexstar.api.database.duckdb_migrations import run_migrations

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

        # Initialize DuckDB connection
        self.con = duckdb.connect(str(self.db_path))

        # Configure for performance
        self.con.execute("SET threads TO 4")  # Use multiple threads
        self.con.execute("SET memory_limit = '2GB'")  # Allow more memory for queries

        # Load fts extension for full-text search
        try:
            self.con.execute("INSTALL fts;")
            self.con.execute("LOAD fts;")
            self._fts_available = True
            logger.debug("Loaded fts extension for full-text search")
        except Exception as e:
            self._fts_available = False
            logger.warning(f"Could not load fts extension: {e}. Falling back to LIKE queries.")

        # Run migrations to ensure schema is up to date
        run_migrations(self.con)

        # Cache parquet file paths
        self._star_parquet_path = self._find_star_parquet_file()
        self._dso_db_path = self._find_dso_database()

    def _get_default_db_path(self) -> Path:
        """Get path to DuckDB database file in user config directory."""
        config_dir = Path.home() / ".config" / "celestron-nexstar"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "catalogs.duckdb"

    def _find_star_parquet_file(self) -> Path | None:
        """Find starplot's star parquet file."""
        # Check for abridged version first (included with starplot)
        try:
            import starplot
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
            import starplot
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
        query_lower = query.lower()
        results: list[CelestialObject] = []

        # Search custom data (planets, moons, asterisms, constellations)
        # Use FTS if available, otherwise LIKE
        if self._fts_available:
            try:
                # Use FTS with parameterized query
                custom_query = """
                    SELECT 'planet' as object_type, name, common_name, ra_hours, dec_degrees, 
                           magnitude, catalog, description, NULL as parent_planet, constellation
                    FROM planets
                    WHERE fts_main_match(name || ' ' || COALESCE(common_name, '') || ' ' || COALESCE(description, ''), ?)
                    UNION ALL
                    SELECT 'moon' as object_type, name, common_name, ra_hours, dec_degrees,
                           magnitude, catalog, description, parent_planet, constellation
                    FROM moons
                    WHERE fts_main_match(name || ' ' || COALESCE(common_name, '') || ' ' || COALESCE(description, ''), ?)
                    UNION ALL
                    SELECT 'asterism' as object_type, name, common_name, ra_hours, dec_degrees,
                           NULL as magnitude, catalog, description, NULL as parent_planet, constellation
                    FROM asterisms
                    WHERE fts_main_match(name || ' ' || COALESCE(common_name, '') || ' ' || COALESCE(description, ''), ?)
                    LIMIT ?
                """
                custom_results = self.con.execute(custom_query, [query, query, query, limit]).fetchdf()

                # Search constellations from starplot using Constellation model
                from starplot.models import Constellation

                # Get all constellations and filter by query
                all_constellations = Constellation.all()
                matching_constellations = []
                for c in all_constellations:
                    # Check name (substring match)
                    if query_lower in c.name.lower():
                        matching_constellations.append(c)
                        continue
                    # Check IAU ID if available
                    if hasattr(c, 'iau_id') and c.iau_id and query_lower in str(c.iau_id).lower():
                        matching_constellations.append(c)
                        continue
                    # Check abbreviation if available
                    if hasattr(c, 'abbreviation') and c.abbreviation and query_lower in str(c.abbreviation).lower():
                        matching_constellations.append(c)
                        continue
                    # Check common_name if available
                    if hasattr(c, 'common_name') and c.common_name and query_lower in str(c.common_name).lower():
                        matching_constellations.append(c)
                        continue
                    if len(matching_constellations) >= limit:
                        break

                if matching_constellations:
                    import pandas as pd
                    constellation_data = []
                    for const in matching_constellations:
                        # Get RA/Dec from constellation
                        ra_hours = None
                        dec_degrees = None
                        if hasattr(const, 'ra') and const.ra is not None:
                            ra_hours = const.ra / 15.0 if const.ra > 24 else const.ra
                        if hasattr(const, 'dec') and const.dec is not None:
                            dec_degrees = const.dec

                        constellation_data.append({
                            'object_type': 'constellation',
                            'name': const.name,
                            'common_name': None,
                            'ra_hours': ra_hours,
                            'dec_degrees': dec_degrees,
                            'magnitude': None,
                            'catalog': 'starplot',
                            'description': None,
                            'parent_planet': None,
                            'constellation': None,
                        })
                    constellation_results = pd.DataFrame(constellation_data)
                    logger.debug(f"Found {len(matching_constellations)} constellations from starplot")

                    # Combine results
                    if not custom_results.empty:
                        custom_results = pd.concat([custom_results, constellation_results], ignore_index=True)
                    else:
                        custom_results = constellation_results
            except Exception as e:
                logger.debug(f"FTS search failed, falling back to LIKE: {e}")
                self._fts_available = False  # Disable FTS for future queries
                # Fall through to LIKE queries

        if not self._fts_available:
            # Use LIKE queries with parameterized queries
            # Note: Constellations are queried from starplot if available
            custom_query = """
                SELECT 'planet' as object_type, name, common_name, ra_hours, dec_degrees,
                       magnitude, catalog, description, NULL as parent_planet, constellation
                FROM planets
                WHERE name ILIKE ? 
                   OR common_name ILIKE ?
                   OR description ILIKE ?
                UNION ALL
                SELECT 'moon' as object_type, name, common_name, ra_hours, dec_degrees,
                       magnitude, catalog, description, parent_planet, constellation
                FROM moons
                WHERE name ILIKE ?
                   OR common_name ILIKE ?
                   OR description ILIKE ?
                UNION ALL
                SELECT 'asterism' as object_type, name, common_name, ra_hours, dec_degrees,
                       NULL as magnitude, catalog, description, NULL as parent_planet, constellation
                FROM asterisms
                WHERE name ILIKE ?
                   OR common_name ILIKE ?
                   OR description ILIKE ?
                LIMIT ?
            """
            pattern = f"%{query_lower}%"
            custom_results = self.con.execute(
                custom_query,
                [pattern] * 9 + [limit],  # 9 patterns (3 per table * 3 tables)
            ).fetchdf()

            # Search constellations from starplot using Constellation model
            from starplot.models import Constellation

            # Get all constellations and filter by query
            all_constellations = Constellation.all()
            matching_constellations = []
            for c in all_constellations:
                # Check name (substring match)
                if query_lower in c.name.lower():
                    matching_constellations.append(c)
                    continue
                # Check IAU ID if available
                if hasattr(c, 'iau_id') and c.iau_id and query_lower in str(c.iau_id).lower():
                    matching_constellations.append(c)
                    continue
                # Check abbreviation if available
                if hasattr(c, 'abbreviation') and c.abbreviation and query_lower in str(c.abbreviation).lower():
                    matching_constellations.append(c)
                    continue
                # Check common_name if available
                if hasattr(c, 'common_name') and c.common_name and query_lower in str(c.common_name).lower():
                    matching_constellations.append(c)
                    continue
                if len(matching_constellations) >= limit:
                    break

            if matching_constellations:
                import pandas as pd
                constellation_data = []
                for const in matching_constellations:
                    # Get RA/Dec from constellation
                    ra_hours = None
                    dec_degrees = None
                    if hasattr(const, 'ra') and const.ra is not None:
                        ra_hours = const.ra / 15.0 if const.ra > 24 else const.ra
                    if hasattr(const, 'dec') and const.dec is not None:
                        dec_degrees = const.dec

                    constellation_data.append({
                        'object_type': 'constellation',
                        'name': const.name,
                        'common_name': None,
                        'ra_hours': ra_hours,
                        'dec_degrees': dec_degrees,
                        'magnitude': None,
                        'catalog': 'starplot',
                        'description': None,
                        'parent_planet': None,
                        'constellation': None,
                    })
                constellation_results = pd.DataFrame(constellation_data)
                logger.debug(f"Found {len(matching_constellations)} constellations from starplot")

                # Combine custom results with constellation results
                if not custom_results.empty:
                    custom_results = pd.concat([custom_results, constellation_results], ignore_index=True)
                else:
                    custom_results = constellation_results

        # Convert custom results
        for _, row in custom_results.iterrows():
            try:
                obj_type = CelestialObjectType(row["object_type"])
                results.append(self._row_to_celestial_object(row.to_dict(), obj_type))
            except Exception as e:
                logger.debug(f"Error converting custom result: {e}")

        # Search stars from parquet file (if available)
        if self._star_parquet_path and self._star_parquet_path.exists():
            try:
            # Query stars directly from parquet using parameterized query
            star_query = """
                SELECT 
                    COALESCE(name, CAST(hip AS VARCHAR), CAST(tyc_id AS VARCHAR)) as name,
                    NULL as common_name,
                    ra_degrees / 15.0 as ra_hours,
                    dec_degrees,
                    magnitude,
                    'big_sky' as catalog,
                    NULL as description,
                    NULL as parent_planet,
                    constellation
                FROM read_parquet(?)
                WHERE name ILIKE ?
                   OR CAST(hip AS VARCHAR) ILIKE ?
                   OR CAST(tyc_id AS VARCHAR) ILIKE ?
                ORDER BY magnitude NULLS LAST
                LIMIT ?
            """
            pattern = f"%{query_lower}%"
            star_results = self.con.execute(
                star_query, [str(self._star_parquet_path), pattern, pattern, pattern, limit]
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

        # Search DSOs from starplot database
        if not self._dso_db_path or not self._dso_db_path.exists():
            raise FileNotFoundError(
                f"DSO database not found at {self._dso_db_path}. "
                "Starplot data is required. Please ensure starplot is properly installed and configured."
            )
        # Query DSOs directly from starplot's DuckDB database
        pattern = f"%{query_lower}%"
        # Attach the database
        self.con.execute(f"ATTACH '{self._dso_db_path}' AS starplot_dso (READ_ONLY)")
        dso_query_attached = """
            SELECT 
                name,
                NULL as common_name,
                ra / 15.0 as ra_hours,
                dec as dec_degrees,
                magnitude,
                CASE 
                    WHEN type = 'G' THEN 'galaxy'
                    WHEN type = 'Neb' OR type = 'PN' OR type = 'EmN' OR type = 'RfN' OR type = 'DrkN' THEN 'nebula'
                    WHEN type = 'OCl' OR type = 'GCl' THEN 'cluster'
                    ELSE 'dso'
                END as object_type,
                'openngc' as catalog,
                NULL as description,
                NULL as parent_planet,
                NULL as constellation
            FROM starplot_dso.dsos
            WHERE name ILIKE ?
            ORDER BY magnitude NULLS LAST
            LIMIT ?
        """
        dso_results = self.con.execute(dso_query_attached, [pattern, limit]).fetchdf()
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
            where_clauses.append(f"catalog = '{catalog.replace("'", "''")}'")
        if max_magnitude is not None:
            where_clauses.append(f"(magnitude <= {max_magnitude} OR magnitude IS NULL)")
        if min_magnitude is not None:
            where_clauses.append(f"magnitude >= {min_magnitude}")
        if constellation:
            where_clauses.append(f"constellation ILIKE '%{constellation.replace("'", "''")}%'")

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        # Query custom data based on object_type
        if object_type is None or object_type in [
            CelestialObjectType.PLANET,
            CelestialObjectType.MOON,
            CelestialObjectType.ASTERISM,
            CelestialObjectType.CONSTELLATION,
        ]:
            queries = []

            if object_type is None or object_type == CelestialObjectType.PLANET:
                if is_dynamic is None or is_dynamic:
                    queries.append(f"""
                        SELECT 'planet' as object_type, name, common_name, ra_hours, dec_degrees,
                               magnitude, catalog, description, NULL as parent_planet, constellation
                        FROM planets
                        WHERE {where_sql}
                    """)

            if object_type is None or object_type == CelestialObjectType.MOON:
                if is_dynamic is None or is_dynamic:
                    queries.append(f"""
                        SELECT 'moon' as object_type, name, common_name, ra_hours, dec_degrees,
                               magnitude, catalog, description, parent_planet, constellation
                        FROM moons
                        WHERE {where_sql}
                    """)

            if object_type is None or object_type == CelestialObjectType.ASTERISM:
                queries.append(f"""
                    SELECT 'asterism' as object_type, name, common_name, ra_hours, dec_degrees,
                           NULL as magnitude, catalog, description, NULL as parent_planet, constellation
                    FROM asterisms
                    WHERE {where_sql.replace('magnitude', '1')}  -- Remove magnitude filter for asterisms
                """)

            if object_type is None or object_type == CelestialObjectType.CONSTELLATION:
                # Constellations are queried from starplot model, not database
                # This will be handled separately after the database queries
                pass

            if queries:
                custom_query = " UNION ALL ".join(queries) + f" ORDER BY magnitude NULLS LAST, name LIMIT {limit}"
                custom_results = self.con.execute(custom_query).fetchdf()
                for _, row in custom_results.iterrows():
                    try:
                        obj_type = CelestialObjectType(row["object_type"])
                        results.append(self._row_to_celestial_object(row.to_dict(), obj_type))
                    except Exception as e:
                        logger.debug(f"Error converting custom result: {e}")

        # Query constellations from starplot if requested
        if object_type is None or object_type == CelestialObjectType.CONSTELLATION:
            from starplot.models import Constellation

            all_constellations = Constellation.all()
            matching_constellations = all_constellations[:limit] if limit else all_constellations

            for const in matching_constellations:
                # Get RA/Dec from constellation
                ra_hours = None
                dec_degrees = None
                if hasattr(const, 'ra') and const.ra is not None:
                    ra_hours = const.ra / 15.0 if const.ra > 24 else const.ra
                if hasattr(const, 'dec') and const.dec is not None:
                    dec_degrees = const.dec

                results.append(
                    CelestialObject(
                        name=const.name,
                        common_name=None,
                        ra_hours=ra_hours if ra_hours is not None else 0.0,
                        dec_degrees=dec_degrees if dec_degrees is not None else 0.0,
                        magnitude=None,
                        object_type=CelestialObjectType.CONSTELLATION,
                        catalog="starplot",
                        description=None,
                        parent_planet=None,
                        constellation=None,
                    )
                )

        # Query stars from parquet if requested
        if object_type is None or object_type == CelestialObjectType.STAR:
            if not self._star_parquet_path or not self._star_parquet_path.exists():
                raise FileNotFoundError(
                    f"Star catalog parquet file not found at {self._star_parquet_path}. "
                    "Starplot data is required. Please ensure starplot is properly installed and configured."
                )
            try:
                star_where = []
                if max_magnitude is not None:
                    star_where.append(f"(magnitude <= {max_magnitude} OR magnitude IS NULL)")
                if min_magnitude is not None:
                    star_where.append(f"magnitude >= {min_magnitude}")
                if constellation:
                    star_where.append(f"constellation ILIKE '%{constellation.replace("'", "''")}%'")

            star_where_sql = " AND ".join(star_where) if star_where else "1=1"

            star_query = f"""
                SELECT 
                    COALESCE(name, CAST(hip AS VARCHAR), CAST(tyc_id AS VARCHAR)) as name,
                    NULL as common_name,
                    ra_degrees / 15.0 as ra_hours,
                    dec_degrees,
                    magnitude,
                    'big_sky' as catalog,
                    NULL as description,
                    NULL as parent_planet,
                    constellation
                FROM read_parquet('{self._star_parquet_path}')
                WHERE {star_where_sql}
                ORDER BY magnitude NULLS LAST, name
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
                dso_where.append(f"(magnitude <= {max_magnitude} OR magnitude IS NULL)")
            if min_magnitude is not None:
                dso_where.append(f"magnitude >= {min_magnitude}")

            # Filter by DSO type
            if object_type == CelestialObjectType.GALAXY:
                dso_where.append("type = 'G'")
            elif object_type == CelestialObjectType.NEBULA:
                dso_where.append("type IN ('Neb', 'PN', 'EmN', 'RfN', 'DrkN')")
            elif object_type == CelestialObjectType.CLUSTER:
                dso_where.append("type IN ('OCl', 'GCl')")

            dso_where_sql = " AND ".join(dso_where) if dso_where else "1=1"

            # Attach DSO database
            self.con.execute(f"ATTACH '{self._dso_db_path}' AS starplot_dso (READ_ONLY)")
            dso_query = f"""
                SELECT 
                    name,
                    NULL as common_name,
                    ra / 15.0 as ra_hours,
                    dec as dec_degrees,
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
                    NULL as constellation
                FROM starplot_dso.dsos
                WHERE {dso_where_sql}
                ORDER BY magnitude NULLS LAST, name
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
        # Search custom data first (fastest) using parameterized query
        query = """
            SELECT 'planet' as object_type, name, common_name, ra_hours, dec_degrees,
                   magnitude, catalog, description, NULL as parent_planet, constellation
            FROM planets
            WHERE name = ?
            UNION ALL
            SELECT 'moon' as object_type, name, common_name, ra_hours, dec_degrees,
                   magnitude, catalog, description, parent_planet, constellation
            FROM moons
            WHERE name = ?
            UNION ALL
            SELECT 'asterism' as object_type, name, common_name, ra_hours, dec_degrees,
                   NULL as magnitude, catalog, description, NULL as parent_planet, constellation
            FROM asterisms
            WHERE name = ?
            LIMIT 1
        """
        result = self.con.execute(query, [name] * 3).fetchdf()
        if not result.empty:
            row = result.iloc[0]
            obj_type = CelestialObjectType(row["object_type"])
            return self._row_to_celestial_object(row.to_dict(), obj_type)

        # Search stars using parameterized query
        if not self._star_parquet_path or not self._star_parquet_path.exists():
            raise FileNotFoundError(
                f"Star catalog parquet file not found at {self._star_parquet_path}. "
                "Starplot data is required. Please ensure starplot is properly installed and configured."
            )
        star_query = """
            SELECT 
                COALESCE(name, CAST(hip AS VARCHAR), CAST(tyc_id AS VARCHAR)) as name,
                NULL as common_name,
                ra_degrees / 15.0 as ra_hours,
                dec_degrees,
                magnitude,
                'big_sky' as catalog
            FROM read_parquet(?)
            WHERE name = ?
               OR CAST(hip AS VARCHAR) = ?
            LIMIT 1
        """
        star_result = self.con.execute(star_query, [str(self._star_parquet_path), name, name]).fetchdf()
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

        # Search constellations from starplot
        from starplot.models import Constellation
        try:
            constellation = Constellation.get(name=name)
            if constellation:
                ra_hours = None
                dec_degrees = None
                if hasattr(constellation, 'ra') and constellation.ra is not None:
                    ra_hours = constellation.ra / 15.0 if constellation.ra > 24 else constellation.ra
                if hasattr(constellation, 'dec') and constellation.dec is not None:
                    dec_degrees = constellation.dec

                return CelestialObject(
                    name=constellation.name,
                    common_name=None,
                    ra_hours=ra_hours if ra_hours is not None else 0.0,
                    dec_degrees=dec_degrees if dec_degrees is not None else 0.0,
                    magnitude=None,
                    object_type=CelestialObjectType.CONSTELLATION,
                    catalog="starplot",
                    description=None,
                    parent_planet=None,
                    constellation=None,
                )
        except Exception:
            pass

        # Search DSOs using parameterized query
        if not self._dso_db_path or not self._dso_db_path.exists():
            raise FileNotFoundError(
                f"DSO database not found at {self._dso_db_path}. "
                "Starplot data is required. Please ensure starplot is properly installed and configured."
            )
        # Attach DSO database
        self.con.execute(f"ATTACH '{self._dso_db_path}' AS starplot_dso (READ_ONLY)")
        dso_query = """
            SELECT 
                name,
                ra / 15.0 as ra_hours,
                dec as dec_degrees,
                magnitude,
                CASE 
                    WHEN type = 'G' THEN 'galaxy'
                    WHEN type IN ('Neb', 'PN', 'EmN', 'RfN', 'DrkN') THEN 'nebula'
                    WHEN type IN ('OCl', 'GCl') THEN 'cluster'
                    ELSE 'dso'
                END as object_type,
                'openngc' as catalog
            FROM starplot_dso.dsos
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

        # Search custom data
        if ra_min <= ra_max:
            coord_query = """
                SELECT 'planet' as object_type, name, common_name, ra_hours, dec_degrees,
                       magnitude, catalog, description, NULL as parent_planet, constellation
                FROM planets
                WHERE ra_hours BETWEEN ? AND ? AND dec_degrees BETWEEN ? AND ?
                UNION ALL
                SELECT 'moon' as object_type, name, common_name, ra_hours, dec_degrees,
                       magnitude, catalog, description, parent_planet, constellation
                FROM moons
                WHERE ra_hours BETWEEN ? AND ? AND dec_degrees BETWEEN ? AND ?
                UNION ALL
                SELECT 'asterism' as object_type, name, common_name, ra_hours, dec_degrees,
                       NULL as magnitude, catalog, description, NULL as parent_planet, constellation
                FROM asterisms
                WHERE ra_hours BETWEEN ? AND ? AND dec_degrees BETWEEN ? AND ?
                UNION ALL
                SELECT 'constellation' as object_type, name, common_name, ra_hours, dec_degrees,
                       NULL as magnitude, catalog, description, NULL as parent_planet, NULL as constellation
                FROM constellations
                WHERE ra_hours BETWEEN ? AND ? AND dec_degrees BETWEEN ? AND ?
                LIMIT ?
            """
            coord_results = self.con.execute(
                coord_query,
                [ra_min, ra_max, dec_min, dec_max] * 4 + [limit * 5],  # 4 tables, get more candidates
            ).fetchdf()
        else:
            # Handle RA wrap-around
            coord_query = """
                SELECT 'planet' as object_type, name, common_name, ra_hours, dec_degrees,
                       magnitude, catalog, description, NULL as parent_planet, constellation
                FROM planets
                WHERE (ra_hours >= ? OR ra_hours <= ?) AND dec_degrees BETWEEN ? AND ?
                UNION ALL
                SELECT 'moon' as object_type, name, common_name, ra_hours, dec_degrees,
                       magnitude, catalog, description, parent_planet, constellation
                FROM moons
                WHERE (ra_hours >= ? OR ra_hours <= ?) AND dec_degrees BETWEEN ? AND ?
                UNION ALL
                SELECT 'asterism' as object_type, name, common_name, ra_hours, dec_degrees,
                       NULL as magnitude, catalog, description, NULL as parent_planet, constellation
                FROM asterisms
                WHERE (ra_hours >= ? OR ra_hours <= ?) AND dec_degrees BETWEEN ? AND ?
                UNION ALL
                SELECT 'constellation' as object_type, name, common_name, ra_hours, dec_degrees,
                       NULL as magnitude, catalog, description, NULL as parent_planet, NULL as constellation
                FROM constellations
                WHERE (ra_hours >= ? OR ra_hours <= ?) AND dec_degrees BETWEEN ? AND ?
                LIMIT ?
            """
            coord_results = self.con.execute(
                coord_query,
                [ra_min, ra_max, dec_min, dec_max] * 4 + [limit * 5],
            ).fetchdf()

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
        ra_deg = ra_hours * 15.0
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

        # Query custom data
        catalog_query = """
            SELECT 'planet' as object_type, name, common_name, ra_hours, dec_degrees,
                   magnitude, catalog, description, NULL as parent_planet, constellation
            FROM planets
            WHERE catalog = ?
            UNION ALL
            SELECT 'moon' as object_type, name, common_name, ra_hours, dec_degrees,
                   magnitude, catalog, description, parent_planet, constellation
            FROM moons
            WHERE catalog = ?
            UNION ALL
            SELECT 'asterism' as object_type, name, common_name, ra_hours, dec_degrees,
                   NULL as magnitude, catalog, description, NULL as parent_planet, constellation
            FROM asterisms
            WHERE catalog = ?
            UNION ALL
            SELECT 'constellation' as object_type, name, common_name, ra_hours, dec_degrees,
                   NULL as magnitude, catalog, description, NULL as parent_planet, NULL as constellation
            FROM constellations
            WHERE catalog = ?
            ORDER BY name
            LIMIT ?
        """
        catalog_results = self.con.execute(catalog_query, [catalog] * 4 + [limit]).fetchdf()

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
                self.con.execute(f"ATTACH '{self._dso_db_path}' AS starplot_dso (READ_ONLY)")
                dso_catalog_query = """
                    SELECT 
                        name,
                        NULL as common_name,
                        ra / 15.0 as ra_hours,
                        dec as dec_degrees,
                        magnitude,
                        CASE 
                            WHEN type = 'G' THEN 'galaxy'
                            WHEN type IN ('Neb', 'PN', 'EmN', 'RfN', 'DrkN') THEN 'nebula'
                            WHEN type IN ('OCl', 'GCl') THEN 'cluster'
                            ELSE 'dso'
                        END as object_type,
                        'openngc' as catalog
                    FROM starplot_dso.dsos
                    ORDER BY magnitude NULLS LAST, name
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


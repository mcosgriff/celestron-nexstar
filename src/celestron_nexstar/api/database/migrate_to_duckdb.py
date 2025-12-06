"""
Migration utility to migrate data from SQLite to DuckDB.

Migrates custom data (planets, moons, asterisms, constellations) from SQLite
to DuckDB. Stars and DSOs are not migrated as they're queried directly from
starplot's parquet files and database.
"""

from __future__ import annotations

import logging
from pathlib import Path

from celestron_nexstar.api.database.duckdb_database import DuckDBCatalogDatabase
from celestron_nexstar.api.database.database import CatalogDatabase

logger = logging.getLogger(__name__)

__all__ = ["migrate_sqlite_to_duckdb"]


async def migrate_sqlite_to_duckdb(
    sqlite_db_path: Path | str | None = None,
    duckdb_db_path: Path | str | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """
    Migrate data from SQLite to DuckDB.

    Only migrates custom data (planets, moons, asterisms, constellations).
    Stars and DSOs are not migrated as they're queried directly from starplot.

    Args:
        sqlite_db_path: Path to SQLite database (default: ~/.config/celestron-nexstar/catalogs.db)
        duckdb_db_path: Path to DuckDB database (default: ~/.config/celestron-nexstar/catalogs.duckdb)
        dry_run: If True, only count records without migrating

    Returns:
        Dictionary with counts of migrated records by table
    """
    from sqlalchemy import select

    # Get default paths if not provided
    if sqlite_db_path is None:
        sqlite_db_path = Path.home() / ".config" / "celestron-nexstar" / "catalogs.db"

    if duckdb_db_path is None:
        duckdb_db_path = Path.home() / ".config" / "celestron-nexstar" / "catalogs.duckdb"

    sqlite_db_path = Path(sqlite_db_path)
    duckdb_db_path = Path(duckdb_db_path)

    if not sqlite_db_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {sqlite_db_path}")

    logger.info(f"Starting migration from {sqlite_db_path} to {duckdb_db_path}")
    if dry_run:
        logger.info("DRY RUN MODE - No data will be written")

    # Open SQLite database
    sqlite_db = CatalogDatabase(db_path=sqlite_db_path, use_memory=False)

    # Create DuckDB database
    duckdb_db = DuckDBCatalogDatabase(db_path=duckdb_db_path)

    counts: dict[str, int] = {
        "planets": 0,
        "moons": 0,
        "asterisms": 0,
        "constellations": 0,
    }

    try:
        # Migrate planets
        async with sqlite_db._AsyncSession() as session:
            from celestron_nexstar.api.database.models import PlanetModel

            stmt = select(PlanetModel)
            result = await session.execute(stmt)
            planets = result.scalars().all()

            logger.info(f"Found {len(planets)} planets to migrate")

            if not dry_run and planets:
                for planet in planets:
                    try:
                        duckdb_db.con.execute(
                            """
                            INSERT OR REPLACE INTO planets 
                            (id, name, common_name, ra_hours, dec_degrees, magnitude, catalog, 
                             description, constellation, ephemeris_name, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            [
                                planet.id,
                                planet.name,
                                planet.common_name,
                                planet.ra_hours,
                                planet.dec_degrees,
                                planet.magnitude,
                                planet.catalog,
                                planet.description,
                                planet.constellation,
                                getattr(planet, "ephemeris_name", None),
                                planet.created_at,
                                planet.updated_at,
                            ],
                        )
                        counts["planets"] += 1
                    except Exception as e:
                        logger.warning(f"Error migrating planet {planet.name}: {e}")
            else:
                counts["planets"] = len(planets)

        # Migrate moons
        async with sqlite_db._AsyncSession() as session:
            from celestron_nexstar.api.database.models import MoonModel

            stmt = select(MoonModel)
            result = await session.execute(stmt)
            moons = result.scalars().all()

            logger.info(f"Found {len(moons)} moons to migrate")

            if not dry_run and moons:
                for moon in moons:
                    try:
                        duckdb_db.con.execute(
                            """
                            INSERT OR REPLACE INTO moons 
                            (id, name, common_name, ra_hours, dec_degrees, magnitude, catalog, 
                             description, parent_planet, constellation, ephemeris_name, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            [
                                moon.id,
                                moon.name,
                                moon.common_name,
                                moon.ra_hours,
                                moon.dec_degrees,
                                moon.magnitude,
                                moon.catalog,
                                moon.description,
                                moon.parent_planet,
                                moon.constellation,
                                getattr(moon, "ephemeris_name", None),
                                moon.created_at,
                                moon.updated_at,
                            ],
                        )
                        counts["moons"] += 1
                    except Exception as e:
                        logger.warning(f"Error migrating moon {moon.name}: {e}")
            else:
                counts["moons"] = len(moons)

        # Migrate asterisms
        async with sqlite_db._AsyncSession() as session:
            from celestron_nexstar.api.database.models import AsterismModel

            stmt = select(AsterismModel)
            result = await session.execute(stmt)
            asterisms = result.scalars().all()

            logger.info(f"Found {len(asterisms)} asterisms to migrate")

            if not dry_run and asterisms:
                for asterism in asterisms:
                    try:
                        duckdb_db.con.execute(
                            """
                            INSERT OR REPLACE INTO asterisms 
                            (id, name, common_name, ra_hours, dec_degrees, catalog, 
                             description, constellation, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            [
                                asterism.id,
                                asterism.name,
                                asterism.common_name,
                                asterism.ra_hours,
                                asterism.dec_degrees,
                                asterism.catalog if hasattr(asterism, "catalog") else "asterisms",
                                asterism.description,
                                asterism.parent_constellation,
                                asterism.created_at if hasattr(asterism, "created_at") else None,
                                asterism.updated_at if hasattr(asterism, "updated_at") else None,
                            ],
                        )
                        counts["asterisms"] += 1
                    except Exception as e:
                        logger.warning(f"Error migrating asterism {asterism.name}: {e}")
            else:
                counts["asterisms"] = len(asterisms)

        # Migrate constellations
        async with sqlite_db._AsyncSession() as session:
            from celestron_nexstar.api.database.models import ConstellationModel

            stmt = select(ConstellationModel)
            result = await session.execute(stmt)
            constellations = result.scalars().all()

            logger.info(f"Found {len(constellations)} constellations to migrate")

            if not dry_run and constellations:
                for constellation in constellations:
                    try:
                        duckdb_db.con.execute(
                            """
                            INSERT OR REPLACE INTO constellations 
                            (id, name, common_name, ra_hours, dec_degrees, catalog, 
                             description, abbreviation, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            [
                                constellation.id,
                                constellation.name,
                                constellation.common_name,
                                constellation.ra_hours,
                                constellation.dec_degrees,
                                "constellations",
                                constellation.mythology,
                                constellation.abbreviation,
                                constellation.created_at if hasattr(constellation, "created_at") else None,
                                constellation.updated_at if hasattr(constellation, "updated_at") else None,
                            ],
                        )
                        counts["constellations"] += 1
                    except Exception as e:
                        logger.warning(f"Error migrating constellation {constellation.name}: {e}")
            else:
                counts["constellations"] = len(constellations)

        if not dry_run:
            logger.info(f"Migration complete: {sum(counts.values())} records migrated")
            logger.info(f"  - Planets: {counts['planets']}")
            logger.info(f"  - Moons: {counts['moons']}")
            logger.info(f"  - Asterisms: {counts['asterisms']}")
            logger.info(f"  - Constellations: {counts['constellations']}")
        else:
            logger.info(f"Dry run complete: {sum(counts.values())} records would be migrated")
            logger.info(f"  - Planets: {counts['planets']}")
            logger.info(f"  - Moons: {counts['moons']}")
            logger.info(f"  - Asterisms: {counts['asterisms']}")
            logger.info(f"  - Constellations: {counts['constellations']}")

        return counts

    finally:
        duckdb_db.close()
        sqlite_db.close()


def migrate_sqlite_to_duckdb_sync(
    sqlite_db_path: Path | str | None = None,
    duckdb_db_path: Path | str | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """
    Synchronous wrapper for migrate_sqlite_to_duckdb.

    Args:
        sqlite_db_path: Path to SQLite database
        duckdb_db_path: Path to DuckDB database
        dry_run: If True, only count records without migrating

    Returns:
        Dictionary with counts of migrated records by table
    """
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(
            migrate_sqlite_to_duckdb(sqlite_db_path, duckdb_db_path, dry_run)
        )
    except RuntimeError:
        return asyncio.run(migrate_sqlite_to_duckdb(sqlite_db_path, duckdb_db_path, dry_run))


"""
DuckDB Database Seeder

Seeds DuckDB database with static reference data using DuckDB's native API.

Note: Constellations may be available in starplot's database. If so, they're queried from there
instead of seeding. The seeder will still seed constellations as a fallback and for additional
metadata (common_name, mythology, boundaries, etc.) that starplot may not provide.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import duckdb

from celestron_nexstar.api.core.exceptions import CatalogNotFoundError
from celestron_nexstar.api.database.database_seeder import get_seed_data_path, load_seed_json

logger = logging.getLogger(__name__)


def seed_planets(con: duckdb.DuckDBPyConnection, force: bool = False) -> int:
    """Seed planets into DuckDB."""
    logger.info("Seeding planets...")

    if force:
        con.execute("DELETE FROM planets")
        logger.info("Cleared existing planets")

    data = load_seed_json("sol_planets.json")

    added = 0
    for item in data:
        # Check if already exists
        existing = con.execute(
            "SELECT id FROM planets WHERE name = ?", [item["name"]]
        ).fetchone()
        if existing:
            continue

        # Insert planet
        con.execute(
            """
            INSERT INTO planets 
            (id, name, common_name, catalog, catalog_number, ra_hours, dec_degrees, 
             magnitude, size_arcmin, description, constellation, is_dynamic, ephemeris_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                item.get("id"),
                item["name"],
                item.get("common_name"),
                item.get("catalog", "planets"),
                item.get("catalog_number"),
                item.get("ra_hours", 0.0),
                item.get("dec_degrees", 0.0),
                item.get("magnitude"),
                item.get("size_arcmin"),
                item.get("description"),
                item.get("constellation"),
                item.get("is_dynamic", True),
                item.get("ephemeris_name"),
            ],
        )
        added += 1

    if added > 0:
        logger.info(f"Added {added} planets")
    else:
        logger.info("Planets already seeded (no new records)")

    return added


def seed_moons(con: duckdb.DuckDBPyConnection, force: bool = False) -> int:
    """Seed moons into DuckDB."""
    logger.info("Seeding moons...")

    if force:
        con.execute("DELETE FROM moons")
        logger.info("Cleared existing moons")

    data = load_seed_json("sol_moons.json")

    added = 0
    for item in data:
        # Check if already exists
        existing = con.execute(
            "SELECT id FROM moons WHERE name = ?", [item["name"]]
        ).fetchone()
        if existing:
            continue

        # Insert moon
        con.execute(
            """
            INSERT INTO moons 
            (id, name, common_name, catalog, catalog_number, ra_hours, dec_degrees, 
             magnitude, size_arcmin, description, constellation, is_dynamic, ephemeris_name, parent_planet)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                item.get("id"),
                item["name"],
                item.get("common_name"),
                item.get("catalog", "moons"),
                item.get("catalog_number"),
                item.get("ra_hours", 0.0),
                item.get("dec_degrees", 0.0),
                item.get("magnitude"),
                item.get("size_arcmin"),
                item.get("description"),
                item.get("constellation"),
                item.get("is_dynamic", True),
                item.get("ephemeris_name"),
                item.get("parent_planet"),
            ],
        )
        added += 1

    if added > 0:
        logger.info(f"Added {added} moons")
    else:
        logger.info("Moons already seeded (no new records)")

    return added


def seed_constellations(con: duckdb.DuckDBPyConnection, force: bool = False) -> int:
    """Seed constellations into DuckDB."""
    logger.info("Seeding constellations...")

    if force:
        con.execute("DELETE FROM constellations")
        logger.info("Cleared existing constellations")

    data = load_seed_json("constellations.json")

    added = 0
    for item in data:
        # Check if already exists
        existing = con.execute(
            "SELECT id FROM constellations WHERE name = ?", [item["name"]]
        ).fetchone()
        if existing:
            continue

        # Extract common_name from description if needed
        common_name = item.get("common_name")
        if not common_name and item.get("description"):
            import re

            match = re.match(r"^(The [^-]+) -", item["description"])
            if match:
                common_name = match.group(1)

        # Insert constellation
        con.execute(
            """
            INSERT INTO constellations 
            (id, name, abbreviation, common_name, ra_hours, dec_degrees,
             ra_min_hours, ra_max_hours, dec_min_degrees, dec_max_degrees,
             area_sq_deg, brightest_star, mythology, season)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                item.get("id"),
                item["name"],
                item["abbreviation"],
                common_name,
                item.get("ra_hours", 0.0),
                item.get("dec_degrees", 0.0),
                item.get("ra_min_hours", 0.0),
                item.get("ra_max_hours", 0.0),
                item.get("dec_min_degrees", 0.0),
                item.get("dec_max_degrees", 0.0),
                item.get("area_sq_deg"),
                item.get("brightest_star"),
                item.get("mythology"),
                item.get("season"),
            ],
        )
        added += 1

    if added > 0:
        logger.info(f"Added {added} constellations")
    else:
        logger.info("Constellations already seeded (no new records)")

    return added


def seed_asterisms(con: duckdb.DuckDBPyConnection, force: bool = False) -> int:
    """Seed asterisms into DuckDB."""
    logger.info("Seeding asterisms...")

    if force:
        con.execute("DELETE FROM asterisms")
        logger.info("Cleared existing asterisms")

    data = load_seed_json("asterisms.json")

    added = 0
    for item in data:
        # Check if already exists
        existing = con.execute(
            "SELECT id FROM asterisms WHERE name = ?", [item["name"]]
        ).fetchone()
        if existing:
            continue

        # Insert asterism
        con.execute(
            """
            INSERT INTO asterisms 
            (id, name, alt_names, ra_hours, dec_degrees, size_degrees,
             parent_constellation, description, stars, season,
             wikipedia_url, cultural_info, guidepost_info, historical_notes, shape_description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                item.get("id"),
                item["name"],
                item.get("alt_names"),
                item.get("ra_hours", 0.0),
                item.get("dec_degrees", 0.0),
                item.get("size_degrees"),
                item.get("parent_constellation"),
                item.get("description"),
                item.get("stars"),
                item.get("season"),
                item.get("wikipedia_url"),
                item.get("cultural_info"),
                item.get("guidepost_info"),
                item.get("historical_notes"),
                item.get("shape_description"),
            ],
        )
        added += 1

    if added > 0:
        logger.info(f"Added {added} asterisms")
    else:
        logger.info("Asterisms already seeded (no new records)")

    return added


def seed_star_name_mappings(con: duckdb.DuckDBPyConnection, force: bool = False) -> int:
    """Seed star name mappings into DuckDB."""
    logger.info("Seeding star name mappings...")

    if force:
        con.execute("DELETE FROM star_name_mappings")
        logger.info("Cleared existing star name mappings")

    data = load_seed_json("star_name_mappings.json")

    added = 0
    for item in data:
        # Check if already exists
        existing = con.execute(
            "SELECT hr_number FROM star_name_mappings WHERE hr_number = ?",
            [item["hr_number"]],
        ).fetchone()
        if existing:
            continue

        # Insert mapping
        con.execute(
            """
            INSERT INTO star_name_mappings (hr_number, common_name, bayer_designation)
            VALUES (?, ?, ?)
            """,
            [
                item["hr_number"],
                item.get("common_name", ""),
                item.get("bayer_designation"),
            ],
        )
        added += 1

    if added > 0:
        logger.info(f"Added {added} star name mappings")
    else:
        logger.info("Star name mappings already seeded (no new records)")

    return added


def seed_meteor_showers(con: duckdb.DuckDBPyConnection, force: bool = False) -> int:
    """Seed meteor showers into DuckDB."""
    logger.info("Seeding meteor showers...")

    if force:
        con.execute("DELETE FROM meteor_showers")
        logger.info("Cleared existing meteor showers")

    data = load_seed_json("meteor_showers.json")

    added = 0
    for item in data:
        # Check if already exists
        existing = con.execute(
            "SELECT id FROM meteor_showers WHERE name = ?", [item["name"]]
        ).fetchone()
        if existing:
            continue

        # Insert meteor shower
        con.execute(
            """
            INSERT INTO meteor_showers 
            (id, name, code, start_month, start_day, end_month, end_day,
             peak_month, peak_day, radiant_ra_hours, radiant_dec_degrees,
             radiant_constellation, zhr_peak, velocity_km_s, parent_comet, best_time, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                item.get("id"),
                item["name"],
                item.get("code"),
                item.get("start_month", 1),
                item.get("start_day", 1),
                item.get("end_month", 12),
                item.get("end_day", 31),
                item.get("peak_month", 1),
                item.get("peak_day", 1),
                item.get("radiant_ra_hours", 0.0),
                item.get("radiant_dec_degrees", 0.0),
                item.get("radiant_constellation"),
                item.get("zhr_peak", 0),
                item.get("velocity_km_s"),
                item.get("parent_comet"),
                item.get("best_time"),
                item.get("notes"),
            ],
        )
        added += 1

    if added > 0:
        logger.info(f"Added {added} meteor showers")
    else:
        logger.info("Meteor showers already seeded (no new records)")

    return added


def seed_dark_sky_sites(con: duckdb.DuckDBPyConnection, force: bool = False) -> int:
    """Seed dark sky sites into DuckDB."""
    logger.info("Seeding dark sky sites...")

    if force:
        con.execute("DELETE FROM dark_sky_sites")
        logger.info("Cleared existing dark sky sites")

    try:
        data = load_seed_json("dark_sky_sites.json")
    except CatalogNotFoundError:
        logger.warning("Dark sky sites seed file not found, skipping")
        return 0

    added = 0
    for item in data:
        # Check if already exists
        existing = con.execute(
            "SELECT id FROM dark_sky_sites WHERE name = ?", [item["name"]]
        ).fetchone()
        if existing:
            continue

        # Insert dark sky site
        con.execute(
            """
            INSERT INTO dark_sky_sites 
            (id, name, latitude, longitude, geohash, bortle_class, sqm_value, description, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                item.get("id"),
                item["name"],
                item.get("latitude", 0.0),
                item.get("longitude", 0.0),
                item.get("geohash"),
                item.get("bortle_class", 1),
                item.get("sqm_value", 22.0),
                item.get("description", ""),
                item.get("notes"),
            ],
        )
        added += 1

    if added > 0:
        logger.info(f"Added {added} dark sky sites")
    else:
        logger.info("Dark sky sites already seeded (no new records)")

    return added


def seed_all(con: duckdb.DuckDBPyConnection, force: bool = False) -> dict[str, int]:
    """
    Seed all static reference data into DuckDB.

    Args:
        con: DuckDB connection
        force: If True, clear existing data before seeding

    Returns:
        Dictionary mapping data type to number of records added
    """
    results: dict[str, int] = {}

    try:
        results["planets"] = seed_planets(con, force=force)
    except Exception as e:
        logger.error(f"Failed to seed planets: {e}")
        results["planets"] = 0

    try:
        results["moons"] = seed_moons(con, force=force)
    except Exception as e:
        logger.error(f"Failed to seed moons: {e}")
        results["moons"] = 0

    try:
        results["constellations"] = seed_constellations(con, force=force)
    except Exception as e:
        logger.error(f"Failed to seed constellations: {e}")
        results["constellations"] = 0

    try:
        results["asterisms"] = seed_asterisms(con, force=force)
    except Exception as e:
        logger.error(f"Failed to seed asterisms: {e}")
        results["asterisms"] = 0

    try:
        results["star_name_mappings"] = seed_star_name_mappings(con, force=force)
    except Exception as e:
        logger.error(f"Failed to seed star name mappings: {e}")
        results["star_name_mappings"] = 0

    try:
        results["meteor_showers"] = seed_meteor_showers(con, force=force)
    except Exception as e:
        logger.error(f"Failed to seed meteor showers: {e}")
        results["meteor_showers"] = 0

    try:
        results["dark_sky_sites"] = seed_dark_sky_sites(con, force=force)
    except Exception as e:
        logger.error(f"Failed to seed dark sky sites: {e}")
        results["dark_sky_sites"] = 0

    return results


def get_seed_status(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """
    Get current seed data status.

    Args:
        con: DuckDB connection

    Returns:
        Dictionary mapping data type to record count
    """
    status: dict[str, int] = {}

    try:
        result = con.execute("SELECT COUNT(*) FROM planets").fetchone()
        status["planets"] = result[0] if result else 0
    except Exception:
        status["planets"] = 0

    try:
        result = con.execute("SELECT COUNT(*) FROM moons").fetchone()
        status["moons"] = result[0] if result else 0
    except Exception:
        status["moons"] = 0

    try:
        result = con.execute("SELECT COUNT(*) FROM constellations").fetchone()
        status["constellations"] = result[0] if result else 0
    except Exception:
        status["constellations"] = 0

    try:
        result = con.execute("SELECT COUNT(*) FROM asterisms").fetchone()
        status["asterisms"] = result[0] if result else 0
    except Exception:
        status["asterisms"] = 0

    try:
        result = con.execute("SELECT COUNT(*) FROM star_name_mappings").fetchone()
        status["star_name_mappings"] = result[0] if result else 0
    except Exception:
        status["star_name_mappings"] = 0

    try:
        result = con.execute("SELECT COUNT(*) FROM meteor_showers").fetchone()
        status["meteor_showers"] = result[0] if result else 0
    except Exception:
        status["meteor_showers"] = 0

    try:
        result = con.execute("SELECT COUNT(*) FROM dark_sky_sites").fetchone()
        status["dark_sky_sites"] = result[0] if result else 0
    except Exception:
        status["dark_sky_sites"] = 0

    return status


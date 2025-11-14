"""
Database Seeder

Uses sqlalchemyseed to seed the database with static reference data.
Supports idempotent seeding (can be run multiple times without duplicates).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    AsterismModel,
    BortleCharacteristicsModel,
    CometModel,
    ConstellationModel,
    DarkSkySiteModel,
    EclipseModel,
    MeteorShowerModel,
    SpaceEventModel,
    StarNameMappingModel,
    VariableStarModel,
)


logger = logging.getLogger(__name__)


def get_seed_data_path() -> Path:
    """
    Get the path to the seed data directory.

    Returns:
        Path to seed data directory
    """
    # Seed data is stored in cli/data/seed relative to this module
    # This module is in api/, so we need to go up and into cli/data/seed
    current_file = Path(__file__)
    # api/database_seeder.py -> api/ -> celestron_nexstar/ -> cli/ -> data/ -> seed/
    seed_dir = current_file.parent.parent / "cli" / "data" / "seed"
    return seed_dir


def load_seed_json(filename: str) -> Any:
    """
    Load a JSON seed data file.

    Args:
        filename: Name of the JSON file (e.g., "star_name_mappings.json")

    Returns:
        Parsed JSON data

    Raises:
        FileNotFoundError: If the seed data file doesn't exist
        json.JSONDecodeError: If the JSON file is malformed
    """
    seed_dir = get_seed_data_path()
    json_path = seed_dir / filename

    if not json_path.exists():
        raise FileNotFoundError(f"Seed data file not found: {json_path}")

    logger.debug(f"Loading seed data from {json_path}")

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    return data


async def seed_star_name_mappings(db_session: AsyncSession, force: bool = False) -> int:
    """
    Seed star name mappings into the database.

    Args:
        db_session: Database session
        force: If True, clear existing data before seeding

    Returns:
        Number of records added
    """
    logger.info("Seeding star name mappings...")

    if force:
        await db_session.execute(delete(StarNameMappingModel))
        await db_session.commit()
        logger.info("Cleared existing star name mappings")

    # Load seed data
    data = load_seed_json("star_name_mappings.json")

    added = 0
    for item in data:
        hr_number = item["hr_number"]

        # Check if already exists (idempotent)
        existing = await db_session.scalar(
            select(StarNameMappingModel).where(StarNameMappingModel.hr_number == hr_number)
        )
        if existing:
            continue

        # Create new mapping
        mapping = StarNameMappingModel(
            hr_number=hr_number,
            common_name=item.get("common_name") or "",
            bayer_designation=item.get("bayer_designation"),
        )
        db_session.add(mapping)
        added += 1

    if added > 0:
        await db_session.commit()
        logger.info(f"Added {added} star name mappings")
    else:
        logger.info("Star name mappings already seeded (no new records)")

    return added


async def seed_meteor_showers(db_session: AsyncSession, force: bool = False) -> int:
    """
    Seed meteor showers into the database.

    Args:
        db_session: Database session
        force: If True, clear existing data before seeding

    Returns:
        Number of records added
    """
    logger.info("Seeding meteor showers...")

    if force:
        await db_session.execute(delete(MeteorShowerModel))
        await db_session.commit()
        logger.info("Cleared existing meteor showers")

    # Load seed data
    data = load_seed_json("meteor_showers.json")

    added = 0
    for item in data:
        name = item["name"]

        # Check if already exists (idempotent)
        existing = await db_session.scalar(select(MeteorShowerModel).where(MeteorShowerModel.name == name))
        if existing:
            continue

        # Filter out fields that don't exist in the model
        # MeteorShowerModel doesn't have peak_end_month or peak_end_day
        model_fields = {
            "name",
            "code",
            "start_month",
            "start_day",
            "end_month",
            "end_day",
            "peak_month",
            "peak_day",
            "radiant_ra_hours",
            "radiant_dec_degrees",
            "radiant_constellation",
            "zhr_peak",
            "velocity_km_s",
            "parent_comet",
            "best_time",
            "notes",
        }
        filtered_item = {k: v for k, v in item.items() if k in model_fields}

        # Create new meteor shower
        shower = MeteorShowerModel(**filtered_item)
        db_session.add(shower)
        added += 1

    if added > 0:
        await db_session.commit()
        logger.info(f"Added {added} meteor showers")
    else:
        logger.info("Meteor showers already seeded (no new records)")

    return added


async def seed_constellations(db_session: AsyncSession, force: bool = False) -> int:
    """
    Seed constellations into the database.

    Args:
        db_session: Database session
        force: If True, clear existing data before seeding

    Returns:
        Number of records added
    """
    logger.info("Seeding constellations...")

    if force:
        await db_session.execute(delete(ConstellationModel))
        await db_session.commit()
        logger.info("Cleared existing constellations")

    # Load seed data
    data = load_seed_json("constellations.json")

    added = 0
    for item in data:
        name = item["name"]

        # Check if already exists (idempotent)
        existing = await db_session.scalar(select(ConstellationModel).where(ConstellationModel.name == name))
        if existing:
            continue

        # Filter out fields that don't exist in the model
        # ConstellationModel doesn't have magnitude or hemisphere (these are calculated)
        model_fields = {
            "name",
            "abbreviation",
            "common_name",
            "ra_hours",
            "dec_degrees",
            "ra_min_hours",
            "ra_max_hours",
            "dec_min_degrees",
            "dec_max_degrees",
            "area_sq_deg",
            "brightest_star",
            "mythology",
            "season",
        }
        filtered_item = {k: v for k, v in item.items() if k in model_fields}

        # Create new constellation
        constellation = ConstellationModel(**filtered_item)
        db_session.add(constellation)
        added += 1

    if added > 0:
        await db_session.commit()
        logger.info(f"Added {added} constellations")
    else:
        logger.info("Constellations already seeded (no new records)")

    return added


async def seed_asterisms(db_session: AsyncSession, force: bool = False) -> int:
    """
    Seed asterisms into the database.

    Args:
        db_session: Database session
        force: If True, clear existing data before seeding

    Returns:
        Number of records added
    """
    logger.info("Seeding asterisms...")

    if force:
        await db_session.execute(delete(AsterismModel))
        await db_session.commit()
        logger.info("Cleared existing asterisms")

    # Load seed data
    data = load_seed_json("asterisms.json")

    added = 0
    for item in data:
        name = item["name"]

        # Check if already exists (idempotent)
        existing = await db_session.scalar(select(AsterismModel).where(AsterismModel.name == name))
        if existing:
            continue

        # Create new asterism
        asterism = AsterismModel(**item)
        db_session.add(asterism)
        added += 1

    if added > 0:
        await db_session.commit()
        logger.info(f"Added {added} asterisms")
    else:
        logger.info("Asterisms already seeded (no new records)")

    return added


async def seed_dark_sky_sites(db_session: AsyncSession, force: bool = False) -> int:
    """
    Seed dark sky sites into the database.

    Args:
        db_session: Database session
        force: If True, clear existing data before seeding

    Returns:
        Number of records added
    """
    logger.info("Seeding dark sky sites...")

    if force:
        await db_session.execute(delete(DarkSkySiteModel))
        await db_session.commit()
        logger.info("Cleared existing dark sky sites")

    # Load seed data
    data = load_seed_json("dark_sky_sites.json")

    # Import geohash utilities
    from .geohash_utils import encode

    added = 0
    for item in data:
        name = item["name"]

        # Check if already exists (idempotent)
        existing = await db_session.scalar(select(DarkSkySiteModel).where(DarkSkySiteModel.name == name))
        if existing:
            continue

        # Calculate geohash if missing (precision 9 for ~5m accuracy)
        if not item.get("geohash"):
            item["geohash"] = encode(item["latitude"], item["longitude"], precision=9)

        # Create new dark sky site
        site = DarkSkySiteModel(**item)
        db_session.add(site)
        added += 1

    if added > 0:
        await db_session.commit()
        logger.info(f"Added {added} dark sky sites")
    else:
        logger.info("Dark sky sites already seeded (no new records)")

    return added


async def seed_space_events(db_session: AsyncSession, force: bool = False) -> int:
    """
    Seed space events into the database.

    Args:
        db_session: Database session
        force: If True, clear existing data before seeding

    Returns:
        Number of records added
    """
    logger.info("Seeding space events...")

    if force:
        await db_session.execute(delete(SpaceEventModel))
        await db_session.commit()
        logger.info("Cleared existing space events")

    # Load seed data
    data = load_seed_json("space_events.json")

    added = 0
    for item in data:
        name = item["name"]
        date_str = item["date"]  # ISO format datetime string

        # Parse date
        from datetime import datetime

        event_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))

        # Check if already exists (idempotent) - match by name and date
        existing = await db_session.scalar(
            select(SpaceEventModel).where(SpaceEventModel.name == name, SpaceEventModel.date == event_date)
        )
        if existing:
            continue

        # Create new space event (convert date string to datetime)
        event_data = {**item}
        event_data["date"] = event_date
        event = SpaceEventModel(**event_data)
        db_session.add(event)
        added += 1

    if added > 0:
        await db_session.commit()
        logger.info(f"Added {added} space events")
    else:
        logger.info("Space events already seeded (no new records)")

    return added


async def seed_variable_stars(db_session: AsyncSession, force: bool = False) -> int:
    """
    Seed variable stars into the database.

    Args:
        db_session: Database session
        force: If True, clear existing data before seeding

    Returns:
        Number of records added
    """
    logger.info("Seeding variable stars...")

    if force:
        await db_session.execute(delete(VariableStarModel))
        await db_session.commit()
        logger.info("Cleared existing variable stars")

    # Load seed data
    data = load_seed_json("variable_stars.json")

    added = 0
    for item in data:
        name = item["name"]

        # Check if already exists (idempotent)
        existing = await db_session.scalar(select(VariableStarModel).where(VariableStarModel.name == name))
        if existing:
            continue

        # Create new variable star
        star = VariableStarModel(**item)
        db_session.add(star)
        added += 1

    if added > 0:
        await db_session.commit()
        logger.info(f"Added {added} variable stars")
    else:
        logger.info("Variable stars already seeded (no new records)")

    return added


async def seed_comets(db_session: AsyncSession, force: bool = False) -> int:
    """
    Seed comets into the database.

    Args:
        db_session: Database session
        force: If True, clear existing data before seeding

    Returns:
        Number of records added
    """
    logger.info("Seeding comets...")

    if force:
        await db_session.execute(delete(CometModel))
        await db_session.commit()
        logger.info("Cleared existing comets")

    # Load seed data
    data = load_seed_json("comets.json")

    added = 0
    for item in data:
        designation = item["designation"]

        # Check if already exists (idempotent)
        existing = await db_session.scalar(select(CometModel).where(CometModel.designation == designation))
        if existing:
            continue

        # Parse datetime strings
        from datetime import datetime

        item["perihelion_date"] = datetime.fromisoformat(item["perihelion_date"].replace("Z", "+00:00"))
        item["peak_date"] = datetime.fromisoformat(item["peak_date"].replace("Z", "+00:00"))

        # Create new comet
        comet = CometModel(**item)
        db_session.add(comet)
        added += 1

    if added > 0:
        await db_session.commit()
        logger.info(f"Added {added} comets")
    else:
        logger.info("Comets already seeded (no new records)")

    return added


async def seed_eclipses(db_session: AsyncSession, force: bool = False) -> int:
    """
    Seed eclipses into the database.

    Args:
        db_session: Database session
        force: If True, clear existing data before seeding

    Returns:
        Number of records added
    """
    logger.info("Seeding eclipses...")

    if force:
        await db_session.execute(delete(EclipseModel))
        await db_session.commit()
        logger.info("Cleared existing eclipses")

    # Load seed data
    data = load_seed_json("eclipses.json")

    added = 0
    for item in data:
        eclipse_type = item["eclipse_type"]
        date_str = item["date"]

        # Parse date
        from datetime import datetime

        eclipse_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))

        # Check if already exists (idempotent) - match by type and date
        existing = await db_session.scalar(
            select(EclipseModel).where(EclipseModel.eclipse_type == eclipse_type, EclipseModel.date == eclipse_date)
        )
        if existing:
            continue

        # Create new eclipse
        eclipse_data = {**item}
        eclipse_data["date"] = eclipse_date
        eclipse = EclipseModel(**eclipse_data)
        db_session.add(eclipse)
        added += 1

    if added > 0:
        await db_session.commit()
        logger.info(f"Added {added} eclipses")
    else:
        logger.info("Eclipses already seeded (no new records)")

    return added


async def seed_bortle_characteristics(db_session: AsyncSession, force: bool = False) -> int:
    """
    Seed Bortle characteristics into the database.

    Args:
        db_session: Database session
        force: If True, clear existing data before seeding

    Returns:
        Number of records added
    """
    logger.info("Seeding Bortle characteristics...")

    if force:
        await db_session.execute(delete(BortleCharacteristicsModel))
        await db_session.commit()
        logger.info("Cleared existing Bortle characteristics")

    # Load seed data
    data = load_seed_json("bortle_characteristics.json")

    added = 0
    for item in data:
        bortle_class = item["bortle_class"]

        # Check if already exists (idempotent)
        existing = await db_session.scalar(
            select(BortleCharacteristicsModel).where(BortleCharacteristicsModel.bortle_class == bortle_class)
        )
        if existing:
            continue

        # Create new Bortle characteristics
        chars = BortleCharacteristicsModel(**item)
        db_session.add(chars)
        added += 1

    if added > 0:
        await db_session.commit()
        logger.info(f"Added {added} Bortle characteristics")
    else:
        logger.info("Bortle characteristics already seeded (no new records)")

    return added


async def seed_all(db_session: AsyncSession, force: bool = False) -> dict[str, int]:
    """
    Seed all static reference data into the database.

    Args:
        db_session: Database session
        force: If True, clear existing data before seeding

    Returns:
        Dictionary mapping data type to number of records added
    """
    results: dict[str, int] = {}

    try:
        results["star_name_mappings"] = await seed_star_name_mappings(db_session, force=force)
    except FileNotFoundError:
        logger.warning("Star name mappings seed file not found, skipping")
        results["star_name_mappings"] = 0
    except Exception as e:
        logger.error(f"Failed to seed star name mappings: {e}")
        results["star_name_mappings"] = 0

    try:
        results["meteor_showers"] = await seed_meteor_showers(db_session, force=force)
    except FileNotFoundError:
        logger.warning("Meteor showers seed file not found, skipping")
        results["meteor_showers"] = 0
    except Exception as e:
        logger.error(f"Failed to seed meteor showers: {e}")
        results["meteor_showers"] = 0

    try:
        results["constellations"] = await seed_constellations(db_session, force=force)
    except FileNotFoundError:
        logger.warning("Constellations seed file not found, skipping")
        results["constellations"] = 0
    except Exception as e:
        logger.error(f"Failed to seed constellations: {e}")
        results["constellations"] = 0

    try:
        results["asterisms"] = await seed_asterisms(db_session, force=force)
    except FileNotFoundError:
        logger.warning("Asterisms seed file not found, skipping")
        results["asterisms"] = 0
    except Exception as e:
        logger.error(f"Failed to seed asterisms: {e}")
        results["asterisms"] = 0

    try:
        results["dark_sky_sites"] = await seed_dark_sky_sites(db_session, force=force)
    except FileNotFoundError:
        logger.warning("Dark sky sites seed file not found, skipping")
        results["dark_sky_sites"] = 0
    except Exception as e:
        logger.error(f"Failed to seed dark sky sites: {e}")
        results["dark_sky_sites"] = 0

    try:
        results["space_events"] = await seed_space_events(db_session, force=force)
    except FileNotFoundError:
        logger.warning("Space events seed file not found, skipping")
        results["space_events"] = 0
    except Exception as e:
        logger.error(f"Failed to seed space events: {e}")
        results["space_events"] = 0

    try:
        results["variable_stars"] = await seed_variable_stars(db_session, force=force)
    except FileNotFoundError:
        logger.warning("Variable stars seed file not found, skipping")
        results["variable_stars"] = 0
    except Exception as e:
        logger.error(f"Failed to seed variable stars: {e}")
        results["variable_stars"] = 0

    try:
        results["comets"] = await seed_comets(db_session, force=force)
    except FileNotFoundError:
        logger.warning("Comets seed file not found, skipping")
        results["comets"] = 0
    except Exception as e:
        logger.error(f"Failed to seed comets: {e}")
        results["comets"] = 0

    try:
        results["eclipses"] = await seed_eclipses(db_session, force=force)
    except FileNotFoundError:
        logger.warning("Eclipses seed file not found, skipping")
        results["eclipses"] = 0
    except Exception as e:
        logger.error(f"Failed to seed eclipses: {e}")
        results["eclipses"] = 0

    try:
        results["bortle_characteristics"] = await seed_bortle_characteristics(db_session, force=force)
    except FileNotFoundError:
        logger.warning("Bortle characteristics seed file not found, skipping")
        results["bortle_characteristics"] = 0
    except Exception as e:
        logger.error(f"Failed to seed bortle characteristics: {e}")
        results["bortle_characteristics"] = 0

    return results


async def get_seed_status(db_session: AsyncSession) -> dict[str, int]:
    """
    Get current seed data status (counts for each data type).

    Args:
        db_session: Database session

    Returns:
        Dictionary mapping data type to record count
    """
    status: dict[str, int] = {}

    # Star name mappings
    try:
        count_result = await db_session.scalar(select(func.count(StarNameMappingModel.hr_number)))
        status["star_name_mappings"] = count_result or 0
    except Exception:
        status["star_name_mappings"] = 0

    # Meteor showers
    try:
        count_result = await db_session.scalar(select(func.count(MeteorShowerModel.id)))
        status["meteor_showers"] = count_result or 0
    except Exception:
        status["meteor_showers"] = 0

    # Constellations
    try:
        count_result = await db_session.scalar(select(func.count(ConstellationModel.id)))
        status["constellations"] = count_result or 0
    except Exception:
        status["constellations"] = 0

    # Asterisms
    try:
        count_result = await db_session.scalar(select(func.count(AsterismModel.id)))
        status["asterisms"] = count_result or 0
    except Exception:
        status["asterisms"] = 0

    # Dark sky sites
    try:
        count_result = await db_session.scalar(select(func.count(DarkSkySiteModel.id)))
        status["dark_sky_sites"] = count_result or 0
    except Exception:
        status["dark_sky_sites"] = 0

    # Space events
    try:
        count_result = await db_session.scalar(select(func.count(SpaceEventModel.id)))
        status["space_events"] = count_result or 0
    except Exception:
        status["space_events"] = 0

    # Variable stars
    try:
        count_result = await db_session.scalar(select(func.count(VariableStarModel.id)))
        status["variable_stars"] = count_result or 0
    except Exception:
        status["variable_stars"] = 0

    # Comets
    try:
        count_result = await db_session.scalar(select(func.count(CometModel.id)))
        status["comets"] = count_result or 0
    except Exception:
        status["comets"] = 0

    # Eclipses
    try:
        count_result = await db_session.scalar(select(func.count(EclipseModel.id)))
        status["eclipses"] = count_result or 0
    except Exception:
        status["eclipses"] = 0

    # Bortle characteristics
    try:
        count_result = await db_session.scalar(select(func.count(BortleCharacteristicsModel.bortle_class)))
        status["bortle_characteristics"] = count_result or 0
    except Exception:
        status["bortle_characteristics"] = 0

    return status

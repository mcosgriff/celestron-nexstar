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

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    AsterismModel,
    ConstellationModel,
    DarkSkySiteModel,
    MeteorShowerModel,
    SpaceEventModel,
    StarNameMappingModel,
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


def seed_star_name_mappings(db_session: Session, force: bool = False) -> int:
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
        db_session.query(StarNameMappingModel).delete()
        logger.info("Cleared existing star name mappings")

    # Load seed data
    data = load_seed_json("star_name_mappings.json")

    added = 0
    for item in data:
        hr_number = item["hr_number"]

        # Check if already exists (idempotent)
        existing = db_session.scalar(select(StarNameMappingModel).where(StarNameMappingModel.hr_number == hr_number))
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
        db_session.commit()
        logger.info(f"Added {added} star name mappings")
    else:
        logger.info("Star name mappings already seeded (no new records)")

    return added


def seed_meteor_showers(db_session: Session, force: bool = False) -> int:
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
        db_session.query(MeteorShowerModel).delete()
        logger.info("Cleared existing meteor showers")

    # Load seed data
    data = load_seed_json("meteor_showers.json")

    added = 0
    for item in data:
        name = item["name"]

        # Check if already exists (idempotent)
        existing = db_session.scalar(select(MeteorShowerModel).where(MeteorShowerModel.name == name))
        if existing:
            continue

        # Create new meteor shower
        shower = MeteorShowerModel(**item)
        db_session.add(shower)
        added += 1

    if added > 0:
        db_session.commit()
        logger.info(f"Added {added} meteor showers")
    else:
        logger.info("Meteor showers already seeded (no new records)")

    return added


def seed_constellations(db_session: Session, force: bool = False) -> int:
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
        db_session.query(ConstellationModel).delete()
        logger.info("Cleared existing constellations")

    # Load seed data
    data = load_seed_json("constellations.json")

    added = 0
    for item in data:
        name = item["name"]

        # Check if already exists (idempotent)
        existing = db_session.scalar(select(ConstellationModel).where(ConstellationModel.name == name))
        if existing:
            continue

        # Create new constellation
        constellation = ConstellationModel(**item)
        db_session.add(constellation)
        added += 1

    if added > 0:
        db_session.commit()
        logger.info(f"Added {added} constellations")
    else:
        logger.info("Constellations already seeded (no new records)")

    return added


def seed_asterisms(db_session: Session, force: bool = False) -> int:
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
        db_session.query(AsterismModel).delete()
        logger.info("Cleared existing asterisms")

    # Load seed data
    data = load_seed_json("asterisms.json")

    added = 0
    for item in data:
        name = item["name"]

        # Check if already exists (idempotent)
        existing = db_session.scalar(select(AsterismModel).where(AsterismModel.name == name))
        if existing:
            continue

        # Create new asterism
        asterism = AsterismModel(**item)
        db_session.add(asterism)
        added += 1

    if added > 0:
        db_session.commit()
        logger.info(f"Added {added} asterisms")
    else:
        logger.info("Asterisms already seeded (no new records)")

    return added


def seed_dark_sky_sites(db_session: Session, force: bool = False) -> int:
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
        db_session.query(DarkSkySiteModel).delete()
        logger.info("Cleared existing dark sky sites")

    # Load seed data
    data = load_seed_json("dark_sky_sites.json")

    added = 0
    for item in data:
        name = item["name"]

        # Check if already exists (idempotent)
        existing = db_session.scalar(select(DarkSkySiteModel).where(DarkSkySiteModel.name == name))
        if existing:
            continue

        # Create new dark sky site
        site = DarkSkySiteModel(**item)
        db_session.add(site)
        added += 1

    if added > 0:
        db_session.commit()
        logger.info(f"Added {added} dark sky sites")
    else:
        logger.info("Dark sky sites already seeded (no new records)")

    return added


def seed_space_events(db_session: Session, force: bool = False) -> int:
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
        db_session.query(SpaceEventModel).delete()
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
        existing = db_session.scalar(
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
        db_session.commit()
        logger.info(f"Added {added} space events")
    else:
        logger.info("Space events already seeded (no new records)")

    return added


def seed_all(db_session: Session, force: bool = False) -> dict[str, int]:
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
        results["star_name_mappings"] = seed_star_name_mappings(db_session, force=force)
    except FileNotFoundError:
        logger.warning("Star name mappings seed file not found, skipping")
        results["star_name_mappings"] = 0
    except Exception as e:
        logger.error(f"Failed to seed star name mappings: {e}")
        results["star_name_mappings"] = 0

    try:
        results["meteor_showers"] = seed_meteor_showers(db_session, force=force)
    except FileNotFoundError:
        logger.warning("Meteor showers seed file not found, skipping")
        results["meteor_showers"] = 0
    except Exception as e:
        logger.error(f"Failed to seed meteor showers: {e}")
        results["meteor_showers"] = 0

    try:
        results["constellations"] = seed_constellations(db_session, force=force)
    except FileNotFoundError:
        logger.warning("Constellations seed file not found, skipping")
        results["constellations"] = 0
    except Exception as e:
        logger.error(f"Failed to seed constellations: {e}")
        results["constellations"] = 0

    try:
        results["asterisms"] = seed_asterisms(db_session, force=force)
    except FileNotFoundError:
        logger.warning("Asterisms seed file not found, skipping")
        results["asterisms"] = 0
    except Exception as e:
        logger.error(f"Failed to seed asterisms: {e}")
        results["asterisms"] = 0

    try:
        results["dark_sky_sites"] = seed_dark_sky_sites(db_session, force=force)
    except FileNotFoundError:
        logger.warning("Dark sky sites seed file not found, skipping")
        results["dark_sky_sites"] = 0
    except Exception as e:
        logger.error(f"Failed to seed dark sky sites: {e}")
        results["dark_sky_sites"] = 0

    try:
        results["space_events"] = seed_space_events(db_session, force=force)
    except FileNotFoundError:
        logger.warning("Space events seed file not found, skipping")
        results["space_events"] = 0
    except Exception as e:
        logger.error(f"Failed to seed space events: {e}")
        results["space_events"] = 0

    return results


def get_seed_status(db_session: Session) -> dict[str, int]:
    """
    Get current seed data status (counts for each data type).

    Args:
        db_session: Database session

    Returns:
        Dictionary mapping data type to record count
    """
    from sqlalchemy import func, select

    status: dict[str, int] = {}

    # Star name mappings
    try:
        count = db_session.scalar(select(func.count(StarNameMappingModel.hr_number))) or 0
        status["star_name_mappings"] = count
    except Exception:
        status["star_name_mappings"] = 0

    # Meteor showers
    try:
        count = db_session.scalar(select(func.count(MeteorShowerModel.id))) or 0
        status["meteor_showers"] = count
    except Exception:
        status["meteor_showers"] = 0

    # Constellations
    try:
        count = db_session.scalar(select(func.count(ConstellationModel.id))) or 0
        status["constellations"] = count
    except Exception:
        status["constellations"] = 0

    # Asterisms
    try:
        count = db_session.scalar(select(func.count(AsterismModel.id))) or 0
        status["asterisms"] = count
    except Exception:
        status["asterisms"] = 0

    # Dark sky sites
    try:
        count = db_session.scalar(select(func.count(DarkSkySiteModel.id))) or 0
        status["dark_sky_sites"] = count
    except Exception:
        status["dark_sky_sites"] = 0

    # Space events
    try:
        count = db_session.scalar(select(func.count(SpaceEventModel.id))) or 0
        status["space_events"] = count
    except Exception:
        status["space_events"] = 0

    return status

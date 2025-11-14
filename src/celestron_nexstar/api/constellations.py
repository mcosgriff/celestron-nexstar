"""
Constellation and Asterism Catalog

Static data for prominent constellations and famous asterisms visible
to binoculars and naked eye. Includes visibility calculations based on
observer location and time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from .utils import ra_dec_to_alt_az


if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)

__all__ = [
    "Asterism",
    "Constellation",
    "get_famous_asterisms",
    "get_prominent_constellations",
    "get_visible_asterisms",
    "get_visible_constellations",
    "populate_constellation_database",
]


@dataclass(frozen=True)
class Constellation:
    """A constellation with position and metadata."""

    name: str
    abbreviation: str
    ra_hours: float  # Right ascension of center (hours)
    dec_degrees: float  # Declination of center (degrees)
    area_sq_deg: float  # Size in square degrees
    brightest_star: str  # Name of brightest star
    magnitude: float  # Magnitude of brightest star
    season: str  # Best viewing season (Spring, Summer, Fall, Winter)
    hemisphere: str  # Northern, Southern, or Equatorial
    description: str  # Brief description


@dataclass(frozen=True)
class Asterism:
    """A star pattern (asterism) within or across constellations."""

    name: str
    alt_names: list[str]  # Alternative names
    ra_hours: float  # Right ascension of center
    dec_degrees: float  # Declination of center
    size_degrees: float  # Approximate angular size
    parent_constellation: str | None  # Primary constellation (if any)
    season: str  # Best viewing season
    hemisphere: str  # Visibility
    member_stars: list[str]  # Notable stars in the asterism
    description: str  # How to find and what it looks like


# NOTE: Constellation data is now stored in database seed files.
# See get_prominent_constellations() which loads from database.
# To regenerate seed files, run: python scripts/create_seed_files.py

# Removed _PROMINENT_CONSTELLATIONS_FALLBACK - data is now in constellations.json seed file
# Removed FAMOUS_ASTERISMS - data is now in asterisms.json seed file and loaded via get_famous_asterisms()


async def get_prominent_constellations(db_session: AsyncSession) -> list[Constellation]:
    """
    Get list of prominent constellations from database.

    Args:
        db_session: Database session

    Returns:
        List of Constellation objects

    Raises:
        RuntimeError: If no constellations found in database (seed data required)
    """
    from sqlalchemy import func, select

    from .models import ConstellationModel

    count = await db_session.scalar(select(func.count(ConstellationModel.id)))
    if count == 0:
        raise RuntimeError(
            "No constellations found in database. Please seed the database by running: nexstar data seed"
        )

    result = await db_session.execute(select(ConstellationModel))
    models = result.scalars().all()

    constellations = []
    for model in models:
        # Calculate hemisphere from declination
        if model.dec_degrees > 30:
            hemisphere = "Northern"
        elif model.dec_degrees < -30:
            hemisphere = "Southern"
        else:
            hemisphere = "Equatorial"

        # Use mythology as description, or empty string
        description = model.mythology or ""

        # Magnitude not stored in model - use 0.0 as placeholder
        magnitude = 0.0

        constellation = Constellation(
            name=model.name,
            abbreviation=model.abbreviation,
            ra_hours=model.ra_hours,
            dec_degrees=model.dec_degrees,
            area_sq_deg=model.area_sq_deg or 0.0,
            brightest_star=model.brightest_star or "",
            magnitude=magnitude,
            season=model.season or "",
            hemisphere=hemisphere,
            description=description,
        )
        constellations.append(constellation)
    return constellations


async def get_famous_asterisms(db_session: AsyncSession) -> list[Asterism]:
    """
    Get list of famous asterisms from database.

    Args:
        db_session: Database session

    Returns:
        List of Asterism objects

    Raises:
        RuntimeError: If no asterisms found in database (seed data required)
    """
    from sqlalchemy import func, select

    from .models import AsterismModel

    count = await db_session.scalar(select(func.count(AsterismModel.id)))
    if count == 0:
        raise RuntimeError("No asterisms found in database. Please seed the database by running: nexstar data seed")

    result = await db_session.execute(select(AsterismModel))
    models = result.scalars().all()

    asterisms = []
    for model in models:
        # Parse alt_names and stars (stored as comma-separated strings)
        alt_names = model.alt_names.split(",") if model.alt_names else []
        member_stars = model.stars.split(",") if model.stars else []

        # Calculate hemisphere from declination
        if model.dec_degrees > 30:
            hemisphere = "Northern"
        elif model.dec_degrees < -30:
            hemisphere = "Southern"
        else:
            hemisphere = "Equatorial"

        asterism = Asterism(
            name=model.name,
            alt_names=alt_names,
            ra_hours=model.ra_hours,
            dec_degrees=model.dec_degrees,
            size_degrees=model.size_degrees or 0.0,
            parent_constellation=model.parent_constellation or "",
            season=model.season or "",
            hemisphere=hemisphere,
            member_stars=member_stars,
            description=model.description or "",
        )
        asterisms.append(asterism)
    return asterisms


async def get_visible_constellations(
    db_session: AsyncSession,
    latitude: float,
    longitude: float,
    observation_time: datetime | None = None,
    min_altitude_deg: float = 20.0,
) -> list[tuple[Constellation, float, float]]:
    """
    Get constellations visible above horizon at given time.

    Args:
        db_session: Database session
        latitude: Observer latitude in degrees
        longitude: Observer longitude in degrees
        observation_time: Time of observation (default: now)
        min_altitude_deg: Minimum altitude for visibility (default: 20°)

    Returns:
        List of (Constellation, altitude_deg, azimuth_deg) tuples sorted by altitude
    """
    if observation_time is None:
        observation_time = datetime.now(UTC)
    elif observation_time.tzinfo is None:
        observation_time = observation_time.replace(tzinfo=UTC)
    else:
        observation_time = observation_time.astimezone(UTC)

    visible = []

    constellations = await get_prominent_constellations(db_session)
    for constellation in constellations:
        # Calculate altitude and azimuth
        alt, az = ra_dec_to_alt_az(
            constellation.ra_hours,
            constellation.dec_degrees,
            latitude,
            longitude,
            observation_time,
        )

        if alt >= min_altitude_deg:
            visible.append((constellation, alt, az))

    # Sort by altitude (highest first)
    visible.sort(key=lambda x: x[1], reverse=True)

    return visible


async def get_visible_asterisms(
    db_session: AsyncSession,
    latitude: float,
    longitude: float,
    observation_time: datetime | None = None,
    min_altitude_deg: float = 20.0,
) -> list[tuple[Asterism, float, float]]:
    """
    Get asterisms visible above horizon at given time.

    Args:
        db_session: Database session
        latitude: Observer latitude in degrees
        longitude: Observer longitude in degrees
        observation_time: Time of observation (default: now)
        min_altitude_deg: Minimum altitude for visibility (default: 20°)

    Returns:
        List of (Asterism, altitude_deg, azimuth_deg) tuples sorted by altitude
    """
    if observation_time is None:
        observation_time = datetime.now(UTC)
    elif observation_time.tzinfo is None:
        observation_time = observation_time.replace(tzinfo=UTC)
    else:
        observation_time = observation_time.astimezone(UTC)

    visible = []

    asterisms = await get_famous_asterisms(db_session)
    for asterism in asterisms:
        # Calculate altitude and azimuth
        alt, az = ra_dec_to_alt_az(
            asterism.ra_hours,
            asterism.dec_degrees,
            latitude,
            longitude,
            observation_time,
        )

        if alt >= min_altitude_deg:
            visible.append((asterism, alt, az))

    # Sort by altitude (highest first)
    visible.sort(key=lambda x: x[1], reverse=True)

    return visible


def populate_constellation_database(db_session: Session) -> None:
    """
    Populate database with constellation and asterism data.

    This should be called once to initialize the database with static data.
    Now uses seed data from JSON files instead of hardcoded Python data.

    Args:
        db_session: SQLAlchemy database session
    """
    import asyncio

    from .database_seeder import seed_asterisms, seed_constellations
    from .models import get_db_session

    logger.info("Populating constellation database...")

    async def _seed() -> None:
        async with get_db_session() as async_session:
            await seed_constellations(async_session, force=True)
            await seed_asterisms(async_session, force=True)

    asyncio.run(_seed())

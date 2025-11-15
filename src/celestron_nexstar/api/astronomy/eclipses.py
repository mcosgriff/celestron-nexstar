"""
Lunar and Solar Eclipse Predictions

Provides eclipse predictions including visibility from observer location,
path of totality for solar eclipses, and best viewing conditions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

# skyfield is a required dependency
from skyfield.api import Topos


if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from celestron_nexstar.api.location.observer import ObserverLocation

logger = logging.getLogger(__name__)

__all__ = [
    "Eclipse",
    "EclipseType",
    "get_next_lunar_eclipse",
    "get_next_solar_eclipse",
    "get_upcoming_eclipses",
]


@dataclass
class Eclipse:
    """Information about a lunar or solar eclipse."""

    eclipse_type: (
        str  # "lunar_total", "lunar_partial", "lunar_penumbral", "solar_total", "solar_partial", "solar_annular"
    )
    date: datetime
    maximum_time: datetime  # Time of maximum eclipse
    duration_minutes: float  # Duration of eclipse in minutes
    magnitude: float  # Eclipse magnitude (0.0-1.0+)
    is_visible: bool  # Whether eclipse is visible from observer location
    visibility_start: datetime | None  # When eclipse becomes visible
    visibility_end: datetime | None  # When eclipse ends
    altitude_at_maximum: float  # Altitude of moon/sun at maximum eclipse
    notes: str  # Additional information


class EclipseType:
    """Eclipse type constants."""

    LUNAR_TOTAL = "lunar_total"
    LUNAR_PARTIAL = "lunar_partial"
    LUNAR_PENUMBRAL = "lunar_penumbral"
    SOLAR_TOTAL = "solar_total"
    SOLAR_PARTIAL = "solar_partial"
    SOLAR_ANNULAR = "solar_annular"


def _get_skyfield_objects() -> tuple[Any, Any, Any, Any | None, Any] | tuple[None, None, None, None, None]:
    """Get Skyfield objects for calculations."""

    try:
        from celestron_nexstar.api.ephemeris.skyfield_utils import get_skyfield_loader

        loader = get_skyfield_loader()
        ts = loader.timescale()

        # Load ephemeris - de421 includes Moon
        try:
            eph = loader("de421.bsp")
        except FileNotFoundError:
            logger.warning("de421.bsp not found, eclipse calculations may fail")
            return None, None, None, None, None

        earth = eph["earth"]
        sun = eph["sun"]
        try:
            moon = eph["moon"]
        except KeyError:
            moon = None

        return ts, earth, sun, moon, eph
    except Exception as e:
        logger.error(f"Error loading Skyfield data: {e}")
        return None, None, None, None, None


def _calculate_lunar_eclipse(
    observer_lat: float,
    observer_lon: float,
    eclipse_time: datetime,
    eclipse_type: str,
    magnitude: float,
    ts: Any,
    earth: Any,
    sun: Any,
    moon: Any | None,
) -> Eclipse | None:
    """
    Calculate lunar eclipse details for a specific time.

    Args:
        observer_lat: Observer latitude
        observer_lon: Observer longitude
        eclipse_time: Time of eclipse
        eclipse_type: Type of eclipse
        magnitude: Eclipse magnitude
        ts: Skyfield timescale
        earth: Skyfield earth object
        sun: Skyfield sun object
        moon: Skyfield moon object

    Returns:
        Eclipse object or None if calculation fails
    """
    try:
        t = ts.from_datetime(eclipse_time.replace(tzinfo=UTC))
        observer = earth + Topos(latitude_degrees=observer_lat, longitude_degrees=observer_lon)

        # Get moon position
        moon_astrometric = observer.at(t).observe(moon)
        moon_alt, _moon_az, _ = moon_astrometric.apparent().altaz()

        # For lunar eclipse, check if moon is above horizon
        is_visible = moon_alt.degrees > 0

        # Determine duration and notes based on type
        if eclipse_type == "lunar_total":
            duration_minutes = 180.0  # Typical total lunar eclipse duration
            notes = "Total lunar eclipse - moon fully in Earth's shadow"
        elif eclipse_type == "lunar_partial":
            duration_minutes = 200.0  # Partial eclipses last longer
            notes = f"Partial lunar eclipse - {magnitude:.0%} of moon in shadow"
        else:  # penumbral
            duration_minutes = 240.0
            notes = "Penumbral lunar eclipse - subtle darkening"

        return Eclipse(
            eclipse_type=eclipse_type,
            date=eclipse_time,
            maximum_time=eclipse_time,
            duration_minutes=duration_minutes,
            magnitude=magnitude,
            is_visible=is_visible,
            visibility_start=eclipse_time - timedelta(minutes=duration_minutes / 2) if is_visible else None,
            visibility_end=eclipse_time + timedelta(minutes=duration_minutes / 2) if is_visible else None,
            altitude_at_maximum=moon_alt.degrees,
            notes=notes,
        )
    except Exception as e:
        logger.error(f"Error calculating lunar eclipse: {e}")
        return None


def _get_moon_phase_at_time(ts: Any, earth: Any, sun: Any, moon: Any | None, t: Any) -> float:
    """Get moon phase (illumination) at a specific time."""
    try:
        import math

        sun_pos = earth.at(t).observe(sun).position.au
        moon_pos = earth.at(t).observe(moon).position.au

        dot = sum(sun_pos[i] * moon_pos[i] for i in range(3))
        sun_dist = math.sqrt(sum(sun_pos[i] ** 2 for i in range(3)))
        moon_dist = math.sqrt(sum(moon_pos[i] ** 2 for i in range(3)))
        cos_angle = dot / (sun_dist * moon_dist)
        cos_angle = max(-1.0, min(1.0, cos_angle))
        phase_angle = math.acos(cos_angle)
        illumination = (1.0 - math.cos(phase_angle)) / 2.0
        return illumination
    except Exception:
        return 0.5


async def get_next_lunar_eclipse(
    db_session: AsyncSession,
    location: ObserverLocation,
    years_ahead: int = 5,
) -> list[Eclipse]:
    """
    Find next lunar eclipses visible from observer location.

    Uses known eclipse data from NASA's Five Millennium Catalog.

    Args:
        location: Observer location
        years_ahead: How many years ahead to search (default: 5)

    Returns:
        List of Eclipse objects, sorted by date
    """

    ts, earth, sun, moon, eph = _get_skyfield_objects()
    if ts is None or eph is None:
        return []

    eclipses = []
    now = datetime.now(UTC)
    end_date = now + timedelta(days=365 * years_ahead)

    known_eclipses = await get_known_eclipses(db_session)
    for eclipse_data in known_eclipses:
        eclipse_type = eclipse_data["type"]
        eclipse_date = eclipse_data["date"]
        magnitude = eclipse_data["magnitude"]
        if (
            isinstance(eclipse_type, str)
            and eclipse_type.startswith("lunar")
            and isinstance(eclipse_date, datetime)
            and isinstance(magnitude, (int, float))
        ) and now <= eclipse_date <= end_date:
            eclipse = _calculate_lunar_eclipse(
                location.latitude,
                location.longitude,
                eclipse_date,
                eclipse_type,
                float(magnitude),
                ts,
                earth,
                sun,
                moon,
            )
            if eclipse:
                eclipses.append(eclipse)

    return eclipses


# NOTE: Eclipse data is now stored in database seed files.
# See get_known_eclipses() which loads from database.
# To regenerate seed files, run: python scripts/create_seed_files.py
# Data from NASA's Five Millennium Catalog


async def get_known_eclipses(db_session: AsyncSession) -> list[dict[str, Any]]:
    """
    Get list of known eclipses from database.

    Args:
        db_session: Database session

    Returns:
        List of dicts with keys: type, date, magnitude

    Raises:
        RuntimeError: If no eclipses found in database (seed data required)
    """
    from sqlalchemy import func, select

    from celestron_nexstar.api.core.exceptions import DatabaseError
    from celestron_nexstar.api.database.models import EclipseModel

    count = await db_session.scalar(select(func.count(EclipseModel.id)))
    if count == 0:
        raise DatabaseError("No eclipses found in database. Please seed the database by running: nexstar data seed")

    result = await db_session.execute(select(EclipseModel))
    models = result.scalars().all()

    eclipses = []
    for model in models:
        eclipses.append(
            {
                "type": model.eclipse_type,
                "date": model.date,
                "magnitude": model.magnitude,
            }
        )
    return eclipses


async def get_next_solar_eclipse(
    db_session: AsyncSession,
    location: ObserverLocation,
    years_ahead: int = 10,
) -> list[Eclipse]:
    """
    Find next solar eclipses visible from observer location.

    Args:
        location: Observer location
        years_ahead: How many years ahead to search (default: 10)

    Returns:
        List of Eclipse objects, sorted by date
    """

    ts, earth, sun, moon, eph = _get_skyfield_objects()
    if ts is None or eph is None:
        return []

    eclipses = []
    now = datetime.now(UTC)
    end_date = now + timedelta(days=365 * years_ahead)

    known_eclipses = await get_known_eclipses(db_session)
    for eclipse_data in known_eclipses:
        eclipse_type = eclipse_data["type"]
        eclipse_date = eclipse_data["date"]
        magnitude = eclipse_data["magnitude"]
        if (
            isinstance(eclipse_type, str)
            and eclipse_type.startswith("solar")
            and isinstance(eclipse_date, datetime)
            and isinstance(magnitude, (int, float))
        ) and now <= eclipse_date <= end_date:
            eclipse = _calculate_solar_eclipse(
                location.latitude,
                location.longitude,
                eclipse_date,
                eclipse_type,
                float(magnitude),
                ts,
                earth,
                sun,
                moon,
            )
            if eclipse:
                eclipses.append(eclipse)

    return eclipses


def _calculate_solar_eclipse(
    observer_lat: float,
    observer_lon: float,
    eclipse_time: datetime,
    eclipse_type: str,
    magnitude: float,
    ts: Any,
    earth: Any,
    sun: Any,
    moon: Any | None,
) -> Eclipse | None:
    """
    Calculate solar eclipse details for a specific time.

    Args:
        observer_lat: Observer latitude
        observer_lon: Observer longitude
        eclipse_time: Time of eclipse
        eclipse_type: Type of eclipse
        magnitude: Eclipse magnitude
        ts: Skyfield timescale
        earth: Skyfield earth object
        sun: Skyfield sun object
        moon: Skyfield moon object

    Returns:
        Eclipse object or None if calculation fails
    """
    try:
        t = ts.from_datetime(eclipse_time.replace(tzinfo=UTC))
        observer = earth + Topos(latitude_degrees=observer_lat, longitude_degrees=observer_lon)

        # Get sun position
        sun_astrometric = observer.at(t).observe(sun)
        sun_alt, _sun_az, _ = sun_astrometric.apparent().altaz()

        # For solar eclipse, sun must be above horizon
        is_visible = sun_alt.degrees > 0

        # Determine duration (varies by type and location)
        if eclipse_type == "solar_total":
            duration_minutes = 2.0  # Typical total eclipse duration (varies by location)
            notes = "Total solar eclipse - requires special eye protection"
        elif eclipse_type == "solar_annular":
            duration_minutes = 3.0  # Typical annular eclipse duration
            notes = "Annular solar eclipse - requires special eye protection"
        else:  # partial
            duration_minutes = 120.0  # Partial eclipses last longer
            notes = f"Partial solar eclipse ({magnitude:.0%} coverage) - requires special eye protection"

        return Eclipse(
            eclipse_type=eclipse_type,
            date=eclipse_time,
            maximum_time=eclipse_time,
            duration_minutes=duration_minutes,
            magnitude=magnitude,
            is_visible=is_visible,
            visibility_start=eclipse_time - timedelta(minutes=duration_minutes / 2) if is_visible else None,
            visibility_end=eclipse_time + timedelta(minutes=duration_minutes / 2) if is_visible else None,
            altitude_at_maximum=sun_alt.degrees,
            notes=notes,
        )
    except Exception as e:
        logger.error(f"Error calculating solar eclipse: {e}")
        return None


async def get_upcoming_eclipses(
    db_session: AsyncSession,
    location: ObserverLocation,
    years_ahead: int = 5,
    eclipse_type: str | None = None,
) -> list[Eclipse]:
    """
    Get all upcoming eclipses (lunar and solar) visible from location.

    Args:
        db_session: Database session
        location: Observer location
        years_ahead: How many years ahead to search
        eclipse_type: Filter by type ("lunar" or "solar"), or None for all

    Returns:
        List of Eclipse objects, sorted by date
    """
    all_eclipses: list[Eclipse] = []

    if eclipse_type is None or eclipse_type == "lunar":
        lunar_eclipses = await get_next_lunar_eclipse(db_session, location, years_ahead=years_ahead)
        all_eclipses.extend(lunar_eclipses)

    if eclipse_type is None or eclipse_type == "solar":
        solar_eclipses = await get_next_solar_eclipse(db_session, location, years_ahead=years_ahead)
        all_eclipses.extend(solar_eclipses)

    # Sort by date
    all_eclipses.sort(key=lambda e: e.date)

    return all_eclipses

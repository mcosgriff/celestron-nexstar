"""
Meteor Shower Calendar

Static data for major annual meteor showers with activity periods, peak dates,
and radiant positions. Useful for planning naked-eye observing sessions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from celestron_nexstar.api.core.utils import ra_dec_to_alt_az


logger = logging.getLogger(__name__)

__all__ = [
    "MeteorShower",
    "get_active_showers",
    "get_all_meteor_showers",
    "get_peak_showers",
    "populate_meteor_shower_database",
]


@dataclass(frozen=True)
class MeteorShower:
    """A meteor shower with timing and characteristics."""

    name: str
    activity_start_month: int  # Month when shower begins (1-12)
    activity_start_day: int  # Day when shower begins
    activity_end_month: int  # Month when shower ends (1-12)
    activity_end_day: int  # Day when shower ends
    peak_month: int  # Month of peak activity
    peak_day: int  # Day of peak activity
    peak_end_month: int  # Month when peak ends (often same as peak_month)
    peak_end_day: int  # Day when peak ends (often same as peak_day)
    zhr_peak: int  # Zenithal Hourly Rate at peak (meteors per hour under ideal conditions)
    velocity_km_s: int  # Meteor velocity in km/s
    radiant_ra_hours: float  # Right ascension of radiant (hours)
    radiant_dec_degrees: float  # Declination of radiant (degrees)
    parent_comet: str | None  # Parent comet/asteroid (if known)
    description: str  # Notable characteristics


# NOTE: Meteor shower data is now stored in database seed files.
# See get_all_meteor_showers() which loads from database.
# To regenerate seed files, run: python scripts/create_seed_files.py
# Data from IMO (International Meteor Organization) and reliable sources


def get_all_meteor_showers(db_session: None = None) -> list[MeteorShower]:  # db_session deprecated
    """
    Get list of all major meteor showers from database.

    Args:
        db_session: Deprecated parameter, kept for compatibility

    Returns:
        List of MeteorShower objects

    Raises:
        RuntimeError: If no meteor showers found in database (seed data required)
    """
    from celestron_nexstar.api.core.exceptions import DatabaseError
    from celestron_nexstar.api.database.duckdb_access import get_all_meteor_showers as get_all_meteor_showers_db

    showers_db = get_all_meteor_showers_db()
    if not showers_db:
        raise DatabaseError(
            "No meteor showers found in database. Please seed the database by running: nexstar data seed"
        )

    return [
        MeteorShower(
            name=s.name,
            activity_start_month=s.activity_start_month,  # Property maps to start_month
            activity_start_day=s.activity_start_day,  # Property maps to start_day
            activity_end_month=s.activity_end_month,  # Property maps to end_month
            activity_end_day=s.activity_end_day,  # Property maps to end_day
            peak_month=s.peak_month,
            peak_day=s.peak_day,
            peak_end_month=s.peak_end_month,  # Property maps to peak_month
            peak_end_day=s.peak_end_day,  # Property maps to peak_day
            zhr_peak=s.zhr_peak,
            velocity_km_s=int(s.velocity_km_s) if s.velocity_km_s is not None else 0,
            radiant_ra_hours=s.radiant_ra_hours,
            radiant_dec_degrees=s.radiant_dec_degrees,
            parent_comet=s.parent_comet,
            description=s.description,  # Property maps to notes
        )
        for s in showers_db
    ]


def _is_date_in_range(
    check_month: int,
    check_day: int,
    start_month: int,
    start_day: int,
    end_month: int,
    end_day: int,
) -> bool:
    """
    Check if a date falls within a date range (handles year wraparound).

    Args:
        check_month: Month to check (1-12)
        check_day: Day to check
        start_month: Range start month (1-12)
        start_day: Range start day
        end_month: Range end month (1-12)
        end_day: Range end day

    Returns:
        True if date is in range
    """
    # Convert to day-of-year for comparison (approximate)
    check_doy = check_month * 100 + check_day
    start_doy = start_month * 100 + start_day
    end_doy = end_month * 100 + end_day

    if start_doy <= end_doy:
        # Normal range (e.g., April 14 to April 30)
        return start_doy <= check_doy <= end_doy
    else:
        # Wraparound range (e.g., Dec 28 to Jan 12)
        return check_doy >= start_doy or check_doy <= end_doy


async def get_active_showers(
    date: datetime | None = None, db_session: None = None
) -> list[MeteorShower]:  # db_session deprecated
    """
    Get meteor showers active on a given date.

    Args:
        date: Date to check (default: today)
        db_session: Deprecated parameter, kept for compatibility

    Returns:
        List of active meteor showers
    """
    if date is None:
        date = datetime.now(UTC)

    month = date.month
    day = date.day

    active = []
    showers = get_all_meteor_showers()
    for shower in showers:
        if _is_date_in_range(
            month,
            day,
            shower.activity_start_month,
            shower.activity_start_day,
            shower.activity_end_month,
            shower.activity_end_day,
        ):
            active.append(shower)

    return active


async def get_peak_showers(
    date: datetime | None = None,
    tolerance_days: int = 2,
    db_session: None = None,  # Deprecated, kept for compatibility
) -> list[MeteorShower]:
    """
    Get meteor showers at or near peak on a given date.

    Args:
        date: Date to check (default: today)
        tolerance_days: How many days before/after peak to include (default: 2)
        db_session: Deprecated parameter, kept for compatibility

    Returns:
        List of meteor showers at/near peak
    """
    if date is None:
        date = datetime.now(UTC)

    month = date.month
    day = date.day

    # Calculate date range (approximation)
    start_month = month
    start_day = max(1, day - tolerance_days)

    end_month = month
    end_day = day + tolerance_days

    # Handle month boundaries (simplified - doesn't handle year wraparound perfectly)
    if start_day < 1:
        start_month = month - 1 if month > 1 else 12
        start_day = 28 + start_day  # Approximate

    if end_day > 28:  # Conservative
        end_month = month + 1 if month < 12 else 1
        end_day = end_day - 28

    peak = []
    showers = get_all_meteor_showers()
    for shower in showers:
        # Check if shower peak overlaps with our date range
        if _is_date_in_range(
            shower.peak_month,
            shower.peak_day,
            start_month,
            start_day,
            end_month,
            end_day,
        ) or _is_date_in_range(
            month,
            day,
            shower.peak_month,
            shower.peak_day,
            shower.peak_end_month,
            shower.peak_end_day,
        ):
            peak.append(shower)

    return peak


def get_radiant_position(
    shower: MeteorShower,
    latitude: float,
    longitude: float,
    observation_time: datetime | None = None,
) -> tuple[float, float]:
    """
    Calculate radiant position (alt/az) for a meteor shower.

    Args:
        shower: Meteor shower
        latitude: Observer latitude in degrees
        longitude: Observer longitude in degrees
        observation_time: Time of observation (default: now)

    Returns:
        Tuple of (altitude_deg, azimuth_deg)
    """
    if observation_time is None:
        observation_time = datetime.now(UTC)
    elif observation_time.tzinfo is None:
        observation_time = observation_time.replace(tzinfo=UTC)
    else:
        observation_time = observation_time.astimezone(UTC)

    alt, az = ra_dec_to_alt_az(
        shower.radiant_ra_hours,
        shower.radiant_dec_degrees,
        latitude,
        longitude,
        observation_time,
    )

    return alt, az


def populate_meteor_shower_database(db_session: None = None) -> None:  # db_session deprecated
    """
    Populate database with meteor shower data.

    This should be called once to initialize the database with static data.
    Now uses seed data from JSON files instead of hardcoded Python data.

    Args:
        db_session: Deprecated parameter, kept for compatibility
    """
    from celestron_nexstar.api.database.duckdb_seeder import seed_meteor_showers_duckdb

    logger.info("Populating meteor shower database...")
    seed_meteor_showers_duckdb(force=True)

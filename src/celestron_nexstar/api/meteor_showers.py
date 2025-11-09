"""
Meteor Shower Calendar

Static data for major annual meteor showers with activity periods, peak dates,
and radiant positions. Useful for planning naked-eye observing sessions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from .utils import ra_dec_to_alt_az


if TYPE_CHECKING:
    from sqlalchemy.orm import Session


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


# Major annual meteor showers
# Data from IMO (International Meteor Organization) and reliable sources
METEOR_SHOWERS = [
    MeteorShower(
        name="Quadrantids",
        activity_start_month=12,
        activity_start_day=28,
        activity_end_month=1,
        activity_end_day=12,
        peak_month=1,
        peak_day=3,
        peak_end_month=1,
        peak_end_day=4,
        zhr_peak=120,
        velocity_km_s=41,
        radiant_ra_hours=15.3,
        radiant_dec_degrees=49.5,
        parent_comet="2003 EH1 (asteroid)",
        description="Strong shower with short peak. Best viewed after midnight. Named for obsolete constellation Quadrans Muralis",
    ),
    MeteorShower(
        name="Lyrids",
        activity_start_month=4,
        activity_start_day=14,
        activity_end_month=4,
        activity_end_day=30,
        peak_month=4,
        peak_day=22,
        peak_end_month=4,
        peak_end_day=23,
        zhr_peak=18,
        velocity_km_s=49,
        radiant_ra_hours=18.1,
        radiant_dec_degrees=34.0,
        parent_comet="C/1861 G1 Thatcher",
        description="Moderate shower with occasional outbursts. Ancient shower observed for 2700 years. Radiant near Vega",
    ),
    MeteorShower(
        name="Eta Aquariids",
        activity_start_month=4,
        activity_start_day=19,
        activity_end_month=5,
        activity_end_day=28,
        peak_month=5,
        peak_day=6,
        peak_end_month=5,
        peak_end_day=7,
        zhr_peak=50,
        velocity_km_s=66,
        radiant_ra_hours=22.5,
        radiant_dec_degrees=-1.0,
        parent_comet="1P/Halley",
        description="Fast meteors with persistent trains. Best viewed from southern hemisphere. Dawn shower",
    ),
    MeteorShower(
        name="Southern Delta Aquariids",
        activity_start_month=7,
        activity_start_day=12,
        activity_end_month=8,
        activity_end_day=23,
        peak_month=7,
        peak_day=30,
        peak_end_month=7,
        peak_end_day=31,
        zhr_peak=25,
        velocity_km_s=41,
        radiant_ra_hours=22.6,
        radiant_dec_degrees=-16.0,
        parent_comet="96P/Machholz",
        description="Reliable summer shower. Best from southern hemisphere. Faint meteors with few fireballs",
    ),
    MeteorShower(
        name="Alpha Capricornids",
        activity_start_month=7,
        activity_start_day=3,
        activity_end_month=8,
        activity_end_day=15,
        peak_month=7,
        peak_day=30,
        peak_end_month=7,
        peak_end_day=31,
        zhr_peak=5,
        velocity_km_s=23,
        radiant_ra_hours=20.3,
        radiant_dec_degrees=-10.0,
        parent_comet="169P/NEAT",
        description="Weak but notable for bright fireballs. Slow meteors. Often overlaps with Delta Aquariids",
    ),
    MeteorShower(
        name="Perseids",
        activity_start_month=7,
        activity_start_day=17,
        activity_end_month=8,
        activity_end_day=24,
        peak_month=8,
        peak_day=12,
        peak_end_month=8,
        peak_end_day=13,
        zhr_peak=100,
        velocity_km_s=59,
        radiant_ra_hours=3.1,
        radiant_dec_degrees=58.0,
        parent_comet="109P/Swift-Tuttle",
        description="Most popular meteor shower. Warm nights, high rates, bright meteors. Consistent and reliable",
    ),
    MeteorShower(
        name="Draconids",
        activity_start_month=10,
        activity_start_day=6,
        activity_end_month=10,
        activity_end_day=10,
        peak_month=10,
        peak_day=8,
        peak_end_month=10,
        peak_end_day=9,
        zhr_peak=10,
        velocity_km_s=20,
        radiant_ra_hours=17.5,
        radiant_dec_degrees=54.0,
        parent_comet="21P/Giacobini-Zinner",
        description="Usually weak but has produced storms. Best viewed in early evening. Very slow meteors",
    ),
    MeteorShower(
        name="Orionids",
        activity_start_month=10,
        activity_start_day=2,
        activity_end_month=11,
        activity_end_day=7,
        peak_month=10,
        peak_day=21,
        peak_end_month=10,
        peak_end_day=22,
        zhr_peak=20,
        velocity_km_s=66,
        radiant_ra_hours=6.3,
        radiant_dec_degrees=16.0,
        parent_comet="1P/Halley",
        description="Fast meteors from Halley's Comet. Persistent trains common. Broad peak lasting several days",
    ),
    MeteorShower(
        name="Southern Taurids",
        activity_start_month=9,
        activity_start_day=10,
        activity_end_month=11,
        activity_end_day=20,
        peak_month=10,
        peak_day=10,
        peak_end_month=10,
        peak_end_day=11,
        zhr_peak=5,
        velocity_km_s=27,
        radiant_ra_hours=3.4,
        radiant_dec_degrees=9.0,
        parent_comet="2P/Encke",
        description="Long-lasting shower with bright fireballs. Very slow meteors. Part of Taurid complex",
    ),
    MeteorShower(
        name="Northern Taurids",
        activity_start_month=10,
        activity_start_day=20,
        activity_end_month=12,
        activity_end_day=10,
        peak_month=11,
        peak_day=12,
        peak_end_month=11,
        peak_end_day=13,
        zhr_peak=5,
        velocity_km_s=29,
        radiant_ra_hours=3.9,
        radiant_dec_degrees=22.0,
        parent_comet="2P/Encke",
        description="Companion to Southern Taurids. Known for fireballs. Long activity period",
    ),
    MeteorShower(
        name="Leonids",
        activity_start_month=11,
        activity_start_day=6,
        activity_end_month=11,
        activity_end_day=30,
        peak_month=11,
        peak_day=17,
        peak_end_month=11,
        peak_end_day=18,
        zhr_peak=15,
        velocity_km_s=71,
        radiant_ra_hours=10.1,
        radiant_dec_degrees=22.0,
        parent_comet="55P/Tempel-Tuttle",
        description="Fast meteors. Famous for meteor storms every 33 years. Last storm in 1999-2002",
    ),
    MeteorShower(
        name="Geminids",
        activity_start_month=12,
        activity_start_day=4,
        activity_end_month=12,
        activity_end_day=20,
        peak_month=12,
        peak_day=14,
        peak_end_month=12,
        peak_end_day=15,
        zhr_peak=150,
        velocity_km_s=35,
        radiant_ra_hours=7.5,
        radiant_dec_degrees=32.0,
        parent_comet="3200 Phaethon (asteroid)",
        description="Best shower of the year. High rates, bright meteors, all night viewing. Multi-colored meteors",
    ),
    MeteorShower(
        name="Ursids",
        activity_start_month=12,
        activity_start_day=17,
        activity_end_month=12,
        activity_end_day=26,
        peak_month=12,
        peak_day=22,
        peak_end_month=12,
        peak_end_day=23,
        zhr_peak=10,
        velocity_km_s=33,
        radiant_ra_hours=14.5,
        radiant_dec_degrees=75.0,
        parent_comet="8P/Tuttle",
        description="Minor shower but can surprise with outbursts. Radiant near Little Dipper. Best after midnight",
    ),
]


def get_all_meteor_showers() -> list[MeteorShower]:
    """Get list of all major meteor showers."""
    return METEOR_SHOWERS


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


def get_active_showers(date: datetime | None = None) -> list[MeteorShower]:
    """
    Get meteor showers active on a given date.

    Args:
        date: Date to check (default: today)

    Returns:
        List of active meteor showers
    """
    if date is None:
        date = datetime.now(UTC)

    month = date.month
    day = date.day

    active = []
    for shower in METEOR_SHOWERS:
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


def get_peak_showers(
    date: datetime | None = None,
    tolerance_days: int = 2,
) -> list[MeteorShower]:
    """
    Get meteor showers at or near peak on a given date.

    Args:
        date: Date to check (default: today)
        tolerance_days: How many days before/after peak to include (default: 2)

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
    for shower in METEOR_SHOWERS:
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


def populate_meteor_shower_database(db_session: Session) -> None:
    """
    Populate database with meteor shower data.

    This should be called once to initialize the database with static data.

    Args:
        db_session: SQLAlchemy database session
    """
    from .models import MeteorShowerModel

    logger.info("Populating meteor shower database...")

    # Clear existing data
    db_session.query(MeteorShowerModel).delete()

    # Add meteor showers
    for shower in METEOR_SHOWERS:
        model = MeteorShowerModel(
            name=shower.name,
            activity_start_month=shower.activity_start_month,
            activity_start_day=shower.activity_start_day,
            activity_end_month=shower.activity_end_month,
            activity_end_day=shower.activity_end_day,
            peak_month=shower.peak_month,
            peak_day=shower.peak_day,
            peak_end_month=shower.peak_end_month,
            peak_end_day=shower.peak_end_day,
            zhr_peak=shower.zhr_peak,
            velocity_km_s=shower.velocity_km_s,
            radiant_ra_hours=shower.radiant_ra_hours,
            radiant_dec_degrees=shower.radiant_dec_degrees,
            parent_comet=shower.parent_comet,
            description=shower.description,
        )
        db_session.add(model)

    db_session.commit()
    logger.info(f"Added {len(METEOR_SHOWERS)} meteor showers to database")

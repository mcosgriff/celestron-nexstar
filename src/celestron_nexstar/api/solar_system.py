"""
Solar System Calculations

Calculations for Sun and Moon positions, phases, and events.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import NamedTuple

from skyfield.api import Loader, Topos, load


logger = logging.getLogger(__name__)

__all__ = [
    "MoonInfo",
    "SunInfo",
    "calculate_moon_phase",
    "get_moon_info",
    "get_sun_info",
]


class MoonInfo(NamedTuple):
    """Moon information."""

    phase_name: str  # "New", "Waxing Crescent", "First Quarter", etc.
    illumination: float  # 0.0 to 1.0 (0 = new moon, 1 = full moon)
    altitude_deg: float  # Current altitude above horizon
    azimuth_deg: float  # Current azimuth
    ra_hours: float  # Right ascension
    dec_degrees: float  # Declination


class SunInfo(NamedTuple):
    """Sun information."""

    altitude_deg: float  # Current altitude above horizon
    azimuth_deg: float  # Current azimuth
    ra_hours: float  # Right ascension
    dec_degrees: float  # Declination
    sunset_time: datetime | None  # Next sunset (local time)
    sunrise_time: datetime | None  # Next sunrise (local time)
    is_daytime: bool  # True if sun is above horizon


def _get_skyfield_objects():
    """Get Skyfield Earth, Sun, and Moon objects."""
    try:
        skyfield_dir = _get_skyfield_directory()
        loader = Loader(str(skyfield_dir))
        ts = load.timescale()

        # Load ephemeris - de421 includes Moon
        try:
            eph = loader("de421.bsp")
        except FileNotFoundError:
            logger.warning("de421.bsp not found, moon calculations may fail")
            # Fallback to de440s (no moon) for sun only
            eph = loader("de440s.bsp")

        earth = eph["earth"]
        sun = eph["sun"]
        try:
            moon = eph["moon"]
        except KeyError:
            moon = None

        return ts, earth, sun, moon
    except Exception as e:
        logger.error(f"Failed to load Skyfield objects: {e}")
        return None, None, None, None


def _get_skyfield_directory():
    """Get the Skyfield cache directory."""
    from pathlib import Path

    return Path.home() / ".skyfield"


def calculate_moon_phase(illumination: float) -> str:
    """
    Calculate moon phase name from illumination percentage.

    Args:
        illumination: Illumination fraction (0.0 to 1.0)

    Returns:
        Phase name string
    """
    if illumination < 0.01:
        return "New Moon"
    elif illumination < 0.25:
        return "Waxing Crescent"
    elif illumination < 0.26:
        return "First Quarter"
    elif illumination < 0.49:
        return "Waxing Gibbous"
    elif illumination < 0.51:
        return "Full Moon"
    elif illumination < 0.74:
        return "Waning Gibbous"
    elif illumination < 0.76:
        return "Last Quarter"
    else:
        return "Waning Crescent"


def get_moon_info(
    observer_lat: float,
    observer_lon: float,
    dt: datetime | None = None,
) -> MoonInfo | None:
    """
    Get current moon information including phase and position.

    Args:
        observer_lat: Observer latitude in degrees
        observer_lon: Observer longitude in degrees
        dt: Datetime to calculate for (default: now)

    Returns:
        MoonInfo or None if calculation fails
    """
    if dt is None:
        dt = datetime.now(UTC)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    try:
        ts, earth, sun, moon = _get_skyfield_objects()
        if ts is None or earth is None or sun is None or moon is None:
            return None

        t = ts.from_datetime(dt)
        observer = earth + Topos(latitude_degrees=observer_lat, longitude_degrees=observer_lon)

        # Get moon position
        astrometric = observer.at(t).observe(moon)
        alt, az, _distance = astrometric.apparent().altaz()
        moon_alt = alt.degrees
        moon_az = az.degrees

        # Get moon RA/Dec
        ra, dec, _ = astrometric.apparent().radec()
        moon_ra = ra.hours
        moon_dec = dec.degrees

        # Calculate moon phase (illumination) using Skyfield's built-in method
        import math

        # Get positions relative to earth
        sun_astrometric = earth.at(t).observe(sun)
        moon_astrometric = earth.at(t).observe(moon)

        # Calculate elongation angle (angle between sun and moon as seen from earth)
        sun_pos = sun_astrometric.position.au
        moon_pos = moon_astrometric.position.au

        # Dot product to find angle
        dot = sum(sun_pos[i] * moon_pos[i] for i in range(3))
        sun_dist = math.sqrt(sum(sun_pos[i] ** 2 for i in range(3)))
        moon_dist = math.sqrt(sum(moon_pos[i] ** 2 for i in range(3)))
        cos_angle = dot / (sun_dist * moon_dist)

        # Clamp to valid range
        cos_angle = max(-1.0, min(1.0, cos_angle))
        phase_angle = math.acos(cos_angle)

        # Illumination: 0 at new moon (angle = 0), 1 at full moon (angle = pi)
        # Formula: (1 + cos(phase_angle)) / 2
        illumination = (1.0 + math.cos(phase_angle)) / 2.0

        phase_name = calculate_moon_phase(illumination)

        return MoonInfo(
            phase_name=phase_name,
            illumination=illumination,
            altitude_deg=moon_alt,
            azimuth_deg=moon_az,
            ra_hours=moon_ra,
            dec_degrees=moon_dec,
        )
    except Exception as e:
        logger.error(f"Failed to calculate moon info: {e}")
        return None


def get_sun_info(
    observer_lat: float,
    observer_lon: float,
    dt: datetime | None = None,
) -> SunInfo | None:
    """
    Get current sun information including position and sunset/sunrise.

    Args:
        observer_lat: Observer latitude in degrees
        observer_lon: Observer longitude in degrees
        dt: Datetime to calculate for (default: now)

    Returns:
        SunInfo or None if calculation fails
    """
    if dt is None:
        dt = datetime.now(UTC)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    try:
        ts, earth, sun, _moon = _get_skyfield_objects()
        if ts is None or earth is None or sun is None:
            return None

        t = ts.from_datetime(dt)
        observer = earth + Topos(latitude_degrees=observer_lat, longitude_degrees=observer_lon)

        # Get sun position
        astrometric = observer.at(t).observe(sun)
        alt, az, _distance = astrometric.apparent().altaz()
        sun_alt = alt.degrees
        sun_az = az.degrees

        # Get sun RA/Dec
        ra, dec, _ = astrometric.apparent().radec()
        sun_ra = ra.hours
        sun_dec = dec.degrees

        is_daytime = sun_alt > 0

        # Calculate sunset/sunrise
        # Simple approach: sample at hourly intervals to find horizon crossing
        sunset_time = None
        sunrise_time = None

        try:
            # Sample next 48 hours at 1-hour intervals
            for hours_ahead in range(1, 49):
                check_dt = dt + timedelta(hours=hours_ahead)
                t_check = ts.from_datetime(check_dt)
                astrometric_check = observer.at(t_check).observe(sun)
                alt_check, _az_check, _ = astrometric_check.apparent().altaz()
                sun_alt_check = alt_check.degrees

                # Check previous hour for comparison
                prev_dt = check_dt - timedelta(hours=1)
                t_prev = ts.from_datetime(prev_dt)
                astrometric_prev = observer.at(t_prev).observe(sun)
                alt_prev, _az_prev, _ = astrometric_prev.apparent().altaz()
                sun_alt_prev = alt_prev.degrees

                # Sunset: was above, now below
                if is_daytime and sun_alt_prev > 0 and sun_alt_check <= 0 and sunset_time is None:
                    # Approximate sunset as midpoint between samples
                    sunset_time = prev_dt + timedelta(minutes=30)
                    if sunrise_time is not None:
                        break

                # Sunrise: was below, now above
                if not is_daytime and sun_alt_prev <= 0 and sun_alt_check > 0 and sunrise_time is None:
                    # Approximate sunrise as midpoint between samples
                    sunrise_time = prev_dt + timedelta(minutes=30)
                    if sunset_time is not None:
                        break
        except Exception:
            # If calculation fails, leave as None
            pass

        return SunInfo(
            altitude_deg=sun_alt,
            azimuth_deg=sun_az,
            ra_hours=sun_ra,
            dec_degrees=sun_dec,
            sunset_time=sunset_time,
            sunrise_time=sunrise_time,
            is_daytime=is_daytime,
        )
    except Exception as e:
        logger.error(f"Failed to calculate sun info: {e}")
        return None

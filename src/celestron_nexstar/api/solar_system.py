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
    "calculate_golden_hour",
    "calculate_blue_hour",
]


class MoonInfo(NamedTuple):
    """Moon information."""

    phase_name: str  # "New", "Waxing Crescent", "First Quarter", etc.
    illumination: float  # 0.0 to 1.0 (0 = new moon, 1 = full moon)
    altitude_deg: float  # Current altitude above horizon
    azimuth_deg: float  # Current azimuth
    ra_hours: float  # Right ascension
    dec_degrees: float  # Declination
    moonrise_time: datetime | None = None  # Next moonrise
    moonset_time: datetime | None = None  # Next moonset


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

        # Calculate moonrise/moonset
        moonrise_time = None
        moonset_time = None
        is_moon_above = moon_alt > 0

        try:
            # Sample next 48 hours at 1-hour intervals
            for hours_ahead in range(1, 49):
                check_dt = dt + timedelta(hours=hours_ahead)
                t_check = ts.from_datetime(check_dt)
                astrometric_check = observer.at(t_check).observe(moon)
                alt_check, _az_check, _ = astrometric_check.apparent().altaz()
                moon_alt_check = alt_check.degrees

                # Check previous hour for comparison
                prev_dt = check_dt - timedelta(hours=1)
                t_prev = ts.from_datetime(prev_dt)
                astrometric_prev = observer.at(t_prev).observe(moon)
                alt_prev, _az_prev, _ = astrometric_prev.apparent().altaz()
                moon_alt_prev = alt_prev.degrees

                # Moonset: was above, now below
                if is_moon_above and moon_alt_prev > 0 and moon_alt_check <= 0 and moonset_time is None:
                    # Approximate moonset as midpoint between samples
                    moonset_time = prev_dt + timedelta(minutes=30)
                    # Ensure UTC timezone
                    if moonset_time.tzinfo is None:
                        moonset_time = moonset_time.replace(tzinfo=UTC)
                    if moonrise_time is not None:
                        break

                # Moonrise: was below, now above
                if not is_moon_above and moon_alt_prev <= 0 and moon_alt_check > 0 and moonrise_time is None:
                    # Approximate moonrise as midpoint between samples
                    moonrise_time = prev_dt + timedelta(minutes=30)
                    # Ensure UTC timezone
                    if moonrise_time.tzinfo is None:
                        moonrise_time = moonrise_time.replace(tzinfo=UTC)
                    if moonset_time is not None:
                        break
        except Exception:
            # If calculation fails, leave as None
            pass

        return MoonInfo(
            phase_name=phase_name,
            illumination=illumination,
            altitude_deg=moon_alt,
            azimuth_deg=moon_az,
            ra_hours=moon_ra,
            dec_degrees=moon_dec,
            moonrise_time=moonrise_time,
            moonset_time=moonset_time,
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
                    # Ensure UTC timezone
                    if sunset_time.tzinfo is None:
                        sunset_time = sunset_time.replace(tzinfo=UTC)
                    if sunrise_time is not None:
                        break

                # Sunrise: was below, now above
                if not is_daytime and sun_alt_prev <= 0 and sun_alt_check > 0 and sunrise_time is None:
                    # Approximate sunrise as midpoint between samples
                    sunrise_time = prev_dt + timedelta(minutes=30)
                    # Ensure UTC timezone
                    if sunrise_time.tzinfo is None:
                        sunrise_time = sunrise_time.replace(tzinfo=UTC)
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


def calculate_golden_hour(
    observer_lat: float,
    observer_lon: float,
    dt: datetime | None = None,
) -> tuple[datetime | None, datetime | None, datetime | None, datetime | None]:
    """
    Calculate golden hour times (sun altitude between -4° and 6°).

    Golden hour is the period when the sun is between -4° and 6° altitude,
    providing warm, soft lighting ideal for photography.

    Args:
        observer_lat: Observer latitude in degrees
        observer_lon: Observer longitude in degrees
        dt: Datetime to calculate for (default: now)

    Returns:
        Tuple of (evening_start, evening_end, morning_start, morning_end)
        where each can be None if not found
    """
    if dt is None:
        dt = datetime.now(UTC)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    try:
        ts, earth, sun, _moon = _get_skyfield_objects()
        if ts is None or earth is None or sun is None:
            return (None, None, None, None)

        observer = earth + Topos(latitude_degrees=observer_lat, longitude_degrees=observer_lon)

        evening_start = None
        evening_end = None
        morning_start = None
        morning_end = None

        # Get current sun altitude to determine if we're looking for evening or morning
        t = ts.from_datetime(dt)
        astrometric = observer.at(t).observe(sun)
        alt, _az, _ = astrometric.apparent().altaz()
        current_alt = alt.degrees

        # Sample next 48 hours at 10-minute intervals for better precision
        prev_alt = current_alt
        in_evening_gh = False
        in_morning_gh = False
        
        for minutes_ahead in range(0, 48 * 60, 10):
            check_dt = dt + timedelta(minutes=minutes_ahead)
            # Ensure UTC timezone
            if check_dt.tzinfo is None:
                check_dt = check_dt.replace(tzinfo=UTC)
            t_check = ts.from_datetime(check_dt)
            astrometric_check = observer.at(t_check).observe(sun)
            alt_check, _az_check, _ = astrometric_check.apparent().altaz()
            sun_alt_check = alt_check.degrees

            # Evening golden hour: sun descending from 6° to -4°
            if sun_alt_check <= 6 and sun_alt_check >= -4:
                if not in_evening_gh:
                    # Entering evening golden hour
                    if prev_alt > 6:
                        evening_start = check_dt
                        if evening_start.tzinfo is None:
                            evening_start = evening_start.replace(tzinfo=UTC)
                    in_evening_gh = True
                evening_end = check_dt
                if evening_end.tzinfo is None:
                    evening_end = evening_end.replace(tzinfo=UTC)
            elif in_evening_gh and sun_alt_check < -4:
                # Exited evening golden hour
                break

            # Morning golden hour: sun ascending from -4° to 6°
            if sun_alt_check >= -4 and sun_alt_check <= 6:
                if not in_morning_gh:
                    # Entering morning golden hour
                    if prev_alt < -4:
                        morning_start = check_dt
                        if morning_start.tzinfo is None:
                            morning_start = morning_start.replace(tzinfo=UTC)
                    in_morning_gh = True
                morning_end = check_dt
                if morning_end.tzinfo is None:
                    morning_end = morning_end.replace(tzinfo=UTC)
            elif in_morning_gh and sun_alt_check > 6:
                # Exited morning golden hour
                break

            prev_alt = sun_alt_check

        return (evening_start, evening_end, morning_start, morning_end)
    except Exception as e:
        logger.error(f"Failed to calculate golden hour: {e}")
        return (None, None, None, None)


def calculate_blue_hour(
    observer_lat: float,
    observer_lon: float,
    dt: datetime | None = None,
) -> tuple[datetime | None, datetime | None, datetime | None, datetime | None]:
    """
    Calculate blue hour times (sun altitude between -6° and -4°).

    Blue hour is the period when the sun is between -6° and -4° altitude,
    providing cool, blue lighting ideal for photography.

    Args:
        observer_lat: Observer latitude in degrees
        observer_lon: Observer longitude in degrees
        dt: Datetime to calculate for (default: now)

    Returns:
        Tuple of (evening_start, evening_end, morning_start, morning_end)
        where each can be None if not found
    """
    if dt is None:
        dt = datetime.now(UTC)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    try:
        ts, earth, sun, _moon = _get_skyfield_objects()
        if ts is None or earth is None or sun is None:
            return (None, None, None, None)

        observer = earth + Topos(latitude_degrees=observer_lat, longitude_degrees=observer_lon)

        evening_start = None
        evening_end = None
        morning_start = None
        morning_end = None

        # Get current sun altitude to determine if we're looking for evening or morning
        t = ts.from_datetime(dt)
        astrometric = observer.at(t).observe(sun)
        alt, _az, _ = astrometric.apparent().altaz()
        current_alt = alt.degrees

        # Sample next 48 hours at 10-minute intervals for better precision
        prev_alt = current_alt
        in_evening_bh = False
        in_morning_bh = False
        
        for minutes_ahead in range(0, 48 * 60, 10):
            check_dt = dt + timedelta(minutes=minutes_ahead)
            # Ensure UTC timezone
            if check_dt.tzinfo is None:
                check_dt = check_dt.replace(tzinfo=UTC)
            t_check = ts.from_datetime(check_dt)
            astrometric_check = observer.at(t_check).observe(sun)
            alt_check, _az_check, _ = astrometric_check.apparent().altaz()
            sun_alt_check = alt_check.degrees

            # Evening blue hour: sun descending from -4° to -6°
            if sun_alt_check <= -4 and sun_alt_check >= -6:
                if not in_evening_bh:
                    # Entering evening blue hour
                    if prev_alt > -4:
                        evening_start = check_dt
                        if evening_start.tzinfo is None:
                            evening_start = evening_start.replace(tzinfo=UTC)
                    in_evening_bh = True
                evening_end = check_dt
                if evening_end.tzinfo is None:
                    evening_end = evening_end.replace(tzinfo=UTC)
            elif in_evening_bh and sun_alt_check < -6:
                # Exited evening blue hour
                break

            # Morning blue hour: sun ascending from -6° to -4°
            if sun_alt_check >= -6 and sun_alt_check <= -4:
                if not in_morning_bh:
                    # Entering morning blue hour
                    if prev_alt < -6:
                        morning_start = check_dt
                        if morning_start.tzinfo is None:
                            morning_start = morning_start.replace(tzinfo=UTC)
                    in_morning_bh = True
                morning_end = check_dt
                if morning_end.tzinfo is None:
                    morning_end = morning_end.replace(tzinfo=UTC)
            elif in_morning_bh and sun_alt_check > -4:
                # Exited morning blue hour
                break

            prev_alt = sun_alt_check

        return (evening_start, evening_end, morning_start, morning_end)
    except Exception as e:
        logger.error(f"Failed to calculate blue hour: {e}")
        return (None, None, None, None)

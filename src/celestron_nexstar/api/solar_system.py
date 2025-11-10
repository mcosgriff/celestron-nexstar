"""
Solar System Calculations

Calculations for Sun and Moon positions, phases, and events.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, NamedTuple

from skyfield.api import Loader, Topos, load

from .enums import MoonPhase


logger = logging.getLogger(__name__)

__all__ = [
    "MoonInfo",
    "SunInfo",
    "calculate_astronomical_twilight",
    "calculate_blue_hour",
    "calculate_golden_hour",
    "calculate_moon_phase",
    "get_moon_info",
    "get_sun_info",
]


class MoonInfo(NamedTuple):
    """Moon information."""

    phase_name: MoonPhase  # Moon phase (e.g., "New Moon", "Waxing Crescent", etc.)
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


def _get_skyfield_objects() -> tuple[Any, Any, Any, Any | None]:
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


def _get_skyfield_directory() -> Path:
    """Get the Skyfield cache directory."""
    return Path.home() / ".skyfield"


def calculate_moon_phase(illumination: float, moon_ra: float, sun_ra: float) -> MoonPhase:
    """
    Calculate moon phase name from illumination percentage and moon/sun positions.

    Args:
        illumination: Illumination fraction (0.0 to 1.0)
        moon_ra: Moon's right ascension in hours
        sun_ra: Sun's right ascension in hours

    Returns:
        Phase name string
    """
    # Determine if moon is waxing (getting brighter) or waning (getting dimmer)
    # Normalize RA difference to -12 to +12 hours
    ra_diff = moon_ra - sun_ra
    if ra_diff > 12:
        ra_diff -= 24
    elif ra_diff < -12:
        ra_diff += 24

    # At full moon (illumination = 1.0), moon and sun are opposite (ra_diff ≈ ±12h)
    # After full moon (illumination > 0.5), moon is waning
    # Before full moon (illumination < 0.5), moon is waxing
    # Use RA difference to determine direction: positive = moon east of sun (waxing), negative = west (waning)
    # But near full moon, we need to be careful - use illumination as primary indicator
    if illumination > 0.5:
        # Past full moon - moon is waning
        is_waxing = False
    elif illumination < 0.5:
        # Before full moon - moon is waxing
        is_waxing = True
    else:
        # Exactly at 50% - use RA to determine
        is_waxing = ra_diff > 0

    if illumination < 0.01:
        return MoonPhase.NEW_MOON
    elif illumination < 0.25:
        return MoonPhase.WAXING_CRESCENT if is_waxing else MoonPhase.WANING_CRESCENT
    elif illumination < 0.26:
        return MoonPhase.FIRST_QUARTER if is_waxing else MoonPhase.LAST_QUARTER
    elif illumination < 0.49:
        return MoonPhase.WAXING_GIBBOUS if is_waxing else MoonPhase.WANING_GIBBOUS
    elif illumination < 0.51:
        return MoonPhase.FULL_MOON
    elif illumination < 0.90:
        return MoonPhase.WANING_GIBBOUS if not is_waxing else MoonPhase.WAXING_GIBBOUS
    elif illumination < 0.91:
        return MoonPhase.LAST_QUARTER if not is_waxing else MoonPhase.FIRST_QUARTER
    else:
        return MoonPhase.WANING_CRESCENT if not is_waxing else MoonPhase.WAXING_CRESCENT


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

        # Get sun RA/Dec for phase calculation
        sun_ra_obj, _sun_dec, _ = sun_astrometric.apparent().radec()
        sun_ra = sun_ra_obj.hours

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
        # Formula: (1 - cos(phase_angle)) / 2
        # At new moon: phase_angle = 0°, cos(0) = 1, (1-1)/2 = 0.0 (0%)
        # At full moon: phase_angle = 180°, cos(180) = -1, (1-(-1))/2 = 1.0 (100%)
        illumination = (1.0 - math.cos(phase_angle)) / 2.0

        phase_name = calculate_moon_phase(illumination, moon_ra, sun_ra)

        # Calculate moonrise/moonset
        moonrise_time = None
        moonset_time = None
        is_moon_above = moon_alt > 0

        def _refine_horizon_crossing(start_dt: datetime, end_dt: datetime, rising: bool) -> datetime:
            """Refine horizon crossing time using binary search between two datetimes."""
            # Use 10-minute intervals for better precision
            best_time = start_dt + timedelta(minutes=30)  # Default midpoint
            min_diff = float("inf")

            for minutes_offset in range(0, 61, 5):  # Check every 5 minutes
                test_dt = start_dt + timedelta(minutes=minutes_offset)
                if test_dt > end_dt:
                    break
                t_test = ts.from_datetime(test_dt)
                astrometric_test = observer.at(t_test).observe(moon)
                alt_test, _az_test, _ = astrometric_test.apparent().altaz()
                moon_alt_test = alt_test.degrees

                # Find the time closest to horizon (altitude = 0)
                diff = abs(moon_alt_test)
                if diff < min_diff:
                    min_diff = diff
                    best_time = test_dt

                # If we're very close to horizon, we're done
                if diff < 0.1:
                    break

            return best_time

        try:
            # First, look backwards to find today's moonrise (if moon is currently above horizon)
            if is_moon_above:
                # Look back up to 24 hours to find when moon rose today
                for hours_back in range(1, 25):
                    check_dt = dt - timedelta(hours=hours_back)
                    t_check = ts.from_datetime(check_dt)
                    astrometric_check = observer.at(t_check).observe(moon)
                    alt_check, _az_check, _ = astrometric_check.apparent().altaz()
                    moon_alt_check = alt_check.degrees

                    # Check next hour (forward in time) for comparison
                    next_dt = check_dt + timedelta(hours=1)
                    t_next = ts.from_datetime(next_dt)
                    astrometric_next = observer.at(t_next).observe(moon)
                    alt_next, _az_next, _ = astrometric_next.apparent().altaz()
                    moon_alt_next = alt_next.degrees

                    # Moonrise: was below, now above (looking backwards)
                    if moon_alt_check <= 0 and moon_alt_next > 0:
                        # Refine the crossing time for better accuracy
                        moonrise_time = _refine_horizon_crossing(check_dt, next_dt, rising=True)
                        # Ensure UTC timezone
                        if moonrise_time.tzinfo is None:
                            moonrise_time = moonrise_time.replace(tzinfo=UTC)
                        break

            # Sample next 48 hours at 1-hour intervals to find moonset and next moonrise
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
                if moon_alt_prev > 0 and moon_alt_check <= 0 and moonset_time is None:
                    # Refine the crossing time for better accuracy
                    moonset_time = _refine_horizon_crossing(prev_dt, check_dt, rising=False)
                    # Ensure UTC timezone
                    if moonset_time.tzinfo is None:
                        moonset_time = moonset_time.replace(tzinfo=UTC)
                    if moonrise_time is not None:
                        break

                # Moonrise: was below, now above (if we haven't found today's moonrise yet)
                if moonrise_time is None and moon_alt_prev <= 0 and moon_alt_check > 0:
                    # Refine the crossing time for better accuracy
                    moonrise_time = _refine_horizon_crossing(prev_dt, check_dt, rising=True)
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

                # Sunset: was above, now below (don't require is_daytime - find next sunset regardless)
                if sun_alt_prev > 0 and sun_alt_check <= 0 and sunset_time is None:
                    # Approximate sunset as midpoint between samples
                    sunset_time = prev_dt + timedelta(minutes=30)
                    # Ensure UTC timezone
                    if sunset_time.tzinfo is None:
                        sunset_time = sunset_time.replace(tzinfo=UTC)
                    if sunrise_time is not None:
                        break

                # Sunrise: was below, now above (don't require not is_daytime - find next sunrise regardless)
                if sun_alt_prev <= 0 and sun_alt_check > 0 and sunrise_time is None:
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
    Calculate golden hour times (sun altitude between 0° and 6°).

    Golden hour (also called magic hour) is the period when the sun is between 0° and 6° altitude,
    providing warm, soft lighting ideal for photography. This occurs just after sunrise and
    just before sunset.

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

            # Evening golden hour: sun descending from 6° to 0°
            if sun_alt_check <= 6 and sun_alt_check >= 0:
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
            elif in_evening_gh and sun_alt_check < 0:
                # Exited evening golden hour
                break

            # Morning golden hour: sun ascending from 0° to 6°
            if sun_alt_check >= 0 and sun_alt_check <= 6:
                if not in_morning_gh:
                    # Entering morning golden hour
                    if prev_alt < 0:
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


def calculate_astronomical_twilight(
    observer_lat: float,
    observer_lon: float,
    dt: datetime | None = None,
) -> tuple[datetime | None, datetime | None, datetime | None, datetime | None]:
    """
    Calculate astronomical twilight times (sun altitude between -18° and -12°).

    Astronomical twilight is the period when the sun is between -18° and -12° altitude.
    During this time, the sky is dark enough for most astronomical observations,
    but some faint objects may still be difficult to see. True night begins when
    the sun is below -18°.

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
        in_evening_at = False
        in_morning_at = False

        for minutes_ahead in range(0, 48 * 60, 10):
            check_dt = dt + timedelta(minutes=minutes_ahead)
            # Ensure UTC timezone
            if check_dt.tzinfo is None:
                check_dt = check_dt.replace(tzinfo=UTC)
            t_check = ts.from_datetime(check_dt)
            astrometric_check = observer.at(t_check).observe(sun)
            alt_check, _az_check, _ = astrometric_check.apparent().altaz()
            sun_alt_check = alt_check.degrees

            # Evening astronomical twilight: sun descending from -12° to -18°
            if sun_alt_check <= -12 and sun_alt_check >= -18:
                if not in_evening_at:
                    # Entering evening astronomical twilight
                    if prev_alt > -12:
                        evening_start = check_dt
                        if evening_start.tzinfo is None:
                            evening_start = evening_start.replace(tzinfo=UTC)
                    in_evening_at = True
                evening_end = check_dt
                if evening_end.tzinfo is None:
                    evening_end = evening_end.replace(tzinfo=UTC)
            elif in_evening_at and sun_alt_check < -18:
                # Exited evening astronomical twilight (entered true night)
                break

            # Morning astronomical twilight: sun ascending from -18° to -12°
            if sun_alt_check >= -18 and sun_alt_check <= -12:
                if not in_morning_at:
                    # Entering morning astronomical twilight
                    if prev_alt < -18:
                        morning_start = check_dt
                        if morning_start.tzinfo is None:
                            morning_start = morning_start.replace(tzinfo=UTC)
                    in_morning_at = True
                morning_end = check_dt
                if morning_end.tzinfo is None:
                    morning_end = morning_end.replace(tzinfo=UTC)
            elif in_morning_at and sun_alt_check > -12:
                # Exited morning astronomical twilight
                break

            prev_alt = sun_alt_check

        return (evening_start, evening_end, morning_start, morning_end)
    except Exception as e:
        logger.error(f"Failed to calculate astronomical twilight: {e}")
        return (None, None, None, None)

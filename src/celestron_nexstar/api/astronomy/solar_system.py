"""
Solar System Calculations

Calculations for Sun and Moon positions, phases, and events.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, NamedTuple

from skyfield.api import Topos

from celestron_nexstar.api.core.enums import MoonPhase
from celestron_nexstar.api.core.utils import get_local_timezone


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
        from celestron_nexstar.api.ephemeris.skyfield_utils import (
            get_skyfield_ephemeris,
            get_skyfield_timescale,
        )

        # Cache timescale to avoid repeatedly reading bundled IERS data.
        ts = get_skyfield_timescale()

        # Load ephemeris - de421 includes Moon
        try:
            eph = get_skyfield_ephemeris("de421.bsp")
        except FileNotFoundError:
            logger.warning("de421.bsp not found, moon calculations may fail")
            # Fallback to de440s (no moon) for sun only
            eph = get_skyfield_ephemeris("de440s.bsp")

        earth = eph["earth"]
        sun = eph["sun"]
        try:
            moon = eph["moon"]
        except KeyError:
            moon = None

        return ts, earth, sun, moon
    except (ImportError, AttributeError, ValueError, TypeError, KeyError) as e:
        # ImportError: missing Skyfield modules
        # AttributeError: missing methods/attributes on loader
        # ValueError: invalid ephemeris data
        # TypeError: wrong argument types
        # KeyError: missing ephemeris objects (beyond moon)
        logger.error(f"Failed to load Skyfield objects: {e}")
        return None, None, None, None


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

    # Determine waxing vs waning using RA difference:
    # - Positive ra_diff (0 to +12h): Moon is east of sun → WAXING (new moon to full moon)
    # - Negative ra_diff (-12 to 0h): Moon is west of sun → WANING (full moon to new moon)
    # Note: Cannot use illumination alone - 80% could be waxing or waning!
    is_waxing = ra_diff > 0

    # Moon phase based on illumination percentage
    if illumination < 0.01:
        return MoonPhase.NEW_MOON
    elif illumination < 0.48:
        # 1-48%: Crescent phase
        return MoonPhase.WAXING_CRESCENT if is_waxing else MoonPhase.WANING_CRESCENT
    elif illumination < 0.52:
        # 48-52%: Quarter moon (50%)
        return MoonPhase.FIRST_QUARTER if is_waxing else MoonPhase.LAST_QUARTER
    elif illumination < 0.99:
        # 52-99%: Gibbous phase
        return MoonPhase.WAXING_GIBBOUS if is_waxing else MoonPhase.WANING_GIBBOUS
    else:
        # 99-100%: Full moon
        return MoonPhase.FULL_MOON


def get_moon_info(
    observer_lat: float,
    observer_lon: float,
    dt: datetime | None = None,
    elevation_ft: float | None = None,
) -> MoonInfo | None:
    """
    Get current moon information including phase and position.

    Args:
        observer_lat: Observer latitude in degrees
        observer_lon: Observer longitude in degrees
        dt: Datetime to calculate for (default: now)
        elevation_ft: Elevation in feet

    Returns:
        MoonInfo or None if calculation fails
    """

    local_timezone = get_local_timezone(observer_lat, observer_lon)

    if dt is None:
        dt = datetime.now(local_timezone)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=local_timezone)

    try:
        ts, earth, sun, moon = _get_skyfield_objects()
        if ts is None or earth is None or sun is None or moon is None:
            return None

        t = ts.from_datetime(dt)
        # Use observer elevation (in meters) for more accurate horizon/altitude calculations.
        # Elevation is stored in feet in our config; Skyfield expects meters.
        elev_m = 0.0
        try:
            from celestron_nexstar.api.location.observer import FEET_TO_METERS, get_observer_location

            if elevation_ft is None:
                loc = get_observer_location()
                if abs(loc.latitude - observer_lat) < 1e-6 and abs(loc.longitude - observer_lon) < 1e-6:
                    elevation_ft = loc.elevation
            elev_m = float(elevation_ft or 0.0) * FEET_TO_METERS
        except Exception:
            elev_m = 0.0

        topos = Topos(latitude_degrees=observer_lat, longitude_degrees=observer_lon, elevation_m=elev_m)
        observer = earth + topos

        # Get moon position
        astrometric = observer.at(t).observe(moon)
        alt, az, _distance = astrometric.apparent().altaz()
        moon_alt = alt.degrees
        moon_az = az.degrees

        # Get moon RA/Dec
        ra, dec, _ = astrometric.apparent().radec()
        moon_ra = ra.hours
        moon_dec = dec.degrees

        # Get positions relative to earth
        sun_astrometric = earth.at(t).observe(sun)

        # Get sun RA/Dec for phase calculation
        sun_ra_obj, _sun_dec, _ = sun_astrometric.apparent().radec()
        sun_ra = sun_ra_obj.hours

        # Use Skyfield's illumination helper for the Moon.
        moon_geo = earth.at(t).observe(moon).apparent()
        illumination = float(moon_geo.fraction_illuminated(sun))

        phase_name = calculate_moon_phase(illumination, moon_ra, sun_ra)

        # Calculate moonrise/moonset
        moonrise_time = None
        moonset_time = None

        try:
            from skyfield import almanac

            # Always look forward to find NEXT moonrise and NEXT moonset.
            t0 = ts.from_datetime(dt)
            t1 = ts.from_datetime(dt + timedelta(hours=48))

            rise_times, _rise_events = almanac.find_risings(observer, moon, t0, t1)
            for t_rise in rise_times:
                event_dt = t_rise.utc_datetime().replace(tzinfo=UTC)
                if event_dt > dt:
                    moonrise_time = event_dt
                    break

            set_times, _set_events = almanac.find_settings(observer, moon, t0, t1)
            for t_set in set_times:
                event_dt = t_set.utc_datetime().replace(tzinfo=UTC)
                if event_dt > dt:
                    moonset_time = event_dt
                    break

            if moonrise_time is None and len(rise_times) == 0:
                logger.warning(
                    "No moonrise events found in next 48 hours for lat=%.4f lon=%.4f (start=%s).",
                    observer_lat,
                    observer_lon,
                    dt,
                )
            if moonset_time is None and len(set_times) == 0:
                logger.warning(
                    "No moonset events found in next 48 hours for lat=%.4f lon=%.4f (start=%s).",
                    observer_lat,
                    observer_lon,
                    dt,
                )
        except (ValueError, TypeError, AttributeError, ZeroDivisionError) as e:
            logger.warning(f"Error calculating moonrise/moonset: {e}", exc_info=True)
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
    except (ValueError, TypeError, AttributeError, ZeroDivisionError, IndexError) as e:
        # ValueError: invalid datetime or coordinates
        # TypeError: wrong argument types
        # AttributeError: missing attributes on Skyfield objects
        # ZeroDivisionError: division by zero in calculations
        # IndexError: position arrays have wrong size
        logger.error(f"Failed to calculate moon info: {e}")
        return None


def get_sun_info(
    observer_lat: float,
    observer_lon: float,
    dt: datetime | None = None,
    elevation_ft: float | None = None,
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
        elev_m = 0.0
        try:
            from celestron_nexstar.api.location.observer import FEET_TO_METERS, get_observer_location

            if elevation_ft is None:
                loc = get_observer_location()
                if abs(loc.latitude - observer_lat) < 1e-6 and abs(loc.longitude - observer_lon) < 1e-6:
                    elevation_ft = loc.elevation
            elev_m = float(elevation_ft or 0.0) * FEET_TO_METERS
        except Exception:
            elev_m = 0.0

        observer = earth + Topos(latitude_degrees=observer_lat, longitude_degrees=observer_lon, elevation_m=elev_m)

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

        # Calculate sunset/sunrise using Skyfield almanac.
        sunset_time = None
        sunrise_time = None

        try:
            from skyfield import almanac

            t0 = ts.from_datetime(dt)
            t1 = ts.from_datetime(dt + timedelta(hours=48))

            rise_times, _rise_events = almanac.find_risings(observer, sun, t0, t1)
            for t_rise in rise_times:
                event_dt = t_rise.utc_datetime().replace(tzinfo=UTC)
                if event_dt > dt:
                    sunrise_time = event_dt
                    break

            set_times, _set_events = almanac.find_settings(observer, sun, t0, t1)
            for t_set in set_times:
                event_dt = t_set.utc_datetime().replace(tzinfo=UTC)
                if event_dt > dt:
                    sunset_time = event_dt
                    break
        except (ValueError, TypeError, AttributeError, ZeroDivisionError) as e:
            logger.debug(f"Error calculating sunrise/sunset: {e}")
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
    except (ValueError, TypeError, AttributeError, ZeroDivisionError) as e:
        # ValueError: invalid datetime or coordinates
        # TypeError: wrong argument types
        # AttributeError: missing attributes on Skyfield objects
        # ZeroDivisionError: division by zero in calculations
        logger.error(f"Failed to calculate sun info: {e}")
        return None


def calculate_golden_hour(
    observer_lat: float,
    observer_lon: float,
    dt: datetime | None = None,
    elevation_ft: float | None = None,
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

        elev_m = 0.0
        try:
            from celestron_nexstar.api.location.observer import FEET_TO_METERS, get_observer_location

            if elevation_ft is None:
                loc = get_observer_location()
                if abs(loc.latitude - observer_lat) < 1e-6 and abs(loc.longitude - observer_lon) < 1e-6:
                    elevation_ft = loc.elevation
            elev_m = float(elevation_ft or 0.0) * FEET_TO_METERS
        except Exception:
            elev_m = 0.0

        observer = earth + Topos(latitude_degrees=observer_lat, longitude_degrees=observer_lon, elevation_m=elev_m)

        evening_start = None
        evening_end = None
        morning_start = None
        morning_end = None

        from skyfield import almanac

        t0 = ts.from_datetime(dt)
        t1 = ts.from_datetime(dt + timedelta(hours=48))

        def _next_event_after(times: Any, after_dt: datetime) -> datetime | None:
            for t_event in times:
                event_dt = t_event.utc_datetime().replace(tzinfo=UTC)
                if event_dt > after_dt:
                    return event_dt
            return None

        evening_start = _next_event_after(almanac.find_settings(observer, sun, t0, t1, horizon_degrees=6)[0], dt)
        evening_end = _next_event_after(
            almanac.find_settings(observer, sun, t0, t1, horizon_degrees=0)[0],
            evening_start or dt,
        )

        morning_start = _next_event_after(almanac.find_risings(observer, sun, t0, t1, horizon_degrees=0)[0], dt)
        morning_end = _next_event_after(
            almanac.find_risings(observer, sun, t0, t1, horizon_degrees=6)[0],
            morning_start or dt,
        )

        return (evening_start, evening_end, morning_start, morning_end)
    except (ValueError, TypeError, AttributeError, ZeroDivisionError) as e:
        # ValueError: invalid datetime or coordinates
        # TypeError: wrong argument types
        # AttributeError: missing attributes on Skyfield objects
        # ZeroDivisionError: division by zero in calculations
        logger.error(f"Failed to calculate golden hour: {e}")
        return (None, None, None, None)


def calculate_blue_hour(
    observer_lat: float,
    observer_lon: float,
    dt: datetime | None = None,
    elevation_ft: float | None = None,
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

        elev_m = 0.0
        try:
            from celestron_nexstar.api.location.observer import FEET_TO_METERS, get_observer_location

            if elevation_ft is None:
                loc = get_observer_location()
                if abs(loc.latitude - observer_lat) < 1e-6 and abs(loc.longitude - observer_lon) < 1e-6:
                    elevation_ft = loc.elevation
            elev_m = float(elevation_ft or 0.0) * FEET_TO_METERS
        except Exception:
            elev_m = 0.0

        observer = earth + Topos(latitude_degrees=observer_lat, longitude_degrees=observer_lon, elevation_m=elev_m)

        evening_start = None
        evening_end = None
        morning_start = None
        morning_end = None

        from skyfield import almanac

        t0 = ts.from_datetime(dt)
        t1 = ts.from_datetime(dt + timedelta(hours=48))

        def _next_event_after(times: Any, after_dt: datetime) -> datetime | None:
            for t_event in times:
                event_dt = t_event.utc_datetime().replace(tzinfo=UTC)
                if event_dt > after_dt:
                    return event_dt
            return None

        evening_start = _next_event_after(almanac.find_settings(observer, sun, t0, t1, horizon_degrees=-4)[0], dt)
        evening_end = _next_event_after(
            almanac.find_settings(observer, sun, t0, t1, horizon_degrees=-6)[0],
            evening_start or dt,
        )

        morning_start = _next_event_after(almanac.find_risings(observer, sun, t0, t1, horizon_degrees=-6)[0], dt)
        morning_end = _next_event_after(
            almanac.find_risings(observer, sun, t0, t1, horizon_degrees=-4)[0],
            morning_start or dt,
        )

        return (evening_start, evening_end, morning_start, morning_end)
    except (ValueError, TypeError, AttributeError, ZeroDivisionError) as e:
        # ValueError: invalid datetime or coordinates
        # TypeError: wrong argument types
        # AttributeError: missing attributes on Skyfield objects
        # ZeroDivisionError: division by zero in calculations
        logger.error(f"Failed to calculate blue hour: {e}")
        return (None, None, None, None)


def calculate_astronomical_twilight(
    observer_lat: float,
    observer_lon: float,
    dt: datetime | None = None,
    elevation_ft: float | None = None,
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

        elev_m = 0.0
        try:
            from celestron_nexstar.api.location.observer import FEET_TO_METERS, get_observer_location

            if elevation_ft is None:
                loc = get_observer_location()
                if abs(loc.latitude - observer_lat) < 1e-6 and abs(loc.longitude - observer_lon) < 1e-6:
                    elevation_ft = loc.elevation
            elev_m = float(elevation_ft or 0.0) * FEET_TO_METERS
        except Exception:
            elev_m = 0.0

        observer = earth + Topos(latitude_degrees=observer_lat, longitude_degrees=observer_lon, elevation_m=elev_m)

        evening_start = None
        evening_end = None
        morning_start = None
        morning_end = None

        from skyfield import almanac

        t0 = ts.from_datetime(dt)
        t1 = ts.from_datetime(dt + timedelta(hours=48))

        def _next_event_after(times: Any, after_dt: datetime) -> datetime | None:
            for t_event in times:
                event_dt = t_event.utc_datetime().replace(tzinfo=UTC)
                if event_dt > after_dt:
                    return event_dt
            return None

        evening_start = _next_event_after(almanac.find_settings(observer, sun, t0, t1, horizon_degrees=-12)[0], dt)
        evening_end = _next_event_after(
            almanac.find_settings(observer, sun, t0, t1, horizon_degrees=-18)[0],
            evening_start or dt,
        )

        morning_start = _next_event_after(almanac.find_risings(observer, sun, t0, t1, horizon_degrees=-18)[0], dt)
        morning_end = _next_event_after(
            almanac.find_risings(observer, sun, t0, t1, horizon_degrees=-12)[0],
            morning_start or dt,
        )

        return (evening_start, evening_end, morning_start, morning_end)
    except (ValueError, TypeError, AttributeError, ZeroDivisionError) as e:
        # ValueError: invalid datetime or coordinates
        # TypeError: wrong argument types
        # AttributeError: missing attributes on Skyfield objects
        # ZeroDivisionError: division by zero in calculations
        logger.error(f"Failed to calculate astronomical twilight: {e}")
        return (None, None, None, None)

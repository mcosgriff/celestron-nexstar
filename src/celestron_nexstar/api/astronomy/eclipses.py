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
    from celestron_nexstar.api.location.observer import ObserverLocation

from sqlalchemy.orm import Session


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
    notes: str
    # Enhanced fields from database
    start_time: datetime | None = None  # Eclipse start (first contact)
    end_time: datetime | None = None  # Eclipse end (last contact)
    obscuration: float | None = None  # Fraction obscured (0-1)
    central_duration_sec: int | None = None  # Duration along centerline (seconds)
    in_path: bool | None = None  # Whether observer is in path of totality/annularity
    path_available: bool = False  # Whether path data is available  # Additional information


class EclipseType:
    """Eclipse type constants."""

    LUNAR_TOTAL = "lunar_total"
    LUNAR_PARTIAL = "lunar_partial"
    LUNAR_PENUMBRAL = "lunar_penumbral"
    SOLAR_TOTAL = "solar_total"
    SOLAR_PARTIAL = "solar_partial"
    SOLAR_ANNULAR = "solar_annular"


def _check_point_in_path(
    observer_lon: float,
    observer_lat: float,
    path_geojson: str | None,
) -> bool | None:
    """
    Check if observer location is within eclipse path polygon.

    Args:
        observer_lon: Observer longitude in degrees
        observer_lat: Observer latitude in degrees
        path_geojson: GeoJSON string of path polygon/multipolygon

    Returns:
        True if in path, False if outside, None if cannot determine
    """
    if not path_geojson:
        return None

    try:
        import json

        from shapely.geometry import Point, shape

        geojson = json.loads(path_geojson)

        # Handle both Feature and direct geometry
        if geojson.get("type") == "Feature":
            geometry = geojson.get("geometry")
        elif geojson.get("type") == "FeatureCollection":
            # Combine all features
            from shapely.ops import unary_union

            geometries = [shape(f["geometry"]) for f in geojson.get("features", [])]
            if not geometries:
                return None
            combined = unary_union(geometries)
            observer_point = Point(observer_lon, observer_lat)
            return bool(combined.contains(observer_point))
        else:
            geometry = geojson

        if not geometry:
            return None

        path_shape = shape(geometry)
        observer_point = Point(observer_lon, observer_lat)

        return bool(path_shape.contains(observer_point))

    except (json.JSONDecodeError, ImportError, ValueError, KeyError, TypeError) as e:
        logger.debug(f"Error checking eclipse path: {e}")
        return None


def _get_skyfield_objects() -> tuple[Any, Any, Any, Any | None, Any] | tuple[None, None, None, None, None]:
    """Get Skyfield objects for calculations."""

    try:
        from celestron_nexstar.api.ephemeris.skyfield_utils import (
            get_skyfield_ephemeris,
            get_skyfield_loader,
            get_skyfield_timescale,
        )

        get_skyfield_loader()
        ts = get_skyfield_timescale()

        # Load ephemeris - de421 includes Moon
        try:
            eph = get_skyfield_ephemeris("de421.bsp")
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
    except (ImportError, AttributeError, ValueError, TypeError, KeyError) as e:
        # ImportError: missing Skyfield modules
        # AttributeError: missing methods/attributes on loader
        # ValueError: invalid ephemeris data
        # TypeError: wrong argument types
        # KeyError: missing ephemeris objects (beyond moon)
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
    start_time: datetime | None = None,
    max_time: datetime | None = None,
    end_time: datetime | None = None,
    obscuration: float | None = None,
    central_duration_sec: int | None = None,
) -> Eclipse | None:
    """
    Calculate lunar eclipse details for a specific time.

    Uses stored contact times when available, otherwise estimates.

    Args:
        observer_lat: Observer latitude
        observer_lon: Observer longitude
        eclipse_time: Time of eclipse (date from DB)
        eclipse_type: Type of eclipse
        magnitude: Eclipse magnitude
        ts: Skyfield timescale
        earth: Skyfield earth object
        sun: Skyfield sun object
        moon: Skyfield moon object
        start_time: Eclipse start (first contact) from DB
        max_time: Eclipse maximum from DB
        end_time: Eclipse end (last contact) from DB
        obscuration: Fraction obscured from DB
        central_duration_sec: Central duration in seconds from DB

    Returns:
        Eclipse object or None if calculation fails
    """
    try:
        # Use stored max_time if available, otherwise use eclipse_time
        eclipse_max = max_time if max_time else eclipse_time

        # Normalize to UTC
        eclipse_max_utc = eclipse_max.replace(tzinfo=UTC) if eclipse_max.tzinfo is None else eclipse_max.astimezone(UTC)

        t = ts.from_datetime(eclipse_max_utc)
        elev_m = 0.0
        try:
            from celestron_nexstar.api.location.observer import FEET_TO_METERS, get_observer_location

            loc = get_observer_location()
            if abs(loc.latitude - observer_lat) < 1e-6 and abs(loc.longitude - observer_lon) < 1e-6:
                elev_m = float(loc.elevation or 0.0) * FEET_TO_METERS
        except Exception:
            elev_m = 0.0

        observer = earth + Topos(latitude_degrees=observer_lat, longitude_degrees=observer_lon, elevation_m=elev_m)

        # Get moon position at maximum
        moon_astrometric = observer.at(t).observe(moon)
        moon_alt, _moon_az, _ = moon_astrometric.apparent().altaz()

        # For lunar eclipse, check if moon is above horizon during event
        is_visible = moon_alt.degrees > 0

        # Use stored contact times if available
        if start_time and end_time:
            start_utc = start_time.replace(tzinfo=UTC) if start_time.tzinfo is None else start_time.astimezone(UTC)
            end_utc = end_time.replace(tzinfo=UTC) if end_time.tzinfo is None else end_time.astimezone(UTC)
            duration_minutes = (end_utc - start_utc).total_seconds() / 60.0
            visibility_start = start_utc if is_visible else None
            visibility_end = end_utc if is_visible else None
        else:
            # Estimate duration based on type
            match eclipse_type:
                case "lunar_total":
                    duration_minutes = 180.0
                case "lunar_partial":
                    duration_minutes = 200.0
                case _:
                    duration_minutes = 240.0
            visibility_start = eclipse_max_utc - timedelta(minutes=duration_minutes / 2) if is_visible else None
            visibility_end = eclipse_max_utc + timedelta(minutes=duration_minutes / 2) if is_visible else None

        # Build notes
        match eclipse_type:
            case "lunar_total":
                notes = "Total lunar eclipse - moon fully in Earth's shadow"
            case "lunar_partial":
                obs_pct = obscuration if obscuration else magnitude
                notes = f"Partial lunar eclipse - {obs_pct:.0%} of moon in shadow"
            case _:
                notes = "Penumbral lunar eclipse - subtle darkening"

        if not is_visible:
            notes += " (Moon below horizon at your location)"

        return Eclipse(
            eclipse_type=eclipse_type,
            date=eclipse_time.replace(tzinfo=UTC) if eclipse_time.tzinfo is None else eclipse_time.astimezone(UTC),
            maximum_time=eclipse_max_utc,
            duration_minutes=duration_minutes,
            magnitude=magnitude,
            is_visible=is_visible,
            visibility_start=visibility_start,
            visibility_end=visibility_end,
            altitude_at_maximum=moon_alt.degrees,
            notes=notes,
            start_time=start_time,
            end_time=end_time,
            obscuration=obscuration,
            central_duration_sec=central_duration_sec,
            in_path=None,  # Not applicable for lunar eclipses
            path_available=False,
        )
    except (ValueError, TypeError, AttributeError, ZeroDivisionError) as e:
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
    except (ValueError, TypeError, AttributeError, ZeroDivisionError, IndexError) as e:
        # ValueError: invalid math operations (e.g., acos out of range)
        # TypeError: wrong argument types
        # AttributeError: missing attributes on Skyfield objects
        # ZeroDivisionError: division by zero
        # IndexError: position arrays have wrong size
        logger.debug(f"Error calculating moon phase: {e}")
        return 0.5


def get_next_lunar_eclipse(
    db_session: Session,
    location: ObserverLocation,
    years_ahead: int = 5,
) -> list[Eclipse]:
    """
    Find next lunar eclipses visible from observer location.

    Uses known eclipse data from NASA's Five Millennium Catalog.

    Args:
        db_session: Database session
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

    known_eclipses = get_known_eclipses(db_session)
    for eclipse_data in known_eclipses:
        eclipse_type = eclipse_data["type"]
        eclipse_date = eclipse_data["date"]
        magnitude = eclipse_data["magnitude"]

        # Normalize eclipse_date to UTC for comparison
        if isinstance(eclipse_date, datetime):
            if eclipse_date.tzinfo is None:
                eclipse_date = eclipse_date.replace(tzinfo=UTC)
            else:
                eclipse_date = eclipse_date.astimezone(UTC)

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
                start_time=eclipse_data.get("start_time"),
                max_time=eclipse_data.get("max_time"),
                end_time=eclipse_data.get("end_time"),
                obscuration=eclipse_data.get("obscuration"),
                central_duration_sec=eclipse_data.get("central_duration_sec"),
            )
            if eclipse:
                eclipses.append(eclipse)

    return eclipses


# NOTE: Eclipse data is now stored in database seed files.
# See get_known_eclipses() which loads from database.
# To regenerate seed files, run: python scripts/create_seed_files.py
# Data from NASA's Five Millennium Catalog


def get_known_eclipses(db_session: Session) -> list[dict[str, Any]]:
    """
    Get list of known eclipses from database.

    Args:
        db_session: Database session

    Returns:
        List of dicts with eclipse data including contact times and path.

    Raises:
        RuntimeError: If no eclipses found in database (seed data required)
    """
    from sqlalchemy import func, select

    from celestron_nexstar.api.core.exceptions import DatabaseError
    from celestron_nexstar.api.database.models import EclipseModel

    count = db_session.scalar(select(func.count(EclipseModel.id)))
    if count == 0:
        raise DatabaseError("No eclipses found in database. Please seed the database by running: nexstar data seed")

    result = db_session.execute(select(EclipseModel))
    models = result.scalars().all()

    eclipses = []
    for model in models:
        eclipses.append(
            {
                "type": model.eclipse_type,
                "date": model.date,
                "magnitude": model.magnitude,
                "start_time": model.start_time,
                "max_time": model.max_time,
                "end_time": model.end_time,
                "obscuration": model.obscuration,
                "central_duration_sec": model.central_duration_sec,
                "path_geojson": model.path_geojson,
            }
        )
    return eclipses


def get_next_solar_eclipse(
    db_session: Session,
    location: ObserverLocation,
    years_ahead: int = 10,
) -> list[Eclipse]:
    """
    Find next solar eclipses visible from observer location.

    Args:
        db_session: Database session
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

    known_eclipses = get_known_eclipses(db_session)
    for eclipse_data in known_eclipses:
        eclipse_type = eclipse_data["type"]
        eclipse_date = eclipse_data["date"]
        magnitude = eclipse_data["magnitude"]

        # Normalize eclipse_date to UTC for comparison
        if isinstance(eclipse_date, datetime):
            if eclipse_date.tzinfo is None:
                eclipse_date = eclipse_date.replace(tzinfo=UTC)
            else:
                eclipse_date = eclipse_date.astimezone(UTC)

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
                start_time=eclipse_data.get("start_time"),
                max_time=eclipse_data.get("max_time"),
                end_time=eclipse_data.get("end_time"),
                obscuration=eclipse_data.get("obscuration"),
                central_duration_sec=eclipse_data.get("central_duration_sec"),
                path_geojson=eclipse_data.get("path_geojson"),
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
    start_time: datetime | None = None,
    max_time: datetime | None = None,
    end_time: datetime | None = None,
    obscuration: float | None = None,
    central_duration_sec: int | None = None,
    path_geojson: str | None = None,
) -> Eclipse | None:
    """
    Calculate solar eclipse details for a specific time.

    Uses stored contact times and path data when available.

    Args:
        observer_lat: Observer latitude
        observer_lon: Observer longitude
        eclipse_time: Time of eclipse (date from DB)
        eclipse_type: Type of eclipse
        magnitude: Eclipse magnitude
        ts: Skyfield timescale
        earth: Skyfield earth object
        sun: Skyfield sun object
        moon: Skyfield moon object
        start_time: Eclipse start from DB
        max_time: Eclipse maximum from DB
        end_time: Eclipse end from DB
        obscuration: Fraction obscured from DB
        central_duration_sec: Central duration in seconds from DB
        path_geojson: Path polygon GeoJSON from DB

    Returns:
        Eclipse object or None if calculation fails
    """
    try:
        # Use stored max_time if available
        eclipse_max = max_time if max_time else eclipse_time

        eclipse_max_utc = eclipse_max.replace(tzinfo=UTC) if eclipse_max.tzinfo is None else eclipse_max.astimezone(UTC)

        t = ts.from_datetime(eclipse_max_utc)
        elev_m = 0.0
        try:
            from celestron_nexstar.api.location.observer import FEET_TO_METERS, get_observer_location

            loc = get_observer_location()
            if abs(loc.latitude - observer_lat) < 1e-6 and abs(loc.longitude - observer_lon) < 1e-6:
                elev_m = float(loc.elevation or 0.0) * FEET_TO_METERS
        except Exception:
            elev_m = 0.0

        observer = earth + Topos(latitude_degrees=observer_lat, longitude_degrees=observer_lon, elevation_m=elev_m)

        # Get sun position at maximum
        sun_astrometric = observer.at(t).observe(sun)
        sun_alt, _sun_az, _ = sun_astrometric.apparent().altaz()

        # For solar eclipse, sun must be above horizon
        is_visible = sun_alt.degrees > 0

        # Check if observer is in path of totality/annularity
        in_path = _check_point_in_path(observer_lon, observer_lat, path_geojson)
        path_available = path_geojson is not None and len(path_geojson) > 0

        # Use stored contact times if available
        if start_time and end_time:
            start_utc = start_time.replace(tzinfo=UTC) if start_time.tzinfo is None else start_time.astimezone(UTC)
            end_utc = end_time.replace(tzinfo=UTC) if end_time.tzinfo is None else end_time.astimezone(UTC)
            duration_minutes = (end_utc - start_utc).total_seconds() / 60.0
            visibility_start = start_utc if is_visible else None
            visibility_end = end_utc if is_visible else None
        else:
            # Estimate duration based on type
            match eclipse_type:
                case "solar_total":
                    duration_minutes = 2.0 if in_path else 120.0
                case "solar_annular":
                    duration_minutes = 3.0 if in_path else 120.0
                case _:
                    duration_minutes = 120.0
            visibility_start = eclipse_max_utc - timedelta(minutes=duration_minutes / 2) if is_visible else None
            visibility_end = eclipse_max_utc + timedelta(minutes=duration_minutes / 2) if is_visible else None

        # Build notes
        match eclipse_type:
            case "solar_total":
                if in_path is True:
                    notes = "Total solar eclipse - YOU ARE IN THE PATH OF TOTALITY!"
                elif in_path is False:
                    notes = "Total solar eclipse - partial from your location"
                else:
                    notes = "Total solar eclipse"
            case "solar_annular":
                if in_path is True:
                    notes = "Annular solar eclipse - YOU ARE IN THE PATH OF ANNULARITY!"
                elif in_path is False:
                    notes = "Annular solar eclipse - partial from your location"
                else:
                    notes = "Annular solar eclipse"
            case _:
                obs_pct = obscuration if obscuration else magnitude
                notes = f"Partial solar eclipse ({obs_pct:.0%} coverage)"

        notes += " - requires special eye protection"

        if not is_visible:
            notes += " (Sun below horizon at your location)"

        return Eclipse(
            eclipse_type=eclipse_type,
            date=eclipse_time.replace(tzinfo=UTC) if eclipse_time.tzinfo is None else eclipse_time.astimezone(UTC),
            maximum_time=eclipse_max_utc,
            duration_minutes=duration_minutes,
            magnitude=magnitude,
            is_visible=is_visible,
            visibility_start=visibility_start,
            visibility_end=visibility_end,
            altitude_at_maximum=sun_alt.degrees,
            notes=notes,
            start_time=start_time,
            end_time=end_time,
            obscuration=obscuration,
            central_duration_sec=central_duration_sec,
            in_path=in_path,
            path_available=path_available,
        )
    except (ValueError, TypeError, AttributeError, ZeroDivisionError) as e:
        logger.error(f"Error calculating solar eclipse: {e}")
        return None


def get_upcoming_eclipses(
    db_session: Session,
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
        lunar_eclipses = get_next_lunar_eclipse(db_session, location, years_ahead=years_ahead)
        all_eclipses.extend(lunar_eclipses)

    if eclipse_type is None or eclipse_type == "solar":
        solar_eclipses = get_next_solar_eclipse(db_session, location, years_ahead=years_ahead)
        all_eclipses.extend(solar_eclipses)

    # Sort by date
    all_eclipses.sort(key=lambda e: e.date)

    return all_eclipses

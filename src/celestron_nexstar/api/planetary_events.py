"""
Planetary Events Predictions

Finds planetary conjunctions, oppositions, transits, and retrograde periods.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

# skyfield is a required dependency
from skyfield.api import Topos
from skyfield.searchlib import find_minima

from .ephemeris import PLANET_NAMES, _get_ephemeris


if TYPE_CHECKING:
    from .observer import ObserverLocation

logger = logging.getLogger(__name__)

__all__ = [
    "EventType",
    "PlanetaryEvent",
    "get_planetary_conjunctions",
    "get_planetary_oppositions",
    "get_retrograde_periods",
]


@dataclass
class PlanetaryEvent:
    """Information about a planetary event."""

    event_type: str  # "conjunction", "opposition", "transit", "retrograde_start", "retrograde_end"
    date: datetime
    planet1: str  # First planet (or planet for opposition/retrograde)
    planet2: str | None  # Second planet (for conjunctions)
    separation_degrees: float  # Angular separation (for conjunctions) or elongation (for oppositions)
    altitude_at_event: float  # Altitude above horizon at event time
    is_visible: bool  # Whether event is visible from observer location
    notes: str  # Additional information


class EventType:
    """Planetary event type constants."""

    CONJUNCTION = "conjunction"
    OPPOSITION = "opposition"
    TRANSIT = "transit"
    RETROGRADE_START = "retrograde_start"
    RETROGRADE_END = "retrograde_end"


# Major planets for event calculations (excluding moons)
MAJOR_PLANETS = ["mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune"]


def _get_planet_position(planet_name: str, t: Any, eph: Any) -> tuple[float, float] | None:
    """Get planet RA/Dec position at time t."""
    planet_key = planet_name.lower()
    if planet_key not in PLANET_NAMES:
        return None

    ephemeris_name, _bsp_file = PLANET_NAMES[planet_key]
    earth = eph["earth"]

    try:
        target = eph[ephemeris_name]
    except KeyError:
        try:
            target = eph[ephemeris_name.upper()]
        except KeyError:
            return None

    astrometric = earth.at(t).observe(target)
    ra, dec, _distance = astrometric.radec()
    return ra.hours, dec.degrees


def _angular_separation(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    """Calculate angular separation between two objects in degrees."""
    # Convert to radians
    ra1_rad = math.radians(ra1 * 15)  # RA in hours to degrees
    dec1_rad = math.radians(dec1)
    ra2_rad = math.radians(ra2 * 15)
    dec2_rad = math.radians(dec2)

    # Spherical law of cosines
    cos_sep = math.sin(dec1_rad) * math.sin(dec2_rad) + math.cos(dec1_rad) * math.cos(dec2_rad) * math.cos(
        ra1_rad - ra2_rad
    )
    cos_sep = max(-1.0, min(1.0, cos_sep))  # Clamp to valid range
    separation_rad = math.acos(cos_sep)
    return math.degrees(separation_rad)


def _get_altitude(planet_name: str, observer_lat: float, observer_lon: float, t: Any, eph: Any) -> float:
    """Get planet altitude above horizon."""
    planet_key = planet_name.lower()
    if planet_key not in PLANET_NAMES:
        return -90.0

    ephemeris_name, _bsp_file = PLANET_NAMES[planet_key]
    earth = eph["earth"]
    observer = earth + Topos(latitude_degrees=observer_lat, longitude_degrees=observer_lon)

    try:
        target = eph[ephemeris_name]
    except KeyError:
        try:
            target = eph[ephemeris_name.upper()]
        except KeyError:
            return -90.0

    astrometric = observer.at(t).observe(target)
    alt, _az, _ = astrometric.apparent().altaz()
    return float(alt.degrees)


def get_planetary_conjunctions(
    location: ObserverLocation,
    max_separation: float = 5.0,  # degrees
    months_ahead: int = 12,
) -> list[PlanetaryEvent]:
    """
    Find planetary conjunctions (planets appearing close together).

    Args:
        location: Observer location
        max_separation: Maximum angular separation in degrees (default: 5.0)
        months_ahead: How many months ahead to search (default: 12)

    Returns:
        List of PlanetaryEvent objects, sorted by date
    """

    try:
        from .skyfield_utils import get_skyfield_loader

        loader = get_skyfield_loader()
        ts = loader.timescale()
        eph = _get_ephemeris("de440s.bsp")
    except Exception as e:
        logger.error(f"Error loading ephemeris: {e}")
        return []

    conjunctions = []
    now = datetime.now(UTC)
    end_date = now + timedelta(days=30 * months_ahead)

    # Check all planet pairs
    for i, planet1 in enumerate(MAJOR_PLANETS):
        for planet2 in MAJOR_PLANETS[i + 1 :]:
            try:
                # Find times when separation is minimized
                # Capture loop variables as default parameters to avoid closure issues
                def separation_at_time(t: Any, p1: str = planet1, p2: str = planet2) -> float:
                    pos1 = _get_planet_position(p1, t, eph)
                    pos2 = _get_planet_position(p2, t, eph)
                    if pos1 is None or pos2 is None:
                        return 180.0  # Maximum separation
                    ra1, dec1 = pos1
                    ra2, dec2 = pos2
                    return _angular_separation(ra1, dec1, ra2, dec2)

                t0 = ts.from_datetime(now)
                t1 = ts.from_datetime(end_date)

                # Find minima (closest approaches)
                minima_times, _ = find_minima(t0, t1, separation_at_time)

                for min_time in minima_times[:10]:  # Limit to first 10
                    separation = separation_at_time(min_time)
                    if separation <= max_separation:
                        event_time = min_time.utc_datetime()
                        if event_time.tzinfo is None:
                            event_time = event_time.replace(tzinfo=UTC)

                        # Get altitude for both planets
                        alt1 = _get_altitude(planet1, location.latitude, location.longitude, min_time, eph)
                        alt2 = _get_altitude(planet2, location.latitude, location.longitude, min_time, eph)
                        is_visible = alt1 > 0 or alt2 > 0
                        avg_altitude = (alt1 + alt2) / 2.0

                        notes = f"{planet1.capitalize()} and {planet2.capitalize()} appear {separation:.2f}° apart"

                        conjunctions.append(
                            PlanetaryEvent(
                                event_type=EventType.CONJUNCTION,
                                date=event_time,
                                planet1=planet1,
                                planet2=planet2,
                                separation_degrees=separation,
                                altitude_at_event=avg_altitude,
                                is_visible=is_visible,
                                notes=notes,
                            )
                        )
            except Exception as e:
                logger.debug(f"Error finding conjunction for {planet1}-{planet2}: {e}")
                continue

    # Sort by date
    conjunctions.sort(key=lambda e: e.date)
    return conjunctions


def get_planetary_oppositions(
    location: ObserverLocation,
    years_ahead: int = 5,
) -> list[PlanetaryEvent]:
    """
    Find planetary oppositions (planets at opposition - best viewing).

    Args:
        location: Observer location
        years_ahead: How many years ahead to search (default: 5)

    Returns:
        List of PlanetaryEvent objects, sorted by date
    """

    try:
        from .skyfield_utils import get_skyfield_loader

        loader = get_skyfield_loader()
        ts = loader.timescale()
        eph = _get_ephemeris("de440s.bsp")
        sun = eph["sun"]
        earth = eph["earth"]
    except Exception as e:
        logger.error(f"Error loading ephemeris: {e}")
        return []

    oppositions = []
    now = datetime.now(UTC)
    end_date = now + timedelta(days=365 * years_ahead)

    # Outer planets only (Mars, Jupiter, Saturn, Uranus, Neptune)
    outer_planets = ["mars", "jupiter", "saturn", "uranus", "neptune"]

    for planet_name in outer_planets:
        try:
            # Find times when planet is opposite sun (elongation = 180°)
            # Capture loop variable as default parameter to avoid closure issues
            def elongation_at_time(t: Any, pname: str = planet_name) -> float:
                pos = _get_planet_position(pname, t, eph)
                if pos is None:
                    return 0.0
                ra_planet, dec_planet = pos
                sun_astrometric = earth.at(t).observe(sun)
                ra_sun_obj, dec_sun_obj, _ = sun_astrometric.radec()
                ra_sun = ra_sun_obj.hours
                dec_sun = dec_sun_obj.degrees

                # Calculate elongation (angle between sun and planet)
                separation = _angular_separation(ra_planet, dec_planet, ra_sun, dec_sun)
                # We want 180°, so return difference from 180°
                return abs(separation - 180.0)

            t0 = ts.from_datetime(now)
            t1 = ts.from_datetime(end_date)

            # Find minima (closest to 180°)
            minima_times, _ = find_minima(t0, t1, elongation_at_time)

            for min_time in minima_times[:5]:  # Limit to first 5
                elongation_diff = elongation_at_time(min_time)
                if elongation_diff < 5.0:  # Within 5° of opposition
                    event_time = min_time.utc_datetime()
                    if event_time.tzinfo is None:
                        event_time = event_time.replace(tzinfo=UTC)

                    # Get actual elongation
                    pos = _get_planet_position(planet_name, min_time, eph)
                    if pos is None:
                        continue
                    ra_planet, dec_planet = pos
                    sun_astrometric = earth.at(min_time).observe(sun)
                    ra_sun_obj, dec_sun_obj, _ = sun_astrometric.radec()
                    ra_sun = ra_sun_obj.hours
                    dec_sun = dec_sun_obj.degrees
                    elongation = _angular_separation(ra_planet, dec_planet, ra_sun, dec_sun)

                    altitude = _get_altitude(planet_name, location.latitude, location.longitude, min_time, eph)
                    is_visible = altitude > 0

                    notes = f"{planet_name.capitalize()} at opposition - best viewing time"

                    oppositions.append(
                        PlanetaryEvent(
                            event_type=EventType.OPPOSITION,
                            date=event_time,
                            planet1=planet_name,
                            planet2=None,
                            separation_degrees=elongation,
                            altitude_at_event=altitude,
                            is_visible=is_visible,
                            notes=notes,
                        )
                    )
        except Exception as e:
            logger.debug(f"Error finding opposition for {planet_name}: {e}")
            continue

    # Sort by date
    oppositions.sort(key=lambda e: e.date)
    return oppositions


def get_retrograde_periods(
    location: ObserverLocation,
    years_ahead: int = 2,
) -> list[PlanetaryEvent]:
    """
    Find retrograde periods for planets.

    Args:
        location: Observer location
        years_ahead: How many years ahead to search (default: 2)

    Returns:
        List of PlanetaryEvent objects (retrograde_start and retrograde_end)
    """

    # Retrograde detection is complex - simplified version
    # For now, return empty list - can be enhanced later
    return []

"""
Ephemeris Calculations for Solar System Objects

Uses Skyfield library to calculate real-time positions of planets and moons.
"""

from datetime import datetime, timezone
from functools import lru_cache

from skyfield.api import load, wgs84
from skyfield.timelib import Time


# Planet names mapping to Skyfield ephemeris names
PLANET_NAMES = {
    "mercury": "mercury",
    "venus": "venus",
    "mars": "mars",
    "jupiter": "jupiter barycenter",
    "saturn": "saturn barycenter",
    "uranus": "uranus barycenter",
    "neptune": "neptune barycenter",
    "moon": "moon",
    # Jupiter moons
    "io": "io",
    "europa": "europa",
    "ganymede": "ganymede",
    "callisto": "callisto",
    # Saturn moons
    "titan": "titan",
    "rhea": "rhea",
    "iapetus": "iapetus",
    "dione": "dione",
    "tethys": "tethys",
}


@lru_cache(maxsize=1)
def _get_ephemeris():
    """
    Load planetary ephemeris data.

    Cached to avoid reloading the ephemeris file on every call.
    Downloads de421.bsp on first use (~17 MB).

    Returns:
        Loaded ephemeris data
    """
    return load("de421.bsp")


def get_planetary_position(
    planet_name: str,
    observer_lat: float | None = None,
    observer_lon: float | None = None,
    dt: datetime | None = None,
) -> tuple[float, float]:
    """
    Calculate the current RA/Dec position of a solar system object.

    Args:
        planet_name: Name of planet or moon (case-insensitive)
        observer_lat: Observer's latitude in degrees (default: uses saved location)
        observer_lon: Observer's longitude in degrees (default: uses saved location)
        dt: Datetime to calculate position for (default: now in UTC)

    Returns:
        Tuple of (ra_hours, dec_degrees)

    Raises:
        ValueError: If planet name is not recognized
    """
    # Use saved observer location if not specified
    if observer_lat is None or observer_lon is None:
        from .observer import get_observer_location

        location = get_observer_location()
        observer_lat = location.latitude
        observer_lon = location.longitude
    planet_key = planet_name.lower()

    if planet_key not in PLANET_NAMES:
        raise ValueError(
            f"Unknown planet/moon: {planet_name}. "
            f"Valid names: {', '.join(sorted(PLANET_NAMES.keys()))}"
        )

    # Load ephemeris
    eph = _get_ephemeris()

    # Get timescale and current time
    ts = load.timescale()
    if dt is None:
        dt = datetime.now(timezone.utc)
    elif dt.tzinfo is None:
        # Assume UTC if no timezone
        dt = dt.replace(tzinfo=timezone.utc)

    t = ts.from_datetime(dt)

    # Get Earth and target body
    earth = eph["earth"]

    # For moons, we need to reference them from their parent planet
    ephemeris_name = PLANET_NAMES[planet_key]

    try:
        target = eph[ephemeris_name]
    except KeyError:
        # Fallback for objects not in de421
        raise ValueError(f"Ephemeris data not available for {planet_name}")

    # Calculate apparent position from Earth
    astrometric = earth.at(t).observe(target)
    ra, dec, distance = astrometric.radec()

    # Convert RA from hours and Dec from degrees
    ra_hours = ra.hours
    dec_degrees = dec.degrees

    return (ra_hours, dec_degrees)


def is_dynamic_object(object_name: str) -> bool:
    """
    Check if an object has dynamic (time-varying) coordinates.

    Args:
        object_name: Name of the celestial object

    Returns:
        True if object position changes over time (planets, moons)
    """
    return object_name.lower() in PLANET_NAMES


def get_planet_magnitude(planet_name: str) -> float | None:
    """
    Get approximate magnitude for a planet.

    Note: Actual magnitude varies with distance and phase.
    These are typical/average values.

    Args:
        planet_name: Name of the planet

    Returns:
        Approximate magnitude or None if not available
    """
    # Approximate typical magnitudes
    magnitudes = {
        "mercury": -0.4,
        "venus": -4.4,
        "mars": -2.0,
        "jupiter": -2.5,
        "saturn": 0.2,
        "uranus": 5.7,
        "neptune": 7.8,
        "moon": -12.6,
        "io": 5.0,
        "europa": 5.3,
        "ganymede": 4.6,
        "callisto": 5.6,
        "titan": 8.4,
        "rhea": 9.7,
        "iapetus": 10.2,
        "dione": 10.4,
        "tethys": 10.3,
    }

    return magnitudes.get(planet_name.lower())

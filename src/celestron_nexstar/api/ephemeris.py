"""
Ephemeris Calculations for Solar System Objects

Uses Skyfield library to calculate real-time positions of planets and moons.
"""

from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from skyfield.api import Loader, load  # type: ignore[import-untyped]
from skyfield.jpllib import SpiceKernel  # type: ignore[import-untyped]


# Planet names mapping to Skyfield ephemeris names and required BSP files
PLANET_NAMES = {
    "mercury": ("mercury", "de440s.bsp"),
    "venus": ("venus", "de440s.bsp"),
    "mars": ("mars", "de440s.bsp"),
    "jupiter": ("jupiter barycenter", "de440s.bsp"),
    "saturn": ("saturn barycenter", "de440s.bsp"),
    "uranus": ("uranus barycenter", "de440s.bsp"),
    "neptune": ("neptune barycenter", "de440s.bsp"),
    "moon": ("moon", "de421.bsp"),  # de440s doesn't include Moon
    # Jupiter moons (jup365.bsp)
    "io": ("io", "jup365.bsp"),
    "europa": ("europa", "jup365.bsp"),
    "ganymede": ("ganymede", "jup365.bsp"),
    "callisto": ("callisto", "jup365.bsp"),
    # Saturn moons (sat441.bsp)
    "titan": ("titan", "sat441.bsp"),
    "rhea": ("rhea", "sat441.bsp"),
    "iapetus": ("iapetus", "sat441.bsp"),
    "dione": ("dione", "sat441.bsp"),
    "tethys": ("tethys", "sat441.bsp"),
    "enceladus": ("enceladus", "sat441.bsp"),
    "mimas": ("mimas", "sat441.bsp"),
    "hyperion": ("hyperion", "sat441.bsp"),
    # Uranus moons (ura184_part-1.bsp)
    "ariel": ("ariel", "ura184_part-1.bsp"),
    "umbriel": ("umbriel", "ura184_part-1.bsp"),
    "titania": ("titania", "ura184_part-1.bsp"),
    "oberon": ("oberon", "ura184_part-1.bsp"),
    "miranda": ("miranda", "ura184_part-1.bsp"),
    # Neptune moon (nep097.bsp)
    "triton": ("triton", "nep097.bsp"),
    # Mars moons (mar099s.bsp) - very challenging to observe!
    "phobos": ("phobos", "mar099s.bsp"),
    "deimos": ("deimos", "mar099s.bsp"),
}


# Cache for loaded ephemeris files
_ephemeris_cache: dict[str, SpiceKernel] = {}


def _get_skyfield_directory() -> Path:
    """Get the Skyfield cache directory."""
    return Path.home() / ".skyfield"


@lru_cache(maxsize=10)
def _get_ephemeris(bsp_file: str) -> SpiceKernel:
    """
    Load ephemeris data from a specific BSP file.

    Cached to avoid reloading files on every call.
    Will attempt to load from ~/.skyfield/ directory.

    Args:
        bsp_file: Name of the BSP file to load

    Returns:
        Loaded ephemeris data

    Raises:
        FileNotFoundError: If BSP file is not found
    """
    if bsp_file in _ephemeris_cache:
        return _ephemeris_cache[bsp_file]

    # Try to load from Skyfield directory first
    skyfield_dir = _get_skyfield_directory()
    bsp_path = skyfield_dir / bsp_file

    if bsp_path.exists():
        # Load from existing file
        loader = Loader(str(skyfield_dir))
        eph = loader(bsp_file)
    else:
        # File doesn't exist - load will try to download it
        eph = load(bsp_file)

    _ephemeris_cache[bsp_file] = eph
    return eph


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
        raise ValueError(f"Unknown planet/moon: {planet_name}. Valid names: {', '.join(sorted(PLANET_NAMES.keys()))}")

    # Get ephemeris name and required BSP file
    ephemeris_name, bsp_file = PLANET_NAMES[planet_key]

    # Load the appropriate ephemeris file
    try:
        eph = _get_ephemeris(bsp_file)
    except FileNotFoundError:
        raise ValueError(
            f"Ephemeris file {bsp_file} not found. "
            f"Download it with: nexstar ephemeris download {bsp_file.replace('.bsp', '')}"
        ) from None

    # Get timescale and current time
    ts = load.timescale()
    if dt is None:
        dt = datetime.now(UTC)
    elif dt.tzinfo is None:
        # Assume UTC if no timezone
        dt = dt.replace(tzinfo=UTC)

    t = ts.from_datetime(dt)

    # Get Earth and target body
    earth = eph["earth"]

    try:
        target = eph[ephemeris_name]
    except KeyError:
        raise ValueError(
            f"Object '{ephemeris_name}' not found in {bsp_file}. The ephemeris file may be missing or corrupted."
        ) from None

    # Calculate apparent position from Earth
    astrometric = earth.at(t).observe(target)
    ra, dec, _distance = astrometric.radec()

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
    # Source: NASA JPL Horizons and various astronomical databases
    magnitudes = {
        # Planets
        "mercury": -0.4,
        "venus": -4.4,
        "mars": -2.0,
        "jupiter": -2.5,
        "saturn": 0.2,
        "uranus": 5.7,
        "neptune": 7.8,
        "moon": -12.6,
        # Jupiter moons (Galilean satellites - easily visible with 6SE)
        "io": 5.0,
        "europa": 5.3,
        "ganymede": 4.6,
        "callisto": 5.6,
        # Saturn moons (Titan visible with 6SE, others challenging)
        "titan": 8.4,
        "rhea": 9.7,
        "iapetus": 10.2,  # Variable: 10.2-11.9
        "dione": 10.4,
        "tethys": 10.3,
        "enceladus": 11.7,
        "mimas": 12.9,
        "hyperion": 14.2,
        # Uranus moons (very challenging - need excellent conditions)
        "titania": 13.7,
        "oberon": 13.9,
        "umbriel": 14.5,
        "ariel": 14.2,
        "miranda": 15.8,
        # Neptune moon (extremely challenging)
        "triton": 13.5,
        # Mars moons (nearly impossible with amateur equipment)
        "phobos": 11.8,  # Very close to Mars, overwhelmed by planet's glare
        "deimos": 12.9,  # Even more challenging
    }

    return magnitudes.get(planet_name.lower())

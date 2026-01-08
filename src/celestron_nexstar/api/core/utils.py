"""
Utility functions for Celestron NexStar telescope coordinate conversions
and astronomical calculations.

Skyfield is preferred for astronomical calculations.
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from timezonefinder import TimezoneFinder


logger = logging.getLogger(__name__)


__all__ = [
    "alt_az_to_ra_dec",
    "angular_separation",
    "calculate_julian_date",
    "calculate_lst",
    "configure_astropy_iers",
    "dec_to_degrees",
    "degrees_to_dms",
    "ensure_utc",
    "format_dec",
    "format_local_time",
    "format_position",
    "format_ra",
    "get_local_timezone",
    "hours_to_hms",
    "point_in_polygon",
    "ra_dec_to_alt_az",
    "ra_to_degrees",
    "ra_to_hours",
]

# Global timezone finder instance (cached for performance)
_tz_finder = TimezoneFinder()


def ensure_utc(dt: datetime | None) -> datetime | None:
    """Return a UTC-aware datetime, treating naive values as UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def configure_astropy_iers() -> None:
    """Retained for backward compatibility; Skyfield does not require IERS setup here."""
    logger.debug("Astropy IERS configuration is no longer required; using Skyfield for calculations.")


def ra_to_degrees(hours: float, minutes: float = 0, seconds: float = 0) -> float:
    """
    Convert Right Ascension from hours/minutes/seconds to decimal degrees.

    Args:
        hours: RA hours (0-24)
        minutes: RA minutes (0-59)
        seconds: RA seconds (0-59)

    Returns:
        RA in decimal degrees (0-360)
    """
    total_hours = hours + minutes / 60.0 + seconds / 3600.0
    return total_hours * 15.0


def ra_to_hours(hours: float, minutes: float = 0, seconds: float = 0) -> float:
    """
    Convert Right Ascension from hours/minutes/seconds to decimal hours.

    Args:
        hours: RA hours (0-24)
        minutes: RA minutes (0-59)
        seconds: RA seconds (0-59)

    Returns:
        RA in decimal hours (0-24)
    """
    # Simple arithmetic conversion - no need for Astropy here
    return hours + minutes / 60.0 + seconds / 3600.0


def dec_to_degrees(degrees: float, minutes: float = 0, seconds: float = 0, sign: str = "+") -> float:
    """
    Convert Declination from degrees/minutes/seconds to decimal degrees.

    Args:
        degrees: Dec degrees (0-90)
        minutes: Dec minutes (0-59)
        seconds: Dec seconds (0-59)
        sign: '+' for north, '-' for south

    Returns:
        Dec in decimal degrees (-90 to +90)
    """
    total_degrees = abs(degrees) + minutes / 60.0 + seconds / 3600.0
    if sign == "-":
        total_degrees = -total_degrees
    return total_degrees


def degrees_to_dms(degrees: float) -> tuple[int, int, float, str]:
    """
    Convert decimal degrees to degrees/minutes/seconds format.

    Args:
        degrees: Decimal degrees

    Returns:
        Tuple of (degrees, minutes, seconds, sign)
    """
    sign = "+" if degrees >= 0 else "-"
    degrees = abs(degrees)
    d = int(degrees)
    minutes_full = (degrees - d) * 60.0
    m = int(minutes_full)
    s = (minutes_full - m) * 60.0
    return d, m, s, sign


def hours_to_hms(hours: float) -> tuple[int, int, float]:
    """
    Convert decimal hours to hours/minutes/seconds format.

    Args:
        hours: Decimal hours (0-24)

    Returns:
        Tuple of (hours, minutes, seconds)
    """
    hours = hours % 24.0
    h = int(hours)
    minutes_full = (hours - h) * 60.0
    m = int(minutes_full)
    s = (minutes_full - m) * 60.0
    return h, m, s


def alt_az_to_ra_dec(
    azimuth: float, altitude: float, latitude: float, longitude: float, utc_time: datetime
) -> tuple[float, float]:
    """
    Convert Alt/Az coordinates to RA/Dec coordinates.

    Args:
        azimuth: Azimuth in degrees (0-360)
        altitude: Altitude in degrees (-90 to +90)
        latitude: Observer latitude in degrees
        longitude: Observer longitude in degrees
        utc_time: UTC time as datetime object

    Returns:
        Tuple of (RA in hours, Dec in degrees)
    """
    from skyfield.api import Topos

    from celestron_nexstar.api.ephemeris.skyfield_utils import get_skyfield_ephemeris, get_skyfield_timescale

    if utc_time.tzinfo is None:
        utc_time = utc_time.replace(tzinfo=UTC)

    ts = get_skyfield_timescale()
    t = ts.from_datetime(utc_time)
    try:
        eph = get_skyfield_ephemeris("de421.bsp")
    except FileNotFoundError as e:
        raise RuntimeError("Skyfield ephemeris not found; install a BSP (e.g., de421.bsp).") from e

    earth = eph["earth"]
    observer = earth + Topos(latitude_degrees=latitude, longitude_degrees=longitude)
    apparent = observer.at(t).from_altaz(alt_degrees=altitude, az_degrees=azimuth)
    ra, dec, _ = apparent.radec()
    return ra.hours, dec.degrees


def ra_dec_to_alt_az(
    ra_hours: float, dec_degrees: float, latitude: float, longitude: float, utc_time: datetime
) -> tuple[float, float]:
    """
    Convert RA/Dec coordinates to Alt/Az coordinates.

    Args:
        ra_hours: Right Ascension in hours (0-24)
        dec_degrees: Declination in degrees (-90 to +90)
        latitude: Observer latitude in degrees
        longitude: Observer longitude in degrees
        utc_time: UTC time as datetime object

    Returns:
        Tuple of (Azimuth in degrees, Altitude in degrees)
    """
    # Validate declination is within valid range
    if not (-90.0 <= dec_degrees <= 90.0):
        raise ValueError(
            f"Invalid declination {dec_degrees}°. Declination must be between -90 and 90 degrees. RA: {ra_hours} hours"
        )

    # Validate RA is within valid range
    if not (0.0 <= ra_hours < 24.0):
        # Normalize RA to 0-24 range
        ra_hours = ra_hours % 24.0

    from skyfield.api import Star, Topos

    from celestron_nexstar.api.ephemeris.skyfield_utils import get_skyfield_ephemeris, get_skyfield_timescale

    if utc_time.tzinfo is None:
        utc_time = utc_time.replace(tzinfo=UTC)

    ts = get_skyfield_timescale()
    t = ts.from_datetime(utc_time)
    try:
        eph = get_skyfield_ephemeris("de421.bsp")
    except FileNotFoundError as e:
        raise RuntimeError("Skyfield ephemeris not found; install a BSP (e.g., de421.bsp).") from e

    earth = eph["earth"]
    observer = earth + Topos(latitude_degrees=latitude, longitude_degrees=longitude)
    star = Star(ra_hours=ra_hours, dec_degrees=dec_degrees)
    alt, az, _ = observer.at(t).observe(star).apparent().altaz()
    return az.degrees, alt.degrees


def calculate_lst(longitude: float, utc_time: datetime) -> float:
    """
    Calculate Local Sidereal Time.

    Args:
        longitude: Observer longitude in degrees (positive east)
        utc_time: UTC time as datetime object

    Returns:
        LST in hours (0-24)
    """
    from celestron_nexstar.api.ephemeris.skyfield_utils import get_skyfield_timescale

    if utc_time.tzinfo is None:
        utc_time = utc_time.replace(tzinfo=UTC)
    ts = get_skyfield_timescale()
    t = ts.from_datetime(utc_time)
    lst = (t.gmst + (longitude / 15.0)) % 24.0
    return float(lst)


def calculate_julian_date(dt: datetime) -> float:
    """
    Calculate Julian Date from datetime.

    Args:
        dt: datetime object (assumed to be UTC)

    Returns:
        Julian Date (UT1-based)
    """
    from celestron_nexstar.api.ephemeris.skyfield_utils import get_skyfield_timescale

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    ts = get_skyfield_timescale()
    t = ts.from_datetime(dt)
    return float(t.ut1)


def angular_separation(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    """
    Calculate angular separation between two celestial coordinates.

    Args:
        ra1: First RA in hours
        dec1: First Dec in degrees
        ra2: Second RA in hours
        dec2: Second Dec in degrees

    Returns:
        Angular separation in degrees
    """
    ra1_rad = math.radians(ra1 * 15.0)
    ra2_rad = math.radians(ra2 * 15.0)
    dec1_rad = math.radians(dec1)
    dec2_rad = math.radians(dec2)

    cos_sep = (
        math.sin(dec1_rad) * math.sin(dec2_rad)
        + math.cos(dec1_rad) * math.cos(dec2_rad) * math.cos(ra1_rad - ra2_rad)
    )
    cos_sep = max(-1.0, min(1.0, cos_sep))
    return math.degrees(math.acos(cos_sep))


def format_ra(hours: float, precision: int = 2) -> str:
    """
    Format RA as a readable string.

    Args:
        hours: RA in decimal hours
        precision: Decimal places for seconds

    Returns:
        Formatted string (e.g., "12h 34m 56.78s")
    """
    h, m, s = hours_to_hms(hours)
    return f"{h:02d}h {m:02d}m {s:0{precision + 3}.{precision}f}s"


def format_dec(degrees: float, precision: int = 1) -> str:
    """
    Format Dec as a readable string.

    Args:
        degrees: Dec in decimal degrees
        precision: Decimal places for arcseconds

    Returns:
        Formatted string (e.g., "+45° 12' 34.5\"")
    """
    d, m, s, sign = degrees_to_dms(degrees)
    return f"{sign}{d:02d}° {m:02d}' {s:0{precision + 3}.{precision}f}\""


def format_position(ra_hours: float, dec_degrees: float) -> str:
    """
    Format celestial position as readable string.

    Args:
        ra_hours: RA in hours
        dec_degrees: Dec in degrees

    Returns:
        Formatted position string
    """
    return f"RA: {format_ra(ra_hours)}, Dec: {format_dec(dec_degrees)}"


def get_local_timezone(lat: float, lon: float) -> ZoneInfo | None:
    """
    Get timezone for a given latitude and longitude.

    Args:
        lat: Latitude in degrees
        lon: Longitude in degrees

    Returns:
        ZoneInfo object for the timezone, or None if timezone cannot be determined
    """
    try:
        tz_name = _tz_finder.timezone_at(lat=lat, lng=lon)
        if tz_name:
            return ZoneInfo(tz_name)
    except Exception:
        pass
    return None


def format_local_time(dt: datetime, lat: float, lon: float) -> str:
    """
    Format datetime in local timezone, falling back to UTC if timezone unavailable.

    Args:
        dt: Datetime to format (assumed UTC if no timezone info)
        lat: Observer latitude in degrees
        lon: Observer longitude in degrees

    Returns:
        Formatted time string (e.g., "2024-10-14 08:30 PM PDT" or "2024-10-14 08:30 PM UTC")
    """
    # Ensure datetime has timezone info
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    tz = get_local_timezone(lat, lon)
    if tz:
        local_dt = dt.astimezone(tz)
        tz_name = local_dt.tzname() or (tz.key if hasattr(tz, "key") else "Local")
        return local_dt.strftime(f"%Y-%m-%d %I:%M %p {tz_name}")
    else:
        return dt.strftime("%Y-%m-%d %I:%M %p UTC")


def point_in_polygon(ra_hours: float, dec_degrees: float, polygon_coords: list[list[float]]) -> bool:
    """
    Check if a point (RA, Dec) is inside a polygon using the ray casting algorithm.

    The polygon coordinates should be in GeoJSON format: list of [lon, lat] pairs
    where lon is RA in degrees (converted from hours) and lat is Dec in degrees.

    Args:
        ra_hours: Right ascension in hours (0-24)
        dec_degrees: Declination in degrees (-90 to +90)
        polygon_coords: List of [lon, lat] coordinate pairs forming the polygon boundary

    Returns:
        True if point is inside polygon, False otherwise
    """
    if not polygon_coords or len(polygon_coords) < 3:
        return False

    # Convert RA from hours to degrees (longitude in GeoJSON)
    # GeoJSON uses: 0-12h RA = 0-180° lon, 12-24h RA = -180-0° lon
    ra_degrees = ra_hours * 15.0  # Convert hours to degrees
    if ra_degrees > 180:
        ra_degrees = ra_degrees - 360  # Convert to -180 to 180 range

    x, y = ra_degrees, dec_degrees
    n = len(polygon_coords)
    inside = False

    # Ray casting algorithm
    j = n - 1
    for i in range(n):
        xi, yi = polygon_coords[i][0], polygon_coords[i][1]
        xj, yj = polygon_coords[j][0], polygon_coords[j][1]

        # Check if ray crosses edge
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside

        j = i

    return inside

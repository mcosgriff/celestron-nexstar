"""
Utility functions for Celestron NexStar telescope coordinate conversions
and astronomical calculations.

This module uses Astropy extensively for all astronomical calculations,
providing a clean interface while leveraging a well-tested astronomy library.
"""

from __future__ import annotations

import logging
import warnings
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from astropy import units as u
from astropy.coordinates import ICRS, AltAz, Angle, EarthLocation, SkyCoord
from astropy.time import Time
from astropy.utils import iers
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
    "format_dec",
    "format_local_time",
    "format_position",
    "format_ra",
    "get_local_timezone",
    "hours_to_hms",
    "ra_dec_to_alt_az",
    "ra_to_degrees",
    "ra_to_hours",
]

# Global timezone finder instance (cached for performance)
_tz_finder = TimezoneFinder()


def configure_astropy_iers() -> None:
    """
    Configure Astropy IERS (International Earth Rotation Service) data handling.

    This function:
    1. Enables automatic downloading of the latest IERS data when needed
    2. Suppresses warnings about IERS data validity for dates beyond the current data range
       (these warnings are not critical for most applications as precision is only affected
       at the arcsec level, which is acceptable for most telescope control applications)

    Should be called early in application startup, before any astropy coordinate calculations.
    """
    try:
        # Enable automatic downloading of IERS data
        # Astropy will automatically download the latest IERS data when needed
        iers.conf.auto_download = True

        # Suppress the specific warning about IERS data validity
        # This warning appears when calculating positions for dates beyond the current IERS data range
        # For telescope control applications, the precision loss (arcsec level) is acceptable
        warnings.filterwarnings(
            "ignore",
            message=".*Tried to get polar motions for times after IERS data is valid.*",
            category=UserWarning,
            module="astropy.coordinates.builtin_frames.utils",
        )

        logger.debug("Astropy IERS configuration applied successfully")
    except Exception as e:
        # If configuration fails, log but don't raise - astropy will still work
        logger.warning(f"Could not configure Astropy IERS settings: {e}")


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
    # Use Astropy's Angle with explicit unit conversion
    total_hours = hours + minutes / 60.0 + seconds / 3600.0
    angle = Angle(total_hours, unit=u.hour)
    return float(angle.degree)


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
    # Use Astropy's Angle for conversion
    total_degrees = abs(degrees) + minutes / 60.0 + seconds / 3600.0
    if sign == "-":
        total_degrees = -total_degrees
    angle = Angle(total_degrees, unit=u.deg)
    return float(angle.degree)


def degrees_to_dms(degrees: float) -> tuple[int, int, float, str]:
    """
    Convert decimal degrees to degrees/minutes/seconds format.

    Args:
        degrees: Decimal degrees

    Returns:
        Tuple of (degrees, minutes, seconds, sign)
    """
    angle = Angle(degrees, unit=u.deg)
    dms = angle.dms
    sign = "+" if degrees >= 0 else "-"
    return int(abs(dms.d)), int(abs(dms.m)), abs(dms.s), sign


def hours_to_hms(hours: float) -> tuple[int, int, float]:
    """
    Convert decimal hours to hours/minutes/seconds format.

    Args:
        hours: Decimal hours (0-24)

    Returns:
        Tuple of (hours, minutes, seconds)
    """
    angle = Angle(hours, unit=u.hour)
    hms = angle.hms
    return int(hms.h), int(hms.m), hms.s


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
    # Create observer location
    location = EarthLocation(lat=latitude * u.deg, lon=longitude * u.deg)

    # Create time object
    time = Time(utc_time, scale="utc")

    # Create AltAz coordinate
    altaz = AltAz(az=azimuth * u.deg, alt=altitude * u.deg, location=location, obstime=time)

    # Convert to ICRS (RA/Dec)
    icrs = altaz.transform_to(ICRS())

    # Return RA in hours and Dec in degrees
    return icrs.ra.hour, icrs.dec.degree


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
    # Create observer location
    location = EarthLocation(lat=latitude * u.deg, lon=longitude * u.deg)

    # Create time object
    time = Time(utc_time, scale="utc")

    # Create ICRS coordinate (RA/Dec)
    icrs = SkyCoord(ra=ra_hours * u.hourangle, dec=dec_degrees * u.deg, frame="icrs")

    # Convert to AltAz
    altaz = icrs.transform_to(AltAz(location=location, obstime=time))

    # Return azimuth and altitude in degrees
    return altaz.az.degree, altaz.alt.degree


def calculate_lst(longitude: float, utc_time: datetime) -> float:
    """
    Calculate Local Sidereal Time.

    Args:
        longitude: Observer longitude in degrees (positive east)
        utc_time: UTC time as datetime object

    Returns:
        LST in hours (0-24)
    """
    # Create time object
    time = Time(utc_time, scale="utc")

    # Calculate LST using Astropy's sidereal time
    # longitude parameter expects Angle, so convert degrees to Angle
    lst = time.sidereal_time("mean", longitude=longitude * u.deg)

    return float(lst.hour)


def calculate_julian_date(dt: datetime) -> float:
    """
    Calculate Julian Date from datetime.

    Args:
        dt: datetime object (assumed to be UTC)

    Returns:
        Julian Date
    """
    time = Time(dt, scale="utc")
    return float(time.jd)


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
    # Create SkyCoord objects for both positions
    coord1 = SkyCoord(ra=ra1 * u.hourangle, dec=dec1 * u.deg, frame="icrs")
    coord2 = SkyCoord(ra=ra2 * u.hourangle, dec=dec2 * u.deg, frame="icrs")

    # Calculate separation using Astropy's built-in method
    separation = coord1.separation(coord2)

    return float(separation.degree)


def format_ra(hours: float, precision: int = 2) -> str:
    """
    Format RA as a readable string.

    Args:
        hours: RA in decimal hours
        precision: Decimal places for seconds

    Returns:
        Formatted string (e.g., "12h 34m 56.78s")
    """
    angle = Angle(hours, unit=u.hour)
    hms = angle.hms
    # Format with spaces: "12h 34m 56.78s"
    return f"{int(hms.h):02d}h {int(hms.m):02d}m {hms.s:0{precision + 3}.{precision}f}s"


def format_dec(degrees: float, precision: int = 1) -> str:
    """
    Format Dec as a readable string.

    Args:
        degrees: Dec in decimal degrees
        precision: Decimal places for arcseconds

    Returns:
        Formatted string (e.g., "+45° 12' 34.5\"")
    """
    angle = Angle(degrees, unit=u.deg)
    dms = angle.dms
    sign = "+" if degrees >= 0 else "-"
    # Format with spaces: "+45° 12' 34.5\""
    return f"{sign}{int(abs(dms.d)):02d}° {int(abs(dms.m)):02d}' {abs(dms.s):0{precision + 3}.{precision}f}\""


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

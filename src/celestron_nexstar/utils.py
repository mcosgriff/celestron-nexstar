"""
Utility functions for Celestron NexStar telescope coordinate conversions
and astronomical calculations.
"""

import math
from typing import Tuple
from datetime import datetime


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
    return total_hours * 15.0  # 15 degrees per hour


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
    return hours + minutes / 60.0 + seconds / 3600.0


def dec_to_degrees(degrees: float, minutes: float = 0, seconds: float = 0, sign: str = '+') -> float:
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

    if sign == '-':
        return -total_degrees
    return total_degrees


def degrees_to_dms(degrees: float) -> Tuple[int, int, float, str]:
    """
    Convert decimal degrees to degrees/minutes/seconds format.

    Args:
        degrees: Decimal degrees

    Returns:
        Tuple of (degrees, minutes, seconds, sign)
    """
    sign = '+' if degrees >= 0 else '-'
    abs_degrees = abs(degrees)

    deg = int(abs_degrees)
    min_decimal = (abs_degrees - deg) * 60
    minutes = int(min_decimal)
    seconds = (min_decimal - minutes) * 60

    return (deg, minutes, seconds, sign)


def hours_to_hms(hours: float) -> Tuple[int, int, float]:
    """
    Convert decimal hours to hours/minutes/seconds format.

    Args:
        hours: Decimal hours (0-24)

    Returns:
        Tuple of (hours, minutes, seconds)
    """
    h = int(hours)
    min_decimal = (hours - h) * 60
    minutes = int(min_decimal)
    seconds = (min_decimal - minutes) * 60

    return (h, minutes, seconds)


def alt_az_to_ra_dec(azimuth: float, altitude: float, latitude: float,
                      longitude: float, utc_time: datetime) -> Tuple[float, float]:
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
    # Convert to radians
    az_rad = math.radians(azimuth)
    alt_rad = math.radians(altitude)
    lat_rad = math.radians(latitude)

    # Calculate Local Sidereal Time
    lst_hours = calculate_lst(longitude, utc_time)
    lst_rad = math.radians(lst_hours * 15.0)

    # Calculate declination
    sin_dec = math.sin(alt_rad) * math.sin(lat_rad) + \
              math.cos(alt_rad) * math.cos(lat_rad) * math.cos(az_rad)
    dec_rad = math.asin(sin_dec)
    dec_deg = math.degrees(dec_rad)

    # Calculate hour angle
    cos_ha = (math.sin(alt_rad) - math.sin(lat_rad) * math.sin(dec_rad)) / \
             (math.cos(lat_rad) * math.cos(dec_rad))

    # Clamp to valid range to avoid numerical errors
    cos_ha = max(-1.0, min(1.0, cos_ha))
    ha_rad = math.acos(cos_ha)

    # Determine sign of hour angle
    if math.sin(az_rad) > 0:
        ha_rad = -ha_rad

    ha_hours = math.degrees(ha_rad) / 15.0

    # Calculate RA
    ra_hours = lst_hours - ha_hours

    # Normalize RA to 0-24 hours
    while ra_hours < 0:
        ra_hours += 24
    while ra_hours >= 24:
        ra_hours -= 24

    return (ra_hours, dec_deg)


def ra_dec_to_alt_az(ra_hours: float, dec_degrees: float, latitude: float,
                      longitude: float, utc_time: datetime) -> Tuple[float, float]:
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
    # Convert to radians
    ra_rad = math.radians(ra_hours * 15.0)
    dec_rad = math.radians(dec_degrees)
    lat_rad = math.radians(latitude)

    # Calculate Local Sidereal Time
    lst_hours = calculate_lst(longitude, utc_time)
    lst_rad = math.radians(lst_hours * 15.0)

    # Calculate hour angle
    ha_rad = lst_rad - ra_rad

    # Calculate altitude
    sin_alt = math.sin(dec_rad) * math.sin(lat_rad) + \
              math.cos(dec_rad) * math.cos(lat_rad) * math.cos(ha_rad)
    alt_rad = math.asin(sin_alt)
    altitude = math.degrees(alt_rad)

    # Calculate azimuth
    cos_az = (math.sin(dec_rad) - math.sin(lat_rad) * math.sin(alt_rad)) / \
             (math.cos(lat_rad) * math.cos(alt_rad))

    # Clamp to valid range
    cos_az = max(-1.0, min(1.0, cos_az))
    az_rad = math.acos(cos_az)

    # Determine sign of azimuth
    if math.sin(ha_rad) > 0:
        azimuth = 360 - math.degrees(az_rad)
    else:
        azimuth = math.degrees(az_rad)

    return (azimuth, altitude)


def calculate_lst(longitude: float, utc_time: datetime) -> float:
    """
    Calculate Local Sidereal Time.

    Args:
        longitude: Observer longitude in degrees (positive east)
        utc_time: UTC time as datetime object

    Returns:
        LST in hours (0-24)
    """
    # Julian Date
    jd = calculate_julian_date(utc_time)

    # Days since J2000.0
    d = jd - 2451545.0

    # Greenwich Mean Sidereal Time at 0h UT
    gmst = 18.697374558 + 24.06570982441908 * d

    # Normalize to 0-24 hours
    gmst = gmst % 24

    # Local Sidereal Time
    lst = gmst + longitude / 15.0

    # Normalize to 0-24 hours
    lst = lst % 24

    return lst


def calculate_julian_date(dt: datetime) -> float:
    """
    Calculate Julian Date from datetime.

    Args:
        dt: datetime object (assumed to be UTC)

    Returns:
        Julian Date
    """
    a = (14 - dt.month) // 12
    y = dt.year + 4800 - a
    m = dt.month + 12 * a - 3

    jdn = dt.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045

    # Time fraction
    time_fraction = (dt.hour - 12) / 24.0 + dt.minute / 1440.0 + dt.second / 86400.0

    return jdn + time_fraction


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
    # Convert to radians
    ra1_rad = math.radians(ra1 * 15.0)
    dec1_rad = math.radians(dec1)
    ra2_rad = math.radians(ra2 * 15.0)
    dec2_rad = math.radians(dec2)

    # Use spherical law of cosines
    cos_sep = math.sin(dec1_rad) * math.sin(dec2_rad) + \
              math.cos(dec1_rad) * math.cos(dec2_rad) * math.cos(ra1_rad - ra2_rad)

    # Clamp to valid range
    cos_sep = max(-1.0, min(1.0, cos_sep))

    separation_rad = math.acos(cos_sep)
    return math.degrees(separation_rad)


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
    return f"{h:02d}h {m:02d}m {s:0{precision+3}.{precision}f}s"


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
    return f"{sign}{d:02d}° {m:02d}' {s:0{precision+3}.{precision}f}\""


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

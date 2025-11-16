"""
Celestron NexStar Telescope Control Library

A comprehensive Python library for controlling Celestron NexStar telescopes
(including the NexStar 6SE/8SE) via serial and TCP/IP communication.

Based on NexStar 6/8SE specifications:
- Motor Resolution: 0.26 arc seconds
- Software Precision: 16-bit, 20 arc second calculations
- Slew Speeds: Nine speeds (5°/sec, 3°/sec, 1°/sec, 0.5°/sec, 32x, 16x, 8x, 4x, 2x)
- Tracking Rates: Sidereal, Solar, Lunar, and King
- Tracking Modes: Alt-Az, EQ North, EQ South

Example:
    >>> from celestron_nexstar import NexStarTelescope, TelescopeConfig, TrackingMode
    >>> config = TelescopeConfig(port='/dev/ttyUSB0')
    >>> telescope = NexStarTelescope(config)
    >>> telescope.connect()
    >>> position = telescope.get_position_ra_dec()
    >>> print(position)
    >>> telescope.set_tracking_mode(TrackingMode.ALT_AZ)
    >>> telescope.disconnect()
"""

# Main telescope class
# Coordinate converter
from celestron_nexstar.api.catalogs.converters import CoordinateConverter

# Exceptions
from celestron_nexstar.api.core.exceptions import (
    CommandError,
    InvalidCoordinateError,
    NexstarError,
    NotConnectedError,
    TelescopeConnectionError,
    TelescopeTimeoutError,
)

# Type definitions
from celestron_nexstar.api.core.types import (
    AlignmentMode,
    EquatorialCoordinates,
    GeographicLocation,
    HorizontalCoordinates,
    TelescopeConfig,
    TelescopeInfo,
    TelescopeTime,
    TrackingMode,
)

# Coordinate conversion utilities
from celestron_nexstar.api.core.utils import (
    alt_az_to_ra_dec,
    angular_separation,
    calculate_julian_date,
    calculate_lst,
    dec_to_degrees,
    degrees_to_dms,
    format_dec,
    format_position,
    format_ra,
    hours_to_hms,
    ra_dec_to_alt_az,
    ra_to_hours,
)
from celestron_nexstar.api.telescope.telescope import NexStarTelescope


__version__ = "0.1.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

__all__ = [
    "AlignmentMode",
    "CommandError",
    # Coordinate converter class
    "CoordinateConverter",
    "EquatorialCoordinates",
    "GeographicLocation",
    "HorizontalCoordinates",
    "InvalidCoordinateError",
    # Main telescope class
    "NexStarTelescope",
    # Exceptions
    "NexstarError",
    "NotConnectedError",
    "TelescopeConfig",
    "TelescopeConnectionError",
    "TelescopeInfo",
    "TelescopeTime",
    "TelescopeTimeoutError",
    # Type definitions
    "TrackingMode",
    "alt_az_to_ra_dec",
    "angular_separation",
    "calculate_julian_date",
    # Astronomical calculations
    "calculate_lst",
    "dec_to_degrees",
    "degrees_to_dms",
    "format_dec",
    "format_position",
    # Formatting
    "format_ra",
    "hours_to_hms",
    "ra_dec_to_alt_az",
    # Coordinate conversions (from utils.py)
    "ra_to_hours",
]

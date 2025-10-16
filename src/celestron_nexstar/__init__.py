"""
Celestron NexStar Telescope Control Library

A comprehensive Python library for controlling Celestron NexStar telescopes
(including the NexStar 6SE) via serial communication.

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
from celestron_nexstar.telescope import NexStarTelescope

# Type definitions
from celestron_nexstar.types import (
    TrackingMode,
    AlignmentMode,
    EquatorialCoordinates,
    HorizontalCoordinates,
    GeographicLocation,
    TelescopeInfo,
    TelescopeTime,
    TelescopeConfig,
)

# Exceptions
from celestron_nexstar.exceptions import (
    NexStarError,
    TelescopeConnectionError,
    TelescopeTimeoutError,
    InvalidCoordinateError,
    CommandError,
    NotConnectedError,
)

# Coordinate conversion utilities (from utils.py)
from celestron_nexstar.utils import (
    ra_to_hours,
    dec_to_degrees,
    hours_to_hms,
    degrees_to_dms,
    calculate_lst,
    calculate_julian_date,
    alt_az_to_ra_dec,
    ra_dec_to_alt_az,
    angular_separation,
    format_ra,
    format_dec,
    format_position,
)

# Coordinate converters (internal helper class)
from celestron_nexstar.converters import CoordinateConverter

__version__ = "0.2.0"  # Bumped version for new architecture
__author__ = "Your Name"
__email__ = "your.email@example.com"

__all__ = [
    # Main telescope class
    "NexStarTelescope",

    # Type definitions
    "TrackingMode",
    "AlignmentMode",
    "EquatorialCoordinates",
    "HorizontalCoordinates",
    "GeographicLocation",
    "TelescopeInfo",
    "TelescopeTime",
    "TelescopeConfig",

    # Exceptions
    "NexStarError",
    "TelescopeConnectionError",
    "TelescopeTimeoutError",
    "InvalidCoordinateError",
    "CommandError",
    "NotConnectedError",

    # Coordinate conversions (from utils.py)
    "ra_to_hours",
    "dec_to_degrees",
    "hours_to_hms",
    "degrees_to_dms",

    # Astronomical calculations
    "calculate_lst",
    "calculate_julian_date",
    "alt_az_to_ra_dec",
    "ra_dec_to_alt_az",
    "angular_separation",

    # Formatting
    "format_ra",
    "format_dec",
    "format_position",

    # Coordinate converter class
    "CoordinateConverter",
]

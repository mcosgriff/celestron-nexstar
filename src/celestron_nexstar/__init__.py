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
# Coordinate converters (internal helper class)
from celestron_nexstar.converters import CoordinateConverter

# Exceptions
from celestron_nexstar.exceptions import (
    CommandError,
    InvalidCoordinateError,
    NexStarError,
    NotConnectedError,
    TelescopeConnectionError,
    TelescopeTimeoutError,
)
from celestron_nexstar.telescope import NexStarTelescope

# Type definitions
from celestron_nexstar.types import (
    AlignmentMode,
    EquatorialCoordinates,
    GeographicLocation,
    HorizontalCoordinates,
    TelescopeConfig,
    TelescopeInfo,
    TelescopeTime,
    TrackingMode,
)

# Coordinate conversion utilities (from utils.py)
from celestron_nexstar.utils import (
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


__version__ = "0.2.0"  # Bumped version for new architecture
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
    # Exceptions
    "NexStarError",
    # Main telescope class
    "NexStarTelescope",
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

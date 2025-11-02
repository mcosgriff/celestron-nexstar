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

# Re-export everything from the api package for backward compatibility
from celestron_nexstar.api import (
    AlignmentMode,
    CommandError,
    # Coordinate converter class
    CoordinateConverter,
    EquatorialCoordinates,
    GeographicLocation,
    HorizontalCoordinates,
    InvalidCoordinateError,
    # Exceptions
    NexStarError,
    # Main telescope class
    NexStarTelescope,
    NotConnectedError,
    TelescopeConfig,
    TelescopeConnectionError,
    TelescopeInfo,
    TelescopeTime,
    TelescopeTimeoutError,
    # Type definitions
    TrackingMode,
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
    # Coordinate conversions
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

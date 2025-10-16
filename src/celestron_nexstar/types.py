"""
Type definitions for Celestron NexStar telescope control.

This module contains enums, dataclasses, and type definitions used
throughout the library.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TrackingMode(Enum):
    """
    Telescope tracking modes.

    Tracking compensates for Earth's rotation to keep celestial objects
    in the field of view.
    """
    OFF = 0        # No tracking
    ALT_AZ = 1     # Alt-Az tracking (for terrestrial or casual observing)
    EQ_NORTH = 2   # Equatorial tracking for Northern Hemisphere
    EQ_SOUTH = 3   # Equatorial tracking for Southern Hemisphere


class AlignmentMode(Enum):
    """
    Telescope alignment modes.

    Alignment calibrates the telescope's pointing model for accurate goto.
    More alignment stars generally result in better accuracy.
    """
    NO_ALIGNMENT = 0  # No alignment performed
    ONE_STAR = 1      # One-star alignment (basic)
    TWO_STAR = 2      # Two-star alignment (recommended)
    THREE_STAR = 3    # Three-star alignment (best accuracy)


@dataclass
class EquatorialCoordinates:
    """
    Equatorial coordinate system (RA/Dec).

    This is the standard celestial coordinate system used in astronomy.
    Coordinates are fixed relative to the celestial sphere.

    Attributes:
        ra_hours: Right Ascension in hours (0-24)
        dec_degrees: Declination in degrees (-90 to +90)
    """
    ra_hours: float
    dec_degrees: float

    def __str__(self) -> str:
        sign = '+' if self.dec_degrees >= 0 else '-'
        return f"RA {self.ra_hours:.4f}h, Dec {sign}{abs(self.dec_degrees):.4f}°"


@dataclass
class HorizontalCoordinates:
    """
    Horizontal coordinate system (Alt/Az).

    This system is relative to the observer's local horizon.
    Coordinates change as Earth rotates.

    Attributes:
        azimuth: Azimuth in degrees (0-360, where 0=North, 90=East, 180=South, 270=West)
        altitude: Altitude in degrees (-90 to +90, where 0=horizon, 90=zenith)
    """
    azimuth: float
    altitude: float

    def __str__(self) -> str:
        return f"Az {self.azimuth:.2f}°, Alt {self.altitude:.2f}°"


@dataclass
class GeographicLocation:
    """
    Observer's geographic location on Earth.

    Attributes:
        latitude: Latitude in degrees (-90 to +90, positive=North, negative=South)
        longitude: Longitude in degrees (-180 to +180, positive=East, negative=West)
    """
    latitude: float
    longitude: float

    def __str__(self) -> str:
        lat_dir = 'N' if self.latitude >= 0 else 'S'
        lon_dir = 'E' if self.longitude >= 0 else 'W'
        return f"{abs(self.latitude):.4f}°{lat_dir}, {abs(self.longitude):.4f}°{lon_dir}"


@dataclass
class TelescopeInfo:
    """
    Telescope hardware information.

    Attributes:
        model: Model number (e.g., 6 for NexStar 6SE)
        firmware_major: Firmware major version
        firmware_minor: Firmware minor version
    """
    model: int
    firmware_major: int
    firmware_minor: int

    def __str__(self) -> str:
        return f"Model {self.model}, Firmware {self.firmware_major}.{self.firmware_minor}"


@dataclass
class TelescopeTime:
    """
    Date and time information from the telescope.

    Attributes:
        hour: Hour (0-23)
        minute: Minute (0-59)
        second: Second (0-59)
        month: Month (1-12)
        day: Day (1-31)
        year: Year (e.g., 2024)
        timezone: Timezone offset from GMT in hours
        daylight_savings: Daylight savings flag (0 or 1)
    """
    hour: int
    minute: int
    second: int
    month: int
    day: int
    year: int
    timezone: int = 0
    daylight_savings: int = 0

    def __str__(self) -> str:
        return f"{self.year}-{self.month:02d}-{self.day:02d} {self.hour:02d}:{self.minute:02d}:{self.second:02d}"


@dataclass
class TelescopeConfig:
    """
    Configuration for telescope connection.

    Attributes:
        port: Serial port path (e.g., '/dev/ttyUSB0' on Linux, 'COM3' on Windows)
        baudrate: Communication speed (default 9600 for NexStar)
        timeout: Serial timeout in seconds
        auto_connect: Automatically connect on initialization
        verbose: Enable verbose logging
    """
    port: str = '/dev/ttyUSB0'
    baudrate: int = 9600
    timeout: float = 2.0
    auto_connect: bool = False
    verbose: bool = False

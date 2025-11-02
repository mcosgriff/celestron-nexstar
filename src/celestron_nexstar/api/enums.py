"""
Common Enums

Enumerations used throughout the Celestron NexStar API.
"""

from enum import Enum


class SkyBrightness(str, Enum):
    """Sky brightness/quality conditions for astronomical observation."""

    EXCELLENT = "excellent"  # Dark sky site (Bortle 1-2)
    GOOD = "good"  # Rural sky (Bortle 3-4)
    FAIR = "fair"  # Suburban sky (Bortle 5-6)
    POOR = "poor"  # Urban sky (Bortle 7-8)
    URBAN = "urban"  # City center (Bortle 9)


class CelestialObjectType(str, Enum):
    """Types of celestial objects in catalogs."""

    STAR = "star"
    PLANET = "planet"
    GALAXY = "galaxy"
    NEBULA = "nebula"
    CLUSTER = "cluster"
    DOUBLE_STAR = "double_star"
    ASTERISM = "asterism"
    CONSTELLATION = "constellation"
    MOON = "moon"


class EphemerisSet(str, Enum):
    """Predefined sets of ephemeris files."""

    MINIMAL = "minimal"  # Planets + Jupiter moons
    STANDARD = "standard"  # Planets + Jupiter & Saturn moons
    COMPLETE = "complete"  # All major moons except Mars
    FULL = "full"  # Everything including Mars moons


class Direction(str, Enum):
    """Movement directions for telescope control."""

    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


class Axis(str, Enum):
    """Telescope axes for control operations."""

    AZ = "az"  # Azimuth
    ALT = "alt"  # Altitude
    BOTH = "both"  # Both axes


class TrackingMode(str, Enum):
    """Telescope tracking modes."""

    ALT_AZ = "alt-az"  # Alt-azimuth mode
    EQ_NORTH = "eq-north"  # Equatorial mode (northern hemisphere)
    EQ_SOUTH = "eq-south"  # Equatorial mode (southern hemisphere)


class OutputFormat(str, Enum):
    """Output format options for CLI commands."""

    PRETTY = "pretty"  # Pretty-printed table
    JSON = "json"  # JSON output
    CSV = "csv"  # CSV output
    DMS = "dms"  # Degrees/minutes/seconds
    HMS = "hms"  # Hours/minutes/seconds

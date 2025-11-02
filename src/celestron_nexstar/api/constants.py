"""
Physical and Astronomical Constants

Constants used throughout the Celestron NexStar API for calculations.
"""

from typing import Final


__all__ = [
    "MM_PER_INCH",
    "HUMAN_EYE_PUPIL_MM",
    "DEGREES_PER_HOUR_ANGLE",
    "ARCSEC_PER_DEGREE",
    "ARCSEC_PER_ARCMIN",
]


# Conversion factors
MM_PER_INCH: Final[float] = 25.4
"""Millimeters per inch conversion factor."""

ARCSEC_PER_DEGREE: Final[float] = 3600.0
"""Arcseconds per degree."""

ARCSEC_PER_ARCMIN: Final[float] = 60.0
"""Arcseconds per arcminute."""

# Astronomical constants
DEGREES_PER_HOUR_ANGLE: Final[float] = 15.0
"""Degrees of sky rotation per hour of Right Ascension."""

# Optical constants
HUMAN_EYE_PUPIL_MM: Final[float] = 7.0
"""Average dark-adapted human eye pupil diameter in millimeters."""

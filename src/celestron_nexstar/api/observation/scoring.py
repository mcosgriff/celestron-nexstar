"""
Observation Scoring Functions

Functions for calculating observation quality scores, moon interference,
light pollution penalties, and other scoring metrics used in planning.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from celestron_nexstar.api.catalogs.catalogs import CelestialObject
from celestron_nexstar.api.core.enums import CelestialObjectType
from celestron_nexstar.api.core.utils import angular_separation
from celestron_nexstar.api.location.light_pollution import BortleClass, LightPollutionData
from celestron_nexstar.api.observation.observation_planner import ObservingConditions
from celestron_nexstar.api.observation.visibility import VisibilityInfo


__all__ = [
    "ObjectTypeWeights",
    "ObservationScoringWeights",
    "calculate_light_pollution_score",
    "calculate_moon_separation_score",
    "calculate_object_type_score",
    "is_nighttime",
]


# Scoring weights for best-night calculation
DEFAULT_SCORING_WEIGHTS = {
    "conditions_quality": 0.35,  # Overall conditions (clouds, transparency, wind)
    "seeing": 0.25,  # Atmospheric steadiness
    "visibility": 0.20,  # Object altitude and observability
    "moon_separation": 0.15,  # Angular distance from moon
    "moon_brightness": 0.05,  # Moon illumination
}

# Object-type specific scoring weights
# Different celestial objects have different observing requirements
OBJECT_TYPE_WEIGHTS: dict[CelestialObjectType | str, dict[str, float]] = {
    CelestialObjectType.PLANET: {
        "seeing": 0.45,  # Planets critically need steady air
        "visibility": 0.25,  # High altitude important for steadiness
        "conditions_quality": 0.20,  # General conditions matter
        "moon_separation": 0.05,  # Planets tolerate moon well (bright targets)
        "moon_brightness": 0.05,  # Moon brightness less critical
        "light_pollution_sensitivity": 0.0,  # Planets unaffected by light pollution
    },
    CelestialObjectType.GALAXY: {
        "moon_separation": 0.30,  # Galaxies very sensitive to moon proximity
        "conditions_quality": 0.25,  # Need dark, transparent skies
        "visibility": 0.25,  # Need good altitude
        "seeing": 0.10,  # Seeing less critical for extended objects
        "moon_brightness": 0.10,  # Also sensitive to moon brightness
        "light_pollution_sensitivity": 0.9,  # Extremely sensitive to light pollution
    },
    CelestialObjectType.NEBULA: {
        "moon_separation": 0.25,  # Nebulae sensitive to moon
        "conditions_quality": 0.30,  # Need transparency and darkness
        "visibility": 0.25,  # Need good altitude
        "seeing": 0.10,  # Seeing less critical
        "moon_brightness": 0.10,  # Moon brightness matters
        "light_pollution_sensitivity": 0.8,  # Very sensitive to light pollution
    },
    CelestialObjectType.CLUSTER: {
        "visibility": 0.30,  # Altitude very important
        "conditions_quality": 0.25,  # General conditions
        "seeing": 0.20,  # Some benefit from steady air
        "moon_separation": 0.15,  # Moderate moon sensitivity
        "moon_brightness": 0.10,  # Less sensitive than galaxies
        "light_pollution_sensitivity": 0.4,  # Moderately sensitive to light pollution
    },
    CelestialObjectType.DOUBLE_STAR: {
        "seeing": 0.50,  # Critical for resolving close pairs
        "visibility": 0.25,  # High altitude for steadiness
        "conditions_quality": 0.15,  # General conditions
        "moon_separation": 0.05,  # Stars tolerate moon well
        "moon_brightness": 0.05,  # Bright targets
        "light_pollution_sensitivity": 0.0,  # Stars unaffected by light pollution
    },
    # Default weights for other types (star, asterism, constellation, moon)
    "default": {
        "conditions_quality": 0.30,
        "seeing": 0.25,
        "visibility": 0.25,
        "moon_separation": 0.15,
        "moon_brightness": 0.05,
        "light_pollution_sensitivity": 0.3,  # Moderate sensitivity
    },
}


@dataclass(frozen=True)
class ObservationScoringWeights:
    """Scoring weights for observation quality calculation."""

    conditions_quality: float = 0.35
    seeing: float = 0.25
    visibility: float = 0.20
    moon_separation: float = 0.15
    moon_brightness: float = 0.05


@dataclass(frozen=True)
class ObjectTypeWeights:
    """Object-type specific scoring weights."""

    seeing: float
    visibility: float
    conditions_quality: float
    moon_separation: float
    moon_brightness: float
    light_pollution_sensitivity: float


def calculate_light_pollution_score(bortle_class: BortleClass) -> float:
    """
    Calculate light pollution quality score from Bortle class.

    Args:
        bortle_class: Bortle dark-sky scale class (1-9)

    Returns:
        Score from 0.0 (worst light pollution) to 1.0 (best darkness)
    """
    # Map Bortle class to quality score
    bortle_scores = {
        BortleClass.CLASS_1: 1.0,  # Excellent dark-sky site
        BortleClass.CLASS_2: 0.95,  # Typical truly dark site
        BortleClass.CLASS_3: 0.85,  # Rural sky
        BortleClass.CLASS_4: 0.70,  # Rural/suburban transition
        BortleClass.CLASS_5: 0.50,  # Suburban sky
        BortleClass.CLASS_6: 0.30,  # Bright suburban sky
        BortleClass.CLASS_7: 0.15,  # Suburban/urban transition
        BortleClass.CLASS_8: 0.05,  # City sky
        BortleClass.CLASS_9: 0.0,  # Inner-city sky
    }
    return bortle_scores.get(bortle_class, 0.5)  # Default to suburban


def calculate_moon_separation_score(
    object_ra_hours: float,
    object_dec_degrees: float,
    moon_ra_hours: float,
    moon_dec_degrees: float,
    moon_illumination: float,
) -> tuple[float, float]:
    """
    Calculate moon interference score based on separation and illumination.

    Args:
        object_ra_hours: Object's RA in hours
        object_dec_degrees: Object's declination in degrees
        moon_ra_hours: Moon's RA in hours
        moon_dec_degrees: Moon's declination in degrees
        moon_illumination: Moon illumination fraction (0.0-1.0)

    Returns:
        Tuple of (score, separation_degrees)
        - score: 0.0 (worst interference) to 1.0 (no interference)
        - separation_degrees: Angular separation in degrees
    """
    # Calculate angular separation between object and moon
    separation_deg = angular_separation(
        object_ra_hours,
        object_dec_degrees,
        moon_ra_hours,
        moon_dec_degrees,
    )

    # Moon interference is combination of:
    # 1. Angular separation (closer = worse)
    # 2. Moon brightness (brighter = worse)

    # Separation scoring:
    # - <15°: Very bad (moon glare ruins observation)
    # - 15-30°: Poor (significant interference)
    # - 30-60°: Fair (moderate interference)
    # - 60-90°: Good (minimal interference)
    # - >90°: Excellent (opposite sides of sky)

    if separation_deg >= 90:
        separation_score = 1.0
    elif separation_deg >= 60:
        separation_score = 0.8 + 0.2 * ((separation_deg - 60) / 30)
    elif separation_deg >= 30:
        separation_score = 0.5 + 0.3 * ((separation_deg - 30) / 30)
    elif separation_deg >= 15:
        separation_score = 0.2 + 0.3 * ((separation_deg - 15) / 15)
    else:
        separation_score = 0.2 * (separation_deg / 15)

    # Brightness factor: brighter moon = more interference
    # New moon (0% illumination) = no penalty
    # Full moon (100% illumination) = maximum penalty
    brightness_factor = 1.0 - (moon_illumination * 0.5)  # Max 50% reduction

    # Combined score
    final_score = separation_score * brightness_factor

    return final_score, separation_deg


def calculate_object_type_score(
    obj: CelestialObject,
    conditions: ObservingConditions,
    visibility: VisibilityInfo,
    moon_separation_score: float,
    light_pollution_data: LightPollutionData | None = None,
) -> float:
    """
    Calculate observation quality score tailored to the object's type.

    Different objects have different observing requirements:
    - Planets: Need excellent seeing, less affected by moon or light pollution
    - Galaxies: Need dark skies, distance from moon, and minimal light pollution
    - Nebulae: Need darkness, transparency, and low light pollution
    - Clusters: Need good altitude and moderate darkness
    - Double stars: Need excellent seeing to resolve

    Args:
        obj: Celestial object being observed
        conditions: Observing conditions for the night
        visibility: Visibility assessment for the object
        moon_separation_score: Pre-calculated moon-object separation score
        light_pollution_data: Light pollution information for observer location

    Returns:
        Total score (0.0-1.0) weighted for object type and adjusted for light pollution
    """
    # Get weights for this object type, fall back to default
    weights = OBJECT_TYPE_WEIGHTS.get(obj.object_type, OBJECT_TYPE_WEIGHTS["default"])

    # Calculate component scores
    conditions_score = conditions.observing_quality_score * weights["conditions_quality"]
    seeing_score = (conditions.seeing_score / 100.0) * weights["seeing"]
    visibility_score = visibility.observability_score * weights["visibility"]
    moon_sep_score = moon_separation_score * weights["moon_separation"]
    moon_brightness_score = (1.0 - conditions.moon_illumination) * weights["moon_brightness"]

    # Calculate base score (before light pollution penalty)
    base_score = conditions_score + seeing_score + visibility_score + moon_sep_score + moon_brightness_score

    # Apply light pollution penalty based on object sensitivity
    if light_pollution_data:
        light_pollution_quality = calculate_light_pollution_score(light_pollution_data.bortle_class)
        sensitivity = weights["light_pollution_sensitivity"]

        # Penalty formula: objects with higher sensitivity get more penalty in poor conditions
        # - Sensitivity 0.0 (planets, double stars): no penalty
        # - Sensitivity 0.9 (galaxies) in Bortle 5 (0.5 quality): 45% penalty (score reduced to 55%)
        # - Sensitivity 0.8 (nebulae) in Bortle 7 (0.15 quality): 68% penalty (score reduced to 32%)
        light_pollution_penalty = 1.0 - (sensitivity * (1.0 - light_pollution_quality))
        final_score = base_score * light_pollution_penalty
    else:
        # No light pollution data available, use base score
        final_score = base_score

    return final_score


def is_nighttime(timestamp: datetime, lat: float, lon: float) -> bool:
    """
    Determine if a timestamp is during nighttime (after sunset, before sunrise).

    Args:
        timestamp: Datetime to check
        lat: Observer latitude
        lon: Observer longitude

    Returns:
        True if timestamp is during nighttime, False otherwise
    """

    from celestron_nexstar.api.astronomy.solar_system import get_sun_info

    # Get sun info for this timestamp
    sun_info = get_sun_info(lat, lon, timestamp)

    # Check if sun is below horizon (nighttime)
    # get_sun_info always returns SunInfo (never None)
    if sun_info is None:
        # Fallback: assume daytime if we can't determine
        return False
    return not sun_info.is_daytime

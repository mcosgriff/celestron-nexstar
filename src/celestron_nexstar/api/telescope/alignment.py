"""
Telescope Alignment Methods

Implements various alignment methods including SkyAlign, which allows
beginners to align without knowing object names.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import combinations

import deal

from celestron_nexstar.api.astronomy.solar_system import get_moon_info
from celestron_nexstar.api.catalogs.catalogs import CelestialObject
from celestron_nexstar.api.core.enums import CelestialObjectType
from celestron_nexstar.api.core.utils import angular_separation
from celestron_nexstar.api.database.database import get_database
from celestron_nexstar.api.ephemeris.ephemeris import get_planet_magnitude, get_planetary_position
from celestron_nexstar.api.location.observer import get_observer_location
from celestron_nexstar.api.observation.visibility import VisibilityInfo, assess_visibility


logger = logging.getLogger(__name__)

__all__ = [
    "AlignmentConditions",
    "SkyAlignGroup",
    "SkyAlignObject",
    "TwoStarAlignPair",
    "find_skyalign_object_by_name",
    "get_alignment_conditions",
    "get_bright_objects_for_skyalign",
    "suggest_skyalign_objects",
    "suggest_two_star_align_objects",
]


@dataclass(frozen=True)
class SkyAlignObject:
    """An object suitable for SkyAlign alignment."""

    obj: CelestialObject
    visibility: VisibilityInfo
    display_name: str  # User-friendly name (e.g., "Vega" or "Jupiter")


@dataclass(frozen=True)
class SkyAlignGroup:
    """A group of 3 objects suitable for SkyAlign."""

    objects: tuple[SkyAlignObject, SkyAlignObject, SkyAlignObject]
    min_separation_deg: float  # Minimum angular separation between any two objects
    avg_observability_score: float  # Average observability score
    separation_score: float  # Score based on separation (higher = better separation)
    conditions_score: float = 1.0  # Score based on weather/sky conditions (0.0-1.0, higher = better conditions)


@dataclass(frozen=True)
class TwoStarAlignPair:
    """A pair of objects suitable for Two-Star alignment."""

    star1: SkyAlignObject  # First star (user manually slews to this)
    star2: SkyAlignObject  # Second star (telescope automatically slews to this)
    separation_deg: float  # Angular separation between the two stars
    avg_observability_score: float  # Average observability score
    separation_score: float  # Score based on separation (higher = better separation)
    conditions_score: float = 1.0  # Score based on weather/sky conditions (0.0-1.0, higher = better conditions)


@dataclass(frozen=True)
class AlignmentConditions:
    """Observing conditions data for alignment suggestions."""

    cloud_cover_percent: float | None = None
    moon_ra_hours: float | None = None
    moon_dec_degrees: float | None = None
    moon_illumination: float | None = None
    seeing_score: float | None = None


# SkyAlign requires bright objects: magnitude ≤ 2.5 for stars, or planets/Moon
SKYALIGN_MAX_MAGNITUDE = 2.5

# SkyAlign-suitable planets (bright enough and commonly visible)
SKYALIGN_PLANETS = ["venus", "jupiter", "saturn", "mars", "moon"]

# Minimum separation between objects (degrees) for good SkyAlign
MIN_SEPARATION_DEG = 30.0  # Objects should be at least 30° apart

# Ideal separation (degrees) - objects this far apart are optimal
IDEAL_SEPARATION_DEG = 60.0


@deal.post(lambda result: isinstance(result, list), message="Must return list of objects")
def get_bright_objects_for_skyalign(
    observer_lat: float | None = None,
    observer_lon: float | None = None,
    dt: datetime | None = None,
    min_altitude_deg: float = 20.0,
) -> list[SkyAlignObject]:
    """
    Get bright objects suitable for SkyAlign alignment.

    Returns objects that are:
    - Magnitude ≤ 2.5 (for stars) or planets/Moon
    - Currently visible (above horizon, good altitude)
    - Bright enough to see easily

    Args:
        observer_lat: Observer latitude
        observer_lon: Observer longitude
        dt: Datetime to check for (default: now)
        min_altitude_deg: Minimum altitude for comfortable viewing

    Returns:
        List of SkyAlignObject instances, sorted by observability score (best first)
    """
    if dt is None:
        dt = datetime.now(UTC)

    # Get observer location
    if observer_lat is None or observer_lon is None:
        location = get_observer_location()
        observer_lat = location.latitude
        observer_lon = location.longitude

    bright_objects: list[SkyAlignObject] = []

    # 1. Get bright stars from database (magnitude ≤ 2.5)
    db = get_database()
    import asyncio

    bright_stars = asyncio.run(
        db.filter_objects(
            object_type=CelestialObjectType.STAR,
            max_magnitude=SKYALIGN_MAX_MAGNITUDE,
            limit=100,
        )
    )

    # Assess visibility for each star
    for star in bright_stars:
        visibility = assess_visibility(
            star,
            min_altitude_deg=min_altitude_deg,
            observer_lat=observer_lat,
            observer_lon=observer_lon,
            dt=dt,
        )

        if visibility.is_visible and visibility.observability_score >= 0.5:
            display_name = star.common_name or star.name
            bright_objects.append(
                SkyAlignObject(
                    obj=star,
                    visibility=visibility,
                    display_name=display_name,
                )
            )

    # 2. Get planets and Moon
    for planet_name in SKYALIGN_PLANETS:
        try:
            # Get planet magnitude
            mag = get_planet_magnitude(planet_name)
            if (mag is None or mag > SKYALIGN_MAX_MAGNITUDE) and planet_name != "moon":
                # Moon is always included regardless of magnitude
                continue

            # Get current position
            ra_hours, dec_degrees = get_planetary_position(
                planet_name, observer_lat=observer_lat, observer_lon=observer_lon, dt=dt
            )

            # Create CelestialObject for planet
            planet_obj = CelestialObject(
                name=planet_name,
                common_name=planet_name.capitalize(),
                ra_hours=ra_hours,
                dec_degrees=dec_degrees,
                magnitude=mag,
                object_type=CelestialObjectType.PLANET if planet_name != "moon" else CelestialObjectType.MOON,
                catalog="solar_system",
            )

            # Assess visibility
            visibility = assess_visibility(
                planet_obj,
                min_altitude_deg=min_altitude_deg,
                observer_lat=observer_lat,
                observer_lon=observer_lon,
                dt=dt,
            )

            if visibility.is_visible and visibility.observability_score >= 0.5:
                display_name = planet_name.capitalize()
                if planet_name == "moon":
                    display_name = "Moon"
                bright_objects.append(
                    SkyAlignObject(
                        obj=planet_obj,
                        visibility=visibility,
                        display_name=display_name,
                    )
                )

        except Exception as e:
            logger.debug(f"Could not get position for {planet_name}: {e}")
            continue

    # Sort by observability score (best first)
    bright_objects.sort(key=lambda x: x.visibility.observability_score, reverse=True)

    return bright_objects


def get_alignment_conditions(
    observer_lat: float | None = None,
    observer_lon: float | None = None,
    dt: datetime | None = None,
) -> AlignmentConditions:
    """
    Get observing conditions data for alignment suggestions.

    Fetches weather, moon, and seeing data that can be used to improve
    alignment object suggestions. Returns None values if conditions are unavailable.

    Args:
        observer_lat: Observer latitude (default: from saved location)
        observer_lon: Observer longitude (default: from saved location)
        dt: Datetime to check for (default: now)

    Returns:
        AlignmentConditions with available data (some fields may be None)
    """
    if dt is None:
        dt = datetime.now(UTC)

    # Get observer location
    if observer_lat is None or observer_lon is None:
        location = get_observer_location()
        observer_lat = location.latitude
        observer_lon = location.longitude

    cloud_cover_percent = None
    moon_ra_hours = None
    moon_dec_degrees = None
    moon_illumination = None
    seeing_score = None

    try:
        from celestron_nexstar.api.observation.observation_planner import ObservationPlanner

        planner = ObservationPlanner()
        conditions = planner.get_tonight_conditions(lat=observer_lat, lon=observer_lon, start_time=dt)
        cloud_cover_percent = conditions.weather.cloud_cover_percent
        seeing_score = conditions.seeing_score

        # Get moon info
        moon_info = get_moon_info(observer_lat, observer_lon, dt)
        if moon_info:
            moon_ra_hours = moon_info.ra_hours
            moon_dec_degrees = moon_info.dec_degrees
            moon_illumination = moon_info.illumination
    except Exception as e:
        # Conditions unavailable - return with None values
        logger.debug(f"Could not fetch observing conditions: {e}")

    return AlignmentConditions(
        cloud_cover_percent=cloud_cover_percent,
        moon_ra_hours=moon_ra_hours,
        moon_dec_degrees=moon_dec_degrees,
        moon_illumination=moon_illumination,
        seeing_score=seeing_score,
    )


def find_skyalign_object_by_name(
    display_name: str,
    observer_lat: float | None = None,
    observer_lon: float | None = None,
    dt: datetime | None = None,
) -> SkyAlignObject | None:
    """
    Find a SkyAlignObject by its display name.

    Searches through bright objects suitable for alignment to find one
    matching the given display name.

    Args:
        display_name: Display name to search for (e.g., "Vega", "Jupiter")
        observer_lat: Observer latitude (default: from saved location)
        observer_lon: Observer longitude (default: from saved location)
        dt: Datetime to check for (default: now)

    Returns:
        SkyAlignObject if found, None otherwise
    """
    bright_objects = get_bright_objects_for_skyalign(observer_lat=observer_lat, observer_lon=observer_lon, dt=dt)

    for obj in bright_objects:
        if obj.display_name == display_name:
            return obj

    return None


def _calculate_separation_score(
    obj1: SkyAlignObject, obj2: SkyAlignObject, obj3: SkyAlignObject
) -> tuple[float, float]:
    """
    Calculate separation metrics for a group of 3 objects.

    Returns:
        (min_separation_deg, separation_score)
        - min_separation_deg: Minimum angular separation between any two objects
        - separation_score: Score from 0.0 to 1.0 (higher = better separation)
    """
    # Get positions
    alt1, az1 = obj1.visibility.altitude_deg or 0.0, obj1.visibility.azimuth_deg or 0.0
    alt2, az2 = obj2.visibility.altitude_deg or 0.0, obj2.visibility.azimuth_deg or 0.0
    alt3, az3 = obj3.visibility.altitude_deg or 0.0, obj3.visibility.azimuth_deg or 0.0

    # Convert alt/az to unit vectors for angular separation calculation
    # Using spherical coordinates: x = cos(alt) * cos(az), y = cos(alt) * sin(az), z = sin(alt)
    def alt_az_to_vector(alt_deg: float, az_deg: float) -> tuple[float, float, float]:
        alt_rad = math.radians(alt_deg)
        az_rad = math.radians(az_deg)
        x = math.cos(alt_rad) * math.cos(az_rad)
        y = math.cos(alt_rad) * math.sin(az_rad)
        z = math.sin(alt_rad)
        return (x, y, z)

    vec1 = alt_az_to_vector(alt1, az1)
    vec2 = alt_az_to_vector(alt2, az2)
    vec3 = alt_az_to_vector(alt3, az3)

    # Calculate angular separations using dot product
    def angular_sep_deg(v1: tuple[float, float, float], v2: tuple[float, float, float]) -> float:
        dot = sum(a * b for a, b in zip(v1, v2, strict=False))
        dot = max(-1.0, min(1.0, dot))  # Clamp to valid range
        angle_rad = math.acos(dot)
        return math.degrees(angle_rad)

    sep12 = angular_sep_deg(vec1, vec2)
    sep13 = angular_sep_deg(vec1, vec3)
    sep23 = angular_sep_deg(vec2, vec3)

    min_separation = min(sep12, sep13, sep23)
    avg_separation = (sep12 + sep13 + sep23) / 3.0

    # Calculate separation score
    # - Penalize if minimum separation is too small (< MIN_SEPARATION_DEG)
    # - Reward if separations are close to ideal (IDEAL_SEPARATION_DEG)
    if min_separation < MIN_SEPARATION_DEG:
        separation_score = min_separation / MIN_SEPARATION_DEG * 0.5  # Max 0.5 if too close
    else:
        # Score based on how close average separation is to ideal
        ideal_diff = abs(avg_separation - IDEAL_SEPARATION_DEG)
        separation_score = 0.5 + 0.5 * (1.0 - min(ideal_diff / IDEAL_SEPARATION_DEG, 1.0))

    return min_separation, separation_score


def _calculate_conditions_score(
    obj1: SkyAlignObject,
    obj2: SkyAlignObject,
    obj3: SkyAlignObject,
    cloud_cover_percent: float | None = None,
    moon_ra_hours: float | None = None,
    moon_dec_degrees: float | None = None,
    moon_illumination: float | None = None,
    seeing_score: float | None = None,
) -> float:
    """
    Calculate conditions score for a group based on weather and sky conditions.

    Args:
        obj1, obj2, obj3: Objects in the group
        cloud_cover_percent: Cloud cover percentage (0-100, None = unknown)
        moon_ra_hours: Moon RA in hours (None = unknown)
        moon_dec_degrees: Moon declination in degrees (None = unknown)
        moon_illumination: Moon illumination fraction (0.0-1.0, None = unknown)
        seeing_score: Astronomical seeing score (0-100, None = unknown)

    Returns:
        Conditions score from 0.0 to 1.0 (higher = better conditions)
    """
    score = 1.0

    # Factor 1: Cloud cover (heavily penalize if cloudy)
    if cloud_cover_percent is not None:
        if cloud_cover_percent > 80:
            score *= 0.3  # Very cloudy - objects may be obscured
        elif cloud_cover_percent > 50:
            score *= 0.6  # Partly cloudy - some objects may be obscured
        elif cloud_cover_percent > 20:
            score *= 0.85  # Light clouds - minor impact
        # <20% clouds: no penalty

    # Factor 2: Moon interference (bright moon washes out stars)
    if moon_ra_hours is not None and moon_dec_degrees is not None and moon_illumination is not None:
        # Calculate average moon separation for the group
        separations = []
        for obj in [obj1, obj2, obj3]:
            try:
                sep_deg = angular_separation(obj.obj.ra_hours, obj.obj.dec_degrees, moon_ra_hours, moon_dec_degrees)
                separations.append(sep_deg)
            except Exception:
                separations.append(180.0)  # Assume far if calculation fails

        avg_separation = sum(separations) / len(separations) if separations else 180.0

        # Moon interference scoring (similar to observation planner)
        if avg_separation >= 90:
            moon_score = 1.0  # Opposite side of sky
        elif avg_separation >= 60:
            moon_score = 0.8 + 0.2 * ((avg_separation - 60) / 30)
        elif avg_separation >= 30:
            moon_score = 0.5 + 0.3 * ((avg_separation - 30) / 30)
        elif avg_separation >= 15:
            moon_score = 0.2 + 0.3 * ((avg_separation - 15) / 15)
        else:
            moon_score = 0.2 * (avg_separation / 15)

        # Brightness factor: brighter moon = more interference
        brightness_factor = 1.0 - (moon_illumination * 0.5)  # Max 50% reduction
        moon_interference = moon_score * brightness_factor

        # Apply moon interference (only penalize if moon is bright and close)
        if moon_illumination > 0.3:  # Only consider if moon is >30% illuminated
            score *= 0.7 + 0.3 * moon_interference

    # Factor 3: Seeing conditions (affects how clearly objects can be seen)
    if seeing_score is not None:
        # Seeing score is 0-100, convert to 0.0-1.0 multiplier
        seeing_factor = seeing_score / 100.0
        # Apply moderate weight (seeing affects alignment less than observation)
        score *= 0.8 + 0.2 * seeing_factor

    return max(0.0, min(1.0, score))  # Clamp to 0.0-1.0


def _check_collinear(
    obj1: SkyAlignObject, obj2: SkyAlignObject, obj3: SkyAlignObject, threshold_deg: float = 10.0
) -> bool:
    """
    Check if three objects are approximately collinear.

    Args:
        obj1, obj2, obj3: Objects to check
        threshold_deg: Maximum deviation from straight line (degrees)

    Returns:
        True if objects appear collinear
    """
    # Get positions
    alt1, az1 = obj1.visibility.altitude_deg or 0.0, obj1.visibility.azimuth_deg or 0.0
    alt2, az2 = obj2.visibility.altitude_deg or 0.0, obj2.visibility.azimuth_deg or 0.0
    alt3, az3 = obj3.visibility.altitude_deg or 0.0, obj3.visibility.azimuth_deg or 0.0

    # Convert to unit vectors
    def alt_az_to_vector(alt_deg: float, az_deg: float) -> tuple[float, float, float]:
        alt_rad = math.radians(alt_deg)
        az_rad = math.radians(az_deg)
        x = math.cos(alt_rad) * math.cos(az_rad)
        y = math.cos(alt_rad) * math.sin(az_rad)
        z = math.sin(alt_rad)
        return (x, y, z)

    vec1 = alt_az_to_vector(alt1, az1)
    vec2 = alt_az_to_vector(alt2, az2)
    vec3 = alt_az_to_vector(alt3, az3)

    # Check if obj3 is close to the great circle arc between obj1 and obj2
    # Calculate cross product of vec1 and vec2 to get normal to the plane
    cross_x = vec1[1] * vec2[2] - vec1[2] * vec2[1]
    cross_y = vec1[2] * vec2[0] - vec1[0] * vec2[2]
    cross_z = vec1[0] * vec2[1] - vec1[1] * vec2[0]

    # Distance from vec3 to the plane (normalized)
    dist_to_plane = abs(cross_x * vec3[0] + cross_y * vec3[1] + cross_z * vec3[2]) / math.sqrt(
        cross_x**2 + cross_y**2 + cross_z**2
    )

    # Convert to angular distance
    angular_dist_deg = math.degrees(math.asin(min(1.0, dist_to_plane)))

    return angular_dist_deg < threshold_deg


@deal.pre(
    lambda observer_lat, observer_lon, *args, **kwargs: (
        -90 <= observer_lat <= 90 if observer_lat is not None else True
    ),
    message="Latitude must be -90 to +90",
)
@deal.pre(
    lambda observer_lat, observer_lon, *args, **kwargs: (
        -180 <= observer_lon <= 180 if observer_lon is not None else True
    ),
    message="Longitude must be -180 to +180",
)
@deal.post(lambda result: isinstance(result, list), message="Must return list of groups")
def suggest_skyalign_objects(
    observer_lat: float | None = None,
    observer_lon: float | None = None,
    dt: datetime | None = None,
    min_altitude_deg: float = 20.0,
    max_groups: int = 5,
    cloud_cover_percent: float | None = None,
    moon_ra_hours: float | None = None,
    moon_dec_degrees: float | None = None,
    moon_illumination: float | None = None,
    seeing_score: float | None = None,
) -> list[SkyAlignGroup]:
    """
    Suggest groups of 3 objects suitable for SkyAlign alignment.

    Uses visibility checks to find bright, well-separated objects that are
    currently visible and suitable for alignment. Optionally considers weather
    and sky conditions to rank groups.

    Args:
        observer_lat: Observer latitude
        observer_lon: Observer longitude
        dt: Datetime to check for (default: now)
        min_altitude_deg: Minimum altitude for comfortable viewing
        max_groups: Maximum number of groups to return
        cloud_cover_percent: Cloud cover percentage (0-100) for conditions scoring
        moon_ra_hours: Moon RA in hours for conditions scoring
        moon_dec_degrees: Moon declination in degrees for conditions scoring
        moon_illumination: Moon illumination fraction (0.0-1.0) for conditions scoring
        seeing_score: Astronomical seeing score (0-100) for conditions scoring

    Returns:
        List of SkyAlignGroup instances, sorted by quality (best first)
    """
    # Get bright objects
    bright_objects = get_bright_objects_for_skyalign(
        observer_lat=observer_lat, observer_lon=observer_lon, dt=dt, min_altitude_deg=min_altitude_deg
    )

    if len(bright_objects) < 3:
        logger.warning("Not enough bright objects visible for SkyAlign")
        return []

    # Find good groups of 3 objects
    groups: list[SkyAlignGroup] = []

    # Try combinations (limit to top N objects to avoid too many combinations)
    top_objects = bright_objects[:20]  # Consider top 20 objects

    for obj1, obj2, obj3 in combinations(top_objects, 3):
        # Check minimum separation
        min_sep, sep_score = _calculate_separation_score(obj1, obj2, obj3)

        if min_sep < MIN_SEPARATION_DEG:
            continue  # Objects too close together

        # Check if collinear
        if _check_collinear(obj1, obj2, obj3):
            continue  # Objects in a line

        # Calculate average observability score
        avg_score = (
            obj1.visibility.observability_score
            + obj2.visibility.observability_score
            + obj3.visibility.observability_score
        ) / 3.0

        # Only include groups with good observability
        if avg_score < 0.6:
            continue

        # Calculate conditions score if conditions data provided
        conditions_score = _calculate_conditions_score(
            obj1,
            obj2,
            obj3,
            cloud_cover_percent=cloud_cover_percent,
            moon_ra_hours=moon_ra_hours,
            moon_dec_degrees=moon_dec_degrees,
            moon_illumination=moon_illumination,
            seeing_score=seeing_score,
        )

        groups.append(
            SkyAlignGroup(
                objects=(obj1, obj2, obj3),
                min_separation_deg=min_sep,
                avg_observability_score=avg_score,
                separation_score=sep_score,
                conditions_score=conditions_score,
            )
        )

    # Sort by combined score (observability + separation + conditions)
    def group_score(group: SkyAlignGroup) -> float:
        # Weight: 50% observability, 30% separation, 20% conditions
        return group.avg_observability_score * 0.5 + group.separation_score * 0.3 + group.conditions_score * 0.2

    groups.sort(key=group_score, reverse=True)

    return groups[:max_groups]


def _calculate_two_star_separation_score(obj1: SkyAlignObject, obj2: SkyAlignObject) -> tuple[float, float]:
    """
    Calculate separation metrics for a pair of 2 objects.

    Returns:
        (separation_deg, separation_score)
        - separation_deg: Angular separation between the two objects
        - separation_score: Score from 0.0 to 1.0 (higher = better separation)
    """
    # Get positions
    alt1, az1 = obj1.visibility.altitude_deg or 0.0, obj1.visibility.azimuth_deg or 0.0
    alt2, az2 = obj2.visibility.altitude_deg or 0.0, obj2.visibility.azimuth_deg or 0.0

    # Convert alt/az to unit vectors for angular separation calculation
    def alt_az_to_vector(alt_deg: float, az_deg: float) -> tuple[float, float, float]:
        alt_rad = math.radians(alt_deg)
        az_rad = math.radians(az_deg)
        x = math.cos(alt_rad) * math.cos(az_rad)
        y = math.cos(alt_rad) * math.sin(az_rad)
        z = math.sin(alt_rad)
        return (x, y, z)

    vec1 = alt_az_to_vector(alt1, az1)
    vec2 = alt_az_to_vector(alt2, az2)

    # Calculate angular separation using dot product
    def angular_sep_deg(v1: tuple[float, float, float], v2: tuple[float, float, float]) -> float:
        dot = sum(a * b for a, b in zip(v1, v2, strict=False))
        dot = max(-1.0, min(1.0, dot))  # Clamp to valid range
        angle_rad = math.acos(dot)
        return math.degrees(angle_rad)

    separation = angular_sep_deg(vec1, vec2)

    # Calculate separation score
    # - Penalize if separation is too small (< MIN_SEPARATION_DEG)
    # - Reward if separation is close to ideal (IDEAL_SEPARATION_DEG)
    if separation < MIN_SEPARATION_DEG:
        separation_score = separation / MIN_SEPARATION_DEG * 0.5  # Max 0.5 if too close
    else:
        # Score based on how close separation is to ideal
        ideal_diff = abs(separation - IDEAL_SEPARATION_DEG)
        separation_score = 0.5 + 0.5 * (1.0 - min(ideal_diff / IDEAL_SEPARATION_DEG, 1.0))

    return separation, separation_score


def _calculate_two_star_conditions_score(
    obj1: SkyAlignObject,
    obj2: SkyAlignObject,
    cloud_cover_percent: float | None = None,
    moon_ra_hours: float | None = None,
    moon_dec_degrees: float | None = None,
    moon_illumination: float | None = None,
    seeing_score: float | None = None,
) -> float:
    """
    Calculate conditions score for a pair based on weather and sky conditions.

    Args:
        obj1, obj2: Objects in the pair
        cloud_cover_percent: Cloud cover percentage (0-100, None = unknown)
        moon_ra_hours: Moon RA in hours (None = unknown)
        moon_dec_degrees: Moon declination in degrees (None = unknown)
        moon_illumination: Moon illumination fraction (0.0-1.0, None = unknown)
        seeing_score: Astronomical seeing score (0-100, None = unknown)

    Returns:
        Conditions score from 0.0 to 1.0 (higher = better conditions)
    """
    score = 1.0

    # Factor 1: Cloud cover (heavily penalize if cloudy)
    if cloud_cover_percent is not None:
        if cloud_cover_percent > 80:
            score *= 0.3  # Very cloudy - objects may be obscured
        elif cloud_cover_percent > 50:
            score *= 0.6  # Partly cloudy - some objects may be obscured
        elif cloud_cover_percent > 20:
            score *= 0.85  # Light clouds - minor impact
        # <20% clouds: no penalty

    # Factor 2: Moon interference (bright moon washes out stars)
    if moon_ra_hours is not None and moon_dec_degrees is not None and moon_illumination is not None:
        # Calculate average moon separation for the pair
        separations = []
        for obj in [obj1, obj2]:
            try:
                sep_deg = angular_separation(obj.obj.ra_hours, obj.obj.dec_degrees, moon_ra_hours, moon_dec_degrees)
                separations.append(sep_deg)
            except Exception:
                separations.append(180.0)  # Assume far if calculation fails

        avg_separation = sum(separations) / len(separations) if separations else 180.0

        # Moon interference scoring
        if avg_separation >= 90:
            moon_score = 1.0  # Opposite side of sky
        elif avg_separation >= 60:
            moon_score = 0.8 + 0.2 * ((avg_separation - 60) / 30)
        elif avg_separation >= 30:
            moon_score = 0.5 + 0.3 * ((avg_separation - 30) / 30)
        elif avg_separation >= 15:
            moon_score = 0.2 + 0.3 * ((avg_separation - 15) / 15)
        else:
            moon_score = 0.2 * (avg_separation / 15)

        # Brightness factor: brighter moon = more interference
        brightness_factor = 1.0 - (moon_illumination * 0.5)  # Max 50% reduction
        moon_interference = moon_score * brightness_factor

        # Apply moon interference (only penalize if moon is bright and close)
        if moon_illumination > 0.3:  # Only consider if moon is >30% illuminated
            score *= 0.7 + 0.3 * moon_interference

    # Factor 3: Seeing conditions (affects how clearly objects can be seen)
    if seeing_score is not None:
        # Seeing score is 0-100, convert to 0.0-1.0 multiplier
        seeing_factor = seeing_score / 100.0
        # Apply moderate weight (seeing affects alignment less than observation)
        score *= 0.8 + 0.2 * seeing_factor

    return max(0.0, min(1.0, score))  # Clamp to 0.0-1.0


@deal.pre(
    lambda observer_lat, observer_lon, *args, **kwargs: (
        -90 <= observer_lat <= 90 if observer_lat is not None else True
    ),
    message="Latitude must be -90 to +90",
)
@deal.pre(
    lambda observer_lat, observer_lon, *args, **kwargs: (
        -180 <= observer_lon <= 180 if observer_lon is not None else True
    ),
    message="Longitude must be -180 to +180",
)
@deal.post(lambda result: isinstance(result, list), message="Must return list of pairs")
def suggest_two_star_align_objects(
    observer_lat: float | None = None,
    observer_lon: float | None = None,
    dt: datetime | None = None,
    min_altitude_deg: float = 20.0,
    max_pairs: int = 10,
    cloud_cover_percent: float | None = None,
    moon_ra_hours: float | None = None,
    moon_dec_degrees: float | None = None,
    moon_illumination: float | None = None,
    seeing_score: float | None = None,
) -> list[TwoStarAlignPair]:
    """
    Suggest pairs of objects suitable for Two-Star alignment.

    Uses visibility checks to find bright, well-separated objects that are
    currently visible and suitable for alignment. The first star should be
    selected by the user, and the telescope will automatically slew to the
    second star.

    Args:
        observer_lat: Observer latitude
        observer_lon: Observer longitude
        dt: Datetime to check for (default: now)
        min_altitude_deg: Minimum altitude for comfortable viewing
        max_pairs: Maximum number of pairs to return
        cloud_cover_percent: Cloud cover percentage (0-100) for conditions scoring
        moon_ra_hours: Moon RA in hours for conditions scoring
        moon_dec_degrees: Moon declination in degrees for conditions scoring
        moon_illumination: Moon illumination fraction (0.0-1.0) for conditions scoring
        seeing_score: Astronomical seeing score (0-100) for conditions scoring

    Returns:
        List of TwoStarAlignPair instances, sorted by quality (best first)
    """
    # Get bright objects
    bright_objects = get_bright_objects_for_skyalign(
        observer_lat=observer_lat, observer_lon=observer_lon, dt=dt, min_altitude_deg=min_altitude_deg
    )

    if len(bright_objects) < 2:
        logger.warning("Not enough bright objects visible for Two-Star alignment")
        return []

    # Find good pairs of objects
    pairs: list[TwoStarAlignPair] = []

    # Try combinations (limit to top N objects to avoid too many combinations)
    top_objects = bright_objects[:30]  # Consider top 30 objects for more options

    for obj1, obj2 in combinations(top_objects, 2):
        # Check minimum separation
        separation, sep_score = _calculate_two_star_separation_score(obj1, obj2)

        if separation < MIN_SEPARATION_DEG:
            continue  # Objects too close together

        # Calculate average observability score
        avg_score = (obj1.visibility.observability_score + obj2.visibility.observability_score) / 2.0

        # Only include pairs with good observability
        if avg_score < 0.6:
            continue

        # Calculate conditions score if conditions data provided
        conditions_score = _calculate_two_star_conditions_score(
            obj1,
            obj2,
            cloud_cover_percent=cloud_cover_percent,
            moon_ra_hours=moon_ra_hours,
            moon_dec_degrees=moon_dec_degrees,
            moon_illumination=moon_illumination,
            seeing_score=seeing_score,
        )

        pairs.append(
            TwoStarAlignPair(
                star1=obj1,
                star2=obj2,
                separation_deg=separation,
                avg_observability_score=avg_score,
                separation_score=sep_score,
                conditions_score=conditions_score,
            )
        )

    # Sort by combined score (observability + separation + conditions)
    def pair_score(pair: TwoStarAlignPair) -> float:
        # Weight: 50% observability, 30% separation, 20% conditions
        return pair.avg_observability_score * 0.5 + pair.separation_score * 0.3 + pair.conditions_score * 0.2

    pairs.sort(key=pair_score, reverse=True)

    return pairs[:max_pairs]

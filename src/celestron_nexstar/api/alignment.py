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

import deal

from .catalogs import CelestialObject
from .database import get_database
from .enums import CelestialObjectType
from .ephemeris import get_planet_magnitude, get_planetary_position
from .observer import get_observer_location
from .visibility import VisibilityInfo, assess_visibility


logger = logging.getLogger(__name__)

__all__ = [
    "SkyAlignGroup",
    "SkyAlignObject",
    "get_bright_objects_for_skyalign",
    "suggest_skyalign_objects",
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
    bright_stars = db.filter_objects(
        object_type=CelestialObjectType.STAR,
        max_magnitude=SKYALIGN_MAX_MAGNITUDE,
        limit=100,
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
) -> list[SkyAlignGroup]:
    """
    Suggest groups of 3 objects suitable for SkyAlign alignment.

    Uses visibility checks to find bright, well-separated objects that are
    currently visible and suitable for alignment.

    Args:
        observer_lat: Observer latitude
        observer_lon: Observer longitude
        dt: Datetime to check for (default: now)
        min_altitude_deg: Minimum altitude for comfortable viewing
        max_groups: Maximum number of groups to return

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

    for i in range(len(top_objects)):
        for j in range(i + 1, len(top_objects)):
            for k in range(j + 1, len(top_objects)):
                obj1, obj2, obj3 = top_objects[i], top_objects[j], top_objects[k]

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

                groups.append(
                    SkyAlignGroup(
                        objects=(obj1, obj2, obj3),
                        min_separation_deg=min_sep,
                        avg_observability_score=avg_score,
                        separation_score=sep_score,
                    )
                )

    # Sort by combined score (observability + separation)
    def group_score(group: SkyAlignGroup) -> float:
        return group.avg_observability_score * 0.6 + group.separation_score * 0.4

    groups.sort(key=group_score, reverse=True)

    return groups[:max_groups]

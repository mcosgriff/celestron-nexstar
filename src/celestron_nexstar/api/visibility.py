"""
Visibility Filtering and Calculations

Determines which celestial objects are visible based on telescope capabilities,
sky conditions, altitude, and other observing factors.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime


try:
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    np = None  # type: ignore[assignment]

from .catalogs import CelestialObject
from .enums import SkyBrightness
from .ephemeris import get_planetary_position, is_dynamic_object
from .observer import get_observer_location
from .optics import OpticalConfiguration, calculate_limiting_magnitude, get_current_configuration
from .utils import angular_separation, calculate_lst, ra_dec_to_alt_az


logger = logging.getLogger(__name__)


__all__ = [
    "VisibilityInfo",
    "assess_visibility",
    "calculate_atmospheric_extinction",
    "calculate_parent_separation",
    "filter_visible_objects",
    "get_object_altitude_azimuth",
]


@dataclass(frozen=True, slots=True)
class VisibilityInfo:
    """Information about an object's visibility."""

    object_name: str
    is_visible: bool
    magnitude: float | None
    altitude_deg: float | None  # Current altitude above horizon
    azimuth_deg: float | None  # Current azimuth
    limiting_magnitude: float  # Telescope's limiting magnitude
    reasons: tuple[str, ...]  # Reasons why visible or not visible
    observability_score: float  # 0.0 to 1.0, higher is better


def calculate_atmospheric_extinction(altitude_deg: float) -> float:
    """
    Calculate atmospheric extinction magnitude loss.

    Atmospheric extinction increases as objects get closer to the horizon
    due to longer path through atmosphere (higher airmass).

    Args:
        altitude_deg: Altitude above horizon in degrees

    Returns:
        Magnitude loss due to atmosphere (always positive)
    """
    if altitude_deg <= 0:
        return float("inf")  # Below horizon

    if altitude_deg >= 90:
        return 0.0  # At zenith, minimal extinction

    # Calculate airmass using plane-parallel approximation
    # Valid for altitudes > ~10 degrees
    if altitude_deg >= 10:
        zenith_angle_rad = math.radians(90 - altitude_deg)
        airmass = 1.0 / math.cos(zenith_angle_rad)
    else:
        # Use more accurate formula for low altitudes
        # Rozenberg 1966 formula
        zenith_angle_rad = math.radians(90 - altitude_deg)
        airmass = 1.0 / (math.cos(zenith_angle_rad) + 0.50572 * (96.07995 - (90 - altitude_deg)) ** -1.6364)

    # Typical extinction coefficient at sea level: ~0.2 mag/airmass at V-band
    # This varies with site quality, weather, and wavelength
    extinction_coefficient = 0.2

    return extinction_coefficient * (airmass - 1.0)


def get_object_altitude_azimuth(
    obj: CelestialObject,
    observer_lat: float | None = None,
    observer_lon: float | None = None,
    dt: datetime | None = None,
) -> tuple[float, float]:
    """
    Calculate object's current altitude and azimuth.

    Args:
        obj: Celestial object
        observer_lat: Observer's latitude in degrees
        observer_lon: Observer's longitude in degrees
        dt: Datetime to calculate for (default: now)

    Returns:
        Tuple of (altitude_deg, azimuth_deg)
    """
    # Get observer location
    if observer_lat is None or observer_lon is None:
        location = get_observer_location()
        observer_lat = location.latitude
        observer_lon = location.longitude

    if dt is None:
        dt = datetime.now(UTC)

    # Get object's RA/Dec
    if is_dynamic_object(obj.name):
        # Dynamic object - calculate current position
        ra_hours, dec_degrees = get_planetary_position(obj.name, observer_lat, observer_lon, dt)
    else:
        # Fixed object - use catalog coordinates
        ra_hours = obj.ra_hours
        dec_degrees = obj.dec_degrees

    # Convert to altitude/azimuth
    alt_deg, az_deg = ra_dec_to_alt_az(ra_hours, dec_degrees, observer_lat, observer_lon, dt)

    return alt_deg, az_deg


def calculate_parent_separation(
    moon_name: str,
    observer_lat: float | None = None,
    observer_lon: float | None = None,
    dt: datetime | None = None,
) -> float | None:
    """
    Calculate angular separation between a moon and its parent planet.

    Moons very close to their parent planet can be difficult to observe
    due to glare, even if they're bright enough.

    Args:
        moon_name: Name of the moon
        observer_lat: Observer latitude
        observer_lon: Observer longitude
        dt: Datetime to calculate for

    Returns:
        Angular separation in arcminutes, or None if not a moon
    """
    # Map moons to their parent planets
    moon_parents = {
        # Jupiter moons
        "io": "jupiter",
        "europa": "jupiter",
        "ganymede": "jupiter",
        "callisto": "jupiter",
        # Saturn moons
        "titan": "saturn",
        "rhea": "saturn",
        "iapetus": "saturn",
        "dione": "saturn",
        "tethys": "saturn",
        "enceladus": "saturn",
        "mimas": "saturn",
        "hyperion": "saturn",
        # Uranus moons
        "titania": "uranus",
        "oberon": "uranus",
        "ariel": "uranus",
        "umbriel": "uranus",
        "miranda": "uranus",
        # Neptune moon
        "triton": "neptune",
        # Mars moons
        "phobos": "mars",
        "deimos": "mars",
    }

    moon_key = moon_name.lower()
    if moon_key not in moon_parents:
        return None

    parent_name = moon_parents[moon_key]

    # Get positions of both objects
    try:
        moon_ra, moon_dec = get_planetary_position(moon_name, observer_lat, observer_lon, dt)
        parent_ra, parent_dec = get_planetary_position(parent_name, observer_lat, observer_lon, dt)

        # Calculate angular separation
        separation_deg = angular_separation(moon_ra, moon_dec, parent_ra, parent_dec)

        # Convert to arcminutes
        return separation_deg * 60.0

    except Exception:
        return None


def assess_visibility(
    obj: CelestialObject,
    config: OpticalConfiguration | None = None,
    sky_brightness: SkyBrightness = SkyBrightness.GOOD,
    min_altitude_deg: float = 20.0,
    observer_lat: float | None = None,
    observer_lon: float | None = None,
    dt: datetime | None = None,
) -> VisibilityInfo:
    """
    Assess whether an object is visible with given equipment and conditions.

    Args:
        obj: Celestial object to assess
        config: Optical configuration (telescope + eyepiece)
        sky_brightness: Sky quality
        min_altitude_deg: Minimum altitude for comfortable viewing
        observer_lat: Observer latitude
        observer_lon: Observer longitude
        dt: Datetime to assess for

    Returns:
        Visibility information with reasons
    """
    # Get optical configuration
    if config is None:
        config = get_current_configuration()

    # Calculate telescope's limiting magnitude
    limiting_mag = calculate_limiting_magnitude(
        config.telescope.effective_aperture_mm,
        sky_brightness=sky_brightness,
        exit_pupil_mm=config.exit_pupil_mm,
    )

    # Get object's current position
    try:
        altitude_deg, azimuth_deg = get_object_altitude_azimuth(obj, observer_lat, observer_lon, dt)
    except Exception as e:
        # Error getting position (e.g., missing ephemeris)
        return VisibilityInfo(
            object_name=obj.name,
            is_visible=False,
            magnitude=obj.magnitude,
            altitude_deg=None,
            azimuth_deg=None,
            limiting_magnitude=limiting_mag,
            reasons=(f"Cannot calculate position: {e!s}",),
            observability_score=0.0,
        )

    reasons = []
    is_visible = True
    observability_score = 1.0  # Start at perfect

    # Check 1: Above horizon
    if altitude_deg <= 0:
        is_visible = False
        reasons.append(f"Below horizon (alt: {altitude_deg:.1f}°)")
        observability_score = 0.0
    elif altitude_deg < min_altitude_deg:
        observability_score *= altitude_deg / min_altitude_deg
        reasons.append(f"Low altitude (alt: {altitude_deg:.1f}°, optimal >{min_altitude_deg:.0f}°)")

    # Check 2: Magnitude vs limiting magnitude (with atmospheric extinction)
    if obj.magnitude is not None and is_visible:
        extinction = calculate_atmospheric_extinction(altitude_deg)
        apparent_mag = obj.magnitude + extinction

        if apparent_mag > limiting_mag:
            is_visible = False
            reasons.append(f"Too faint: mag {apparent_mag:.1f} (with extinction) vs limit {limiting_mag:.1f}")
            observability_score = 0.0
        else:
            # Calculate how much "headroom" we have
            mag_headroom = limiting_mag - apparent_mag
            if mag_headroom < 1.0:
                observability_score *= 0.5 + 0.5 * mag_headroom
                reasons.append(f"Near detection limit (mag {apparent_mag:.1f}, limit {limiting_mag:.1f})")
            else:
                reasons.append(f"Magnitude {apparent_mag:.1f} well within limit")

    # Check 3: For moons, check separation from parent planet
    if obj.object_type == "moon" and obj.name.lower() != "moon":  # Not Earth's Moon
        separation_arcmin = calculate_parent_separation(obj.name, observer_lat, observer_lon, dt)

        if separation_arcmin is not None:
            # Moons very close to parent are hard to see due to glare
            if separation_arcmin < 1.0:
                is_visible = False
                reasons.append(f"Too close to parent planet ({separation_arcmin:.1f}' separation)")
                observability_score = 0.0
            elif separation_arcmin < 5.0:
                observability_score *= separation_arcmin / 5.0
                reasons.append(f"Close to parent planet ({separation_arcmin:.1f}' separation, glare may affect)")
            else:
                reasons.append(f"Good separation from parent ({separation_arcmin:.1f}')")

    # Check 4: Atmospheric conditions at low altitude
    if altitude_deg < 30 and is_visible:
        observability_score *= 0.7 + 0.3 * (altitude_deg / 30.0)
        reasons.append(f"Atmospheric distortion at low altitude ({altitude_deg:.1f}°)")

    # Add positive notes if highly observable
    if is_visible and observability_score > 0.8:
        if altitude_deg > 60:
            reasons.append("Excellent altitude for viewing")
        if obj.magnitude is not None and obj.magnitude < limiting_mag - 3:
            reasons.append("Bright and easy target")

    return VisibilityInfo(
        object_name=obj.name,
        is_visible=is_visible,
        magnitude=obj.magnitude,
        altitude_deg=altitude_deg,
        azimuth_deg=azimuth_deg,
        limiting_magnitude=limiting_mag,
        reasons=tuple(reasons),
        observability_score=observability_score,
    )


def filter_visible_objects(
    objects: list[CelestialObject],
    config: OpticalConfiguration | None = None,
    sky_brightness: SkyBrightness = SkyBrightness.GOOD,
    min_altitude_deg: float = 20.0,
    min_observability_score: float = 0.3,
    observer_lat: float | None = None,
    observer_lon: float | None = None,
    dt: datetime | None = None,
) -> list[tuple[CelestialObject, VisibilityInfo]]:
    """
    Filter a list of objects to only those currently visible.

    Uses vectorized numpy operations when available for faster processing.

    Args:
        objects: List of celestial objects
        config: Optical configuration
        sky_brightness: Sky quality
        min_altitude_deg: Minimum altitude threshold
        min_observability_score: Minimum score (0-1) for inclusion
        observer_lat: Observer latitude
        observer_lon: Observer longitude
        dt: Datetime to check for

    Returns:
        List of (object, visibility_info) tuples for visible objects,
        sorted by observability score (best first)
    """
    if not objects:
        return []

    # Get optical configuration
    if config is None:
        config = get_current_configuration()

    # Get observer location
    if observer_lat is None or observer_lon is None:
        location = get_observer_location()
        observer_lat = location.latitude
        observer_lon = location.longitude

    if dt is None:
        dt = datetime.now(UTC)

    # Calculate telescope's limiting magnitude once
    limiting_mag = calculate_limiting_magnitude(
        config.telescope.effective_aperture_mm,
        sky_brightness=sky_brightness,
        exit_pupil_mm=config.exit_pupil_mm,
    )

    # Use vectorized calculations if numpy is available and we have enough objects
    if NUMPY_AVAILABLE and len(objects) > 10:
        return _filter_visible_objects_vectorized(
            objects,
            config,
            limiting_mag,
            min_altitude_deg,
            min_observability_score,
            observer_lat,
            observer_lon,
            dt,
            sky_brightness,
        )

    # Fallback to original method for small lists or when numpy unavailable
    visible = []

    for obj in objects:
        visibility = assess_visibility(
            obj,
            config=config,
            sky_brightness=sky_brightness,
            min_altitude_deg=min_altitude_deg,
            observer_lat=observer_lat,
            observer_lon=observer_lon,
            dt=dt,
        )

        if visibility.is_visible and visibility.observability_score >= min_observability_score:
            visible.append((obj, visibility))

    # Sort by observability score (best first)
    visible.sort(key=lambda x: x[1].observability_score, reverse=True)

    return visible


def _filter_visible_objects_vectorized(
    objects: list[CelestialObject],
    config: OpticalConfiguration,
    limiting_mag: float,
    min_altitude_deg: float,
    min_observability_score: float,
    observer_lat: float,
    observer_lon: float,
    dt: datetime,
    sky_brightness: SkyBrightness,
) -> list[tuple[CelestialObject, VisibilityInfo]]:
    """
    Vectorized version of filter_visible_objects using numpy.

    Processes all objects in batch for faster computation.
    """
    if not NUMPY_AVAILABLE or np is None:
        # Fallback if numpy not available
        return []

    from .constants import DEGREES_PER_HOUR_ANGLE

    # Separate dynamic and fixed objects
    fixed_objects = []
    dynamic_objects = []
    dynamic_indices = []

    for i, obj in enumerate(objects):
        if is_dynamic_object(obj.name):
            dynamic_objects.append(obj)
            dynamic_indices.append(i)
        else:
            fixed_objects.append((i, obj))

    # Process fixed objects in batch (vectorized)
    if fixed_objects:
        _, fixed_objs = zip(*fixed_objects, strict=False)
        ra_hours = np.array([obj.ra_hours for obj in fixed_objs])
        dec_degrees = np.array([obj.dec_degrees for obj in fixed_objs])
        magnitudes = np.array([obj.magnitude if obj.magnitude is not None else 999.0 for obj in fixed_objs])

        # Calculate LST once
        lst_hours = calculate_lst(observer_lon, dt)
        lst_rad = np.radians(lst_hours * DEGREES_PER_HOUR_ANGLE)

        # Convert to radians
        ra_rad = np.radians(ra_hours * DEGREES_PER_HOUR_ANGLE)
        dec_rad = np.radians(dec_degrees)
        lat_rad = np.radians(observer_lat)

        # Calculate hour angles (vectorized)
        ha_rad = lst_rad - ra_rad

        # Calculate altitudes (vectorized)
        sin_alt = np.sin(dec_rad) * np.sin(lat_rad) + np.cos(dec_rad) * np.cos(lat_rad) * np.cos(ha_rad)
        sin_alt = np.clip(sin_alt, -1.0, 1.0)  # Clamp to valid range
        alt_rad = np.arcsin(sin_alt)
        altitudes = np.degrees(alt_rad)

        # Calculate atmospheric extinction (vectorized)
        extinction = np.where(altitudes > 0, 0.28 / np.tan(np.radians(altitudes)), 0.0)
        apparent_mags = magnitudes + extinction

        # Filter by altitude and magnitude (vectorized)
        above_horizon = altitudes > 0
        above_min_alt = altitudes >= min_altitude_deg
        bright_enough = apparent_mags <= limiting_mag

        # Calculate observability scores (vectorized)
        # Start with perfect score, reduce based on conditions
        scores = np.ones(len(fixed_objs), dtype=np.float64)

        # Reduce score for low altitude
        low_alt_mask = (altitudes > 0) & (altitudes < min_altitude_deg)
        scores[low_alt_mask] *= altitudes[low_alt_mask] / min_altitude_deg

        # Reduce score for objects near detection limit
        mag_headroom = limiting_mag - apparent_mags
        near_limit_mask = (mag_headroom >= 0) & (mag_headroom < 1.0)
        scores[near_limit_mask] *= 0.5 + 0.5 * mag_headroom[near_limit_mask]

        # Set score to 0 for invisible objects
        is_visible_mask = above_horizon & above_min_alt & bright_enough
        scores[~is_visible_mask] = 0.0

        # Process results
        visible = []
        for idx, (_, obj) in enumerate(fixed_objects):
            if is_visible_mask[idx] and scores[idx] >= min_observability_score:
                alt = float(altitudes[idx])
                az = float(
                    np.degrees(
                        np.arccos(
                            np.clip(
                                (np.sin(dec_rad[idx]) - np.sin(lat_rad) * np.sin(alt_rad[idx]))
                                / (np.cos(lat_rad) * np.cos(alt_rad[idx])),
                                -1.0,
                                1.0,
                            )
                        )
                    )
                )
                if np.sin(ha_rad[idx]) > 0:
                    az = 360.0 - az

                reasons = []
                if alt < min_altitude_deg:
                    reasons.append(f"Low altitude (alt: {alt:.1f}°, optimal >{min_altitude_deg:.0f}°)")
                if apparent_mags[idx] > limiting_mag - 1.0:
                    reasons.append(f"Near detection limit (mag {apparent_mags[idx]:.1f}, limit {limiting_mag:.1f})")
                else:
                    reasons.append(f"Magnitude {apparent_mags[idx]:.1f} well within limit")

                visibility = VisibilityInfo(
                    object_name=obj.name,
                    is_visible=True,
                    magnitude=obj.magnitude,
                    altitude_deg=alt,
                    azimuth_deg=az,
                    limiting_magnitude=limiting_mag,
                    reasons=tuple(reasons),
                    observability_score=float(scores[idx]),
                )
                visible.append((obj, visibility))

    # Process dynamic objects individually (can't vectorize easily)
    for obj in dynamic_objects:
        visibility = assess_visibility(
            obj,
            config=config,
            sky_brightness=sky_brightness,
            min_altitude_deg=min_altitude_deg,
            observer_lat=observer_lat,
            observer_lon=observer_lon,
            dt=dt,
        )
        if visibility.is_visible and visibility.observability_score >= min_observability_score:
            visible.append((obj, visibility))

    # Sort by observability score (best first)
    visible.sort(key=lambda x: x[1].observability_score, reverse=True)

    return visible

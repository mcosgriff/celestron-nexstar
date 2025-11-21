"""
Planning Utilities for Observation Sessions

Provides utilities for planning observation sessions including:
- Object visibility timelines (rise/set/transit)
- Time-based recommendations
- Checklists
- Equipment comparisons
- Difficulty ratings
- Moon phase impact guides
- Quick reference cards
- Session log templates
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from celestron_nexstar.api.catalogs.catalogs import CelestialObject
from celestron_nexstar.api.core.enums import CelestialObjectType, MoonPhase
from celestron_nexstar.api.core.utils import calculate_lst, ra_dec_to_alt_az
from celestron_nexstar.api.ephemeris.ephemeris import get_planetary_position, is_dynamic_object
from celestron_nexstar.api.location.observer import get_observer_location
from celestron_nexstar.api.observation.visibility import get_object_altitude_azimuth


logger = logging.getLogger(__name__)

__all__ = [
    "DifficultyLevel",
    "ObjectVisibilityTimeline",
    "compare_equipment",
    "generate_observation_checklist",
    "generate_quick_reference",
    "generate_session_log_template",
    "get_moon_phase_impact",
    "get_object_difficulty",
    "get_object_visibility_timeline",
    "get_time_based_recommendations",
    "get_transit_times",
]


class DifficultyLevel(StrEnum):
    """Difficulty levels for observing objects."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


@dataclass(frozen=True)
class ObjectVisibilityTimeline:
    """Timeline of object visibility events."""

    object_name: str
    rise_time: datetime | None
    transit_time: datetime | None
    set_time: datetime | None
    max_altitude: float
    is_circumpolar: bool
    is_always_visible: bool
    is_never_visible: bool


def _refine_horizon_crossing(
    prev_dt: datetime,
    check_dt: datetime,
    obj: CelestialObject,
    observer_lat: float,
    observer_lon: float,
    rising: bool,
) -> datetime | None:
    """Refine horizon crossing time using binary search."""
    # Sample at 5-minute intervals
    best_time = prev_dt + timedelta(minutes=30)
    min_diff = float("inf")

    for minutes_offset in range(0, 61, 5):
        test_dt = prev_dt + timedelta(minutes=minutes_offset)
        if test_dt > check_dt:
            break

        try:
            alt, _az = get_object_altitude_azimuth(obj, observer_lat, observer_lon, test_dt)
            diff = abs(alt)
            if diff < min_diff:
                min_diff = diff
                best_time = test_dt
            if diff < 0.1:
                break
        except Exception:
            continue

    return best_time if min_diff < 5.0 else None


def get_object_visibility_timeline(
    obj: CelestialObject,
    observer_lat: float | None = None,
    observer_lon: float | None = None,
    start_time: datetime | None = None,
    days: int = 1,
) -> ObjectVisibilityTimeline:
    """
    Calculate rise, set, and transit times for an object.

    Args:
        obj: Celestial object
        observer_lat: Observer latitude (default: from saved location)
        observer_lon: Observer longitude (default: from saved location)
        start_time: Start time for calculation (default: now)
        days: Number of days to search (default: 1)

    Returns:
        ObjectVisibilityTimeline with rise/set/transit times
    """
    if observer_lat is None or observer_lon is None:
        location = get_observer_location()
        observer_lat = location.latitude
        observer_lon = location.longitude

    if start_time is None:
        start_time = datetime.now(UTC)
    elif start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=UTC)

    # Get object RA/Dec
    if is_dynamic_object(obj.name):
        ra_hours, dec_degrees = get_planetary_position(obj.name, observer_lat, observer_lon, start_time)
    else:
        ra_hours = obj.ra_hours
        dec_degrees = obj.dec_degrees

    # Check if object is circumpolar
    # Object is circumpolar if |dec| > 90 - |lat|
    lat_abs = abs(observer_lat)
    dec_abs = abs(dec_degrees)
    is_circumpolar = dec_abs > (90 - lat_abs)

    # Calculate transit time (when object is highest)
    lst_hours = calculate_lst(observer_lon, start_time)
    ha_hours = lst_hours - ra_hours

    # Normalize hour angle
    while ha_hours > 12:
        ha_hours -= 24
    while ha_hours < -12:
        ha_hours += 24

    time_diff_hours = ha_hours * 0.9973
    transit_time = start_time + timedelta(hours=time_diff_hours)

    if abs(time_diff_hours) > 12:
        if time_diff_hours > 0:
            transit_time -= timedelta(hours=24)
        else:
            transit_time += timedelta(hours=24)

    # Get altitude at transit
    transit_alt, _ = ra_dec_to_alt_az(ra_hours, dec_degrees, observer_lat, observer_lon, transit_time)
    max_altitude = transit_alt

    # Check if always visible or never visible
    is_always_visible = is_circumpolar and transit_alt > 0
    is_never_visible = not is_circumpolar and transit_alt < 0

    # Find rise and set times
    rise_time: datetime | None = None
    set_time: datetime | None = None

    if not is_circumpolar and not is_never_visible:
        # Sample next 48 hours to find rise/set
        for hours_ahead in range(1, 49):
            check_dt = start_time + timedelta(hours=hours_ahead)
            try:
                alt_check, _ = get_object_altitude_azimuth(obj, observer_lat, observer_lon, check_dt)
                prev_dt = check_dt - timedelta(hours=1)
                alt_prev, _ = get_object_altitude_azimuth(obj, observer_lat, observer_lon, prev_dt)

                # Rise: was below, now above
                if alt_prev <= 0 and alt_check > 0 and rise_time is None:
                    rise_time = _refine_horizon_crossing(prev_dt, check_dt, obj, observer_lat, observer_lon, True)
                    if set_time is not None:
                        break

                # Set: was above, now below
                if alt_prev > 0 and alt_check <= 0 and set_time is None:
                    set_time = _refine_horizon_crossing(prev_dt, check_dt, obj, observer_lat, observer_lon, False)
                    if rise_time is not None:
                        break
            except Exception:
                continue

    return ObjectVisibilityTimeline(
        object_name=obj.name,
        rise_time=rise_time,
        transit_time=transit_time if transit_alt > 0 else None,
        set_time=set_time,
        max_altitude=max_altitude,
        is_circumpolar=is_circumpolar,
        is_always_visible=is_always_visible,
        is_never_visible=is_never_visible,
    )


def get_time_based_recommendations(
    time_slots: list[datetime],
    observer_lat: float | None = None,
    observer_lon: float | None = None,
    equipment_type: str = "telescope",
) -> dict[datetime, list[CelestialObject]]:
    """
    Get object recommendations for specific time slots.

    Args:
        time_slots: List of datetime objects for different time windows
        observer_lat: Observer latitude
        observer_lon: Observer longitude
        equipment_type: Type of equipment ("telescope", "binoculars", "naked_eye")

    Returns:
        Dictionary mapping time slots to recommended objects
    """
    # This is a placeholder - would need to query database and filter by visibility
    # For now, return empty dict
    return {dt: [] for dt in time_slots}


def generate_observation_checklist(
    equipment_type: str = "telescope",
    include_weather: bool = True,
    include_setup: bool = True,
) -> list[str]:
    """
    Generate a pre-observation checklist.

    Args:
        equipment_type: Type of equipment ("telescope", "binoculars", "naked_eye")
        include_weather: Include weather check items
        include_setup: Include setup items

    Returns:
        List of checklist items
    """
    checklist: list[str] = []

    if include_weather:
        checklist.extend(
            [
                "Check weather forecast",
                "Check cloud cover",
                "Check wind conditions",
                "Check moon phase and position",
                "Check light pollution conditions",
            ]
        )

    if include_setup:
        if equipment_type == "telescope":
            checklist.extend(
                [
                    "Set up telescope mount",
                    "Level the mount",
                    "Align finder scope",
                    "Perform star alignment",
                    "Check battery/power",
                    "Prepare eyepieces",
                    "Prepare filters (if needed)",
                    "Set up red flashlight",
                    "Bring star charts/app",
                ]
            )
        elif equipment_type == "binoculars":
            checklist.extend(
                [
                    "Check binocular focus",
                    "Clean lenses",
                    "Prepare tripod (if using)",
                    "Bring star charts/app",
                    "Set up red flashlight",
                ]
            )
        else:  # naked_eye
            checklist.extend(
                [
                    "Allow 20-30 minutes for dark adaptation",
                    "Bring star charts/app",
                    "Use red flashlight only",
                    "Find dark location away from lights",
                ]
            )

    checklist.extend(
        [
            "Dress appropriately for temperature",
            "Bring water and snacks",
            "Notify someone of your location",
            "Check phone battery",
        ]
    )

    return checklist


def compare_equipment(
    object_name: str,
    equipment_types: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Compare what you can see with different equipment types.

    Args:
        object_name: Name of object to compare
        equipment_types: List of equipment types to compare (default: all)

    Returns:
        Dictionary with comparison data
    """
    if equipment_types is None:
        equipment_types = ["naked_eye", "binoculars", "telescope"]

    # Placeholder - would need to query object and assess visibility
    return {eq: {"visible": False, "notes": "Not implemented"} for eq in equipment_types}


def get_object_difficulty(obj: CelestialObject) -> DifficultyLevel:
    """
    Determine difficulty level for observing an object.

    Args:
        obj: Celestial object

    Returns:
        Difficulty level
    """
    obj_type = obj.object_type
    magnitude = obj.magnitude or 99.0

    # Planets are generally beginner-friendly
    if obj_type == CelestialObjectType.PLANET:
        return DifficultyLevel.BEGINNER

    # Bright stars are beginner-friendly
    if obj_type == CelestialObjectType.STAR and magnitude < 3.0:
        return DifficultyLevel.BEGINNER

    # Bright deep sky objects
    if obj_type in (CelestialObjectType.GALAXY, CelestialObjectType.NEBULA, CelestialObjectType.CLUSTER):
        if magnitude < 6.0:
            return DifficultyLevel.BEGINNER
        elif magnitude < 9.0:
            return DifficultyLevel.INTERMEDIATE
        elif magnitude < 12.0:
            return DifficultyLevel.ADVANCED
        else:
            return DifficultyLevel.EXPERT

    # Double stars
    if obj_type == CelestialObjectType.DOUBLE_STAR:
        if magnitude < 5.0:
            return DifficultyLevel.INTERMEDIATE
        else:
            return DifficultyLevel.ADVANCED

    # Variable stars (treated as regular stars for difficulty)
    # Note: Variable stars are typically STAR type in the catalog
    # They're generally advanced due to the need for magnitude estimation

    # Default
    if magnitude < 4.0:
        return DifficultyLevel.BEGINNER
    elif magnitude < 7.0:
        return DifficultyLevel.INTERMEDIATE
    elif magnitude < 10.0:
        return DifficultyLevel.ADVANCED
    else:
        return DifficultyLevel.EXPERT


def get_moon_phase_impact(
    object_type: CelestialObjectType | str,
    moon_phase: MoonPhase | None = None,
    moon_illumination: float | None = None,
) -> dict[str, Any]:
    """
    Get moon phase impact on observing different object types.

    Args:
        object_type: Type of object to observe
        moon_phase: Current moon phase
        moon_illumination: Moon illumination (0.0 to 1.0)

    Returns:
        Dictionary with impact information
    """
    if isinstance(object_type, str):
        try:
            object_type = CelestialObjectType(object_type)
        except ValueError:
            object_type = CelestialObjectType.STAR  # Default

    impact_data: dict[str, Any] = {
        "recommended": True,
        "impact_level": "none",
        "notes": [],
    }

    # Determine moon brightness
    if moon_illumination is None:
        moon_illumination = 0.5 if moon_phase else 0.0

    is_bright_moon = moon_illumination > 0.5

    # Planets are generally unaffected by moon
    if object_type == CelestialObjectType.PLANET:
        impact_data["impact_level"] = "minimal"
        impact_data["notes"].append("Planets are bright enough to observe even with bright moon")
        return impact_data

    # Bright stars are minimally affected
    if object_type == CelestialObjectType.STAR:
        if is_bright_moon:
            impact_data["impact_level"] = "moderate"
            impact_data["notes"].append("Bright moon may wash out fainter stars")
        else:
            impact_data["impact_level"] = "minimal"
        return impact_data

    # Deep sky objects are heavily affected
    if object_type in (CelestialObjectType.GALAXY, CelestialObjectType.NEBULA):
        if is_bright_moon:
            impact_data["recommended"] = False
            impact_data["impact_level"] = "severe"
            impact_data["notes"].append("Avoid observing galaxies/nebulae during bright moon phases")
            impact_data["notes"].append("Best during new moon or when moon is below horizon")
        else:
            impact_data["impact_level"] = "minimal"
            impact_data["notes"].append("Good conditions for deep sky observing")
        return impact_data

    # Star clusters
    if object_type == CelestialObjectType.CLUSTER:
        if is_bright_moon:
            impact_data["impact_level"] = "moderate"
            impact_data["notes"].append("Bright moon may reduce contrast in star clusters")
        else:
            impact_data["impact_level"] = "minimal"
        return impact_data

    # Default
    if is_bright_moon:
        impact_data["impact_level"] = "moderate"
    else:
        impact_data["impact_level"] = "minimal"

    return impact_data


def generate_quick_reference(
    objects: list[CelestialObject],
    observer_lat: float | None = None,
    observer_lon: float | None = None,
) -> str:
    """
    Generate a quick reference card for objects.

    Args:
        objects: List of objects to include
        observer_lat: Observer latitude
        observer_lon: Observer longitude

    Returns:
        Formatted quick reference text
    """
    lines = ["QUICK REFERENCE CARD", "=" * 50, ""]

    for obj in objects[:20]:  # Limit to 20 objects
        mag_str = f"{obj.magnitude:.1f}" if obj.magnitude else "N/A"
        difficulty = get_object_difficulty(obj)
        lines.append(f"{obj.name:20s} | Mag: {mag_str:>5s} | {difficulty.value}")
        if obj.object_type:
            lines.append(f"  Type: {obj.object_type.value}")

    return "\n".join(lines)


def generate_session_log_template(
    date: datetime | None = None,
    location: str | None = None,
) -> str:
    """
    Generate a session log template.

    Args:
        date: Date for the session
        location: Location name

    Returns:
        Formatted log template
    """
    if date is None:
        date = datetime.now(UTC)

    template = f"""
OBSERVATION SESSION LOG
{"=" * 50}
Date: {date.strftime("%Y-%m-%d")}
Location: {location or "TBD"}
Observer: _________________

CONDITIONS:
- Weather: _________________
- Cloud Cover: _____%
- Temperature: _____°F
- Wind: _____ mph
- Moon Phase: _________________
- Light Pollution: Bortle _____

EQUIPMENT:
- Telescope: _________________
- Eyepieces: _________________
- Filters: _________________

OBSERVATIONS:
{"=" * 50}

Object: _________________
Time: _____:_____
Altitude: _____°
Azimuth: _____°
Conditions: _________________
Notes: _________________

{"=" * 50}
"""
    return template


def get_transit_times(
    objects: list[CelestialObject],
    observer_lat: float | None = None,
    observer_lon: float | None = None,
    date: datetime | None = None,
) -> dict[str, datetime]:
    """
    Get transit times (when objects are highest) for a list of objects.

    Args:
        objects: List of objects
        observer_lat: Observer latitude
        observer_lon: Observer longitude
        date: Date to calculate for (default: tonight)

    Returns:
        Dictionary mapping object names to transit times
    """
    if observer_lat is None or observer_lon is None:
        location = get_observer_location()
        observer_lat = location.latitude
        observer_lon = location.longitude

    if date is None:
        date = datetime.now(UTC)
    elif date.tzinfo is None:
        date = date.replace(tzinfo=UTC)

    transit_times: dict[str, datetime] = {}

    for obj in objects:
        try:
            timeline = get_object_visibility_timeline(obj, observer_lat, observer_lon, date)
            if timeline.transit_time:
                transit_times[obj.name] = timeline.transit_time
        except Exception:
            continue

    return transit_times

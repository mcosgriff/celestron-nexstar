"""
Object Filtering and Sorting Functions

Functions for filtering and sorting celestial objects with visibility information.
These functions are designed to be reusable across CLI, TUI, and other interfaces.
"""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from celestron_nexstar.api.catalogs.catalogs import CelestialObject
    from celestron_nexstar.api.observation.visibility import VisibilityInfo


def filter_objects(
    objects: list[tuple[CelestialObject, VisibilityInfo]],
    *,
    search_query: str | None = None,
    object_type: str | None = None,
    magnitude_min: float | None = None,
    magnitude_max: float | None = None,
    constellation: str | None = None,
) -> list[tuple[CelestialObject, VisibilityInfo]]:
    """
    Filter a list of (object, visibility_info) tuples by various criteria.

    Args:
        objects: List of (CelestialObject, VisibilityInfo) tuples
        search_query: Search string to match against object name or common_name (case-insensitive)
        object_type: Filter by object type (e.g., "star", "galaxy", "nebula")
        magnitude_min: Minimum magnitude (objects with None magnitude are excluded)
        magnitude_max: Maximum magnitude (objects with None magnitude are excluded)
        constellation: Filter by constellation name (case-insensitive)

    Returns:
        Filtered list of (object, visibility_info) tuples
    """
    filtered = objects

    # Apply search filter
    if search_query:
        search_lower = search_query.lower().strip()
        if search_lower:
            filtered = [
                (obj, vis_info)
                for obj, vis_info in filtered
                if search_lower in obj.name.lower() or (obj.common_name and search_lower in obj.common_name.lower())
            ]

    # Apply type filter
    if object_type:
        filtered = [(obj, vis_info) for obj, vis_info in filtered if obj.object_type.value == object_type]

    # Apply magnitude filters
    if magnitude_min is not None:
        filtered = [
            (obj, vis_info)
            for obj, vis_info in filtered
            if obj.magnitude is not None and obj.magnitude >= magnitude_min
        ]

    if magnitude_max is not None:
        filtered = [
            (obj, vis_info)
            for obj, vis_info in filtered
            if obj.magnitude is not None and obj.magnitude <= magnitude_max
        ]

    # Apply constellation filter
    if constellation:
        constellation_lower = constellation.lower().strip()
        if constellation_lower:
            filtered = [
                (obj, vis_info)
                for obj, vis_info in filtered
                if obj.constellation and constellation_lower in obj.constellation.lower()
            ]

    return filtered


def sort_objects(
    objects: list[tuple[CelestialObject, VisibilityInfo]],
    *,
    sort_by: str = "altitude",
    reverse: bool = False,
) -> list[tuple[CelestialObject, VisibilityInfo]]:
    """
    Sort a list of (object, visibility_info) tuples by various criteria.

    Args:
        objects: List of (CelestialObject, VisibilityInfo) tuples
        sort_by: Sort criterion - "altitude", "magnitude", "name", or "type"
        reverse: If True, sort in descending order

    Returns:
        Sorted list of (object, visibility_info) tuples
    """
    if not objects:
        return objects

    def sort_key(item: tuple[CelestialObject, VisibilityInfo]) -> tuple[float | str, ...]:
        obj, vis_info = item
        if sort_by == "altitude":
            # Sort by altitude (higher is better, so use -999 for None to put at end)
            return (vis_info.altitude_deg if vis_info.altitude_deg is not None else -999,)
        elif sort_by == "magnitude":
            # Sort by magnitude (lower is brighter, so use 999 for None to put at end)
            mag = obj.magnitude if obj.magnitude is not None else 999
            return (mag,)
        elif sort_by == "name":
            # Sort alphabetically by name
            return (obj.name.lower(),)
        elif sort_by == "type":
            # Sort by type, then by name
            return (obj.object_type.value, obj.name.lower())
        else:
            # Default: no sorting
            return (0,)

    return sorted(objects, key=sort_key, reverse=reverse)


def filter_and_sort_objects(
    objects: list[tuple[CelestialObject, VisibilityInfo]],
    *,
    search_query: str | None = None,
    object_type: str | None = None,
    magnitude_min: float | None = None,
    magnitude_max: float | None = None,
    constellation: str | None = None,
    sort_by: str = "altitude",
    sort_reverse: bool = False,
    limit: int | None = None,
) -> list[tuple[CelestialObject, VisibilityInfo]]:
    """
    Filter and sort a list of (object, visibility_info) tuples.

    This is a convenience function that combines filter_objects and sort_objects.

    Args:
        objects: List of (CelestialObject, VisibilityInfo) tuples
        search_query: Search string to match against object name or common_name
        object_type: Filter by object type
        magnitude_min: Minimum magnitude
        magnitude_max: Maximum magnitude
        constellation: Filter by constellation name
        sort_by: Sort criterion - "altitude", "magnitude", "name", or "type"
        sort_reverse: If True, sort in descending order
        limit: Maximum number of objects to return (None for no limit)

    Returns:
        Filtered and sorted list of (object, visibility_info) tuples
    """
    # Apply filters
    filtered = filter_objects(
        objects,
        search_query=search_query,
        object_type=object_type,
        magnitude_min=magnitude_min,
        magnitude_max=magnitude_max,
        constellation=constellation,
    )

    # Apply sorting
    sorted_objects = sort_objects(filtered, sort_by=sort_by, reverse=sort_reverse)

    # Apply limit
    if limit is not None:
        if limit <= 0:
            return []
        return sorted_objects[:limit]

    return sorted_objects

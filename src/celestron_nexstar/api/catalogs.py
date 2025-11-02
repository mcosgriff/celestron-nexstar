"""
Celestial Object Catalogs

Loads and caches celestial object catalogs from YAML data files.
Dynamically calculates positions for solar system objects.
"""

from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

import yaml
from cachetools import TTLCache, cached
from fuzzysearch import find_near_matches  # type: ignore[import-untyped]

from .enums import CelestialObjectType
from .ephemeris import get_planetary_position, is_dynamic_object


@dataclass
class CelestialObject:
    """Represents a celestial object with coordinates and metadata."""

    name: str
    common_name: str | None
    ra_hours: float
    dec_degrees: float
    magnitude: float | None
    object_type: CelestialObjectType
    catalog: str
    description: str | None = None
    parent_planet: str | None = None

    def matches_search(self, query: str) -> bool:
        """Check if object matches search query."""
        query_lower = query.lower()
        return bool(
            query_lower in self.name.lower()
            or (self.common_name and query_lower in self.common_name.lower())
            or (self.description and query_lower in self.description.lower())
        )

    def with_current_position(self, dt: datetime | None = None) -> "CelestialObject":
        """
        Return a copy of this object with current ephemeris position if applicable.

        For planets and moons, calculates the current RA/Dec based on the given time.
        For fixed objects (stars, galaxies, etc.), returns self unchanged.

        Args:
            dt: Datetime to calculate position for (default: now)

        Returns:
            New CelestialObject with updated coordinates, or self if not dynamic
        """
        if not is_dynamic_object(self.name):
            return self

        try:
            ra_hours, dec_degrees = get_planetary_position(self.name, dt=dt)
            return replace(self, ra_hours=ra_hours, dec_degrees=dec_degrees)
        except (ValueError, KeyError):
            # If ephemeris calculation fails, return original
            return self


# Cache for loaded catalogs (TTL=3600 seconds / 1 hour)
# This provides fast lookups while allowing periodic refresh
_catalog_cache: TTLCache[str, list[CelestialObject]] = TTLCache(maxsize=100, ttl=3600)


def _get_catalogs_path() -> Path:
    """Get the path to the catalogs.yaml file."""
    # Check if running from installed package or development
    # We're in: src/celestron_nexstar/api/
    # Data is in: src/celestron_nexstar/cli/data/
    module_path = Path(__file__).parent  # api/
    parent = module_path.parent  # celestron_nexstar/
    data_path = parent / "cli" / "data" / "catalogs.yaml"

    if data_path.exists():
        return data_path

    # Fallback for installed package
    import sys

    if hasattr(sys, "_MEIPASS"):
        # PyInstaller path
        data_path = Path(sys._MEIPASS) / "celestron_nexstar" / "cli" / "data" / "catalogs.yaml"
        if data_path.exists():
            return data_path

    raise FileNotFoundError(f"Could not find catalogs.yaml at {data_path}")


@cached(_catalog_cache)
def _load_catalog_from_yaml(catalog_name: str) -> list[CelestialObject]:
    """
    Load a specific catalog from the YAML file.

    Results are cached for performance.

    Args:
        catalog_name: Name of the catalog to load (e.g., 'bright_stars', 'messier')

    Returns:
        List of CelestialObject instances
    """
    catalogs_path = _get_catalogs_path()

    with catalogs_path.open("r") as f:
        data = yaml.safe_load(f)

    if catalog_name not in data:
        raise ValueError(f"Catalog '{catalog_name}' not found in {catalogs_path}")

    objects: list[CelestialObject] = []
    for obj_data in data[catalog_name]:
        obj = CelestialObject(
            name=obj_data["name"],
            common_name=obj_data.get("common_name"),
            ra_hours=obj_data["ra_hours"],
            dec_degrees=obj_data["dec_degrees"],
            magnitude=obj_data.get("magnitude"),
            object_type=CelestialObjectType(obj_data["type"]),
            catalog=catalog_name,
            description=obj_data.get("description"),
            parent_planet=obj_data.get("parent_planet"),
        )
        objects.append(obj)

    return objects


@cached(_catalog_cache)
def _load_all_catalogs() -> dict[str, list[CelestialObject]]:
    """
    Load all catalogs from the YAML file.

    Results are cached for performance.

    Returns:
        Dictionary mapping catalog names to lists of CelestialObject instances
    """
    catalogs_path = _get_catalogs_path()

    with catalogs_path.open("r") as f:
        data = yaml.safe_load(f)

    all_catalogs: dict[str, list[CelestialObject]] = {}
    for catalog_name, objects_data in data.items():
        objects: list[CelestialObject] = []
        for obj_data in objects_data:
            obj = CelestialObject(
                name=obj_data["name"],
                common_name=obj_data.get("common_name"),
                ra_hours=obj_data["ra_hours"],
                dec_degrees=obj_data["dec_degrees"],
                magnitude=obj_data.get("magnitude"),
                object_type=CelestialObjectType(obj_data["type"]),
                catalog=catalog_name,
                description=obj_data.get("description"),
                parent_planet=obj_data.get("parent_planet"),
            )
            objects.append(obj)
        all_catalogs[catalog_name] = objects

    return all_catalogs


# Public API - lazy-loaded catalogs dict
def get_all_catalogs_dict() -> dict[str, list[CelestialObject]]:
    """
    Get all catalogs as a dictionary.

    Returns:
        Dictionary mapping catalog names to lists of CelestialObject instances
    """
    return _load_all_catalogs()


# Module-level cached reference for backwards compatibility
_all_catalogs_cache: dict[str, list[CelestialObject]] | None = None


def _get_all_catalogs() -> dict[str, list[CelestialObject]]:
    """Lazy-load ALL_CATALOGS on first access."""
    global _all_catalogs_cache
    if _all_catalogs_cache is None:
        _all_catalogs_cache = _load_all_catalogs()
    return _all_catalogs_cache


# Backwards compatibility - property-like access
class _AllCatalogsProxy:
    """Proxy object that provides dict-like access to catalogs."""

    def items(self) -> list[tuple[str, list[CelestialObject]]]:
        """Get catalog items."""
        return list(_get_all_catalogs().items())

    def keys(self) -> list[str]:
        """Get catalog names."""
        return list(_get_all_catalogs().keys())

    def values(self) -> list[list[CelestialObject]]:
        """Get catalog object lists."""
        return list(_get_all_catalogs().values())

    def __getitem__(self, key: str) -> list[CelestialObject]:
        """Get catalog by name."""
        return _get_all_catalogs()[key]

    def __iter__(self) -> Iterator[str]:
        """Iterate over catalog names."""
        return iter(_get_all_catalogs())

    def __len__(self) -> int:
        """Get number of catalogs."""
        return len(_get_all_catalogs())


ALL_CATALOGS = _AllCatalogsProxy()


def get_catalog(catalog_name: str) -> list[CelestialObject]:
    """
    Get objects from a specific catalog.

    Args:
        catalog_name: Name of the catalog ('bright_stars', 'messier', 'asterisms', 'ngc', 'planets')

    Returns:
        List of CelestialObject instances from the catalog
    """
    return _load_catalog_from_yaml(catalog_name)


def get_all_objects() -> list[CelestialObject]:
    """
    Get all objects from all catalogs.

    Returns:
        List of all CelestialObject instances across all catalogs
    """
    all_catalogs = _load_all_catalogs()
    objects = []
    for catalog_objects in all_catalogs.values():
        objects.extend(catalog_objects)
    return objects


def get_available_catalogs() -> list[str]:
    """
    Get list of available catalog names.

    Returns:
        List of catalog names
    """
    return list(_load_all_catalogs().keys())


def search_objects(
    query: str, catalog_name: str | None = None, max_l_dist: int = 2, update_positions: bool = True
) -> list[tuple[CelestialObject, str]]:
    """
    Search for objects by name, common name, or description using fuzzy matching.

    If an exact match is found (case-insensitive), only that match is returned.
    Otherwise, returns fuzzy matches sorted by match quality.

    Args:
        query: Search query string
        catalog_name: Optional catalog to search within (None = search all)
        max_l_dist: Maximum Levenshtein distance for fuzzy matching (default: 2)
        update_positions: Update planetary positions to current time (default: True)

    Returns:
        List of tuples (CelestialObject, match_type) sorted by match quality.
        Match types: "exact", "name", "alias", "description", "fuzzy-name",
                     "fuzzy-alias", "fuzzy-description"
    """
    # Get objects to search
    objects = get_catalog(catalog_name) if catalog_name else get_all_objects()

    # Update planetary positions if requested
    if update_positions:
        objects = [obj.with_current_position() for obj in objects]

    query_lower = query.lower()
    results: list[tuple[int, CelestialObject, str]] = []  # (score, object, match_type)
    exact_match = None

    for obj in objects:
        # Check for exact matches first (case-insensitive)
        if obj.name.lower() == query_lower or (obj.common_name and obj.common_name.lower() == query_lower):
            exact_match = (obj, "exact")
            break  # Found exact match, no need to continue

        # Exact substring match in name (score: 0)
        if query_lower in obj.name.lower():
            results.append((0, obj, "name"))
            continue

        # Exact substring match in common name (score: 1)
        if obj.common_name and query_lower in obj.common_name.lower():
            results.append((1, obj, "alias"))
            continue

        # Exact substring match in description (score: 2)
        if obj.description and query_lower in obj.description.lower():
            results.append((2, obj, "description"))
            continue

        # Fuzzy match in name
        name_matches = find_near_matches(query_lower, obj.name.lower(), max_l_dist=max_l_dist)
        if name_matches:
            # Score based on Levenshtein distance (3 + distance)
            best_dist = min(m.dist for m in name_matches)
            results.append((3 + best_dist, obj, f"fuzzy-name (±{best_dist})"))
            continue

        # Fuzzy match in common name
        if obj.common_name:
            common_matches = find_near_matches(query_lower, obj.common_name.lower(), max_l_dist=max_l_dist)
            if common_matches:
                best_dist = min(m.dist for m in common_matches)
                results.append((4 + best_dist, obj, f"fuzzy-alias (±{best_dist})"))
                continue

        # Fuzzy match in description
        if obj.description:
            desc_matches = find_near_matches(query_lower, obj.description.lower(), max_l_dist=max_l_dist)
            if desc_matches:
                best_dist = min(m.dist for m in desc_matches)
                results.append((5 + best_dist, obj, f"fuzzy-desc (±{best_dist})"))

    # If exact match found, return only that
    if exact_match:
        return [exact_match]

    # Sort by score (lower is better) and return
    results.sort(key=lambda x: x[0])
    return [(obj, match_type) for score, obj, match_type in results]


def get_object_by_name(name: str, catalog_name: str | None = None) -> list[CelestialObject]:
    """
    Get objects by name or common name (fuzzy matching).

    This is an alias for search_objects for backwards compatibility.

    Args:
        name: Object name to search for
        catalog_name: Optional catalog to search within

    Returns:
        List of matching CelestialObject instances (without match type info)
    """
    results = search_objects(name, catalog_name)
    return [obj for obj, _ in results]

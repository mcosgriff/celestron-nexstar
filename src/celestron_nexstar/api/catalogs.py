"""
Celestial Object Catalogs

Loads and caches celestial object catalogs from YAML data files.
Dynamically calculates positions for solar system objects.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

import yaml
from cachetools import TTLCache, cached

from .enums import CelestialObjectType
from .ephemeris import get_planetary_position, is_dynamic_object


logger = logging.getLogger(__name__)


__all__ = [
    "CelestialObject",
    "get_all_catalogs_dict",
    "get_all_objects",
    "get_available_catalogs",
    "get_catalog",
    "get_object_by_name",
    "search_objects",
]


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

    def with_current_position(self, dt: datetime | None = None) -> CelestialObject:
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


@cached(_catalog_cache)  # type: ignore[misc]
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


@cached(_catalog_cache)  # type: ignore[misc]
def _load_all_catalogs() -> dict[str, list[CelestialObject]]:
    """
    Load all catalogs from the YAML file.

    Results are cached for performance.

    Returns:
        Dictionary mapping catalog names to lists of CelestialObject instances
    """
    catalogs_path = _get_catalogs_path()
    logger.debug(f"Loading catalogs from {catalogs_path}")

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
        logger.debug(f"Loaded {len(objects)} objects from catalog '{catalog_name}'")

    logger.info(
        f"Loaded {len(all_catalogs)} catalogs with {sum(len(objs) for objs in all_catalogs.values())} total objects"
    )
    return all_catalogs


# Public API - lazy-loaded catalogs dict
def get_all_catalogs_dict() -> dict[str, list[CelestialObject]]:
    """
    Get all catalogs as a dictionary.

    Returns:
        Dictionary mapping catalog names to lists of CelestialObject instances
    """
    return _load_all_catalogs()  # type: ignore[no-any-return]


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
    return _load_catalog_from_yaml(catalog_name)  # type: ignore[no-any-return]


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
    Search for objects by name, common name, or description using database search.

    Searches only the database, prioritizing exact matches.

    If an exact match is found (case-insensitive), only that match is returned.
    Otherwise, returns matches sorted by match quality.

    Args:
        query: Search query string
        catalog_name: Optional catalog to search within (None = search all)
        max_l_dist: Maximum Levenshtein distance for fuzzy matching (unused, kept for compatibility)
        update_positions: Update planetary positions to current time (default: True)

    Returns:
        List of tuples (CelestialObject, match_type) sorted by match quality.
        Match types: "exact", "name", "alias", "description"
    """
    from sqlalchemy import func, select, text

    from .database import get_database

    query_lower = query.lower()
    all_results: list[tuple[int, CelestialObject, str]] = []  # (score, object, match_type)
    exact_match = None

    try:
        db = get_database()
        with db._get_session() as session:
            from .models import CelestialObjectModel

            # First, try exact match (case-insensitive)
            exact_query = (
                select(CelestialObjectModel)
                .filter(
                    (func.lower(CelestialObjectModel.name) == query_lower)
                    | (func.lower(CelestialObjectModel.common_name) == query_lower)
                )
            )
            if catalog_name:
                exact_query = exact_query.filter(CelestialObjectModel.catalog == catalog_name)

            exact_model = session.execute(exact_query).scalar_one_or_none()
            if exact_model:
                exact_obj = db._model_to_object(exact_model)
                if update_positions:
                    exact_obj = exact_obj.with_current_position()
                return [(exact_obj, "exact")]

            # Search for substring matches in name (score: 0)
            name_query = (
                select(CelestialObjectModel)
                .filter(func.lower(CelestialObjectModel.name).like(f"%{query_lower}%"))
            )
            if catalog_name:
                name_query = name_query.filter(CelestialObjectModel.catalog == catalog_name)

            name_models = session.execute(name_query).scalars().all()
            for model in name_models:
                obj = db._model_to_object(model)
                if update_positions:
                    obj = obj.with_current_position()
                # Check if it's an exact match (shouldn't happen, but just in case)
                if obj.name.lower() == query_lower:
                    exact_match = (obj, "exact")
                    break
                all_results.append((0, obj, "name"))

            # If exact match found, return it
            if exact_match:
                return [exact_match]

            # Search for substring matches in common_name (score: 1)
            common_query = (
                select(CelestialObjectModel)
                .filter(
                    CelestialObjectModel.common_name.isnot(None),
                    func.lower(CelestialObjectModel.common_name).like(f"%{query_lower}%"),
                )
            )
            if catalog_name:
                common_query = common_query.filter(CelestialObjectModel.catalog == catalog_name)

            common_models = session.execute(common_query).scalars().all()
            seen_names = {obj.name.lower() for _, obj, _ in all_results}
            for model in common_models:
                obj = db._model_to_object(model)
                if obj.name.lower() not in seen_names:
                    seen_names.add(obj.name.lower())
                    if update_positions:
                        obj = obj.with_current_position()
                    if obj.common_name and obj.common_name.lower() == query_lower:
                        exact_match = (obj, "exact")
                        break
                    all_results.append((1, obj, "alias"))

            # If exact match found, return it
            if exact_match:
                return [exact_match]

            # Use FTS5 for full-text search in description (score: 2)
            fts_query = text("""
                SELECT objects.id FROM objects
                JOIN objects_fts ON objects.id = objects_fts.rowid
                WHERE objects_fts MATCH :query
            """)
            params = {"query": query}
            if catalog_name:
                fts_query = text("""
                    SELECT objects.id FROM objects
                    JOIN objects_fts ON objects.id = objects_fts.rowid
                    WHERE objects_fts MATCH :query
                    AND objects.catalog = :catalog
                """)
                params["catalog"] = catalog_name

            fts_result = session.execute(fts_query, params).fetchall()
            fts_ids = [row[0] for row in fts_result]
            for obj_id in fts_ids:
                fts_model: CelestialObjectModel | None = session.get(CelestialObjectModel, obj_id)
                if fts_model is not None:
                    obj = db._model_to_object(fts_model)
                    if obj.name.lower() not in seen_names:
                        seen_names.add(obj.name.lower())
                        if update_positions:
                            obj = obj.with_current_position()
                        # Check if it matches name or common_name (should have been caught above)
                        if obj.name.lower() == query_lower or (
                            obj.common_name and obj.common_name.lower() == query_lower
                        ):
                            exact_match = (obj, "exact")
                            break
                        # Only add if it's a description match (not already matched above)
                        if query_lower not in obj.name.lower() and (
                            not obj.common_name or query_lower not in obj.common_name.lower()
                        ):
                            all_results.append((2, obj, "description"))

            # If exact match found, return it
            if exact_match:
                return [exact_match]

    except Exception as e:
        logger.warning(f"Database search failed: {e}")
        return []

    # Sort by score (lower is better) and return
    all_results.sort(key=lambda x: x[0])
    return [(obj, match_type) for score, obj, match_type in all_results]


def get_object_by_name(name: str, catalog_name: str | None = None) -> list[CelestialObject]:
    """
    Get objects by name or common name (fuzzy matching).

    Searches both database and YAML catalogs, prioritizing exact matches.

    Args:
        name: Object name to search for
        catalog_name: Optional catalog to search within

    Returns:
        List of matching CelestialObject instances (without match type info)
    """
    from .database import get_database

    all_matches: list[CelestialObject] = []
    seen_names: set[str] = set()

    # First, try exact match in database (highest priority)
    try:
        db = get_database()
        db_obj = db.get_by_name(name)
        if db_obj:
            all_matches.append(db_obj)
            seen_names.add(db_obj.name.lower())
            # If we found an exact match, return it immediately
            return [db_obj]
    except Exception:
        pass  # Database might not be available

    # Search YAML catalogs
    yaml_results = search_objects(name, catalog_name)
    for obj, match_type in yaml_results:
        # Skip if we've already seen this object
        if obj.name.lower() not in seen_names:
            all_matches.append(obj)
            seen_names.add(obj.name.lower())
            # If this is an exact match, prioritize it
            if match_type == "exact":
                return [obj]

    # If no exact match yet, try fuzzy search in database
    try:
        db = get_database()
        db_results = db.search(name, limit=20)
        for obj in db_results:
            if obj.name.lower() not in seen_names:
                all_matches.append(obj)
                seen_names.add(obj.name.lower())
    except Exception:
        pass  # Database might not be available

    return all_matches

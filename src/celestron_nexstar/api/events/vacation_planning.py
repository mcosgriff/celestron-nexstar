"""
Vacation Planning for Astronomy

Helps plan telescope viewing for vacation destinations by finding
what's visible and locating nearby dark sky sites.
"""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from celestron_nexstar.api.location.light_pollution import BortleClass, get_light_pollution_data
from celestron_nexstar.api.location.observer import ObserverLocation, geocode_location


if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

__all__ = [
    "DarkSkySite",
    "VacationViewingInfo",
    "find_dark_sites_near",
    "get_vacation_viewing_info",
    "populate_dark_sky_sites_database",
]


@dataclass
class DarkSkySite:
    """Information about a dark sky viewing site."""

    name: str
    latitude: float
    longitude: float
    bortle_class: BortleClass
    sqm_value: float
    distance_km: float  # Distance from search location
    description: str
    notes: str | None = None


@dataclass
class VacationViewingInfo:
    """Viewing information for a vacation location."""

    location: ObserverLocation
    bortle_class: BortleClass
    sqm_value: float
    naked_eye_limiting_magnitude: float
    milky_way_visible: bool
    description: str
    recommendations: tuple[str, ...]


# Dark sky sites data is now stored in JSON seed files (dark_sky_sites.json)
# and loaded into the database. The database is the primary source of truth.
# See database_seeder.py for seeding logic.


def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate distance between two points using Haversine formula.

    Returns distance in kilometers.
    """
    r = 6371.0  # Earth radius in km

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return r * c


def find_dark_sites_near(
    location: ObserverLocation | str,
    max_distance_km: float = 200.0,
    min_bortle: BortleClass = BortleClass.CLASS_4,
) -> list[DarkSkySite]:
    """
    Find dark sky sites near a location.

    Queries from database first (for offline use), falls back to JSON seed file if database is empty.

    Args:
        location: ObserverLocation or location string to geocode
        max_distance_km: Maximum distance to search (default: 200 km)
        min_bortle: Minimum Bortle class to include (default: CLASS_4)

    Returns:
        List of DarkSkySite objects, sorted by distance
    """
    # Handle string location
    if isinstance(location, str):
        # Run async function - this is a sync entry point, so asyncio.run() is safe
        location = asyncio.run(geocode_location(location))

    sites = []

    # Try database first (offline-capable) using geohash for efficient spatial queries
    try:
        from celestron_nexstar.api.database.models import DarkSkySiteModel, get_db_session
        from celestron_nexstar.api.location.geohash_utils import encode, get_neighbors_for_search

        async def _get_sites() -> list[DarkSkySiteModel]:
            async with get_db_session() as db:
                from sqlalchemy import or_, select

                # Generate geohash for the search point
                center_geohash = encode(location.latitude, location.longitude, precision=12)

                # Get geohash prefixes to search (includes neighbors)
                # This efficiently narrows down the search space
                search_geohashes = get_neighbors_for_search(center_geohash, max_distance_km)

                # Build query using geohash prefix matching for efficient spatial filtering
                geohash_patterns = [f"{gh}%" for gh in search_geohashes]
                geohash_conditions = or_(*[DarkSkySiteModel.geohash.like(pattern) for pattern in geohash_patterns])

                # Query sites using geohash filtering and bortle class filter
                result = await db.execute(
                    select(DarkSkySiteModel).filter(
                        geohash_conditions,
                        DarkSkySiteModel.bortle_class <= min_bortle.value,
                    )
                )
                return list(result.scalars().all())

        db_sites = asyncio.run(_get_sites())

        for db_site in db_sites:
            distance = _haversine_distance(location.latitude, location.longitude, db_site.latitude, db_site.longitude)

            if distance <= max_distance_km:
                site = DarkSkySite(
                    name=db_site.name,
                    latitude=db_site.latitude,
                    longitude=db_site.longitude,
                    bortle_class=BortleClass(db_site.bortle_class),
                    sqm_value=db_site.sqm_value,
                    distance_km=distance,
                    description=db_site.description,
                    notes=db_site.notes,
                )
                sites.append(site)

        # If database has sites, use them
        if sites:
            sites.sort(key=lambda s: s.distance_km)
            return sites
    except Exception as e:
        logger.debug(f"Database query failed, using fallback: {e}")

    # Fallback to JSON seed file if database is empty or query fails
    logger.debug("Database empty or query failed, loading from JSON seed file")
    try:
        from celestron_nexstar.api.database.database_seeder import load_seed_json
        from celestron_nexstar.api.location.geohash_utils import encode, get_neighbors_for_search

        seed_data = load_seed_json("dark_sky_sites.json")

        # Use geohash for efficient filtering even in fallback mode
        center_geohash = encode(location.latitude, location.longitude, precision=12)
        search_geohashes = get_neighbors_for_search(center_geohash, max_distance_km)
        # Use precision 9 for matching (sites are stored with precision 9)
        search_geohash_prefixes = {gh[:9] for gh in search_geohashes}

        for item in seed_data:
            bortle_value = item["bortle_class"]
            if isinstance(bortle_value, str):
                bortle_value = int(bortle_value)
            site_bortle = BortleClass(bortle_value)

            if site_bortle > min_bortle:
                continue

            # Quick geohash-based pre-filtering
            item_geohash = item.get("geohash")
            if item_geohash:
                # Check if site's geohash starts with any of the search prefixes
                # (geohash prefix matching: if item's geohash starts with search prefix, it's in that area)
                item_prefix = item_geohash[:9]  # Sites are stored with precision 9
                if not any(item_prefix.startswith(search_prefix) for search_prefix in search_geohash_prefixes):
                    continue

            distance = _haversine_distance(location.latitude, location.longitude, item["latitude"], item["longitude"])

            if distance <= max_distance_km:
                site = DarkSkySite(
                    name=item["name"],
                    latitude=item["latitude"],
                    longitude=item["longitude"],
                    bortle_class=site_bortle,
                    sqm_value=item["sqm_value"],
                    distance_km=distance,
                    description=item["description"],
                    notes=item.get("notes"),
                )
                sites.append(site)
    except Exception as e:
        logger.warning(f"Failed to load dark sky sites from JSON seed file: {e}")

    # Sort by distance
    sites.sort(key=lambda s: s.distance_km)
    return sites


def populate_dark_sky_sites_database(db_session: Session) -> None:
    """
    Populate database with dark sky site data.

    This should be called once to initialize the database with static data.
    Works offline once populated. Uses seed data from JSON files (dark_sky_sites.json).

    Args:
        db_session: SQLAlchemy database session (unused, kept for API compatibility)
    """
    import asyncio

    from celestron_nexstar.api.database.database_seeder import seed_dark_sky_sites
    from celestron_nexstar.api.database.models import get_db_session

    logger.info("Populating dark sky sites database...")

    async def _seed() -> None:
        async with get_db_session() as async_session:
            await seed_dark_sky_sites(async_session, force=True)

    asyncio.run(_seed())


def get_vacation_viewing_info(location: ObserverLocation | str) -> VacationViewingInfo:
    """
    Get viewing information for a vacation location.

    Args:
        location: ObserverLocation or location string to geocode

    Returns:
        VacationViewingInfo with sky quality and recommendations
    """
    # Handle string location
    if isinstance(location, str):
        # Run async function - this is a sync entry point, so asyncio.run() is safe
        location = asyncio.run(geocode_location(location))

    # Get light pollution data
    # Run async function - this is a sync entry point, so asyncio.run() is safe
    from typing import Any

    async def _get_light_data() -> Any:
        from celestron_nexstar.api.database.models import get_db_session

        async with get_db_session() as db_session:
            return await get_light_pollution_data(db_session, location.latitude, location.longitude)

    light_data = asyncio.run(_get_light_data())

    return VacationViewingInfo(
        location=location,
        bortle_class=light_data.bortle_class,
        sqm_value=light_data.sqm_value,
        naked_eye_limiting_magnitude=light_data.naked_eye_limiting_magnitude,
        milky_way_visible=light_data.milky_way_visible,
        description=light_data.description,
        recommendations=light_data.recommendations,
    )

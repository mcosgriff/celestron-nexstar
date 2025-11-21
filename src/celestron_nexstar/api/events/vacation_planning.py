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

    Uses GeoPandas for efficient spatial queries with spatial indexing (R-tree).
    Queries from database first (for offline use), falls back to JSON seed file if database is empty.

    Args:
        location: ObserverLocation or location string to geocode
        max_distance_km: Maximum distance to search (default: 200 km)
        min_bortle: Minimum Bortle class to include (default: CLASS_4)

    Returns:
        List of DarkSkySite objects, sorted by distance
    """
    import geopandas as gpd
    from shapely.geometry import Point

    # Handle string location
    if isinstance(location, str):
        # Run async function - this is a sync entry point, so asyncio.run() is safe
        location = asyncio.run(geocode_location(location))

    # Create search point geometry (WGS84 / EPSG:4326)
    search_point = Point(location.longitude, location.latitude)
    search_gdf = gpd.GeoDataFrame([1], geometry=[search_point], crs="EPSG:4326")

    # Convert max_distance_km to degrees (approximate, but good enough for filtering)
    # At equator: 1 degree ≈ 111 km, but we'll use a more conservative estimate
    # and let the accurate distance calculation filter precisely
    max_distance_deg = max_distance_km / 111.0  # Rough conversion

    sites = []

    # Try database first (offline-capable)
    try:
        from celestron_nexstar.api.database.models import DarkSkySiteModel, get_db_session

        async def _get_sites() -> list[DarkSkySiteModel]:
            async with get_db_session() as db:
                from sqlalchemy import select

                # Query all sites matching bortle class
                result = await db.execute(
                    select(DarkSkySiteModel).filter(
                        DarkSkySiteModel.bortle_class <= min_bortle.value,
                    )
                )
                return list(result.scalars().all())

        db_sites = asyncio.run(_get_sites())

        if db_sites:
            # Create GeoDataFrame from database sites
            sites_data = {
                "name": [s.name for s in db_sites],
                "latitude": [s.latitude for s in db_sites],
                "longitude": [s.longitude for s in db_sites],
                "bortle_class": [s.bortle_class for s in db_sites],
                "sqm_value": [s.sqm_value for s in db_sites],
                "description": [s.description for s in db_sites],
                "notes": [s.notes for s in db_sites],
            }
            sites_gdf = gpd.GeoDataFrame(
                sites_data,
                geometry=gpd.points_from_xy([s.longitude for s in db_sites], [s.latitude for s in db_sites]),
                crs="EPSG:4326",
            )

            # Use spatial indexing for fast distance queries
            # Create a buffer around search point (in degrees, approximate)
            # Then use spatial join to find sites within buffer
            search_buffer = search_gdf.geometry.buffer(max_distance_deg)
            buffer_gdf = gpd.GeoDataFrame([1], geometry=search_buffer, crs="EPSG:4326")

            # Spatial join to find sites within buffer
            sites_within = gpd.sjoin(sites_gdf, buffer_gdf, how="inner", predicate="within")

            # Calculate accurate distances using GeoPandas (geodesic distance)
            # Project to a suitable CRS for distance calculation (e.g., World Mercator or local UTM)
            # For simplicity, we'll use a projected CRS that's good for the search area
            # EPSG:3857 (Web Mercator) is reasonable for distance calculations
            search_projected = search_gdf.to_crs("EPSG:3857")
            sites_projected = sites_within.to_crs("EPSG:3857")

            # Calculate distances in meters, convert to km
            distances_m = sites_projected.geometry.distance(search_projected.geometry.iloc[0])
            distances_km = distances_m / 1000.0

            # Filter by exact distance and create DarkSkySite objects
            # Use itertuples for better performance (10-100x faster than iterrows)
            for row in sites_within.itertuples():
                # Get distance for this row (distances_km is aligned with sites_within index)
                distance = float(distances_km.loc[row.Index])
                if distance <= max_distance_km:
                    site = DarkSkySite(
                        name=row.name,
                        latitude=row.latitude,
                        longitude=row.longitude,
                        bortle_class=BortleClass(row.bortle_class),
                        sqm_value=row.sqm_value,
                        distance_km=distance,
                        description=row.description,
                        notes=getattr(row, "notes", None),
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

        seed_data = load_seed_json("dark_sky_sites.json")

        # Filter out metadata/attribution objects
        seed_data = [
            item for item in seed_data if not (isinstance(item, dict) and any(key.startswith("_") for key in item))
        ]

        if seed_data:
            # Create GeoDataFrame from seed data
            sites_data = {
                "name": [item["name"] for item in seed_data],
                "latitude": [item["latitude"] for item in seed_data],
                "longitude": [item["longitude"] for item in seed_data],
                "bortle_class": [
                    int(item["bortle_class"]) if isinstance(item["bortle_class"], str) else item["bortle_class"]
                    for item in seed_data
                ],
                "sqm_value": [item["sqm_value"] for item in seed_data],
                "description": [item["description"] for item in seed_data],
                "notes": [item.get("notes") for item in seed_data],
            }
            sites_gdf = gpd.GeoDataFrame(
                sites_data,
                geometry=gpd.points_from_xy(
                    [item["longitude"] for item in seed_data], [item["latitude"] for item in seed_data]
                ),
                crs="EPSG:4326",
            )

            # Filter by bortle class first
            sites_gdf = sites_gdf[sites_gdf["bortle_class"] <= min_bortle.value]

            # Use spatial indexing for fast distance queries
            search_buffer = search_gdf.geometry.buffer(max_distance_deg)
            buffer_gdf = gpd.GeoDataFrame([1], geometry=search_buffer, crs="EPSG:4326")

            # Spatial join to find sites within buffer
            sites_within = gpd.sjoin(sites_gdf, buffer_gdf, how="inner", predicate="within")

            # Calculate accurate distances
            search_projected = search_gdf.to_crs("EPSG:3857")
            sites_projected = sites_within.to_crs("EPSG:3857")
            distances_m = sites_projected.geometry.distance(search_projected.geometry.iloc[0])
            distances_km = distances_m / 1000.0

            # Filter by exact distance and create DarkSkySite objects
            # Use itertuples for better performance (10-100x faster than iterrows)
            for row in sites_within.itertuples():
                # Get distance for this row (distances_km is aligned with sites_within index)
                distance = float(distances_km.loc[row.Index])
                if distance <= max_distance_km:
                    site = DarkSkySite(
                        name=row.name,
                        latitude=row.latitude,
                        longitude=row.longitude,
                        bortle_class=BortleClass(row.bortle_class),
                        sqm_value=row.sqm_value,
                        distance_km=distance,
                        description=row.description,
                        notes=getattr(row, "notes", None),
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

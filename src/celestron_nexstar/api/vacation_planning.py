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

from .light_pollution import BortleClass, get_light_pollution_data
from .models import get_db_session
from .observer import ObserverLocation, geocode_location


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


# Known dark sky sites database
# This is a curated list - can be expanded with more locations
KNOWN_DARK_SITES = [
    # International Dark Sky Parks/Reserves
    DarkSkySite(
        name="Cherry Springs State Park",
        latitude=41.6631,
        longitude=-77.8264,
        bortle_class=BortleClass.CLASS_2,
        sqm_value=21.9,
        distance_km=0.0,  # Will be calculated
        description="Gold-tier International Dark Sky Park in Pennsylvania",
        notes="One of the darkest skies on the East Coast",
    ),
    DarkSkySite(
        name="Big Bend National Park",
        latitude=29.1275,
        longitude=-103.2425,
        bortle_class=BortleClass.CLASS_1,
        sqm_value=22.0,
        distance_km=0.0,
        description="International Dark Sky Park in Texas",
        notes="Some of the darkest skies in the continental US",
    ),
    DarkSkySite(
        name="Death Valley National Park",
        latitude=36.5054,
        longitude=-116.8664,
        bortle_class=BortleClass.CLASS_1,
        sqm_value=22.0,
        distance_km=0.0,
        description="International Dark Sky Park in California",
        notes="Extremely dark skies, excellent for deep-sky observing",
    ),
    DarkSkySite(
        name="Natural Bridges National Monument",
        latitude=37.6094,
        longitude=-110.0139,
        bortle_class=BortleClass.CLASS_1,
        sqm_value=22.0,
        distance_km=0.0,
        description="World's first International Dark Sky Park (2007) in Utah",
        notes="Excellent for Milky Way photography. Some of the darkest skies in the U.S.",
    ),
    # Colorado International Dark Sky Parks
    DarkSkySite(
        name="Black Canyon of the Gunnison National Park",
        latitude=38.5750,
        longitude=-107.7250,
        bortle_class=BortleClass.CLASS_1,
        sqm_value=22.0,
        distance_km=0.0,
        description="International Dark Sky Park in Colorado",
        notes="Steep-walled chasm with minimal light pollution. North Rim and South Rim viewing areas. AstroFest events in September.",
    ),
    DarkSkySite(
        name="Great Sand Dunes National Park and Preserve",
        latitude=37.7306,
        longitude=-105.5125,
        bortle_class=BortleClass.CLASS_1,
        sqm_value=22.0,
        distance_km=0.0,
        description="International Dark Sky Park in Colorado",
        notes="Tallest dunes in North America. Milky Way visible over otherworldly landscape. Best viewing on moonless nights in late summer.",
    ),
    DarkSkySite(
        name="Mesa Verde National Park",
        latitude=37.2306,
        longitude=-108.4617,
        bortle_class=BortleClass.CLASS_1,
        sqm_value=22.0,
        distance_km=0.0,
        description="International Dark Sky Park and UNESCO World Heritage Site in Colorado",
        notes="Best viewing at Morefield Campground and Park Point. Evening ranger programs Memorial Day to Labor Day.",
    ),
    DarkSkySite(
        name="Florissant Fossil Beds National Monument",
        latitude=38.9117,
        longitude=-105.2856,
        bortle_class=BortleClass.CLASS_2,
        sqm_value=21.8,
        distance_km=0.0,
        description="International Dark Sky Park in Colorado",
        notes="Closest dark sky park to Front Range (~1 hour west of Colorado Springs). Hornbek Homestead area open 24/7 for stargazing.",
    ),
    DarkSkySite(
        name="Dinosaur National Monument",
        latitude=40.5333,
        longitude=-108.9833,
        bortle_class=BortleClass.CLASS_1,
        sqm_value=22.0,
        distance_km=0.0,
        description="International Dark Sky Park in Colorado/Utah",
        notes="One of the darkest places in the United States. Echo Park and Split Mountain Campground offer excellent viewing.",
    ),
    DarkSkySite(
        name="Curecanti National Recreation Area",
        latitude=38.4500,
        longitude=-107.3167,
        bortle_class=BortleClass.CLASS_2,
        sqm_value=21.8,
        distance_km=0.0,
        description="International Dark Sky Park in Colorado",
        notes="Three reservoirs with protected dark skies. Elk Creek Campground amphitheater has summer programs.",
    ),
    DarkSkySite(
        name="Browns Canyon National Monument",
        latitude=38.6167,
        longitude=-106.0500,
        bortle_class=BortleClass.CLASS_2,
        sqm_value=21.8,
        distance_km=0.0,
        description="International Dark Sky Park in Colorado",
        notes="Ruby Mountain and Hecla Junction campgrounds offer excellent dark-sky viewing. Summer stargazing programs available.",
    ),
    DarkSkySite(
        name="Gunnison Gorge National Conservation Area",
        latitude=38.5500,
        longitude=-107.7167,
        bortle_class=BortleClass.CLASS_1,
        sqm_value=22.0,
        distance_km=0.0,
        description="International Dark Sky Park in Colorado",
        notes="Some of the darkest skies in the world. Cottonwood Grove Campground and Peach Valley Staging Area accessible by car.",
    ),
    DarkSkySite(
        name="Hovenweep National Monument",
        latitude=37.3833,
        longitude=-109.0833,
        bortle_class=BortleClass.CLASS_1,
        sqm_value=22.0,
        distance_km=0.0,
        description="International Dark Sky Park in Colorado/Utah (2014)",
        notes="Ancient Puebloan ruins with exceptional dark skies. Square Tower Group offers excellent viewing.",
    ),
    DarkSkySite(
        name="Jackson Lake State Park",
        latitude=40.4333,
        longitude=-104.0833,
        bortle_class=BortleClass.CLASS_2,
        sqm_value=21.8,
        distance_km=0.0,
        description="Colorado's first state park International Dark Sky Park",
        notes="Known as 'an oasis of the plains'. Excellent dark sky viewing in eastern Colorado.",
    ),
    DarkSkySite(
        name="Lake City",
        latitude=38.0300,
        longitude=-107.3150,
        bortle_class=BortleClass.CLASS_2,
        sqm_value=21.8,
        distance_km=0.0,
        description="International Dark Sky Community in Colorado",
        notes="High-altitude community (8,661 ft). Lake City Star Fest each June with star parties and telescope viewing.",
    ),
    DarkSkySite(
        name="Top of the Pines",
        latitude=38.1500,
        longitude=-107.7500,
        bortle_class=BortleClass.CLASS_1,
        sqm_value=22.0,
        distance_km=0.0,
        description="International Dark Sky Park in Colorado",
        notes="175-acre recreation area at 8,650 ft elevation. Among the darkest skies in Colorado. Best April-November.",
    ),
    # Colorado International Dark Sky Communities
    DarkSkySite(
        name="Crestone",
        latitude=37.9967,
        longitude=-105.6983,
        bortle_class=BortleClass.CLASS_2,
        sqm_value=21.8,
        distance_km=0.0,
        description="International Dark Sky Community in Colorado",
        notes="Small village at base of Sangre de Cristo Mountains. Dark Sky Crestone hosts periodic community events.",
    ),
    DarkSkySite(
        name="Norwood",
        latitude=38.1333,
        longitude=-108.2833,
        bortle_class=BortleClass.CLASS_2,
        sqm_value=21.8,
        distance_km=0.0,
        description="International Dark Sky Community in Colorado",
        notes="7,000-foot mesa location with wide night-sky vistas. High-desert climate with frequently clear skies.",
    ),
    DarkSkySite(
        name="Ridgway",
        latitude=38.1500,
        longitude=-107.7500,
        bortle_class=BortleClass.CLASS_2,
        sqm_value=21.8,
        distance_km=0.0,
        description="International Dark Sky Community in Colorado",
        notes="Remote setting in San Juan Mountains foothills. Milky Way often visible from downtown. Ridgway Athletic Park recommended.",
    ),
    DarkSkySite(
        name="Westcliffe & Silver Cliff",
        latitude=38.1333,
        longitude=-105.4667,
        bortle_class=BortleClass.CLASS_2,
        sqm_value=21.8,
        distance_km=0.0,
        description="International Dark Sky Community in Colorado",
        notes="Highest-altitude International Dark Sky Communities in the world. Smokey Jack Observatory with powerful telescope.",
    ),
    DarkSkySite(
        name="Paonia",
        latitude=38.8667,
        longitude=-107.6000,
        bortle_class=BortleClass.CLASS_2,
        sqm_value=21.8,
        distance_km=0.0,
        description="International Dark Sky Community in Colorado",
        notes="Cradled within West Elk Mountains. West Elk Loop scenic byway. Dark-sky events with local experts.",
    ),
    # Utah International Dark Sky Parks
    DarkSkySite(
        name="Canyonlands National Park",
        latitude=38.2469,
        longitude=-109.8803,
        bortle_class=BortleClass.CLASS_1,
        sqm_value=22.0,
        distance_km=0.0,
        description="International Dark Sky Park in Utah (2015)",
        notes="Expansive views of the night sky over rugged canyons. Free from light pollution.",
    ),
    DarkSkySite(
        name="Capitol Reef National Park",
        latitude=38.2917,
        longitude=-111.2617,
        bortle_class=BortleClass.CLASS_1,
        sqm_value=22.0,
        distance_km=0.0,
        description="International Dark Sky Park in Utah (2015)",
        notes="Clear, dark skies ideal for stargazing. Waterpocket Fold provides natural light barriers.",
    ),
    DarkSkySite(
        name="Bryce Canyon National Park",
        latitude=37.5931,
        longitude=-112.1872,
        bortle_class=BortleClass.CLASS_1,
        sqm_value=22.0,
        distance_km=0.0,
        description="International Dark Sky Park in Utah (2019)",
        notes="Known for dark skies and astronomy programs. Hoodoos create dramatic silhouettes against the Milky Way.",
    ),
    DarkSkySite(
        name="Arches National Park",
        latitude=38.7331,
        longitude=-109.5925,
        bortle_class=BortleClass.CLASS_1,
        sqm_value=22.0,
        distance_km=0.0,
        description="International Dark Sky Park in Utah (2019)",
        notes="Breathtaking night sky views over iconic arches. Balanced Rock and Delicate Arch are popular viewing spots.",
    ),
    DarkSkySite(
        name="Dead Horse Point State Park",
        latitude=38.4833,
        longitude=-109.7333,
        bortle_class=BortleClass.CLASS_1,
        sqm_value=22.0,
        distance_km=0.0,
        description="International Dark Sky Park in Utah (2016)",
        notes="Stunning views of the night sky over the Colorado River. Overlook provides 360-degree views.",
    ),
    DarkSkySite(
        name="Antelope Island State Park",
        latitude=41.0167,
        longitude=-112.2167,
        bortle_class=BortleClass.CLASS_2,
        sqm_value=21.8,
        distance_km=0.0,
        description="International Dark Sky Park in Utah (2017)",
        notes="Dark skies just outside Salt Lake City. Great Salt Lake provides natural light barrier.",
    ),
    DarkSkySite(
        name="Goblin Valley State Park",
        latitude=38.5667,
        longitude=-110.7000,
        bortle_class=BortleClass.CLASS_1,
        sqm_value=22.0,
        distance_km=0.0,
        description="International Dark Sky Park in Utah (2016)",
        notes="Unique rock formations (goblins) under pristine night skies. Remote location ensures dark skies.",
    ),
    DarkSkySite(
        name="Timpanogos Cave National Monument",
        latitude=40.4406,
        longitude=-111.7089,
        bortle_class=BortleClass.CLASS_2,
        sqm_value=21.8,
        distance_km=0.0,
        description="International Dark Sky Park in Utah (2015)",
        notes="Dark skies near the Wasatch Front. Cave tours available during the day.",
    ),
    DarkSkySite(
        name="Goosenecks State Park",
        latitude=37.1667,
        longitude=-109.9167,
        bortle_class=BortleClass.CLASS_1,
        sqm_value=22.0,
        distance_km=0.0,
        description="International Dark Sky Park in Utah (2021)",
        notes="Deep meanders of the San Juan River. Spectacular night sky views over the canyon.",
    ),
    # Utah International Dark Sky Communities
    DarkSkySite(
        name="Bluff, Utah",
        latitude=37.2833,
        longitude=-109.5500,
        bortle_class=BortleClass.CLASS_2,
        sqm_value=21.8,
        distance_km=0.0,
        description="International Dark Sky Community in Utah (2025)",
        notes="Near Bears Ears National Monument and Monument Valley. Attractive spot for astrotourism.",
    ),
    DarkSkySite(
        name="Springdale, Utah",
        latitude=37.1881,
        longitude=-113.0000,
        bortle_class=BortleClass.CLASS_2,
        sqm_value=21.8,
        distance_km=0.0,
        description="International Dark Sky Community in Utah (2023)",
        notes="Gateway to Zion National Park. Community commitment to preserving the night sky.",
    ),
    # New Mexico International Dark Sky Parks
    DarkSkySite(
        name="Chaco Culture National Historical Park",
        latitude=36.0619,
        longitude=-107.9667,
        bortle_class=BortleClass.CLASS_1,
        sqm_value=22.0,
        distance_km=0.0,
        description="International Dark Sky Park in New Mexico (2013)",
        notes="Ancient Puebloan architecture and dark skies. Renowned for both archaeology and astronomy.",
    ),
    DarkSkySite(
        name="Clayton Lake State Park",
        latitude=36.5667,
        longitude=-103.3167,
        bortle_class=BortleClass.CLASS_2,
        sqm_value=21.8,
        distance_km=0.0,
        description="International Dark Sky Park in New Mexico (2010)",
        notes="Features a 14-inch Meade telescope. Hosts monthly star-gazing events.",
    ),
    DarkSkySite(
        name="Capulin Volcano National Monument",
        latitude=36.7833,
        longitude=-103.9667,
        bortle_class=BortleClass.CLASS_2,
        sqm_value=21.8,
        distance_km=0.0,
        description="International Dark Sky Park in New Mexico (2016)",
        notes="'Park After Dark' events with ranger-led night sky programs. Volcanic crater provides unique viewing.",
    ),
    DarkSkySite(
        name="Cosmic Campground International Dark Sky Sanctuary",
        latitude=33.4667,
        longitude=-108.8833,
        bortle_class=BortleClass.CLASS_1,
        sqm_value=22.0,
        distance_km=0.0,
        description="First International Dark Sky Sanctuary in the Northern Hemisphere (2016)",
        notes="3.5-acre site in Gila National Forest. 360-degree unobstructed views. Nearest significant light source over 40 miles away.",
    ),
    DarkSkySite(
        name="El Morro National Monument",
        latitude=35.0389,
        longitude=-108.3500,
        bortle_class=BortleClass.CLASS_2,
        sqm_value=21.8,
        distance_km=0.0,
        description="International Dark Sky Park in New Mexico (2019)",
        notes="Historical inscriptions and petroglyphs. Pristine night sky views.",
    ),
    DarkSkySite(
        name="Fort Union National Monument",
        latitude=35.9000,
        longitude=-105.0167,
        bortle_class=BortleClass.CLASS_2,
        sqm_value=21.8,
        distance_km=0.0,
        description="International Dark Sky Park in New Mexico (2019)",
        notes="Special evening programs highlighting the unique nighttime environment. Historic fort ruins.",
    ),
    DarkSkySite(
        name="Salinas Pueblo Missions National Monument",
        latitude=34.6000,
        longitude=-106.3667,
        bortle_class=BortleClass.CLASS_2,
        sqm_value=21.8,
        distance_km=0.0,
        description="International Dark Sky Park in New Mexico (2016)",
        notes="Impressive night sky views, especially at Gran Quivira. Spanish mission ruins.",
    ),
    DarkSkySite(
        name="Valles Caldera National Preserve",
        latitude=35.8833,
        longitude=-106.5333,
        bortle_class=BortleClass.CLASS_1,
        sqm_value=22.0,
        distance_km=0.0,
        description="International Dark Sky Park in New Mexico (2021)",
        notes="Stunning views of the night skies over expansive mountain meadows. 13-mile wide volcanic caldera.",
    ),
    DarkSkySite(
        name="Valle de Oro National Wildlife Refuge",
        latitude=35.0167,
        longitude=-106.6833,
        bortle_class=BortleClass.CLASS_3,
        sqm_value=21.5,
        distance_km=0.0,
        description="First Urban Night Sky Place in New Mexico (2019)",
        notes="First Urban Night Sky Place, demonstrating best practices for protecting the night sky from light pollution near Albuquerque.",
    ),
    DarkSkySite(
        name="Great Basin National Park",
        latitude=38.9847,
        longitude=-114.3003,
        bortle_class=BortleClass.CLASS_1,
        sqm_value=22.0,
        distance_km=0.0,
        description="International Dark Sky Park in Nevada",
        notes="High elevation, very dark skies",
    ),
    DarkSkySite(
        name="Mauna Kea Visitor Center",
        latitude=19.8206,
        longitude=-155.4681,
        bortle_class=BortleClass.CLASS_1,
        sqm_value=22.0,
        distance_km=0.0,
        description="High-altitude observing site in Hawaii",
        notes="Elevation 9,200 ft, excellent seeing",
    ),
    # Additional notable dark sites
    DarkSkySite(
        name="Spruce Knob",
        latitude=38.6997,
        longitude=-79.5328,
        bortle_class=BortleClass.CLASS_2,
        sqm_value=21.8,
        distance_km=0.0,
        description="Highest point in West Virginia",
        notes="Dark sky site in the Appalachians",
    ),
    DarkSkySite(
        name="Kitt Peak National Observatory",
        latitude=31.9583,
        longitude=-111.5967,
        bortle_class=BortleClass.CLASS_2,
        sqm_value=21.9,
        distance_km=0.0,
        description="Professional observatory in Arizona",
        notes="Public observing programs available",
    ),
]


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

    Queries from database first (for offline use), falls back to hardcoded list if empty.

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

    # Try database first (offline-capable)
    try:
        with get_db_session() as db:
            from .models import DarkSkySiteModel

            # Query all sites from database
            db_sites = db.query(DarkSkySiteModel).filter(DarkSkySiteModel.bortle_class <= min_bortle.value).all()

            for db_site in db_sites:
                distance = _haversine_distance(
                    location.latitude, location.longitude, db_site.latitude, db_site.longitude
                )

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
            if db_sites:
                sites.sort(key=lambda s: s.distance_km)
                return sites
    except Exception as e:
        logger.debug(f"Database query failed, using fallback: {e}")

    # Fallback to hardcoded list if database is empty or query fails
    logger.debug("Using hardcoded dark sky sites list")
    for site in KNOWN_DARK_SITES:
        distance = _haversine_distance(location.latitude, location.longitude, site.latitude, site.longitude)

        if distance <= max_distance_km and site.bortle_class <= min_bortle:
            # Create new site with calculated distance
            site_with_distance = DarkSkySite(
                name=site.name,
                latitude=site.latitude,
                longitude=site.longitude,
                bortle_class=site.bortle_class,
                sqm_value=site.sqm_value,
                distance_km=distance,
                description=site.description,
                notes=site.notes,
            )
            sites.append(site_with_distance)

    # Sort by distance
    sites.sort(key=lambda s: s.distance_km)
    return sites


def populate_dark_sky_sites_database(db_session: Session) -> None:
    """
    Populate database with dark sky site data.

    This should be called once to initialize the database with static data.
    Works offline once populated. Now uses seed data from JSON files instead of hardcoded Python data.

    Args:
        db_session: SQLAlchemy database session
    """
    from .database_seeder import seed_dark_sky_sites

    logger.info("Populating dark sky sites database...")
    seed_dark_sky_sites(db_session, force=True)


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
    light_data = asyncio.run(get_light_pollution_data(location.latitude, location.longitude))

    return VacationViewingInfo(
        location=location,
        bortle_class=light_data.bortle_class,
        sqm_value=light_data.sqm_value,
        naked_eye_limiting_magnitude=light_data.naked_eye_limiting_magnitude,
        milky_way_visible=light_data.milky_way_visible,
        description=light_data.description,
        recommendations=light_data.recommendations,
    )

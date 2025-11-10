"""
Vacation Planning for Astronomy

Helps plan telescope viewing for vacation destinations by finding
what's visible and locating nearby dark sky sites.
"""

from __future__ import annotations

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
        description="First International Dark Sky Park in Utah",
        notes="Excellent for Milky Way photography",
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
        description="International Dark Sky Park in Colorado/Utah",
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
    R = 6371.0  # Earth radius in km

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


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
        location = geocode_location(location)

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
    Works offline once populated.

    Args:
        db_session: SQLAlchemy database session
    """
    from .models import Base, DarkSkySiteModel

    logger.info("Populating dark sky sites database...")

    # Ensure table exists (create if it doesn't)
    try:
        DarkSkySiteModel.__table__.create(db_session.bind, checkfirst=True)
    except Exception as e:
        logger.debug(f"Table creation check: {e}")

    # Clear existing data (if table exists)
    try:
        db_session.query(DarkSkySiteModel).delete()
    except Exception:
        # Table doesn't exist yet, that's okay
        pass

    # Add dark sky sites
    for site in KNOWN_DARK_SITES:
        model = DarkSkySiteModel(
            name=site.name,
            latitude=site.latitude,
            longitude=site.longitude,
            bortle_class=site.bortle_class.value,
            sqm_value=site.sqm_value,
            description=site.description,
            notes=site.notes,
        )
        db_session.add(model)

    db_session.commit()
    logger.info(f"Added {len(KNOWN_DARK_SITES)} dark sky sites to database")


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
        location = geocode_location(location)

    # Get light pollution data
    light_data = get_light_pollution_data(location.latitude, location.longitude)

    return VacationViewingInfo(
        location=location,
        bortle_class=light_data.bortle_class,
        sqm_value=light_data.sqm_value,
        naked_eye_limiting_magnitude=light_data.naked_eye_limiting_magnitude,
        milky_way_visible=light_data.milky_way_visible,
        description=light_data.description,
        recommendations=light_data.recommendations,
    )


"""
Space Events Calendar

Parses and manages space events from sources like The Planetary Society calendar.
Helps users find optimal viewing locations for upcoming space events.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from .observer import ObserverLocation

logger = logging.getLogger(__name__)

__all__ = [
    "SpaceEvent",
    "SpaceEventType",
    "ViewingRequirement",
    "find_best_viewing_location",
    "get_upcoming_events",
]


class SpaceEventType(StrEnum):
    """Types of space events."""

    METEOR_SHOWER = "meteor_shower"
    PLANETARY_OPPOSITION = "planetary_opposition"
    PLANETARY_ELONGATION = "planetary_elongation"
    PLANETARY_BRIGHTNESS = "planetary_brightness"
    LUNAR_ECLIPSE = "lunar_eclipse"
    SOLAR_ECLIPSE = "solar_eclipse"
    SPACE_MISSION = "space_mission"
    ASTEROID_FLYBY = "asteroid_flyby"
    SOLSTICE = "solstice"
    EQUINOX = "equinox"
    OTHER = "other"


@dataclass
class ViewingRequirement:
    """Requirements for viewing a space event."""

    min_latitude: float | None = None  # Minimum latitude where visible
    max_latitude: float | None = None  # Maximum latitude where visible
    min_longitude: float | None = None  # Minimum longitude where visible
    max_longitude: float | None = None  # Maximum longitude where visible
    dark_sky_required: bool = False  # Whether dark sky is needed
    min_bortle_class: int | None = None  # Minimum Bortle class (1-9)
    equipment_needed: str | None = None  # "naked_eye", "binoculars", "telescope"
    notes: str | None = None


@dataclass
class SpaceEvent:
    """A space event from the calendar."""

    name: str
    event_type: SpaceEventType
    date: datetime
    description: str
    viewing_requirements: ViewingRequirement
    source: str = "Planetary Society"
    url: str | None = None


# Space events from Planetary Society calendar
# Based on https://www.planetary.org/articles/calendar-of-space-events-2025
SPACE_EVENTS_2025 = [
    SpaceEvent(
        name="Quadrantid Meteor Shower Peak",
        event_type=SpaceEventType.METEOR_SHOWER,
        date=datetime(2025, 1, 3),
        description="The Quadrantid meteor shower peaks. The Moon will be a slightly illuminated crescent and should not interfere much with the display.",
        viewing_requirements=ViewingRequirement(
            dark_sky_required=True,
            min_bortle_class=4,
            equipment_needed="naked_eye",
            notes="Best viewed from Northern Hemisphere after midnight",
        ),
        url="https://www.planetary.org/articles/calendar-of-space-events-2025",
    ),
    SpaceEvent(
        name="Mars at Opposition",
        event_type=SpaceEventType.PLANETARY_OPPOSITION,
        date=datetime(2025, 1, 16),
        description="Mars will be at its brightest and most visible of the entire year, making this the best time to try to see the red planet.",
        viewing_requirements=ViewingRequirement(
            equipment_needed="naked_eye",
            notes="Visible all night, best with telescope for detail",
        ),
    ),
    SpaceEvent(
        name="Venus at Greatest Brightness",
        event_type=SpaceEventType.PLANETARY_BRIGHTNESS,
        date=datetime(2025, 2, 16),
        description="Venus will be at its brightest of the entire year, appearing more than twice as bright as during the planet's dimmest moment of 2025.",
        viewing_requirements=ViewingRequirement(
            equipment_needed="naked_eye",
            notes="Visible in evening or morning sky depending on elongation",
        ),
    ),
    SpaceEvent(
        name="Total Lunar Eclipse",
        event_type=SpaceEventType.LUNAR_ECLIPSE,
        date=datetime(2025, 3, 14),
        description="This lunar eclipse will be visible in its entirety from almost all of North America, including the contiguous United States and Central America, as well as from most of South America.",
        viewing_requirements=ViewingRequirement(
            min_latitude=-60.0,
            max_latitude=90.0,
            min_longitude=-180.0,
            max_longitude=-30.0,  # Roughly North/South America
            equipment_needed="naked_eye",
            notes="Visible from North and South America",
        ),
    ),
    SpaceEvent(
        name="March Equinox",
        event_type=SpaceEventType.EQUINOX,
        date=datetime(2025, 3, 20),
        description="Spring equinox in Northern Hemisphere, autumn equinox in Southern Hemisphere.",
        viewing_requirements=ViewingRequirement(equipment_needed="naked_eye"),
    ),
    SpaceEvent(
        name="Partial Solar Eclipse",
        event_type=SpaceEventType.SOLAR_ECLIPSE,
        date=datetime(2025, 3, 29),
        description="The solar eclipse will be best viewed from northeastern Canada, but will also be visible to a lesser extent from most of Europe and parts of North Africa and Russia.",
        viewing_requirements=ViewingRequirement(
            min_latitude=30.0,
            max_latitude=80.0,
            min_longitude=-100.0,
            max_longitude=60.0,
            equipment_needed="telescope",
            notes="NEVER look directly at the Sun without proper solar filters",
        ),
    ),
    SpaceEvent(
        name="Saturn's Rings Edge-On",
        event_type=SpaceEventType.OTHER,
        date=datetime(2025, 3, 1),  # Approximate - "sometime this month"
        description="Saturn's rings will be oriented edge-on toward Earth, making them difficult to see.",
        viewing_requirements=ViewingRequirement(
            equipment_needed="telescope",
            notes="Rings will appear as a thin line, very difficult to see",
        ),
    ),
    SpaceEvent(
        name="Mercury at Greatest Elongation",
        event_type=SpaceEventType.PLANETARY_ELONGATION,
        date=datetime(2025, 4, 21),
        description="Mercury will appear farthest from the Sun in the sky than at any other time in the year, making this the best time to see the planet in 2025.",
        viewing_requirements=ViewingRequirement(
            equipment_needed="binoculars",
            notes="Best viewed just after sunset or before sunrise",
        ),
    ),
    SpaceEvent(
        name="Lyrid Meteor Shower Peak",
        event_type=SpaceEventType.METEOR_SHOWER,
        date=datetime(2025, 4, 22),
        description="The Lyrid meteor shower peaks. The Moon will be only slightly illuminated and should not interfere much with the display.",
        viewing_requirements=ViewingRequirement(
            dark_sky_required=True,
            min_bortle_class=4,
            equipment_needed="naked_eye",
            notes="Best viewed from Northern Hemisphere after midnight",
        ),
    ),
    SpaceEvent(
        name="Eta Aquariid Meteor Shower Peak",
        event_type=SpaceEventType.METEOR_SHOWER,
        date=datetime(2025, 5, 6),
        description="The Eta Aquariid meteor shower peaks. The Moon will be mostly illuminated, which may make it harder to spot this shower.",
        viewing_requirements=ViewingRequirement(
            dark_sky_required=True,
            min_bortle_class=4,
            equipment_needed="naked_eye",
            notes="Best viewed from Southern Hemisphere, but visible in Northern Hemisphere",
        ),
    ),
    SpaceEvent(
        name="Venus at Greatest Elongation",
        event_type=SpaceEventType.PLANETARY_ELONGATION,
        date=datetime(2025, 5, 31),
        description="Venus will appear farthest from the Sun, and so higher in the night sky, than at any other time of the year.",
        viewing_requirements=ViewingRequirement(
            equipment_needed="naked_eye",
            notes="Visible in evening or morning sky depending on elongation",
        ),
    ),
    SpaceEvent(
        name="June Solstice",
        event_type=SpaceEventType.SOLSTICE,
        date=datetime(2025, 6, 21),
        description="Summer solstice in Northern Hemisphere, winter solstice in Southern Hemisphere.",
        viewing_requirements=ViewingRequirement(equipment_needed="naked_eye"),
    ),
    SpaceEvent(
        name="Southern Delta Aquariid Meteor Shower Peak",
        event_type=SpaceEventType.METEOR_SHOWER,
        date=datetime(2025, 7, 31),
        description="The Southern Delta Aquariid meteor shower peaks. The Moon will be only slightly illuminated, so it should not interfere much with views of this shower.",
        viewing_requirements=ViewingRequirement(
            dark_sky_required=True,
            min_bortle_class=4,
            equipment_needed="naked_eye",
            notes="Best viewed from Southern Hemisphere",
        ),
    ),
    SpaceEvent(
        name="Perseid Meteor Shower Peak",
        event_type=SpaceEventType.METEOR_SHOWER,
        date=datetime(2025, 8, 12),
        description="The Perseid meteor shower peaks. The Moon will be almost full, which could make it much harder to see many of these meteors.",
        viewing_requirements=ViewingRequirement(
            dark_sky_required=True,
            min_bortle_class=4,
            equipment_needed="naked_eye",
            notes="Best viewed from Northern Hemisphere. Moon will interfere this year.",
        ),
    ),
    SpaceEvent(
        name="Total Lunar Eclipse",
        event_type=SpaceEventType.LUNAR_ECLIPSE,
        date=datetime(2025, 9, 7),
        description="The lunar eclipse will be visible in its entirety from most of Asia, Russia, Australia, and eastern Africa.",
        viewing_requirements=ViewingRequirement(
            min_latitude=-50.0,
            max_latitude=80.0,
            min_longitude=20.0,
            max_longitude=180.0,
            equipment_needed="naked_eye",
            notes="Visible from Asia, Russia, Australia, and eastern Africa",
        ),
    ),
    SpaceEvent(
        name="Partial Solar Eclipse",
        event_type=SpaceEventType.SOLAR_ECLIPSE,
        date=datetime(2025, 9, 21),
        description="This eclipse will only be visible to those in New Zealand, Antarctica, and the south Pacific Ocean.",
        viewing_requirements=ViewingRequirement(
            min_latitude=-90.0,
            max_latitude=-30.0,
            min_longitude=150.0,
            max_longitude=180.0,
            equipment_needed="telescope",
            notes="NEVER look directly at the Sun without proper solar filters",
        ),
    ),
    SpaceEvent(
        name="Saturn at Opposition",
        event_type=SpaceEventType.PLANETARY_OPPOSITION,
        date=datetime(2025, 9, 21),
        description="Saturn will be at its brightest and most visible of the entire year, so this will be the best time to see it.",
        viewing_requirements=ViewingRequirement(
            equipment_needed="telescope",
            notes="Visible all night, best with telescope to see rings",
        ),
    ),
    SpaceEvent(
        name="Neptune at Opposition",
        event_type=SpaceEventType.PLANETARY_OPPOSITION,
        date=datetime(2025, 9, 23),
        description="Neptune will be at its brightest and most visible of the entire year. It will still be relatively dim and difficult to see, but with the right equipment (like a capable telescope), this will be the best time to try to see it.",
        viewing_requirements=ViewingRequirement(
            dark_sky_required=True,
            min_bortle_class=4,
            equipment_needed="telescope",
            notes="Requires telescope and dark skies",
        ),
    ),
    SpaceEvent(
        name="September Equinox",
        event_type=SpaceEventType.EQUINOX,
        date=datetime(2025, 9, 22),
        description="Autumn equinox in Northern Hemisphere, spring equinox in Southern Hemisphere.",
        viewing_requirements=ViewingRequirement(equipment_needed="naked_eye"),
    ),
    SpaceEvent(
        name="Orionid Meteor Shower Peak",
        event_type=SpaceEventType.METEOR_SHOWER,
        date=datetime(2025, 10, 21),
        description="The Orionid meteor shower peaks. This shower will peak during a new Moon, making for excellent viewing.",
        viewing_requirements=ViewingRequirement(
            dark_sky_required=True,
            min_bortle_class=4,
            equipment_needed="naked_eye",
            notes="Excellent viewing conditions with new moon",
        ),
    ),
    SpaceEvent(
        name="Leonid Meteor Shower Peak",
        event_type=SpaceEventType.METEOR_SHOWER,
        date=datetime(2025, 11, 17),
        description="The Leonid meteor shower peaks. The Moon will be a slightly illuminated crescent and should not interfere much with the display.",
        viewing_requirements=ViewingRequirement(
            dark_sky_required=True,
            min_bortle_class=4,
            equipment_needed="naked_eye",
            notes="Best viewed from Northern Hemisphere after midnight",
        ),
    ),
    SpaceEvent(
        name="Uranus at Opposition",
        event_type=SpaceEventType.PLANETARY_OPPOSITION,
        date=datetime(2025, 11, 21),
        description="Uranus will be at its brightest and most visible of the entire year. It will still be relatively dim and so only visible to most naked-eye stargazers under a very dark sky, but easier to spot with binoculars or a telescope.",
        viewing_requirements=ViewingRequirement(
            dark_sky_required=True,
            min_bortle_class=3,
            equipment_needed="binoculars",
            notes="Visible with binoculars or telescope, very dark sky helps",
        ),
    ),
    SpaceEvent(
        name="Geminid Meteor Shower Peak",
        event_type=SpaceEventType.METEOR_SHOWER,
        date=datetime(2025, 12, 14),
        description="The Geminid meteor shower peaks. The Moon will be about one-third illuminated, which could partially reduce the visibility of this shower, but there will still be plenty to see.",
        viewing_requirements=ViewingRequirement(
            dark_sky_required=True,
            min_bortle_class=4,
            equipment_needed="naked_eye",
            notes="One of the best meteor showers of the year",
        ),
    ),
    SpaceEvent(
        name="December Solstice",
        event_type=SpaceEventType.SOLSTICE,
        date=datetime(2025, 12, 21),
        description="Winter solstice in Northern Hemisphere, summer solstice in Southern Hemisphere.",
        viewing_requirements=ViewingRequirement(equipment_needed="naked_eye"),
    ),
    SpaceEvent(
        name="Ursid Meteor Shower Peak",
        event_type=SpaceEventType.METEOR_SHOWER,
        date=datetime(2025, 12, 22),
        description="The Ursid meteor shower peaks. The Moon will be a barely illuminated crescent and should not affect meteor viewing.",
        viewing_requirements=ViewingRequirement(
            dark_sky_required=True,
            min_bortle_class=4,
            equipment_needed="naked_eye",
            notes="Best viewed from Northern Hemisphere",
        ),
    ),
]

# 2026 events (to be populated when available)
SPACE_EVENTS_2026: list[SpaceEvent] = []


def populate_space_events_database(db_session: Session) -> None:
    """
    Populate the database with space events from seed data.

    This function should be called during database initialization to ensure
    space events are available offline. Now uses seed data from JSON files instead of hardcoded Python data.

    Args:
        db_session: SQLAlchemy database session
    """
    from .database_seeder import seed_space_events

    logger.info("Populating space events database...")
    seed_space_events(db_session, force=True)


def get_upcoming_events(
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    event_types: list[SpaceEventType] | None = None,
) -> list[SpaceEvent]:
    """
    Get upcoming space events within a date range.

    Queries from the database first, falls back to hardcoded lists if database is empty.

    Args:
        start_date: Start of date range (default: today)
        end_date: End of date range (default: 1 year from start)
        event_types: Filter by event types (default: all types)

    Returns:
        List of SpaceEvent objects, sorted by date
    """
    from datetime import timedelta

    from sqlalchemy import and_

    if start_date is None:
        start_date = datetime.now(UTC)
    if end_date is None:
        end_date = start_date + timedelta(days=365)

    # Try to get from database first
    try:
        from .models import SpaceEventModel, get_db_session

        with get_db_session() as db:
            query = db.query(SpaceEventModel).filter(
                and_(
                    SpaceEventModel.date >= start_date,
                    SpaceEventModel.date <= end_date,
                )
            )

            # Filter by event type if specified
            if event_types:
                type_values = [et.value for et in event_types]
                query = query.filter(SpaceEventModel.event_type.in_(type_values))

            # Order by date
            query = query.order_by(SpaceEventModel.date)

            db_events = query.all()

            # If we have events in the database, use them
            if db_events:
                filtered = []
                for db_event in db_events:
                    req = ViewingRequirement(
                        min_latitude=db_event.min_latitude,
                        max_latitude=db_event.max_latitude,
                        min_longitude=db_event.min_longitude,
                        max_longitude=db_event.max_longitude,
                        dark_sky_required=db_event.dark_sky_required,
                        min_bortle_class=db_event.min_bortle_class,
                        equipment_needed=db_event.equipment_needed,
                        notes=db_event.viewing_notes,
                    )

                    event = SpaceEvent(
                        name=db_event.name,
                        event_type=SpaceEventType(db_event.event_type),
                        date=db_event.date,
                        description=db_event.description,
                        viewing_requirements=req,
                        source=db_event.source,
                        url=db_event.url,
                    )
                    filtered.append(event)

                return filtered
    except Exception as e:
        logger.debug(f"Could not query space events from database: {e}, falling back to hardcoded lists")

    # Fallback to hardcoded lists
    all_events = SPACE_EVENTS_2025 + SPACE_EVENTS_2026

    # Filter by date range
    filtered = []
    for event in all_events:
        # Make event date timezone-aware if it's naive
        event_date = event.date
        if event_date.tzinfo is None:
            event_date = event_date.replace(tzinfo=UTC)

        if start_date <= event_date <= end_date:
            filtered.append(event)

    # Filter by event type if specified
    if event_types:
        filtered = [evt for evt in filtered if evt.event_type in event_types]

    # Sort by date
    filtered.sort(key=lambda evt: evt.date)

    return filtered


def is_event_visible_from_location(event: SpaceEvent, location: ObserverLocation) -> bool:
    """
    Check if an event is visible from a given location.

    Args:
        event: Space event to check
        location: Observer location

    Returns:
        True if event should be visible from this location
    """
    req = event.viewing_requirements

    # Check latitude bounds
    if req.min_latitude is not None and location.latitude < req.min_latitude:
        return False
    if req.max_latitude is not None and location.latitude > req.max_latitude:
        return False

    # Check longitude bounds
    if req.min_longitude is not None and location.longitude < req.min_longitude:
        return False
    return not (req.max_longitude is not None and location.longitude > req.max_longitude)


def find_best_viewing_location(
    event: SpaceEvent,
    current_location: ObserverLocation,
    max_distance_km: float = 1000.0,
) -> tuple[ObserverLocation | None, str]:
    """
    Find the best viewing location for an event based on current location.

    Args:
        event: Space event to view
        current_location: User's current location
        max_distance_km: Maximum distance to search for better locations

    Returns:
        Tuple of (best_location, recommendation_message)
        If current location is good, returns (None, message)
    """
    from .light_pollution import BortleClass, get_light_pollution_data
    from .vacation_planning import find_dark_sites_near

    req = event.viewing_requirements

    # Check if event is visible from current location
    if not is_event_visible_from_location(event, current_location):
        # Find nearest location where event is visible
        # For now, return a message - could be enhanced with geocoding
        return (
            None,
            "Event is not visible from your current location. You may need to travel to a different region.",
        )

    # Check if dark sky is required
    if req.dark_sky_required or req.min_bortle_class:
        # Run async function - this is a sync entry point, so asyncio.run() is safe
        current_light = asyncio.run(get_light_pollution_data(current_location.latitude, current_location.longitude))
        current_bortle = current_light.bortle_class.value

        # Check if current location meets requirements
        if req.min_bortle_class and current_bortle > req.min_bortle_class:
            # Find nearby dark sky sites
            min_bortle = BortleClass(req.min_bortle_class)
            dark_sites = find_dark_sites_near(
                current_location,
                max_distance_km=max_distance_km,
                min_bortle=min_bortle,
            )

            if dark_sites:
                closest = dark_sites[0]
                distance_miles = closest.distance_km / 1.60934
                return (
                    None,
                    f"Your current location has Bortle Class {current_bortle} (needs ≤ {req.min_bortle_class}). "
                    f"Consider traveling to {closest.name} ({distance_miles:.1f} miles away) for better viewing.",
                )
            else:
                return (
                    None,
                    f"Your current location has Bortle Class {current_bortle} (needs ≤ {req.min_bortle_class}). "
                    f"Try to find a darker location within {max_distance_km / 1.60934:.0f} miles.",
                )

    # Current location is good
    return (
        None,
        "Your current location should provide good viewing for this event.",
    )

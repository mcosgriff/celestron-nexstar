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
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from celestron_nexstar.api.location.observer import ObserverLocation

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


# NOTE: Space events data is now stored in database seed files.
# See get_upcoming_events() which loads from database.
# To regenerate seed files, run: python scripts/create_seed_files.py
# Based on https://www.planetary.org/articles/calendar-of-space-events-2025


def populate_space_events_database(db_session: Session) -> None:
    """
    Populate the database with space events from seed data.

    This function should be called during database initialization to ensure
    space events are available offline. Now uses seed data from JSON files instead of hardcoded Python data.

    Args:
        db_session: SQLAlchemy database session
    """
    import asyncio

    from celestron_nexstar.api.database.database_seeder import seed_space_events
    from celestron_nexstar.api.database.models import get_db_session

    logger.info("Populating space events database...")

    async def _seed() -> None:
        async with get_db_session() as async_session:
            await seed_space_events(async_session, force=True)

    asyncio.run(_seed())


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
        import asyncio

        from sqlalchemy import select

        from celestron_nexstar.api.database.models import SpaceEventModel, get_db_session

        async def _get_events() -> list[SpaceEventModel]:
            async with get_db_session() as db:
                result = await db.execute(
                    select(SpaceEventModel).filter(
                        and_(
                            SpaceEventModel.date >= start_date,
                            SpaceEventModel.date <= end_date,
                        )
                    )
                )
                return list(result.scalars().all())

        # Filter by event type if specified
        if event_types:
            type_values = [et.value for et in event_types]

            async def _get_filtered_events() -> list[SpaceEventModel]:
                async with get_db_session() as db:
                    result = await db.execute(
                        select(SpaceEventModel)
                        .filter(
                            and_(
                                SpaceEventModel.date >= start_date,
                                SpaceEventModel.date <= end_date,
                                SpaceEventModel.event_type.in_(type_values),
                            )
                        )
                        .order_by(SpaceEventModel.date)
                    )
                    return list(result.scalars().all())

            db_events = asyncio.run(_get_filtered_events())
        else:

            async def _get_ordered_events() -> list[SpaceEventModel]:
                async with get_db_session() as db:
                    result = await db.execute(
                        select(SpaceEventModel)
                        .filter(
                            and_(
                                SpaceEventModel.date >= start_date,
                                SpaceEventModel.date <= end_date,
                            )
                        )
                        .order_by(SpaceEventModel.date)
                    )
                    return list(result.scalars().all())

            db_events = asyncio.run(_get_ordered_events())

        # If we have events in the database, use them
        if not db_events:
            raise RuntimeError(
                "No space events found in database. Please seed the database by running: nexstar data seed"
            )

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

        # Filter by event type if specified
        if event_types:
            filtered = [evt for evt in filtered if evt.event_type in event_types]

        # Sort by date
        filtered.sort(key=lambda evt: evt.date)

        return filtered
    except Exception as e:
        logger.error(f"Could not query space events from database: {e}")
        raise RuntimeError(
            "No space events found in database. Please seed the database by running: nexstar data seed"
        ) from e


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
    from celestron_nexstar.api.events.vacation_planning import find_dark_sites_near
    from celestron_nexstar.api.location.light_pollution import BortleClass, get_light_pollution_data

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
        async def _get_light_data() -> Any:
            from celestron_nexstar.api.database.models import get_db_session

            async with get_db_session() as db_session:
                return await get_light_pollution_data(db_session, current_location.latitude, current_location.longitude)

        current_light = asyncio.run(_get_light_data())
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

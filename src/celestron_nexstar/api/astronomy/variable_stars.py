"""
Variable Star Events

Tracks eclipsing binaries, Cepheids, and other variable star events.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession


if TYPE_CHECKING:
    from celestron_nexstar.api.location.observer import ObserverLocation

logger = logging.getLogger(__name__)

__all__ = [
    "VariableStar",
    "VariableStarEvent",
    "get_known_variable_stars",
    "get_variable_star_events",
]


@dataclass
class VariableStar:
    """Information about a variable star."""

    name: str
    designation: str  # Bayer/Flamsteed designation
    variable_type: str  # "eclipsing_binary", "cepheid", "mira", etc.
    period_days: float  # Period in days
    magnitude_min: float  # Minimum magnitude (brightest)
    magnitude_max: float  # Maximum magnitude (dimmest)
    ra_hours: float  # Right ascension
    dec_degrees: float  # Declination
    notes: str


@dataclass
class VariableStarEvent:
    """Variable star event information."""

    star: VariableStar
    event_type: str  # "minimum", "maximum", "eclipse_start", "eclipse_end"
    date: datetime
    magnitude: float  # Expected magnitude at event
    is_visible: bool  # Whether star is above horizon
    notes: str


# NOTE: Variable star data is now stored in database seed files.
# See get_known_variable_stars() which loads from database.
# To regenerate seed files, run: python scripts/create_seed_files.py


async def get_known_variable_stars(db_session: AsyncSession) -> list[VariableStar]:
    """
    Get list of known variable stars from database.

    Args:
        db_session: Database session

    Returns:
        List of VariableStar objects

    Raises:
        RuntimeError: If no variable stars found in database (seed data required)
    """
    from sqlalchemy import func, select

    from celestron_nexstar.api.database.models import VariableStarModel

    count = await db_session.scalar(select(func.count(VariableStarModel.id)))
    if count == 0:
        raise RuntimeError(
            "No variable stars found in database. Please seed the database by running: nexstar data seed"
        )

    result = await db_session.execute(select(VariableStarModel))
    models = result.scalars().all()

    return [model.to_variable_star() for model in models]


def _calculate_next_event(
    star: VariableStar,
    start_date: datetime,
    event_type: str,
) -> datetime | None:
    """
    Calculate next event date for a variable star.

    Args:
        star: Variable star
        start_date: Start date for calculation
        event_type: "minimum" or "maximum"

    Returns:
        Event date or None
    """
    # Simplified calculation - would need epoch for precise timing
    # For now, estimate based on period
    days_since_epoch = (start_date - datetime(2024, 1, 1, tzinfo=UTC)).days
    cycles = days_since_epoch / star.period_days
    next_cycle = int(cycles) + 1

    # Estimate next event
    days_to_next = (next_cycle * star.period_days) - days_since_epoch
    event_date = start_date + timedelta(days=days_to_next)

    return event_date


async def get_variable_star_events(
    db_session: AsyncSession,
    location: ObserverLocation,
    months_ahead: int = 6,
    event_type: str | None = None,
) -> list[VariableStarEvent]:
    """
    Get variable star events (minima, maxima, eclipses).

    Args:
        location: Observer location
        months_ahead: How many months ahead to search (default: 6)
        event_type: Filter by event type ("minimum", "maximum") or None for all

    Returns:
        List of VariableStarEvent objects, sorted by date
    """
    events = []
    now = datetime.now(UTC)
    end_date = now + timedelta(days=30 * months_ahead)

    stars = await get_known_variable_stars(db_session)
    for star in stars:
        # Calculate next minimum and maximum
        if event_type is None or event_type == "minimum":
            next_minimum = _calculate_next_event(star, now, "minimum")
            if next_minimum and now <= next_minimum <= end_date:
                events.append(
                    VariableStarEvent(
                        star=star,
                        event_type="minimum",
                        date=next_minimum,
                        magnitude=star.magnitude_min,
                        is_visible=True,  # Simplified
                        notes=f"{star.name} at minimum brightness (magnitude {star.magnitude_min:.2f})",
                    )
                )

        if event_type is None or event_type == "maximum":
            next_maximum = _calculate_next_event(star, now, "maximum")
            if next_maximum and now <= next_maximum <= end_date:
                events.append(
                    VariableStarEvent(
                        star=star,
                        event_type="maximum",
                        date=next_maximum,
                        magnitude=star.magnitude_max,
                        is_visible=True,  # Simplified
                        notes=f"{star.name} at maximum brightness (magnitude {star.magnitude_max:.2f})",
                    )
                )

    # Sort by date
    events.sort(key=lambda e: e.date)
    return events

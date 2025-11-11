"""
Variable Star Events

Tracks eclipsing binaries, Cepheids, and other variable star events.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from .observer import ObserverLocation

logger = logging.getLogger(__name__)

__all__ = [
    "VariableStar",
    "VariableStarEvent",
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


# Well-known variable stars
KNOWN_VARIABLE_STARS = [
    VariableStar(
        name="Algol",
        designation="β Persei",
        variable_type="eclipsing_binary",
        period_days=2.867,
        magnitude_min=2.1,
        magnitude_max=3.4,
        ra_hours=3.136,
        dec_degrees=40.956,
        notes="Famous eclipsing binary - 'Demon Star'. Dips every 2.87 days.",
    ),
    VariableStar(
        name="Delta Cephei",
        designation="δ Cephei",
        variable_type="cepheid",
        period_days=5.366,
        magnitude_min=3.5,
        magnitude_max=4.4,
        ra_hours=22.485,
        dec_degrees=58.415,
        notes="Prototype Cepheid variable. Brightness varies smoothly over 5.37 days.",
    ),
    VariableStar(
        name="Mira",
        designation="o Ceti",  # Using Latin 'o' instead of Greek omicron
        variable_type="mira",
        period_days=332.0,
        magnitude_min=2.0,
        magnitude_max=10.1,
        ra_hours=2.322,
        dec_degrees=-2.977,
        notes="Long-period variable. Can be naked-eye visible at maximum.",
    ),
    VariableStar(
        name="Beta Lyrae",
        designation="β Lyrae",
        variable_type="eclipsing_binary",
        period_days=12.94,
        magnitude_min=3.3,
        magnitude_max=4.3,
        ra_hours=18.834,
        dec_degrees=33.363,
        notes="Eclipsing binary with continuous variation.",
    ),
]


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


def get_variable_star_events(
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

    for star in KNOWN_VARIABLE_STARS:
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
                        notes=f"{star.name} at minimum brightness (magnitude {star.magnitude_min:.1f})",
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
                        notes=f"{star.name} at maximum brightness (magnitude {star.magnitude_max:.1f})",
                    )
                )

    # Sort by date
    events.sort(key=lambda e: e.date)
    return events

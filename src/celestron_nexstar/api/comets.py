"""
Comet Tracking and Predictions

Tracks bright comets and their visibility from observer location.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING


try:
    # Import skyfield to check availability (imports not used directly in this module)
    import skyfield.api  # noqa: F401

    SKYFIELD_AVAILABLE = True
except ImportError:
    SKYFIELD_AVAILABLE = False

if TYPE_CHECKING:
    from .observer import ObserverLocation

logger = logging.getLogger(__name__)

__all__ = [
    "Comet",
    "CometVisibility",
    "get_upcoming_comets",
    "get_visible_comets",
]


@dataclass
class Comet:
    """Information about a comet."""

    name: str
    designation: str  # Official designation (e.g., "C/2023 A3")
    perihelion_date: datetime  # Closest approach to sun
    perihelion_distance_au: float  # Distance from sun at perihelion (AU)
    peak_magnitude: float  # Expected peak magnitude
    peak_date: datetime  # Expected peak brightness date
    is_periodic: bool  # Whether comet is periodic
    period_years: float | None  # Orbital period in years (if periodic)
    notes: str  # Additional information


@dataclass
class CometVisibility:
    """Comet visibility information for a specific date."""

    comet: Comet
    date: datetime
    magnitude: float  # Current magnitude
    altitude: float  # Altitude above horizon
    is_visible: bool  # Whether comet is above horizon
    best_viewing_time: datetime | None  # Best time to view (when highest)
    notes: str


# Known bright comets (2024-2030)
# Data from Minor Planet Center and comet observation databases
KNOWN_COMETS = [
    Comet(
        name="Tsuchinshan-ATLAS",
        designation="C/2023 A3",
        perihelion_date=datetime(2024, 9, 27, tzinfo=UTC),
        perihelion_distance_au=0.39,
        peak_magnitude=0.5,
        peak_date=datetime(2024, 10, 12, tzinfo=UTC),
        is_periodic=False,
        period_years=None,
        notes="Potentially bright comet in October 2024. May reach naked-eye visibility.",
    ),
    Comet(
        name="12P/Pons-Brooks",
        designation="12P/Pons-Brooks",
        perihelion_date=datetime(2024, 4, 21, tzinfo=UTC),
        perihelion_distance_au=0.78,
        peak_magnitude=4.5,
        peak_date=datetime(2024, 4, 21, tzinfo=UTC),
        is_periodic=True,
        period_years=71.0,
        notes="Periodic comet with 71-year orbit. Known for outbursts.",
    ),
    Comet(
        name="C/2025 A6 (Lemmon)",
        designation="C/2025 A6",
        perihelion_date=datetime(2025, 10, 21, tzinfo=UTC),
        perihelion_distance_au=0.60,
        peak_magnitude=4.3,
        peak_date=datetime(2025, 10, 21, tzinfo=UTC),
        is_periodic=False,
        period_years=None,
        notes="Non-periodic comet discovered January 2025. May be visible to naked eye.",
    ),
]


def _estimate_comet_magnitude(comet: Comet, date: datetime) -> float:
    """
    Estimate comet magnitude at a given date.

    Simplified model based on distance from sun and Earth.

    Args:
        comet: Comet information
        date: Date to estimate magnitude for

    Returns:
        Estimated magnitude
    """
    # Days from perihelion
    days_from_perihelion = (date - comet.perihelion_date).days

    # Simplified magnitude model
    # Comets are brightest near perihelion
    # Magnitude increases (gets dimmer) as distance increases
    if abs(days_from_perihelion) < 30:
        # Near perihelion - use peak magnitude
        base_magnitude = comet.peak_magnitude
    else:
        # Farther from perihelion - magnitude increases
        # Rough approximation: +0.1 mag per 10 days
        magnitude_increase = abs(days_from_perihelion) / 10.0 * 0.1
        base_magnitude = comet.peak_magnitude + magnitude_increase

    return base_magnitude


def get_visible_comets(
    location: ObserverLocation,
    months_ahead: int = 12,
    max_magnitude: float = 8.0,
) -> list[CometVisibility]:
    """
    Get comets visible from observer location.

    Args:
        location: Observer location
        months_ahead: How many months ahead to search (default: 12)
        max_magnitude: Maximum magnitude to include (default: 8.0)

    Returns:
        List of CometVisibility objects, sorted by date
    """
    if not SKYFIELD_AVAILABLE:
        logger.warning("Skyfield not available, cannot calculate comet positions")
        return []

    visibilities = []
    now = datetime.now(UTC)
    end_date = now + timedelta(days=30 * months_ahead)

    # For each known comet, check visibility
    for comet in KNOWN_COMETS:
        # Check if comet is active in our time window
        # Comets are typically visible for several months around perihelion
        activity_start = comet.perihelion_date - timedelta(days=90)
        activity_end = comet.perihelion_date + timedelta(days=180)

        if activity_end < now or activity_start > end_date:
            continue

        # Check visibility at peak and around it
        check_dates = [
            comet.peak_date,
            comet.peak_date - timedelta(days=30),
            comet.peak_date + timedelta(days=30),
        ]

        for check_date in check_dates:
            if now <= check_date <= end_date:
                magnitude = _estimate_comet_magnitude(comet, check_date)

                if magnitude <= max_magnitude:
                    # Estimate altitude (simplified - would need actual ephemeris)
                    # For now, assume reasonable altitude if in activity window
                    altitude = 30.0  # Placeholder - would calculate from ephemeris
                    is_visible = altitude > 0

                    # Best viewing time (simplified - would calculate transit)
                    best_time = check_date.replace(hour=2, minute=0)  # 2 AM local

                    notes = f"Magnitude {magnitude:.1f}"
                    if magnitude < 6.0:
                        notes += " - potentially visible to naked eye"
                    elif magnitude < 8.0:
                        notes += " - visible with binoculars"

                    visibilities.append(
                        CometVisibility(
                            comet=comet,
                            date=check_date,
                            magnitude=magnitude,
                            altitude=altitude,
                            is_visible=is_visible,
                            best_viewing_time=best_time,
                            notes=notes,
                        )
                    )

    # Sort by date
    visibilities.sort(key=lambda v: v.date)
    return visibilities


def get_upcoming_comets(
    location: ObserverLocation,
    months_ahead: int = 24,
) -> list[CometVisibility]:
    """
    Get upcoming bright comets.

    Args:
        location: Observer location
        months_ahead: How many months ahead to search (default: 24)

    Returns:
        List of CometVisibility objects, sorted by peak date
    """
    return get_visible_comets(location, months_ahead=months_ahead, max_magnitude=10.0)

"""
Comet Tracking and Predictions

Tracks bright comets and their visibility from observer location.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

# skyfield is a required dependency
import skyfield.api  # noqa: F401


if TYPE_CHECKING:
    from celestron_nexstar.api.location.observer import ObserverLocation

logger = logging.getLogger(__name__)

__all__ = [
    "Comet",
    "CometVisibility",
    "get_known_comets",
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


# NOTE: Comet data is now stored in database seed files.
# See get_known_comets() which loads from database.
# To regenerate seed files, run: python scripts/create_seed_files.py
# Data from Minor Planet Center and comet observation databases


def get_known_comets(db_session: None = None) -> list[Comet]:  # db_session deprecated
    """
    Get list of known comets from starplot.

    Args:
        db_session: Deprecated parameter, kept for compatibility

    Returns:
        List of Comet objects

    Raises:
        RuntimeError: If no comets found (starplot data required)
    """
    from celestron_nexstar.api.core.exceptions import DatabaseError

    try:
        from starplot.models import Comet as StarplotComet

        starplot_comets = StarplotComet.all()
        if not starplot_comets:
            raise DatabaseError(
                "No comets found in starplot. Please ensure starplot is properly installed and configured."
            )

        # Convert starplot Comet models to our Comet dataclass
        comets = []
        now = datetime.now(UTC)

        for sc in starplot_comets:
            # Starplot's Comet model provides position at a specific time
            # Get name - starplot Comet has a name attribute
            name = sc.name if hasattr(sc, "name") and sc.name else "Unknown"

            # Use name as designation if no separate designation field
            designation = name

            # Starplot's Comet model calculates positions dynamically from ephemeris
            # For metadata fields, we'll use placeholders since starplot focuses on position calculation
            # The actual position will be calculated when needed using the Comet model

            # Try to get current position to estimate some values
            try:
                # Get current RA/Dec from starplot Comet (for validation, but not used in metadata)
                # Position is calculated dynamically when needed
                _ = sc.ra if hasattr(sc, "ra") and sc.ra is not None else None
                _ = sc.dec if hasattr(sc, "dec") and sc.dec is not None else None

                # If we have position, we can estimate it's visible
                # But we still need perihelion info which would require orbital elements
                # For now, use reasonable defaults
                perihelion_date = now  # Would need orbital calculation
                peak_date = now  # Would need magnitude calculation
            except Exception:
                # If position calculation fails, use defaults
                perihelion_date = now
                peak_date = now

            comets.append(
                Comet(
                    name=name,
                    designation=designation,
                    perihelion_date=perihelion_date,  # Placeholder - would need orbital calculation
                    perihelion_distance_au=1.0,  # Placeholder - would need orbital elements
                    peak_magnitude=10.0,  # Placeholder - would need magnitude calculation
                    peak_date=peak_date,  # Placeholder
                    is_periodic=False,  # Placeholder - would need to check orbital period
                    period_years=None,
                    notes="Data from starplot - position calculated dynamically from ephemeris",
                )
            )

        return comets
    except ImportError as e:
        raise DatabaseError("Could not load comets from starplot. Please ensure starplot is properly installed.") from e
    except Exception as e:
        raise DatabaseError(f"Error loading comets from starplot: {e}") from e


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
    # Normalize datetimes to UTC for comparison
    date = date.replace(tzinfo=UTC) if date.tzinfo is None else date.astimezone(UTC)

    perihelion = comet.perihelion_date
    perihelion = perihelion.replace(tzinfo=UTC) if perihelion.tzinfo is None else perihelion.astimezone(UTC)

    # Days from perihelion
    days_from_perihelion = (date - perihelion).days

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


async def get_visible_comets(
    location: ObserverLocation,
    months_ahead: int = 12,
    max_magnitude: float = 8.0,
    db_session: None = None,  # Deprecated, kept for compatibility
) -> list[CometVisibility]:
    """
    Get comets visible from observer location.

    Args:
        location: Observer location
        months_ahead: How many months ahead to search (default: 12)
        max_magnitude: Maximum magnitude to include (default: 8.0)
        db_session: Deprecated parameter, kept for compatibility

    Returns:
        List of CometVisibility objects, sorted by date
    """

    visibilities = []
    now = datetime.now(UTC)
    end_date = now + timedelta(days=30 * months_ahead)

    # For each known comet, check visibility
    comets = get_known_comets()
    for comet in comets:
        # Normalize comet dates to UTC for comparison
        perihelion = comet.perihelion_date
        perihelion = perihelion.replace(tzinfo=UTC) if perihelion.tzinfo is None else perihelion.astimezone(UTC)

        peak = comet.peak_date
        peak = peak.replace(tzinfo=UTC) if peak.tzinfo is None else peak.astimezone(UTC)

        # Check if comet is active in our time window
        # Comets are typically visible for several months around perihelion
        activity_start = perihelion - timedelta(days=90)
        activity_end = perihelion + timedelta(days=180)

        if activity_end < now or activity_start > end_date:
            continue

        # Check visibility at peak and around it
        check_dates = [
            peak,
            peak - timedelta(days=30),
            peak + timedelta(days=30),
        ]

        for check_date in check_dates:
            # Ensure check_date is timezone-aware
            check_date = check_date.replace(tzinfo=UTC) if check_date.tzinfo is None else check_date.astimezone(UTC)

            if now <= check_date <= end_date:
                magnitude = _estimate_comet_magnitude(comet, check_date)

                if magnitude <= max_magnitude:
                    # Estimate altitude (simplified - would need actual ephemeris)
                    # For now, assume reasonable altitude if in activity window
                    altitude = 30.0  # Placeholder - would calculate from ephemeris
                    is_visible = altitude > 0

                    # Best viewing time (simplified - would calculate transit)
                    # Ensure best_time is timezone-aware
                    best_time = check_date.replace(hour=2, minute=0, second=0, microsecond=0)  # 2 AM UTC
                    if best_time.tzinfo is None:
                        best_time = best_time.replace(tzinfo=UTC)

                    notes = f"Magnitude {magnitude:.2f}"
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


async def get_upcoming_comets(
    location: ObserverLocation,
    months_ahead: int = 24,
    db_session: None = None,  # Deprecated, kept for compatibility
) -> list[CometVisibility]:
    """
    Get upcoming bright comets.

    Args:
        location: Observer location
        months_ahead: How many months ahead to search (default: 24)
        db_session: Deprecated parameter, kept for compatibility

    Returns:
        List of CometVisibility objects, sorted by peak date
    """
    return await get_visible_comets(location, months_ahead=months_ahead, max_magnitude=10.0)

"""
Comet Tracking and Predictions

Tracks bright comets and their visibility from observer location.
Uses Keplerian propagation from orbital elements when available.
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

from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)

__all__ = [
    "Comet",
    "CometVisibility",
    "get_known_comets",
    "get_upcoming_comets",
    "get_visible_comets",
]

# Propagation method constants
PROPAGATION_KEPLERIAN = "keplerian"
PROPAGATION_FALLBACK = "heuristic"


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
    eccentricity: float | None
    inclination_deg: float | None
    arg_perihelion_deg: float | None
    ascending_node_deg: float | None
    semi_major_axis_au: float | None
    perihelion_time: datetime | None
    absolute_magnitude_h: float | None
    slope_g: float | None
    source: str | None
    notes: str  # Additional information


@dataclass
class CometVisibility:
    """Comet visibility information for a specific date."""

    comet: Comet
    date: datetime
    magnitude: float  # Current magnitude
    altitude: float  # Altitude above horizon
    azimuth: float  # Azimuth in degrees
    is_visible: bool  # Whether comet is above horizon
    best_viewing_time: datetime | None  # Best time to view (when highest)
    notes: str
    # Enhanced fields for propagation
    ra_hours: float | None = None  # Right ascension
    dec_degrees: float | None = None  # Declination
    elongation_deg: float | None = None  # Angular separation from Sun
    helio_distance_au: float | None = None  # Distance from Sun
    geo_distance_au: float | None = None  # Distance from Earth
    propagation_method: str = PROPAGATION_FALLBACK  # "keplerian" or "heuristic"
    source: str | None = None  # Data source (e.g., "MPC Soft00Cmt")


# NOTE: Comet data is now stored in database seed files.
# See get_known_comets() which loads from database.
# To regenerate seed files, run: python scripts/create_seed_files.py
# Data from Minor Planet Center and comet observation databases


def get_known_comets(db_session: Session) -> list[Comet]:
    """
    Get list of known comets from database.

    Args:
        db_session: Database session

    Returns:
        List of Comet objects

    Raises:
        RuntimeError: If no comets found in database (seed data required)
    """
    from sqlalchemy import func, select

    from celestron_nexstar.api.core.exceptions import DatabaseError
    from celestron_nexstar.api.database.models import CometModel

    count = db_session.scalar(select(func.count(CometModel.id)))
    if count == 0:
        raise DatabaseError("No comets found in database. Please seed the database by running: nexstar data seed")

    result = db_session.execute(select(CometModel))
    models = result.scalars().all()

    return [model.to_comet() for model in models]


def _estimate_comet_magnitude_fallback(comet: Comet, date: datetime) -> float:
    """
    Estimate comet magnitude using fallback heuristic.

    Simplified model based on time from perihelion.
    Used when orbital elements are not available.

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
    if abs(days_from_perihelion) < 30:
        base_magnitude = comet.peak_magnitude
    else:
        magnitude_increase = abs(days_from_perihelion) / 10.0 * 0.1
        base_magnitude = comet.peak_magnitude + magnitude_increase

    return base_magnitude


def get_visible_comets(
    db_session: Session,
    location: ObserverLocation,
    months_ahead: int = 12,
    max_magnitude: float = 8.0,
    min_altitude_deg: float = 10.0,
    min_elongation_deg: float = 15.0,
) -> list[CometVisibility]:
    """
    Get comets visible from observer location.

    Uses Keplerian propagation from orbital elements when available,
    falling back to perihelion-based heuristics otherwise.

    Args:
        db_session: Database session
        location: Observer location
        months_ahead: How many months ahead to search (default: 12)
        max_magnitude: Maximum magnitude to include (default: 8.0)
        min_altitude_deg: Minimum altitude above horizon (default: 10.0)
        min_elongation_deg: Minimum elongation from Sun (default: 15.0)

    Returns:
        List of CometVisibility objects, sorted by brightness (brightest first)
    """

    visibilities: list[CometVisibility] = []
    now = datetime.now(UTC)
    end_date = now + timedelta(days=30 * months_ahead)

    comets = get_known_comets(db_session)

    for comet in comets:
        # Normalize comet dates
        perihelion = comet.perihelion_date
        perihelion = perihelion.replace(tzinfo=UTC) if perihelion.tzinfo is None else perihelion.astimezone(UTC)

        peak = comet.peak_date
        peak = peak.replace(tzinfo=UTC) if peak.tzinfo is None else peak.astimezone(UTC)

        # Activity window: comets visible ~90 days before to ~180 days after perihelion
        activity_start = perihelion - timedelta(days=120)
        activity_end = perihelion + timedelta(days=240)

        if activity_end < now or activity_start > end_date:
            continue

        # Check if we can use Keplerian propagation
        has_orbital_elements = (
            comet.eccentricity is not None
            and comet.inclination_deg is not None
            and comet.arg_perihelion_deg is not None
            and comet.ascending_node_deg is not None
            and comet.perihelion_time is not None
        )

        if has_orbital_elements:
            # Use Keplerian propagation
            best_visibility = _find_best_visibility_keplerian(
                comet,
                location.latitude,
                location.longitude,
                now,
                end_date,
                max_magnitude,
                min_altitude_deg,
                min_elongation_deg,
            )
            if best_visibility:
                visibilities.append(best_visibility)
        else:
            # Fallback to heuristic approach
            best_visibility = _find_best_visibility_fallback(
                comet,
                now,
                end_date,
                max_magnitude,
            )
            if best_visibility:
                visibilities.append(best_visibility)

    # Sort by magnitude (brightest first)
    visibilities.sort(key=lambda v: v.magnitude)
    return visibilities


def _find_best_visibility_keplerian(
    comet: Comet,
    observer_lat: float,
    observer_lon: float,
    start_date: datetime,
    end_date: datetime,
    max_magnitude: float,
    min_altitude_deg: float,
    min_elongation_deg: float,
) -> CometVisibility | None:
    """
    Find best visibility using Keplerian propagation.

    Samples comet position at multiple dates and returns the best visibility.
    """
    from celestron_nexstar.api.astronomy.keplerian import (
        compute_comet_magnitude,
        compute_comet_position,
    )

    best_result: tuple[datetime, float, float, float, float, float, float, float, float] | None = None

    # Sample dates: perihelion, peak, and intervals
    sample_dates = []

    # Add perihelion and peak
    perihelion = comet.perihelion_date
    perihelion = perihelion.replace(tzinfo=UTC) if perihelion.tzinfo is None else perihelion.astimezone(UTC)

    peak = comet.peak_date
    peak = peak.replace(tzinfo=UTC) if peak.tzinfo is None else peak.astimezone(UTC)

    # Add key dates
    if start_date <= perihelion <= end_date:
        sample_dates.append(perihelion)
    if start_date <= peak <= end_date:
        sample_dates.append(peak)

    # Add weekly samples within window
    current = max(start_date, perihelion - timedelta(days=90))
    window_end = min(end_date, perihelion + timedelta(days=180))

    while current <= window_end:
        if start_date <= current <= end_date:
            sample_dates.append(current)
        current += timedelta(days=7)

    # Evaluate each sample date
    for check_date in sample_dates:
        pos = compute_comet_position(comet, observer_lat, observer_lon, check_date)

        if pos is None:
            continue

        mag = compute_comet_magnitude(comet, pos.helio_distance_au, pos.geo_distance_au)

        # Check visibility criteria
        if mag <= max_magnitude and pos.altitude_deg >= min_altitude_deg and pos.elongation_deg >= min_elongation_deg:
            # Track best (brightest and highest)
            if best_result is None or mag < best_result[1]:
                best_result = (
                    check_date,
                    mag,
                    pos.altitude_deg,
                    pos.azimuth_deg,
                    pos.ra_hours,
                    pos.dec_degrees,
                    pos.elongation_deg,
                    pos.helio_distance_au,
                    pos.geo_distance_au,
                )

    if best_result is None:
        return None

    (
        best_date,
        magnitude,
        altitude,
        azimuth,
        ra_hours,
        dec_degrees,
        elongation,
        helio_dist,
        geo_dist,
    ) = best_result

    # Build notes
    notes = f"Magnitude {magnitude:.1f}"
    if magnitude < 4.0:
        notes += " - bright, easily visible to naked eye"
    elif magnitude < 6.0:
        notes += " - visible to naked eye under dark skies"
    elif magnitude < 8.0:
        notes += " - visible with binoculars"
    else:
        notes += " - requires telescope"

    notes += f" | Elongation {elongation:.0f}°"

    if comet.source:
        notes += f" | Source: {comet.source}"

    # Best viewing time (2 AM local approximation)
    best_time = best_date.replace(hour=2, minute=0, second=0, microsecond=0)

    return CometVisibility(
        comet=comet,
        date=best_date,
        magnitude=magnitude,
        altitude=altitude,
        azimuth=azimuth,
        is_visible=True,
        best_viewing_time=best_time,
        notes=notes,
        ra_hours=ra_hours,
        dec_degrees=dec_degrees,
        elongation_deg=elongation,
        helio_distance_au=helio_dist,
        geo_distance_au=geo_dist,
        propagation_method=PROPAGATION_KEPLERIAN,
        source=comet.source,
    )


def _find_best_visibility_fallback(
    comet: Comet,
    start_date: datetime,
    end_date: datetime,
    max_magnitude: float,
) -> CometVisibility | None:
    """
    Find best visibility using fallback heuristic (no orbital elements).

    Uses peak date and perihelion-based magnitude estimate.
    """
    peak = comet.peak_date
    peak = peak.replace(tzinfo=UTC) if peak.tzinfo is None else peak.astimezone(UTC)

    # Check if peak is in our window
    if not (start_date <= peak <= end_date):
        # Try perihelion instead
        perihelion = comet.perihelion_date
        perihelion = perihelion.replace(tzinfo=UTC) if perihelion.tzinfo is None else perihelion.astimezone(UTC)

        if not (start_date <= perihelion <= end_date):
            return None
        check_date = perihelion
    else:
        check_date = peak

    magnitude = _estimate_comet_magnitude_fallback(comet, check_date)

    if magnitude > max_magnitude:
        return None

    # Build notes
    notes = f"Magnitude ~{magnitude:.1f} (estimated)"
    if magnitude < 6.0:
        notes += " - potentially visible to naked eye"
    elif magnitude < 8.0:
        notes += " - visible with binoculars"

    notes += " | Position approximate (no orbital elements)"

    # Best viewing time
    best_time = check_date.replace(hour=2, minute=0, second=0, microsecond=0)

    return CometVisibility(
        comet=comet,
        date=check_date,
        magnitude=magnitude,
        altitude=30.0,  # Placeholder
        azimuth=180.0,  # Placeholder (south)
        is_visible=True,
        best_viewing_time=best_time,
        notes=notes,
        ra_hours=None,
        dec_degrees=None,
        elongation_deg=None,
        helio_distance_au=None,
        geo_distance_au=None,
        propagation_method=PROPAGATION_FALLBACK,
        source=comet.source,
    )


def get_upcoming_comets(
    db_session: Session,
    location: ObserverLocation,
    months_ahead: int = 24,
) -> list[CometVisibility]:
    """
    Get upcoming bright comets.

    Args:
        db_session: Database session
        location: Observer location
        months_ahead: How many months ahead to search (default: 24)

    Returns:
        List of CometVisibility objects, sorted by brightness
    """
    return get_visible_comets(
        db_session,
        location,
        months_ahead=months_ahead,
        max_magnitude=10.0,
        min_altitude_deg=5.0,  # Lower threshold for upcoming
        min_elongation_deg=10.0,  # Lower threshold for upcoming
    )

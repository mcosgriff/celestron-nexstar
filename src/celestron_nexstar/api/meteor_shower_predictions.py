"""
Enhanced Meteor Shower Predictions

Provides moon phase-adjusted predictions, best viewing windows, and hourly rate estimates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from .meteor_showers import MeteorShower, get_radiant_position
from .solar_system import MoonInfo, get_moon_info


if TYPE_CHECKING:
    from .observer import ObserverLocation

logger = logging.getLogger(__name__)

__all__ = [
    "MeteorShowerPrediction",
    "calculate_moon_adjusted_zhr",
    "get_best_viewing_windows",
    "get_enhanced_meteor_predictions",
]


@dataclass
class MeteorShowerPrediction:
    """Enhanced meteor shower prediction with moon phase and viewing conditions."""

    shower: MeteorShower
    date: datetime
    zhr_peak: int  # Base ZHR at peak
    zhr_adjusted: float  # Moon-phase adjusted ZHR
    moon_illumination: float  # Moon illumination (0.0-1.0)
    moon_altitude: float  # Moon altitude at peak time
    radiant_altitude: float  # Radiant altitude at peak time
    best_viewing_start: datetime | None  # Best viewing window start
    best_viewing_end: datetime | None  # Best viewing window end
    viewing_quality: str  # "excellent", "good", "fair", "poor"
    notes: str


def calculate_moon_adjusted_zhr(base_zhr: int, moon_illumination: float, moon_altitude: float) -> float:
    """
    Calculate moon-phase adjusted ZHR.

    Moonlight significantly reduces visible meteor rates.

    Args:
        base_zhr: Base ZHR under ideal conditions
        moon_illumination: Moon illumination (0.0-1.0)
        moon_altitude: Moon altitude above horizon (degrees)

    Returns:
        Adjusted ZHR accounting for moonlight
    """
    # If moon is below horizon, no impact
    if moon_altitude < 0:
        return float(base_zhr)

    # Moon impact increases with illumination and altitude
    # Full moon at high altitude can reduce rates by 80-90%
    moon_factor = moon_illumination * (1.0 - abs(moon_altitude) / 90.0)  # 0.0 to 1.0

    # Reduction factor: 0.1 (90% reduction) at full moon overhead, 1.0 (no reduction) at new moon
    reduction_factor = 1.0 - (moon_factor * 0.9)

    # Minimum 10% of base ZHR (even with full moon, some bright meteors visible)
    adjusted_zhr = base_zhr * max(0.1, reduction_factor)

    return adjusted_zhr


def get_enhanced_meteor_predictions(
    location: ObserverLocation,
    months_ahead: int = 12,
) -> list[MeteorShowerPrediction]:
    """
    Get enhanced meteor shower predictions with moon phase adjustments.

    Args:
        location: Observer location
        months_ahead: How many months ahead to predict (default: 12)

    Returns:
        List of MeteorShowerPrediction objects, sorted by date
    """
    predictions = []
    now = datetime.now(UTC)
    end_date = now + timedelta(days=30 * months_ahead)

    # This function is sync but calls async get_all_meteor_showers
    # We need to handle this properly
    import asyncio

    from .models import get_db_session

    async def _get_showers() -> list[MeteorShower]:
        async with get_db_session() as db_session:
            from .meteor_showers import get_all_meteor_showers

            return await get_all_meteor_showers(db_session)

    all_showers = asyncio.run(_get_showers())

    # For each shower, find peak dates in the forecast period
    current_date = now
    while current_date <= end_date:
        year = current_date.year

        for shower in all_showers:
            # Calculate peak date for this year
            peak_date = datetime(year, shower.peak_month, shower.peak_day, 0, 0, 0, tzinfo=UTC)

            # Check if this peak is in our forecast window
            if now <= peak_date <= end_date:
                # Get moon info at peak time (use midnight for peak day)
                moon_info = get_moon_info(location.latitude, location.longitude, peak_date)

                if moon_info:
                    # Get radiant position at peak time
                    radiant_alt, _radiant_az = get_radiant_position(
                        shower, location.latitude, location.longitude, peak_date
                    )

                    # Calculate adjusted ZHR
                    zhr_adjusted = calculate_moon_adjusted_zhr(
                        shower.zhr_peak, moon_info.illumination, moon_info.altitude_deg
                    )

                    # Determine viewing quality
                    if moon_info.illumination < 0.1 and moon_info.altitude_deg < 10:
                        viewing_quality = "excellent"
                        notes = "New moon - ideal viewing conditions"
                    elif moon_info.illumination < 0.3 and moon_info.altitude_deg < 20:
                        viewing_quality = "good"
                        notes = "Minimal moonlight interference"
                    elif moon_info.illumination < 0.6:
                        viewing_quality = "fair"
                        notes = "Moderate moonlight will reduce visible meteors"
                    else:
                        viewing_quality = "poor"
                        notes = "Bright moon will significantly reduce visible meteors"

                    # Find best viewing window (when radiant is high and moon is low)
                    best_start, best_end = _find_best_viewing_window(shower, location, peak_date, moon_info)

                    predictions.append(
                        MeteorShowerPrediction(
                            shower=shower,
                            date=peak_date,
                            zhr_peak=shower.zhr_peak,
                            zhr_adjusted=zhr_adjusted,
                            moon_illumination=moon_info.illumination,
                            moon_altitude=moon_info.altitude_deg,
                            radiant_altitude=radiant_alt,
                            best_viewing_start=best_start,
                            best_viewing_end=best_end,
                            viewing_quality=viewing_quality,
                            notes=notes,
                        )
                    )

        # Move to next year
        current_date = datetime(year + 1, 1, 1, tzinfo=UTC)

    # Sort by date
    predictions.sort(key=lambda p: p.date)
    return predictions


def _find_best_viewing_window(
    shower: MeteorShower,
    location: ObserverLocation,
    peak_date: datetime,
    moon_info: MoonInfo | None,
) -> tuple[datetime | None, datetime | None]:
    """
    Find best viewing window when radiant is high and moon is low.

    Args:
        shower: Meteor shower
        location: Observer location
        peak_date: Peak date
        moon_info: Moon information

    Returns:
        Tuple of (start_time, end_time) or (None, None) if not found
    """
    # For now, return None - can be enhanced with hourly calculations
    # Best viewing is typically after midnight when radiant is highest
    return None, None


def get_best_viewing_windows(
    location: ObserverLocation,
    months_ahead: int = 12,
    min_quality: str = "good",
) -> list[MeteorShowerPrediction]:
    """
    Get meteor showers with best viewing conditions.

    Args:
        location: Observer location
        months_ahead: How many months ahead to search
        min_quality: Minimum viewing quality ("excellent", "good", "fair", "poor")

    Returns:
        List of predictions filtered by quality
    """
    all_predictions = get_enhanced_meteor_predictions(location, months_ahead=months_ahead)

    quality_order = {"excellent": 0, "good": 1, "fair": 2, "poor": 3}
    min_quality_level = quality_order.get(min_quality, 1)

    filtered = [p for p in all_predictions if quality_order.get(p.viewing_quality, 3) <= min_quality_level]

    return filtered

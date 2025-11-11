"""
Zodiacal Light and Gegenschein Predictions

Predicts best viewing times for zodiacal light (pre-dawn/post-dusk) and gegenschein.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from .solar_system import get_sun_info


if TYPE_CHECKING:
    from .observer import ObserverLocation

logger = logging.getLogger(__name__)

__all__ = [
    "ZodiacalLightWindow",
    "get_gegenschein_windows",
    "get_zodiacal_light_windows",
]


@dataclass
class ZodiacalLightWindow:
    """Zodiacal light viewing window information."""

    date: datetime
    window_type: str  # "evening" or "morning"
    start_time: datetime  # Window start
    end_time: datetime  # Window end
    sun_altitude_start: float  # Sun altitude at window start
    sun_altitude_end: float  # Sun altitude at window end
    viewing_quality: str  # "excellent", "good", "fair", "poor"
    notes: str


def get_zodiacal_light_windows(
    location: ObserverLocation,
    months_ahead: int = 6,
) -> list[ZodiacalLightWindow]:
    """
    Get zodiacal light viewing windows.

    Zodiacal light is best seen:
    - Evening: 60-90 minutes after sunset (spring)
    - Morning: 60-90 minutes before sunrise (autumn)
    - Requires dark skies (Bortle 3 or better)
    - Best when moon is below horizon

    Args:
        location: Observer location
        months_ahead: How many months ahead to search (default: 6)

    Returns:
        List of ZodiacalLightWindow objects, sorted by date
    """
    windows = []
    now = datetime.now(UTC)
    end_date = now + timedelta(days=30 * months_ahead)

    current_date = now
    while current_date <= end_date:
        # Check evening window (spring - March to May best)
        sun_info_evening = get_sun_info(location.latitude, location.longitude, current_date)
        if sun_info_evening and sun_info_evening.sunset_time:
            # Evening window: 60-90 minutes after sunset
            window_start = sun_info_evening.sunset_time + timedelta(minutes=60)
            window_end = sun_info_evening.sunset_time + timedelta(minutes=90)

            # Check if window is in our search period
            if now <= window_start <= end_date:
                # Determine quality based on season and moon
                month = current_date.month
                if 3 <= month <= 5:  # Spring - best for evening zodiacal light
                    quality = "excellent"
                    notes = "Spring evening - optimal for zodiacal light"
                elif 6 <= month <= 8:  # Summer
                    quality = "good"
                    notes = "Summer evening - good viewing"
                else:
                    quality = "fair"
                    notes = "Evening viewing - less optimal season"

                windows.append(
                    ZodiacalLightWindow(
                        date=current_date,
                        window_type="evening",
                        start_time=window_start,
                        end_time=window_end,
                        sun_altitude_start=-12.0,  # Approximate
                        sun_altitude_end=-18.0,
                        viewing_quality=quality,
                        notes=notes,
                    )
                )

        # Check morning window (autumn - September to November best)
        sun_info_morning = get_sun_info(location.latitude, location.longitude, current_date)
        if sun_info_morning and sun_info_morning.sunrise_time:
            # Morning window: 60-90 minutes before sunrise
            window_start = sun_info_morning.sunrise_time - timedelta(minutes=90)
            window_end = sun_info_morning.sunrise_time - timedelta(minutes=60)

            # Check if window is in our search period
            if now <= window_start <= end_date:
                # Determine quality based on season
                month = current_date.month
                if 9 <= month <= 11:  # Autumn - best for morning zodiacal light
                    quality = "excellent"
                    notes = "Autumn morning - optimal for zodiacal light"
                elif month >= 12 or month <= 2:  # Winter
                    quality = "good"
                    notes = "Winter morning - good viewing"
                else:
                    quality = "fair"
                    notes = "Morning viewing - less optimal season"

                windows.append(
                    ZodiacalLightWindow(
                        date=current_date,
                        window_type="morning",
                        start_time=window_start,
                        end_time=window_end,
                        sun_altitude_start=-18.0,
                        sun_altitude_end=-12.0,
                        viewing_quality=quality,
                        notes=notes,
                    )
                )

        # Move to next day
        current_date += timedelta(days=1)

    # Sort by date
    windows.sort(key=lambda w: w.start_time)
    return windows


def get_gegenschein_windows(
    location: ObserverLocation,
    months_ahead: int = 6,
) -> list[ZodiacalLightWindow]:
    """
    Get gegenschein viewing windows.

    Gegenschein is best seen:
    - Around midnight when anti-sun point is highest
    - Requires very dark skies (Bortle 2 or better)
    - Best when moon is below horizon
    - Visible year-round but best in autumn/winter

    Args:
        location: Observer location
        months_ahead: How many months ahead to search (default: 6)

    Returns:
        List of ZodiacalLightWindow objects, sorted by date
    """
    windows = []
    now = datetime.now(UTC)
    end_date = now + timedelta(days=30 * months_ahead)

    current_date = now
    while current_date <= end_date:
        # Gegenschein is best around midnight when anti-sun is highest
        # Use local midnight
        midnight = current_date.replace(hour=0, minute=0, second=0, microsecond=0)
        if midnight < current_date:
            midnight += timedelta(days=1)

        if now <= midnight <= end_date:
            # Determine quality based on season
            month = midnight.month
            if 9 <= month <= 11 or month >= 12 or month <= 2:  # Autumn/Winter
                quality = "excellent"
                notes = "Autumn/Winter - optimal for gegenschein"
            else:
                quality = "good"
                notes = "Spring/Summer - good viewing"

            # Window is around midnight ± 2 hours
            window_start = midnight - timedelta(hours=2)
            window_end = midnight + timedelta(hours=2)

            windows.append(
                ZodiacalLightWindow(
                    date=midnight,
                    window_type="midnight",
                    start_time=window_start,
                    end_time=window_end,
                    sun_altitude_start=-90.0,  # Anti-sun point
                    sun_altitude_end=-90.0,
                    viewing_quality=quality,
                    notes=notes,
                )
            )

        # Move to next day
        current_date += timedelta(days=1)

    # Sort by date
    windows.sort(key=lambda w: w.start_time)
    return windows

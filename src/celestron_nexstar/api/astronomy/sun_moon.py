"""
Sun and Moon Time Calculations

Convenience functions for calculating sun and moon times.
"""

from __future__ import annotations

from datetime import datetime

from celestron_nexstar.api.astronomy.solar_system import get_sun_info


def calculate_sun_times(lat: float, lon: float, dt: datetime | None = None) -> dict[str, datetime | None]:
    """
    Calculate sunset and sunrise times for a given location and date.

    Args:
        lat: Observer latitude in degrees
        lon: Observer longitude in degrees
        dt: Datetime to calculate for (default: now)

    Returns:
        Dictionary with "sunset" and "sunrise" keys containing datetime objects.
        If times cannot be calculated, returns None values.
    """
    sun_info = get_sun_info(lat, lon, dt)

    if sun_info is None:
        # Return None values if calculation fails
        return {"sunset": None, "sunrise": None}

    return {
        "sunset": sun_info.sunset_time,
        "sunrise": sun_info.sunrise_time,
    }

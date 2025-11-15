"""
Clear Sky Chart Calculations

Functions for calculating transparency, darkness, and other observing conditions
for Clear Sky Chart-style displays. These functions are designed to be reusable
across CLI, TUI, and other interfaces.
"""

from __future__ import annotations

from datetime import UTC, datetime

from celestron_nexstar.api.astronomy.solar_system import get_moon_info, get_sun_info
from celestron_nexstar.api.location.light_pollution import LightPollutionData


def calculate_transparency(
    cloud_cover_percent: float | None,
    humidity_percent: float | None,
) -> str:
    """
    Calculate transparency rating from cloud cover and humidity.

    Transparency is a measure of atmospheric clarity, affected by clouds and humidity.
    Lower humidity generally means better transparency.

    Args:
        cloud_cover_percent: Cloud cover percentage (0-100)
        humidity_percent: Humidity percentage (0-100)

    Returns:
        Transparency rating: "transparent", "above_average", "average",
        "below_average", "poor", or "too_cloudy"
    """
    # If very cloudy, transparency is poor regardless of humidity
    if cloud_cover_percent is not None and cloud_cover_percent > 30:
        return "too_cloudy"

    # Calculate transparency based on humidity
    if humidity_percent is None:
        return "average"

    if humidity_percent < 30:
        return "transparent"
    elif humidity_percent < 50:
        return "above_average"
    elif humidity_percent < 70:
        return "average"
    elif humidity_percent < 85:
        return "below_average"
    else:
        return "poor"


def calculate_darkness(
    sun_altitude_deg: float | None,
    moon_illumination: float | None,
    moon_altitude_deg: float | None,
    base_limiting_magnitude: float,
) -> float | None:
    """
    Calculate limiting magnitude (darkness) at zenith.

    Takes into account:
    - Sun altitude (twilight phases)
    - Moon phase and altitude (moonlight brightens the sky)
    - Base limiting magnitude from light pollution

    Args:
        sun_altitude_deg: Sun altitude in degrees (negative below horizon)
        moon_illumination: Moon illumination (0.0 = new moon, 1.0 = full moon)
        moon_altitude_deg: Moon altitude in degrees (None if moon not visible)
        base_limiting_magnitude: Base limiting magnitude from light pollution data

    Returns:
        Limiting magnitude at zenith, or None if daytime
    """
    if sun_altitude_deg is None:
        return None

    # Daytime - no darkness
    if sun_altitude_deg >= 0:
        return 0.0

    # Civil twilight (sun between 0 and -6 degrees)
    if sun_altitude_deg >= -6:
        return 2.0

    # Nautical twilight (sun between -6 and -12 degrees)
    if sun_altitude_deg >= -12:
        return 3.0

    # Astronomical twilight (sun between -12 and -18 degrees)
    if sun_altitude_deg >= -18:
        # Slightly reduced darkness during twilight
        darkness_mag = base_limiting_magnitude - 0.5
        if moon_illumination is not None:
            darkness_mag = base_limiting_magnitude - 1.0
        return darkness_mag

    # Dark sky (sun below -18 degrees) - astronomical night
    darkness_mag = base_limiting_magnitude

    # Apply moon brightness reduction if moon is up
    if moon_illumination is not None and moon_altitude_deg is not None and moon_altitude_deg > 0:
        # Full moon reduces limiting magnitude by ~3-4 mag
        # Scale by illumination and altitude
        moon_reduction = moon_illumination * 3.5 * (moon_altitude_deg / 90.0)
        darkness_mag = base_limiting_magnitude - moon_reduction

    return darkness_mag


def calculate_chart_data_point(
    forecast_timestamp: datetime,
    cloud_cover_percent: float | None,
    humidity_percent: float | None,
    wind_speed_mph: float | None,
    temperature_f: float | None,
    seeing_score: float | None,
    observer_lat: float,
    observer_lon: float,
    light_pollution_data: LightPollutionData,
) -> dict[str, object]:
    """
    Calculate a single data point for Clear Sky Chart.

    Combines weather forecast data with astronomical calculations to produce
    a complete observing conditions data point.

    Args:
        forecast_timestamp: Timestamp for the forecast point
        cloud_cover_percent: Cloud cover percentage
        humidity_percent: Humidity percentage
        wind_speed_mph: Wind speed in mph
        temperature_f: Temperature in Fahrenheit
        seeing_score: Seeing score (0-100)
        observer_lat: Observer latitude
        observer_lon: Observer longitude
        light_pollution_data: Light pollution data for the location

    Returns:
        Dictionary with calculated values:
        - timestamp: datetime
        - cloud_cover: float (0-100)
        - transparency: str (rating)
        - seeing: float | None (0-100, None if too cloudy)
        - darkness: float | None (limiting magnitude)
        - wind: float | None (mph)
        - humidity: float | None (percent)
        - temperature: float | None (Fahrenheit)
    """
    # Ensure timestamp is timezone-aware (UTC)
    if forecast_timestamp.tzinfo is None:
        forecast_ts = forecast_timestamp.replace(tzinfo=UTC)
    elif forecast_timestamp.tzinfo != UTC:
        forecast_ts = forecast_timestamp.astimezone(UTC)
    else:
        forecast_ts = forecast_timestamp

    # Calculate transparency
    transparency = calculate_transparency(cloud_cover_percent, humidity_percent)

    # Get sun and moon info
    sun_info = get_sun_info(observer_lat, observer_lon, forecast_ts)
    moon_info = get_moon_info(observer_lat, observer_lon, forecast_ts)

    # Calculate darkness
    sun_alt = sun_info.altitude_deg if sun_info else None
    moon_illum = moon_info.illumination if moon_info else None
    moon_alt = moon_info.altitude_deg if moon_info else None
    base_mag = light_pollution_data.naked_eye_limiting_magnitude

    darkness_mag = calculate_darkness(sun_alt, moon_illum, moon_alt, base_mag)

    # Determine if seeing is "too cloudy to forecast" (>80% cloud cover)
    seeing_value: float | None = seeing_score
    if cloud_cover_percent is not None and cloud_cover_percent > 80:
        seeing_value = None  # Mark as too cloudy

    return {
        "timestamp": forecast_ts,
        "cloud_cover": cloud_cover_percent or 100.0,
        "transparency": transparency,
        "seeing": seeing_value,
        "darkness": darkness_mag,
        "wind": wind_speed_mph,
        "humidity": humidity_percent,
        "temperature": temperature_f,
    }

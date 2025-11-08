"""
Weather API Integration

Provides weather data for observing conditions and visibility warnings.
Uses OpenWeatherMap API (free tier available).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib import error, request


if TYPE_CHECKING:
    from ...api.observer import ObserverLocation

logger = logging.getLogger(__name__)


@dataclass
class WeatherData:
    """Weather information for observing conditions."""

    temperature_c: float | None = None
    humidity_percent: float | None = None
    cloud_cover_percent: float | None = None
    wind_speed_ms: float | None = None
    visibility_km: float | None = None
    condition: str | None = None  # e.g., "Clear", "Cloudy", "Rain"
    last_updated: str | None = None
    error: str | None = None


def get_weather_api_key() -> str | None:
    """
    Get OpenWeatherMap API key from environment variable.

    Returns:
        API key if set, None otherwise
    """
    return os.environ.get("OPENWEATHER_API_KEY") or os.environ.get("OWM_API_KEY")


def fetch_weather(location: ObserverLocation) -> WeatherData:
    """
    Fetch current weather data for the observer location.

    Uses OpenWeatherMap API (requires free API key).

    Args:
        location: Observer location with latitude and longitude

    Returns:
        WeatherData with current conditions, or error message if failed
    """
    api_key = get_weather_api_key()
    if not api_key:
        return WeatherData(error="No API key set. Set OPENWEATHER_API_KEY environment variable.")

    try:
        # OpenWeatherMap Current Weather API
        url = (
            f"https://api.openweathermap.org/data/2.5/weather"
            f"?lat={location.latitude}&lon={location.longitude}"
            f"&appid={api_key}&units=metric"
        )

        with request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())

        # Extract relevant weather information
        main = data.get("main", {})
        weather = data.get("weather", [{}])[0]
        clouds = data.get("clouds", {})
        wind = data.get("wind", {})
        visibility = data.get("visibility")

        return WeatherData(
            temperature_c=main.get("temp"),
            humidity_percent=main.get("humidity"),
            cloud_cover_percent=clouds.get("all"),
            wind_speed_ms=wind.get("speed"),
            visibility_km=visibility / 1000.0 if visibility else None,  # Convert m to km
            condition=weather.get("main"),
            last_updated="now",
        )

    except error.HTTPError as e:
        if e.code == 401:
            return WeatherData(error="Invalid API key")
        elif e.code == 404:
            return WeatherData(error="Location not found")
        else:
            return WeatherData(error=f"API error: {e.code}")
    except error.URLError as e:
        return WeatherData(error=f"Network error: {e.reason}")
    except (KeyError, ValueError, TypeError) as e:
        logger.exception("Error parsing weather data")
        return WeatherData(error=f"Data parsing error: {e}")
    except Exception as e:
        logger.exception("Unexpected error fetching weather")
        return WeatherData(error=f"Error: {e}")


def assess_observing_conditions(weather: WeatherData) -> tuple[str, str]:
    """
    Assess observing conditions based on weather data.

    Args:
        weather: Weather data to assess

    Returns:
        Tuple of (status, warning_message)
        Status: "excellent", "good", "fair", "poor", "unavailable"
        Warning: Human-readable warning message
    """
    if weather.error:
        return ("unavailable", weather.error)

    if weather.cloud_cover_percent is None:
        return ("unavailable", "Cloud data unavailable")

    warnings: list[str] = []

    # Cloud cover assessment
    if weather.cloud_cover_percent >= 80:
        status = "poor"
        warnings.append(f"Very cloudy ({weather.cloud_cover_percent:.0f}% cover)")
    elif weather.cloud_cover_percent >= 50:
        status = "fair"
        warnings.append(f"Partly cloudy ({weather.cloud_cover_percent:.0f}% cover)")
    elif weather.cloud_cover_percent >= 20:
        status = "good"
        warnings.append(f"Some clouds ({weather.cloud_cover_percent:.0f}% cover)")
    else:
        status = "excellent"
        if weather.cloud_cover_percent > 0:
            warnings.append(f"Clear skies ({weather.cloud_cover_percent:.0f}% cover)")

    # Humidity assessment (high humidity = poor transparency)
    if weather.humidity_percent is not None:
        if weather.humidity_percent >= 90:
            if status == "excellent":
                status = "good"
            elif status == "good":
                status = "fair"
            warnings.append(f"High humidity ({weather.humidity_percent:.0f}%)")
        elif weather.humidity_percent >= 80:
            if status == "excellent":
                status = "good"
            warnings.append(f"Moderate humidity ({weather.humidity_percent:.0f}%)")

    # Visibility assessment
    if weather.visibility_km is not None:
        if weather.visibility_km < 5:
            if status in ("excellent", "good"):
                status = "fair"
            warnings.append(f"Poor visibility ({weather.visibility_km:.1f} km)")
        elif weather.visibility_km < 10:
            if status == "excellent":
                status = "good"
            warnings.append(f"Reduced visibility ({weather.visibility_km:.1f} km)")

    # Wind assessment (high wind = poor seeing)
    if weather.wind_speed_ms is not None:
        wind_kmh = weather.wind_speed_ms * 3.6  # Convert m/s to km/h
        if wind_kmh > 40:
            if status in ("excellent", "good"):
                status = "fair"
            warnings.append(f"Strong wind ({wind_kmh:.0f} km/h)")
        elif wind_kmh > 25:
            if status == "excellent":
                status = "good"
            warnings.append(f"Moderate wind ({wind_kmh:.0f} km/h)")

    # Precipitation/condition warnings
    if weather.condition:
        condition_lower = weather.condition.lower()
        if any(x in condition_lower for x in ["rain", "drizzle", "snow", "storm", "thunder"]):
            status = "poor"
            warnings.append(f"Precipitation: {weather.condition}")
        elif "fog" in condition_lower or "mist" in condition_lower:
            if status in ("excellent", "good"):
                status = "fair"
            warnings.append(f"Reduced visibility: {weather.condition}")

    warning_msg = "; ".join(warnings) if warnings else "Good observing conditions"
    return (status, warning_msg)

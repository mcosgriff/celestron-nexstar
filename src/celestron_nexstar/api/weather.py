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
    from .observer import ObserverLocation

logger = logging.getLogger(__name__)


@dataclass
class WeatherData:
    """Weather information for observing conditions."""

    temperature_c: float | None = None  # In Fahrenheit when units=imperial
    dew_point_f: float | None = None  # Dew point in Fahrenheit
    humidity_percent: float | None = None
    cloud_cover_percent: float | None = None
    wind_speed_ms: float | None = None  # In mph when units=imperial
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
            f"&appid={api_key}&units=imperial"
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
            temperature_c=main.get("temp"),  # In Fahrenheit when units=imperial
            dew_point_f=main.get("dew_point"),  # In Fahrenheit when units=imperial
            humidity_percent=main.get("humidity"),
            cloud_cover_percent=clouds.get("all"),
            wind_speed_ms=wind.get("speed"),  # In mph when units=imperial
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
        # Don't add warning for essentially clear skies (< 20% cloud cover)
        # Only mention if there are some clouds (10-20%)
        if weather.cloud_cover_percent >= 10:
            warnings.append(f"Mostly clear ({weather.cloud_cover_percent:.0f}% cloud cover)")

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
        # API returns mph when units=imperial (despite field name)
        # Use directly as mph for display
        wind_mph = weather.wind_speed_ms  # Already in mph when units=imperial
        if wind_mph > 25:  # ~40 km/h
            if status in ("excellent", "good"):
                status = "fair"
            warnings.append(f"Strong wind ({wind_mph:.0f} mph)")
        elif wind_mph > 15:  # ~25 km/h
            if status == "excellent":
                status = "good"
            warnings.append(f"Moderate wind ({wind_mph:.0f} mph)")

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


def calculate_seeing_conditions(
    weather: WeatherData, temperature_change_per_hour: float = 0.0
) -> float:
    """
    Calculate astronomical seeing conditions score (0-100).

    Uses a weighted algorithm considering:
    - Temperature-Dew Point Spread (30% weight)
    - Wind Speed (30% weight)
    - Humidity Impact (20% weight)
    - Temperature Stability (20% weight)

    Args:
        weather: Weather data
        temperature_change_per_hour: Rate of temperature change per hour (degrees F)
                                    Default 0.0 if historical data unavailable

    Returns:
        Seeing score from 0-100 (higher is better)
    """
    if weather.error or weather.temperature_c is None:
        return 50.0  # Default score if data unavailable

    total_score = 0.0

    # 1. Temperature-Dew Point Spread (30% weight)
    if weather.temperature_c is not None and weather.dew_point_f is not None:
        temp_spread = weather.temperature_c - weather.dew_point_f
        # Optimal spread: 15-30°F = excellent (30 points)
        # Spread < 5°F = poor (0 points)
        # Spread > 30°F = still good but not better (30 points)
        if temp_spread >= 30:
            spread_score = 30.0
        elif temp_spread >= 15:
            spread_score = 30.0
        elif temp_spread >= 10:
            spread_score = 20.0 + (temp_spread - 10) * 2.0  # 20-30 points
        elif temp_spread >= 5:
            spread_score = 10.0 + (temp_spread - 5) * 2.0  # 10-20 points
        else:
            spread_score = temp_spread * 2.0  # 0-10 points
        total_score += spread_score
    else:
        # If dew point unavailable, use default
        total_score += 15.0

    # 2. Wind Speed (30% weight)
    if weather.wind_speed_ms is not None:
        wind_mph = weather.wind_speed_ms  # Already in mph when units=imperial
        # Optimal: 5-10 mph = excellent (30 points)
        # Below 5 mph: insufficient mixing (reduced score)
        # Above 10 mph: turbulence increases (reduced score)
        # Above 20 mph: poor conditions (0 points)
        if 5.0 <= wind_mph <= 10.0:
            wind_score = 30.0
        elif wind_mph < 5.0:
            # Below 5 mph: score reduces linearly
            wind_score = wind_mph * 6.0  # 0-30 points
        elif wind_mph <= 15.0:
            # 10-15 mph: score reduces gradually
            wind_score = 30.0 - (wind_mph - 10.0) * 3.0  # 30-15 points
        elif wind_mph <= 20.0:
            # 15-20 mph: score reduces more sharply
            wind_score = 15.0 - (wind_mph - 15.0) * 3.0  # 15-0 points
        else:
            wind_score = 0.0
        total_score += wind_score
    else:
        total_score += 15.0

    # 3. Humidity Impact (20% weight)
    if weather.humidity_percent is not None:
        # Lower humidity = better seeing
        # 0-30% = excellent (20 points)
        # 30-60% = good (15 points)
        # 60-80% = fair (10 points)
        # 80-100% = poor (0-5 points)
        if weather.humidity_percent <= 30:
            humidity_score = 20.0
        elif weather.humidity_percent <= 60:
            humidity_score = 20.0 - (weather.humidity_percent - 30) * (5.0 / 30.0)  # 20-15 points
        elif weather.humidity_percent <= 80:
            humidity_score = 15.0 - (weather.humidity_percent - 60) * (5.0 / 20.0)  # 15-10 points
        else:
            humidity_score = 10.0 - (weather.humidity_percent - 80) * (10.0 / 20.0)  # 10-0 points
        total_score += max(0.0, humidity_score)
    else:
        total_score += 10.0

    # 4. Temperature Stability (20% weight)
    # Measures rate of temperature change per hour
    # Smaller changes = more stable air = better seeing
    # Each degree F per hour reduces score
    if abs(temperature_change_per_hour) <= 0.5:
        stability_score = 20.0  # Very stable
    elif abs(temperature_change_per_hour) <= 1.0:
        stability_score = 18.0
    elif abs(temperature_change_per_hour) <= 2.0:
        stability_score = 15.0
    elif abs(temperature_change_per_hour) <= 3.0:
        stability_score = 10.0
    elif abs(temperature_change_per_hour) <= 5.0:
        stability_score = 5.0
    else:
        stability_score = 0.0  # Rapid changes = unstable
    total_score += stability_score

    # Ensure score is between 0-100
    return max(0.0, min(100.0, total_score))

"""
Weather API Integration

Provides weather data for observing conditions and visibility warnings.
Uses Open-Meteo API (free, no API key required).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING


try:
    import numpy as np
    import openmeteo_requests
    import requests_cache
    from retry_requests import retry

    OPENMETEO_AVAILABLE = True
except ImportError:
    OPENMETEO_AVAILABLE = False
    np = None  # type: ignore[assignment]


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


@dataclass
class HourlySeeingForecast:
    """Hourly seeing conditions forecast."""

    timestamp: datetime
    seeing_score: float  # 0-100
    temperature_f: float | None
    dew_point_f: float | None
    humidity_percent: float | None
    wind_speed_mph: float | None
    cloud_cover_percent: float | None


def calculate_dew_point_fahrenheit(temp_f: float, humidity_percent: float) -> float:
    """
    Calculate dew point from temperature and humidity using Magnus formula.

    Args:
        temp_f: Temperature in Fahrenheit
        humidity_percent: Relative humidity as percentage (0-100)

    Returns:
        Dew point in Fahrenheit
    """
    import math

    # Convert to Celsius for calculation
    temp_c = (temp_f - 32.0) * 5.0 / 9.0
    humidity = humidity_percent / 100.0

    # Magnus formula constants
    a = 17.27
    b = 237.7

    # Calculate dew point in Celsius
    alpha = ((a * temp_c) / (b + temp_c)) + math.log(humidity)
    dew_point_c = (b * alpha) / (a - alpha)

    # Convert back to Fahrenheit
    dew_point_f = (dew_point_c * 9.0 / 5.0) + 32.0

    return dew_point_f


def get_weather_api_key() -> str | None:
    """
    Get OpenWeatherMap API key from environment variable (deprecated - kept for backward compatibility).

    Returns:
        API key if set, None otherwise
    """
    return os.environ.get("OPENWEATHER_API_KEY") or os.environ.get("OWM_API_KEY")


def fetch_weather(location: ObserverLocation) -> WeatherData:
    """
    Fetch current weather data for the observer location.

    Uses Open-Meteo API (free, no API key required).

    Args:
        location: Observer location with latitude and longitude

    Returns:
        WeatherData with current conditions, or error message if failed
    """
    if not OPENMETEO_AVAILABLE:
        return WeatherData(
            error="openmeteo-requests library not available. Install with: pip install openmeteo-requests"
        )

    try:
        # Setup the Open-Meteo API client with cache and retry on error
        cache_dir = Path.home() / ".cache" / "celestron-nexstar"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_session = requests_cache.CachedSession(str(cache_dir / "openmeteo_cache"), expire_after=3600)
        retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
        openmeteo = openmeteo_requests.Client(session=retry_session)

        # Get current weather from Open-Meteo
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "current": [
                "temperature_2m",
                "relative_humidity_2m",
                "cloud_cover",
                "wind_speed_10m",
                "weather_code",
            ],
            "hourly": [
                "temperature_2m",
                "dew_point_2m",
                "relative_humidity_2m",
                "cloud_cover",
                "wind_speed_10m",
            ],
            "timezone": "auto",
            "wind_speed_unit": "mph",
            "temperature_unit": "fahrenheit",
            "forecast_days": 1,  # Only need current + a few hours for dew point
        }

        responses = openmeteo.weather_api(url, params=params)
        response = responses[0]

        # Get current weather
        current = response.Current()
        current_temperature_2m = current.Variables(0).Value()
        current_relative_humidity_2m = current.Variables(1).Value()
        current_cloud_cover = current.Variables(2).Value()
        current_wind_speed_10m = current.Variables(3).Value()
        weather_code = current.Variables(4).Value()

        # Get hourly data for dew point (first hour)
        hourly = response.Hourly()
        hourly_dew_point_2m = hourly.Variables(1).ValuesAsNumpy()

        # Extract values (handle NaN)
        def safe_float(value: float) -> float | None:
            """Convert value to float, returning None if NaN."""
            if np is not None and np.isnan(value):
                return None
            try:
                return float(value)
            except (ValueError, TypeError):
                return None

        temp_f = safe_float(current_temperature_2m)
        humidity = safe_float(current_relative_humidity_2m)
        cloud_cover = safe_float(current_cloud_cover)
        wind_speed_mph = safe_float(current_wind_speed_10m)
        dew_point_f = safe_float(hourly_dew_point_2m[0]) if len(hourly_dew_point_2m) > 0 else None

        # If dew point not available, calculate from temp/humidity
        if dew_point_f is None and temp_f is not None and humidity is not None:
            dew_point_f = calculate_dew_point_fahrenheit(temp_f, humidity)

        # Map weather code to condition string (WMO Weather interpretation codes)
        condition = None
        if weather_code is not None:
            code = int(weather_code)
            if code == 0:
                condition = "Clear"
            elif code in (1, 2, 3):
                condition = "Partly Cloudy"
            elif code in (45, 48):
                condition = "Foggy"
            elif code in (51, 53, 55, 56, 57):
                condition = "Drizzle"
            elif code in (61, 63, 65, 66, 67):
                condition = "Rain"
            elif code in (71, 73, 75, 77):
                condition = "Snow"
            elif code in (80, 81, 82):
                condition = "Rain Showers"
            elif code in (85, 86):
                condition = "Snow Showers"
            elif code in (95, 96, 99):
                condition = "Thunderstorm"
            else:
                condition = "Cloudy"

        return WeatherData(
            temperature_c=temp_f,  # In Fahrenheit when units=imperial
            dew_point_f=dew_point_f,
            humidity_percent=humidity,
            cloud_cover_percent=cloud_cover,
            wind_speed_ms=wind_speed_mph,  # Field name is misleading, but value is in mph
            visibility_km=None,  # Open-Meteo doesn't provide visibility in free tier
            condition=condition,
            last_updated="now",
        )

    except Exception as e:
        logger.exception("Error fetching weather from Open-Meteo")
        return WeatherData(error=f"Error fetching weather: {e}")


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


def calculate_seeing_conditions(weather: WeatherData, temperature_change_per_hour: float = 0.0) -> float:
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
        if temp_spread >= 30 or temp_spread >= 15:
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


def fetch_hourly_weather_forecast(location: ObserverLocation, hours: int = 24) -> list[HourlySeeingForecast]:
    """
    Fetch hourly weather forecast and calculate seeing conditions for each hour.

    Uses database cache first, then Open-Meteo API if data is stale or missing.
    Falls back gracefully if API is unavailable.

    Args:
        location: Observer location with latitude and longitude
        hours: Number of hours to forecast (default: 24, max: 168 for 7 days)

    Returns:
        List of HourlySeeingForecast objects, or empty list if unavailable
    """
    if not OPENMETEO_AVAILABLE:
        logger.debug("openmeteo-requests not available, skipping hourly forecast")
        return []

    # Limit to 7 days (168 hours) - Open-Meteo maximum
    hours = min(hours, 168)
    forecast_days = min((hours + 23) // 24, 7)  # Round up to days, max 7

    # Check database for cached data
    try:
        from sqlalchemy import and_, inspect

        from .database import get_database
        from .models import Base, WeatherForecastModel

        db = get_database()

        # Ensure weather_forecast table exists (create if migration hasn't run yet)
        inspector = inspect(db._engine)
        if "weather_forecast" not in inspector.get_table_names():
            logger.debug("weather_forecast table not found, creating it...")
            Base.metadata.create_all(db._engine, tables=[WeatherForecastModel.__table__])  # type: ignore[list-item]

        existing_forecasts = []
        with db._get_session() as session:
            # Check if we have recent data (fetched within last hour)
            now = datetime.now(UTC)
            stale_threshold = now - timedelta(hours=1)

            # Query for forecasts for this location that are not stale
            existing_forecasts = (
                session.query(WeatherForecastModel)
                .filter(
                    and_(
                        WeatherForecastModel.latitude == location.latitude,
                        WeatherForecastModel.longitude == location.longitude,
                        WeatherForecastModel.fetched_at >= stale_threshold,
                    )
                )
                .order_by(WeatherForecastModel.forecast_timestamp)
                .all()
            )

        # If we have enough recent forecasts covering the requested hours, return them
        # Check if we have forecasts covering at least the requested number of hours
        if existing_forecasts and len(existing_forecasts) >= hours and len(existing_forecasts) > 0:
            # Check if the forecasts cover a sufficient time range
            # Get the time span of cached forecasts
            first_ts = existing_forecasts[0].forecast_timestamp
            last_ts = existing_forecasts[-1].forecast_timestamp
            if first_ts.tzinfo is None:
                first_ts = first_ts.replace(tzinfo=UTC)
            if last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=UTC)

            time_span_hours = (last_ts - first_ts).total_seconds() / 3600

            # If we have enough hours of coverage, use cached data
            if time_span_hours >= hours - 1:  # Allow 1 hour tolerance
                logger.debug(
                    f"Using {len(existing_forecasts)} cached weather forecasts from database (spanning {time_span_hours:.1f} hours)"
                )
                forecasts = []
                for forecast in existing_forecasts[:hours]:
                    forecasts.append(
                        HourlySeeingForecast(
                            timestamp=forecast.forecast_timestamp,
                            seeing_score=forecast.seeing_score or 50.0,
                            temperature_f=forecast.temperature_f,
                            dew_point_f=forecast.dew_point_f,
                            humidity_percent=forecast.humidity_percent,
                            wind_speed_mph=forecast.wind_speed_mph,
                            cloud_cover_percent=forecast.cloud_cover_percent,
                        )
                    )
                return forecasts

        # If we get here, we need to fetch from API (either no cache, stale cache, or insufficient coverage)
        if existing_forecasts:
            logger.debug(f"Found {len(existing_forecasts)} cached forecasts, but need {hours} hours, fetching from API")
        else:
            logger.debug("No recent cached forecasts found, fetching from API")
    except Exception as e:
        logger.warning(f"Error checking database for weather forecasts: {e}")
        # Continue to fetch from API

    try:
        # Setup the Open-Meteo API client with cache and retry on error
        cache_dir = Path.home() / ".cache" / "celestron-nexstar"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_session = requests_cache.CachedSession(str(cache_dir / "openmeteo_cache"), expire_after=3600)
        retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
        openmeteo = openmeteo_requests.Client(session=retry_session)

        # Get timezone for the location (simplified - use UTC offset)
        # Open-Meteo can auto-detect, but we'll use "auto" for timezone
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "hourly": [
                "temperature_2m",
                "dew_point_2m",
                "relative_humidity_2m",
                "cloud_cover",
                "wind_speed_10m",
            ],
            "timezone": "auto",  # Auto-detect timezone
            "forecast_days": forecast_days,
            "wind_speed_unit": "mph",
            "temperature_unit": "fahrenheit",
        }

        responses = openmeteo.weather_api(url, params=params)
        response = responses[0]

        # Process hourly data
        hourly = response.Hourly()
        hourly_temperature_2m = hourly.Variables(0).ValuesAsNumpy()
        hourly_dew_point_2m = hourly.Variables(1).ValuesAsNumpy()
        hourly_relative_humidity_2m = hourly.Variables(2).ValuesAsNumpy()
        hourly_cloud_cover = hourly.Variables(3).ValuesAsNumpy()
        hourly_wind_speed_10m = hourly.Variables(4).ValuesAsNumpy()

        # Get time range
        time_range = hourly.Time()
        interval = hourly.Interval()

        forecasts = []
        prev_temp: float | None = None

        # Process each hour
        # Note: Open-Meteo API returns forecasts starting from the current time
        # We need to ensure we get enough data to cover from 1 hour before sunset to sunrise
        for i in range(len(hourly_temperature_2m)):
            # Calculate timestamp
            timestamp_seconds = time_range + (i * interval)
            timestamp = datetime.fromtimestamp(timestamp_seconds, tz=UTC)

            # Extract weather data (handle NaN values)
            def safe_float(value: float) -> float | None:
                """Convert numpy value to float, returning None if NaN."""
                if np is not None and np.isnan(value):
                    return None
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return None

            temp_f = safe_float(hourly_temperature_2m[i])
            dew_point_f = safe_float(hourly_dew_point_2m[i])
            humidity = safe_float(hourly_relative_humidity_2m[i])
            cloud_cover = safe_float(hourly_cloud_cover[i])
            wind_speed_mph = safe_float(hourly_wind_speed_10m[i])

            # Skip if essential data is missing
            if temp_f is None:
                continue

            # Calculate temperature change per hour (for stability)
            temp_change_per_hour = 0.0
            if prev_temp is not None and temp_f is not None:
                temp_change_per_hour = temp_f - prev_temp
            prev_temp = temp_f

            # Create WeatherData for seeing calculation
            weather_data = WeatherData(
                temperature_c=temp_f,
                dew_point_f=dew_point_f,
                humidity_percent=humidity,
                cloud_cover_percent=cloud_cover,
                wind_speed_ms=wind_speed_mph,  # Field name is misleading, but value is in mph
                condition=None,  # Open-Meteo doesn't provide condition strings
            )

            # Calculate seeing score
            seeing_score = calculate_seeing_conditions(weather_data, temp_change_per_hour)

            forecasts.append(
                HourlySeeingForecast(
                    timestamp=timestamp,
                    seeing_score=seeing_score,
                    temperature_f=temp_f,
                    dew_point_f=dew_point_f,
                    humidity_percent=humidity,
                    wind_speed_mph=wind_speed_mph,
                    cloud_cover_percent=cloud_cover,
                )
            )

            # Stop if we have enough hours
            if len(forecasts) >= hours:
                break

        # Store forecasts in database (replace stale data)
        try:
            from sqlalchemy import and_

            from .database import get_database
            from .models import WeatherForecastModel

            db = get_database()
            with db._get_session() as session:
                # Delete stale forecasts for this location
                now = datetime.now(UTC)
                stale_threshold = now - timedelta(hours=1)
                session.query(WeatherForecastModel).filter(
                    and_(
                        WeatherForecastModel.latitude == location.latitude,
                        WeatherForecastModel.longitude == location.longitude,
                        WeatherForecastModel.fetched_at < stale_threshold,
                    )
                ).delete()

                # Insert new forecasts
                for forecast_item in forecasts:
                    # Check if forecast already exists for this timestamp
                    existing = (
                        session.query(WeatherForecastModel)
                        .filter(
                            and_(
                                WeatherForecastModel.latitude == location.latitude,
                                WeatherForecastModel.longitude == location.longitude,
                                WeatherForecastModel.forecast_timestamp == forecast_item.timestamp,
                            )
                        )
                        .first()
                    )

                    if existing:
                        # Update existing forecast
                        existing.temperature_f = forecast_item.temperature_f
                        existing.dew_point_f = forecast_item.dew_point_f
                        existing.humidity_percent = forecast_item.humidity_percent
                        existing.cloud_cover_percent = forecast_item.cloud_cover_percent
                        existing.wind_speed_mph = forecast_item.wind_speed_mph
                        existing.seeing_score = forecast_item.seeing_score
                        existing.fetched_at = now
                    else:
                        # Insert new forecast
                        db_forecast = WeatherForecastModel(
                            latitude=location.latitude,
                            longitude=location.longitude,
                            forecast_timestamp=forecast_item.timestamp,
                            temperature_f=forecast_item.temperature_f,
                            dew_point_f=forecast_item.dew_point_f,
                            humidity_percent=forecast_item.humidity_percent,
                            cloud_cover_percent=forecast_item.cloud_cover_percent,
                            wind_speed_mph=forecast_item.wind_speed_mph,
                            seeing_score=forecast_item.seeing_score,
                            fetched_at=now,
                        )
                        session.add(db_forecast)

                session.commit()
                logger.debug(f"Stored {len(forecasts)} weather forecasts in database")
        except Exception as e:
            logger.warning(f"Error storing weather forecasts in database: {e}")
            # Continue and return forecasts anyway

        return forecasts

    except Exception as e:
        logger.warning(f"Error fetching hourly forecast from Open-Meteo: {e}")
        return []

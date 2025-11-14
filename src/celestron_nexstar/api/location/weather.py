"""
Weather API Integration

Provides weather data for observing conditions and visibility warnings.
Uses Open-Meteo API (free, no API key required).
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import aiohttp
import numpy as np

from celestron_nexstar.api.database.models import WeatherForecastModel
from celestron_nexstar.api.location.observer import ObserverLocation


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
    - Cloud Cover (applied as multiplier - clouds block observation)

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

    # 5. Cloud Cover (blocks measurement, not seeing itself)
    # According to Clear Sky Chart: "A white block on the seeing line means that there was
    # too much cloud (>80% cover) to calculate it." Seeing measures atmospheric turbulence,
    # not cloud cover. However, you cannot measure seeing through clouds.
    # Reference: https://server1.cleardarksky.com/csk/faq/seeing_catagories.html
    if weather.cloud_cover_percent is not None:
        cloud_cover = weather.cloud_cover_percent
        # If cloud cover > 80%, seeing cannot be calculated/measured
        if cloud_cover > 80:
            return 0.0  # Cannot measure seeing through clouds
    # If cloud cover <= 80% or unavailable, calculate seeing normally

    # Ensure score is between 0-100
    return max(0.0, min(100.0, total_score))


def _is_forecast_stale(forecast: WeatherForecastModel, now: datetime) -> bool:
    """
    Determine if a weather forecast is stale.

    A forecast is stale if:
    1. It's for a time in the past, OR
    2. It was fetched too long ago relative to how far in the future it's forecasting

    Args:
        forecast: WeatherForecastModel instance
        now: Current datetime (timezone-aware, UTC)

    Returns:
        True if forecast is stale, False otherwise
    """
    # Ensure both timestamps are timezone-aware (UTC)
    forecast_ts = forecast.forecast_timestamp
    if forecast_ts.tzinfo is None:
        forecast_ts = forecast_ts.replace(tzinfo=UTC)
    elif forecast_ts.tzinfo != UTC:
        forecast_ts = forecast_ts.astimezone(UTC)

    fetched_at = forecast.fetched_at
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=UTC)
    elif fetched_at.tzinfo != UTC:
        fetched_at = fetched_at.astimezone(UTC)

    # Forecasts for past times are always stale
    if forecast_ts < now:
        return True

    # Calculate how far in the future this forecast is
    hours_ahead = (forecast_ts - now).total_seconds() / 3600

    # Calculate how long ago it was fetched
    fetch_age_hours = (now - fetched_at).total_seconds() / 3600

    # Staleness thresholds based on forecast horizon
    if hours_ahead <= 6:
        # Near-term (0-6 hours ahead): refresh every 2 hours
        return fetch_age_hours > 2
    elif hours_ahead <= 24:
        # Medium-term (6-24 hours ahead): refresh every 6 hours
        return fetch_age_hours > 6
    else:
        # Long-term (24+ hours ahead): refresh every 12 hours
        return fetch_age_hours > 12


async def fetch_hourly_weather_forecast(location: ObserverLocation, hours: int = 24) -> list[HourlySeeingForecast]:
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
    # Limit to 7 days (168 hours) - Open-Meteo maximum
    hours = min(hours, 168)
    forecast_days = min((hours + 23) // 24, 7)  # Round up to days, max 7

    # Helper function to check database
    async def _check_database_cache() -> tuple[list[WeatherForecastModel], datetime]:
        """Check database for cached forecasts. Returns (forecasts, now)."""
        from sqlalchemy import and_, select, text

        from celestron_nexstar.api.database.database import get_database
        from celestron_nexstar.api.database.models import Base, WeatherForecastModel

        db = get_database()

        # Ensure weather_forecast table exists (create if migration hasn't run yet)
        try:

            async def _check_and_create_table() -> None:
                async with db._engine.begin() as conn:
                    # Check if table exists by trying to query it
                    # If it doesn't exist, create it
                    try:
                        await conn.execute(text("SELECT 1 FROM weather_forecast LIMIT 1"))
                    except Exception:
                        # Table doesn't exist, create it
                        logger.debug("weather_forecast table not found, creating it...")
                    await conn.run_sync(
                        lambda sync_conn: Base.metadata.create_all(
                            sync_conn,
                            tables=[WeatherForecastModel.__table__],  # type: ignore[list-item]
                        )
                    )

            await _check_and_create_table()
        except Exception as e:
            logger.debug(f"Could not check/create weather_forecast table: {e}")

        now = datetime.now(UTC)
        existing_forecasts = []

        try:
            async with db._AsyncSession() as session:
                # Query for forecasts for this location (we'll filter stale ones after)
                # Get a wider range to check staleness intelligently
                stmt = (
                    select(WeatherForecastModel)
                    .where(
                        and_(
                            WeatherForecastModel.latitude == location.latitude,
                            WeatherForecastModel.longitude == location.longitude,
                            # Only consider forecasts that are not too old (max 24 hours fetch age)
                            WeatherForecastModel.fetched_at >= now - timedelta(hours=24),
                        )
                    )
                    .order_by(WeatherForecastModel.forecast_timestamp)
                )
                result = await session.execute(stmt)
                all_forecasts = result.scalars().all()

                # Filter out stale forecasts using intelligent staleness check
                existing_forecasts = [f for f in all_forecasts if not _is_forecast_stale(f, now)]
        except Exception as e:
            logger.warning(f"Error checking database for weather forecasts: {e}")

        return existing_forecasts, now

    # Check database for cached data
    try:
        existing_forecasts, now = await _check_database_cache()

        # If we have enough non-stale forecasts covering the requested hours, return them
        if existing_forecasts and len(existing_forecasts) >= hours:
            # Check if the forecasts cover a sufficient time range
            # Get the time span of cached forecasts
            first_ts = existing_forecasts[0].forecast_timestamp
            last_ts = existing_forecasts[-1].forecast_timestamp
            if first_ts.tzinfo is None:
                first_ts = first_ts.replace(tzinfo=UTC)
            if last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=UTC)

            time_span_hours = (last_ts - first_ts).total_seconds() / 3600

            # Calculate what time range we need
            needed_end_time = now + timedelta(hours=hours)

            # Check if cached forecasts cover the needed time range
            if first_ts <= now and last_ts >= needed_end_time - timedelta(hours=1):  # Allow 1 hour tolerance
                logger.debug(
                    f"Using {len(existing_forecasts)} cached weather forecasts from database (spanning {time_span_hours:.1f} hours)"
                )
                # Filter to only return forecasts within the requested time range
                filtered_forecasts = [
                    f
                    for f in existing_forecasts
                    if f.forecast_timestamp >= now and f.forecast_timestamp <= needed_end_time
                ][:hours]
                forecasts = []
                for forecast in filtered_forecasts:
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
            logger.debug(
                f"Found {len(existing_forecasts)} cached forecasts, but need {hours} hours of coverage, fetching from API"
            )
        else:
            logger.debug("No valid cached forecasts found, fetching from API")
    except Exception as e:
        logger.warning(f"Error checking database for weather forecasts: {e}")
        # Continue to fetch from API
        now = datetime.now(UTC)

    # Fetch from API using aiohttp (async)
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params: dict[str, str | int | float | list[str]] = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "hourly": "temperature_2m,dew_point_2m,relative_humidity_2m,cloud_cover,wind_speed_10m",
            "timezone": "auto",  # Auto-detect timezone
            "forecast_days": forecast_days,
            "wind_speed_unit": "mph",
            "temperature_unit": "fahrenheit",
        }

        async with (
            aiohttp.ClientSession() as session,
            session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response,
        ):
            if response.status != 200:
                logger.warning(f"Open-Meteo API returned status {response.status}")
                return []

            data = await response.json()

        # Process hourly data from JSON response
        hourly = data.get("hourly", {})
        hourly_time = hourly.get("time", [])
        hourly_temperature_2m = hourly.get("temperature_2m", [])
        hourly_dew_point_2m = hourly.get("dew_point_2m", [])
        hourly_relative_humidity_2m = hourly.get("relative_humidity_2m", [])
        hourly_cloud_cover = hourly.get("cloud_cover", [])
        hourly_wind_speed_10m = hourly.get("wind_speed_10m", [])

        def safe_float(value: float | None) -> float | None:
            """Convert value to float, returning None if NaN or None."""
            if value is None:
                return None
            if np is not None and np.isnan(value):
                return None
            try:
                return float(value)
            except (ValueError, TypeError):
                return None

        forecasts = []
        prev_temp: float | None = None

        # Process each hour
        for i in range(min(len(hourly_time), hours)):
            # Parse timestamp from ISO format string
            try:
                timestamp_str = hourly_time[i]
                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=UTC)
            except (ValueError, IndexError, TypeError):
                continue

            # Extract weather data (handle NaN values)
            temp_f = safe_float(hourly_temperature_2m[i] if i < len(hourly_temperature_2m) else None)
            dew_point_f = safe_float(hourly_dew_point_2m[i] if i < len(hourly_dew_point_2m) else None)
            humidity = safe_float(hourly_relative_humidity_2m[i] if i < len(hourly_relative_humidity_2m) else None)
            cloud_cover = safe_float(hourly_cloud_cover[i] if i < len(hourly_cloud_cover) else None)
            wind_speed_mph = safe_float(hourly_wind_speed_10m[i] if i < len(hourly_wind_speed_10m) else None)

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

        # Store forecasts in database (replace stale data)
        async def _store_forecasts_in_db(forecasts_to_store: list[HourlySeeingForecast]) -> None:
            """Store forecasts in database."""
            from sqlalchemy import and_, select

            from celestron_nexstar.api.database.database import get_database
            from celestron_nexstar.api.database.models import WeatherForecastModel
            from celestron_nexstar.api.location.geohash_utils import encode

            db = get_database()
            try:
                async with db._AsyncSession() as session:
                    # Delete stale forecasts for this location using intelligent staleness check
                    now_db = datetime.now(UTC)
                    # Get all forecasts for this location to check staleness
                    stmt = select(WeatherForecastModel).where(
                        and_(
                            WeatherForecastModel.latitude == location.latitude,
                            WeatherForecastModel.longitude == location.longitude,
                        )
                    )
                    result = await session.execute(stmt)
                    all_location_forecasts = result.scalars().all()

                    # Delete forecasts that are stale
                    for forecast in all_location_forecasts:
                        if _is_forecast_stale(forecast, now_db):
                            await session.delete(forecast)

                    # Insert new forecasts
                    for forecast_item in forecasts_to_store:
                        # Check if forecast already exists for this timestamp
                        stmt = (
                            select(WeatherForecastModel)
                            .where(
                                and_(
                                    WeatherForecastModel.latitude == location.latitude,
                                    WeatherForecastModel.longitude == location.longitude,
                                    WeatherForecastModel.forecast_timestamp == forecast_item.timestamp,
                                )
                            )
                            .limit(1)
                        )
                        result = await session.execute(stmt)
                        existing = result.scalar_one_or_none()

                        # Calculate geohash for this location (precision 9 for ~5m accuracy)
                        location_geohash = encode(location.latitude, location.longitude, precision=9)

                        if existing:
                            # Update existing forecast
                            existing.geohash = location_geohash
                            existing.temperature_f = forecast_item.temperature_f
                            existing.dew_point_f = forecast_item.dew_point_f
                            existing.humidity_percent = forecast_item.humidity_percent
                            existing.cloud_cover_percent = forecast_item.cloud_cover_percent
                            existing.wind_speed_mph = forecast_item.wind_speed_mph
                            existing.seeing_score = forecast_item.seeing_score
                            existing.fetched_at = now_db
                        else:
                            # Insert new forecast
                            db_forecast = WeatherForecastModel(
                                latitude=location.latitude,
                                longitude=location.longitude,
                                geohash=location_geohash,
                                forecast_timestamp=forecast_item.timestamp,
                                temperature_f=forecast_item.temperature_f,
                                dew_point_f=forecast_item.dew_point_f,
                                humidity_percent=forecast_item.humidity_percent,
                                cloud_cover_percent=forecast_item.cloud_cover_percent,
                                wind_speed_mph=forecast_item.wind_speed_mph,
                                seeing_score=forecast_item.seeing_score,
                                fetched_at=now_db,
                            )
                            session.add(db_forecast)

                    await session.commit()
                    logger.debug(f"Stored {len(forecasts_to_store)} weather forecasts in database")
            except Exception as e:
                logger.warning(f"Error storing weather forecasts in database: {e}")

        if forecasts:
            await _store_forecasts_in_db(forecasts)

    except Exception as e:
        logger.warning(f"Error fetching hourly forecast from Open-Meteo: {e}")
        return []

    return forecasts


async def fetch_weather(location: ObserverLocation) -> WeatherData:
    """
    Fetch current weather data for the observer location.

    Checks database first using current location and current time.
    If not found or stale, fetches from Open-Meteo API and stores in database.

    Args:
        location: Observer location with latitude and longitude

    Returns:
        WeatherData with current conditions, or error message if failed
    """
    # Use current time for database query
    now = datetime.now(UTC)
    current_hour_start = now.replace(minute=0, second=0, microsecond=0)
    current_hour_end = current_hour_start + timedelta(hours=1)

    # Helper function to check database
    async def _check_database_cache() -> WeatherForecastModel | None:
        """Check database for cached weather. Returns cached forecast or None."""
        from sqlalchemy import and_, select, text

        from celestron_nexstar.api.database.database import get_database
        from celestron_nexstar.api.database.models import Base, WeatherForecastModel

        db = get_database()

        # Ensure weather_forecast table exists
        try:

            async def _check_and_create_table() -> None:
                async with db._engine.begin() as conn:
                    # Check if table exists by trying to query it
                    # If it doesn't exist, create it
                    try:
                        await conn.execute(text("SELECT 1 FROM weather_forecast LIMIT 1"))
                    except Exception:
                        # Table doesn't exist, create it
                        logger.debug("weather_forecast table not found, creating it...")
                    await conn.run_sync(
                        lambda sync_conn: Base.metadata.create_all(
                            sync_conn,
                            tables=[WeatherForecastModel.__table__],  # type: ignore[list-item]
                        )
                    )

            await _check_and_create_table()
        except Exception as e:
            logger.debug(f"Could not check/create weather_forecast table: {e}")

        try:
            async with db._AsyncSession() as session:
                # Look for forecasts for the current hour
                stmt = (
                    select(WeatherForecastModel)
                    .where(
                        and_(
                            WeatherForecastModel.latitude == location.latitude,
                            WeatherForecastModel.longitude == location.longitude,
                            WeatherForecastModel.forecast_timestamp >= current_hour_start,
                            WeatherForecastModel.forecast_timestamp < current_hour_end,
                        )
                    )
                    .order_by(WeatherForecastModel.forecast_timestamp.desc())
                )
                result = await session.execute(stmt)
                candidates = result.scalars().all()

                # Find the first non-stale forecast
                for candidate in candidates:
                    if not _is_forecast_stale(candidate, now):
                        return candidate
        except Exception as e:
            logger.debug(f"Error checking database for current weather: {e}")

        return None

    # Check database for current weather (within the current hour)
    try:
        existing = await _check_database_cache()

        if existing:
            # Convert database model to WeatherData
            logger.debug("Using cached weather data from database")
            return WeatherData(
                temperature_c=existing.temperature_f,
                dew_point_f=existing.dew_point_f,
                humidity_percent=existing.humidity_percent,
                cloud_cover_percent=existing.cloud_cover_percent,
                wind_speed_ms=existing.wind_speed_mph,
                visibility_km=None,
                condition=None,
                last_updated=existing.fetched_at.isoformat() if existing.fetched_at else None,
            )
    except Exception as e:
        logger.debug(f"Error checking database for current weather: {e}")

    # Not in cache or stale, fetch from API
    logger.debug("Fetching current weather from Open-Meteo API")
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params: dict[str, str | int | float | list[str]] = {
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
            "forecast_days": 1,
        }

        async with (
            aiohttp.ClientSession() as session,
            session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response,
        ):
            if response.status != 200:
                return WeatherData(error=f"HTTP {response.status}")

            data = await response.json()

        # Parse response
        current = data.get("current", {})
        hourly = data.get("hourly", {})

        def safe_float(value: float | None) -> float | None:
            """Convert value to float, returning None if NaN or None."""
            if value is None:
                return None
            if np is not None and np.isnan(value):
                return None
            try:
                return float(value)
            except (ValueError, TypeError):
                return None

        # Open-Meteo API returns data directly in current object, not nested under "variables"
        temp_f = safe_float(current.get("temperature_2m"))
        humidity = safe_float(current.get("relative_humidity_2m"))
        cloud_cover = safe_float(current.get("cloud_cover"))
        wind_speed_mph = safe_float(current.get("wind_speed_10m"))
        weather_code = current.get("weather_code")

        # Get dew point from hourly data (first hour)
        # Open-Meteo API returns hourly data directly in hourly object
        dew_point_values = hourly.get("dew_point_2m", [])
        dew_point_f = safe_float(dew_point_values[0]) if dew_point_values else None

        # If dew point not available, calculate from temp/humidity
        if dew_point_f is None and temp_f is not None and humidity is not None:
            dew_point_f = calculate_dew_point_fahrenheit(temp_f, humidity)

        # Map weather code to condition string
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

        weather_data = WeatherData(
            temperature_c=temp_f,
            dew_point_f=dew_point_f,
            humidity_percent=humidity,
            cloud_cover_percent=cloud_cover,
            wind_speed_ms=wind_speed_mph,
            visibility_km=None,
            condition=condition,
            last_updated="now",
        )

        # Store in database for future use
        if not weather_data.error:

            async def _store_weather_in_db(weather_to_store: WeatherData) -> None:
                """Store weather in database."""
                from sqlalchemy import and_, select

                from celestron_nexstar.api.database.database import get_database
                from celestron_nexstar.api.database.models import WeatherForecastModel
                from celestron_nexstar.api.location.geohash_utils import encode

                db = get_database()
                try:
                    location_geohash = encode(location.latitude, location.longitude, precision=9)
                    now_db = datetime.now(UTC)
                    current_hour_start_db = now_db.replace(minute=0, second=0, microsecond=0)
                    current_hour_end_db = current_hour_start_db + timedelta(hours=1)

                    async with db._AsyncSession() as session:
                        # Check if forecast already exists for this hour
                        stmt = (
                            select(WeatherForecastModel)
                            .where(
                                and_(
                                    WeatherForecastModel.latitude == location.latitude,
                                    WeatherForecastModel.longitude == location.longitude,
                                    WeatherForecastModel.forecast_timestamp >= current_hour_start_db,
                                    WeatherForecastModel.forecast_timestamp < current_hour_end_db,
                                )
                            )
                            .limit(1)
                        )
                        result = await session.execute(stmt)
                        existing = result.scalar_one_or_none()

                        # Calculate seeing score
                        seeing_score = calculate_seeing_conditions(weather_to_store)

                        if existing:
                            # Update existing forecast
                            existing.geohash = location_geohash
                            existing.temperature_f = weather_to_store.temperature_c
                            existing.dew_point_f = weather_to_store.dew_point_f
                            existing.humidity_percent = weather_to_store.humidity_percent
                            existing.cloud_cover_percent = weather_to_store.cloud_cover_percent
                            existing.wind_speed_mph = weather_to_store.wind_speed_ms
                            existing.seeing_score = seeing_score
                            existing.fetched_at = now_db
                        else:
                            # Insert new forecast
                            db_forecast = WeatherForecastModel(
                                latitude=location.latitude,
                                longitude=location.longitude,
                                geohash=location_geohash,
                                forecast_timestamp=current_hour_start_db,
                                temperature_f=weather_to_store.temperature_c,
                                dew_point_f=weather_to_store.dew_point_f,
                                humidity_percent=weather_to_store.humidity_percent,
                                cloud_cover_percent=weather_to_store.cloud_cover_percent,
                                wind_speed_mph=weather_to_store.wind_speed_ms,
                                seeing_score=seeing_score,
                                fetched_at=now_db,
                            )
                            session.add(db_forecast)

                        await session.commit()
                        logger.debug("Stored current weather in database")
                except Exception as e:
                    logger.warning(f"Error storing current weather in database: {e}")

            await _store_weather_in_db(weather_data)

        return weather_data

    except Exception as e:
        logger.exception("Error fetching weather from Open-Meteo (async)")
        return WeatherData(error=f"Error fetching weather: {e}")


async def fetch_weather_batch(locations: list[ObserverLocation]) -> dict[ObserverLocation, WeatherData]:
    """
    Fetch weather data for multiple locations concurrently.

    Args:
        locations: List of observer locations

    Returns:
        Dictionary mapping locations to WeatherData
    """
    tasks = [fetch_weather(loc) for loc in locations]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    data_map: dict[ObserverLocation, WeatherData] = {}
    for location, result in zip(locations, results, strict=False):
        if isinstance(result, Exception):
            logger.error(f"Error fetching weather for {location}: {result}")
            data_map[location] = WeatherData(error=f"Error: {result}")
        elif isinstance(result, WeatherData):
            data_map[location] = result
        else:
            logger.warning(f"Unexpected result type for {location}: {type(result)}")
            data_map[location] = WeatherData(error="Unexpected error")

    return data_map

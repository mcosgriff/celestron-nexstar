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

import numpy as np
import requests

from celestron_nexstar.api.database.models import HistoricalWeatherModel, WeatherForecastModel
from celestron_nexstar.api.location.observer import ObserverLocation


logger = logging.getLogger(__name__)


@dataclass
class WeatherData:
    """Weather information for observing conditions."""

    # EXISTING FIELDS (kept for backward compatibility)
    temperature_c: float | None = None  # DEPRECATED: Actually Fahrenheit when units=imperial
    dew_point_f: float | None = None  # Dew point in Fahrenheit
    humidity_percent: float | None = None
    cloud_cover_percent: float | None = None
    wind_speed_ms: float | None = None  # DEPRECATED: Actually mph when units=imperial
    visibility_km: float | None = None
    condition: str | None = None  # e.g., "Clear", "Cloudy", "Rain"
    last_updated: str | None = None
    error: str | None = None

    # NEW FIELDS - Cloud layers (0-100%)
    cloud_cover_low: float | None = None  # Low clouds/fog (0-3km altitude)
    cloud_cover_mid: float | None = None  # Mid-level clouds (3-8km altitude)
    cloud_cover_high: float | None = None  # High clouds (8km+ altitude)

    # NEW FIELDS - Atmospheric quality
    visibility_m: float | None = None  # Direct atmospheric clarity (meters)
    precipitation_probability: float | None = None  # 0-100%

    # NEW FIELDS - Atmospheric stability
    cape: float | None = None  # Convective Available Potential Energy (J/kg)
    boundary_layer_height_m: float | None = None  # Atmospheric mixing layer (meters)
    freezing_level_height_m: float | None = None  # Frost/dew prediction (meters)
    vapour_pressure_deficit: float | None = None  # Condensation risk (kPa)

    # NEW FIELDS - Upper atmosphere winds
    wind_speed_80m_mph: float | None = None  # Wind at 80m altitude (mph)
    wind_speed_120m_mph: float | None = None  # Wind at 120m altitude (mph)

    # NEW FIELDS - Precipitation & pressure
    precipitation_mm: float | None = None  # Total precipitation (mm)
    rain_mm: float | None = None  # Rain amount (mm)
    snowfall_cm: float | None = None  # Snowfall amount (cm)
    pressure_msl: float | None = None  # Mean sea level pressure (hPa)


@dataclass
class HourlySeeingForecast:
    """Hourly seeing conditions forecast."""

    # EXISTING FIELDS
    timestamp: datetime
    seeing_score: float  # 0-100 (old algorithm)
    temperature_f: float | None
    dew_point_f: float | None
    humidity_percent: float | None
    wind_speed_mph: float | None
    cloud_cover_percent: float | None

    # NEW - Parallel algorithm scores
    seeing_score_v2: float | None = None  # 0-100 (new enhanced algorithm)
    seeing_components: dict[str, float] | None = None  # Component breakdown for v2

    # NEW - Cloud layers
    cloud_cover_low: float | None = None
    cloud_cover_mid: float | None = None
    cloud_cover_high: float | None = None

    # NEW - Atmospheric metrics
    visibility_m: float | None = None
    precipitation_probability: float | None = None
    cape: float | None = None
    boundary_layer_height_m: float | None = None
    wind_speed_80m_mph: float | None = None
    wind_speed_120m_mph: float | None = None


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
        match wind_mph:
            case w if 5.0 <= w <= 10.0:
                wind_score = 30.0
            case w if w < 5.0:
                # Below 5 mph: score reduces linearly
                wind_score = w * 6.0  # 0-30 points
            case w if w <= 15.0:
                # 10-15 mph: score reduces gradually
                wind_score = 30.0 - (w - 10.0) * 3.0  # 30-15 points
            case w if w <= 20.0:
                # 15-20 mph: score reduces more sharply
                wind_score = 15.0 - (w - 15.0) * 3.0  # 15-0 points
            case _:
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
    if temperature_change_per_hour is not None:
        temp_change_abs = abs(temperature_change_per_hour)
        match temp_change_abs:
            case t if t <= 0.5:
                stability_score = 20.0  # Very stable
            case t if t <= 1.0:
                stability_score = 18.0
            case t if t <= 2.0:
                stability_score = 15.0
            case t if t <= 3.0:
                stability_score = 10.0
            case t if t <= 5.0:
                stability_score = 5.0
            case _:
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


def calculate_seeing_conditions_v2(
    weather: WeatherData,
    temperature_change_per_hour: float = 0.0,
) -> tuple[float, dict[str, float]]:
    """
    Calculate enhanced astronomical seeing conditions score (0-100) with component breakdown.

    Uses advanced atmospheric metrics when available. Returns both total score and
    individual component scores for transparency and validation.

    Args:
        weather: Weather data with standard and advanced metrics
        temperature_change_per_hour: Rate of temperature change (°F/hour)

    Returns:
        Tuple of (total_score, component_scores_dict)

    Components (0-100 each):
        - temp_dew_spread: Temperature-dew point separation (20% weight)
        - wind_quality: Surface wind + shear if available (20% weight)
        - temp_stability: Temperature change rate (20% weight)
        - humidity: Relative humidity impact (10% weight)
        - cloud_quality: Cloud layers weighted by altitude (10% weight)
        - atm_stability: CAPE, boundary layer, VPD (10% weight)
        - visibility: Atmospheric clarity (5% weight)
        - precip_risk: Precipitation probability (5% weight)
    """
    if weather.error or weather.temperature_c is None:
        return 50.0, {}

    components = {}

    # 1. Temperature-Dew Point Spread (20% weight)
    components["temp_dew_spread"] = _calc_temp_dew_spread_score(weather)

    # 2. Wind Quality (20% weight)
    components["wind_quality"] = _calc_wind_quality_score(weather)

    # 3. Temperature Stability (20% weight)
    components["temp_stability"] = _calc_temp_stability_score(temperature_change_per_hour)

    # 4. Humidity Impact (10% weight)
    components["humidity"] = _calc_humidity_score(weather)

    # 5. Cloud Quality (10% weight)
    components["cloud_quality"] = _calc_cloud_quality_score(weather)

    # 6. Atmospheric Stability (10% weight)
    components["atm_stability"] = _calc_atmospheric_stability_score(weather)

    # 7. Visibility (5% weight)
    components["visibility"] = _calc_visibility_score(weather)

    # 8. Precipitation Risk (5% weight)
    components["precip_risk"] = _calc_precipitation_risk_score(weather)

    # Calculate weighted total
    weights = {
        "temp_dew_spread": 0.20,
        "wind_quality": 0.20,
        "temp_stability": 0.20,
        "humidity": 0.10,
        "cloud_quality": 0.10,
        "atm_stability": 0.10,
        "visibility": 0.05,
        "precip_risk": 0.05,
    }

    total_score = sum(components[k] * weights[k] for k in weights)

    # Cloud cover hard cutoff (>80% blocks seeing measurement)
    if weather.cloud_cover_percent and weather.cloud_cover_percent > 80:
        return 0.0, components

    return max(0.0, min(100.0, total_score)), components


def _calc_temp_dew_spread_score(weather: WeatherData) -> float:
    """Calculate score from temperature-dew point spread (0-100)."""
    if weather.temperature_c is None or weather.dew_point_f is None:
        return 50.0

    temp_spread = weather.temperature_c - weather.dew_point_f

    if temp_spread >= 30 or temp_spread >= 15:
        return 100.0
    elif temp_spread >= 10:
        return 66.7 + (temp_spread - 10) * 6.67
    elif temp_spread >= 5:
        return 33.3 + (temp_spread - 5) * 6.67
    else:
        return temp_spread * 6.67


def _calc_wind_quality_score(weather: WeatherData) -> float:
    """Calculate wind quality score considering surface wind and shear (0-100)."""
    if weather.wind_speed_ms is None:
        return 50.0

    wind_mph = weather.wind_speed_ms  # Actually mph despite field name

    # Surface wind component
    if 5 <= wind_mph <= 10:
        surface_score = 100.0
    elif wind_mph < 5:
        surface_score = wind_mph * 20.0
    elif wind_mph <= 15:
        surface_score = 100.0 - (wind_mph - 10) * 20.0
    elif wind_mph <= 20:
        surface_score = 50.0 - (wind_mph - 15) * 10.0
    else:
        surface_score = 0.0

    # Wind shear component (if upper level winds available)
    has_upper_winds = weather.wind_speed_80m_mph is not None and weather.wind_speed_120m_mph is not None

    if has_upper_winds:
        shear_80_10 = abs(weather.wind_speed_80m_mph - wind_mph)
        shear_120_80 = abs(weather.wind_speed_120m_mph - weather.wind_speed_80m_mph)
        avg_shear = (shear_80_10 + shear_120_80) / 2

        # Low shear = stable air
        if avg_shear < 5:
            shear_score = 100.0
        elif avg_shear < 10:
            shear_score = 80.0
        elif avg_shear < 15:
            shear_score = 60.0
        elif avg_shear < 20:
            shear_score = 40.0
        else:
            shear_score = 20.0

        # Combine: 60% surface, 40% shear
        return surface_score * 0.6 + shear_score * 0.4
    else:
        return surface_score


def _calc_temp_stability_score(temp_change_per_hour: float) -> float:
    """Calculate temperature stability score (0-100)."""
    temp_change_abs = abs(temp_change_per_hour)

    if temp_change_abs <= 0.5:
        return 100.0
    elif temp_change_abs <= 1.0:
        return 90.0
    elif temp_change_abs <= 2.0:
        return 75.0
    elif temp_change_abs <= 3.0:
        return 50.0
    elif temp_change_abs <= 5.0:
        return 25.0
    else:
        return 0.0


def _calc_humidity_score(weather: WeatherData) -> float:
    """Calculate humidity impact score (0-100)."""
    if weather.humidity_percent is None:
        return 50.0

    humidity = weather.humidity_percent

    if humidity <= 30:
        return 100.0
    elif humidity <= 60:
        return 100.0 - (humidity - 30) * (16.7 / 30.0)
    elif humidity <= 80:
        return 83.3 - (humidity - 60) * (25.0 / 20.0)
    else:
        return max(0.0, 58.3 - (humidity - 80) * (58.3 / 20.0))


def _calc_cloud_quality_score(weather: WeatherData) -> float:
    """Calculate cloud quality score with layer weighting (0-100)."""
    if weather.cloud_cover_percent is None:
        return 50.0

    # If we have layered cloud data, weight by altitude
    has_layers = (
        weather.cloud_cover_low is not None
        or weather.cloud_cover_mid is not None
        or weather.cloud_cover_high is not None
    )

    if has_layers:
        low = weather.cloud_cover_low or 0
        mid = weather.cloud_cover_mid or 0
        high = weather.cloud_cover_high or 0

        # Weight: low clouds affect seeing most, high clouds least
        weighted_clouds = (low * 1.5 + mid * 1.0 + high * 0.5) / 3.0
        score = 100.0 - weighted_clouds
    else:
        # Simple inversion of total cloud cover
        score = 100.0 - weather.cloud_cover_percent

    return max(0.0, min(100.0, score))


def _calc_atmospheric_stability_score(weather: WeatherData) -> float:
    """Calculate atmospheric stability from CAPE, boundary layer, VPD (0-100)."""
    scores = []
    weights = []

    # CAPE component
    if weather.cape is not None:
        if weather.cape < 100:
            cape_score = 100.0
        elif weather.cape < 500:
            cape_score = 80.0
        elif weather.cape < 1000:
            cape_score = 60.0
        elif weather.cape < 2000:
            cape_score = 40.0
        else:
            cape_score = 20.0
        scores.append(cape_score)
        weights.append(0.4)

    # Boundary layer height component
    if weather.boundary_layer_height_m is not None:
        blh = weather.boundary_layer_height_m
        if blh < 500:
            blh_score = 100.0
        elif blh < 1000:
            blh_score = 80.0
        elif blh < 1500:
            blh_score = 60.0
        elif blh < 2000:
            blh_score = 40.0
        else:
            blh_score = 20.0
        scores.append(blh_score)
        weights.append(0.4)

    # Vapour pressure deficit component
    if weather.vapour_pressure_deficit is not None:
        vpd = weather.vapour_pressure_deficit
        if vpd > 1.5:
            vpd_score = 100.0
        elif vpd > 1.0:
            vpd_score = 80.0
        elif vpd > 0.5:
            vpd_score = 60.0
        else:
            vpd_score = 40.0
        scores.append(vpd_score)
        weights.append(0.2)

    if scores:
        # Normalize weights to sum to 1
        total_weight = sum(weights)
        normalized_weights = [w / total_weight for w in weights]
        return sum(s * w for s, w in zip(scores, normalized_weights, strict=False))
    else:
        return 50.0  # Neutral if no data


def _calc_visibility_score(weather: WeatherData) -> float:
    """Calculate visibility score (0-100)."""
    if weather.visibility_m is None:
        return 50.0

    vis_km = weather.visibility_m / 1000.0

    if vis_km >= 20:
        return 100.0
    elif vis_km >= 10:
        return 80.0 + (vis_km - 10) * 2.0
    elif vis_km >= 5:
        return 60.0 + (vis_km - 5) * 4.0
    elif vis_km >= 2:
        return 40.0 + (vis_km - 2) * 6.67
    else:
        return vis_km * 20.0


def _calc_precipitation_risk_score(weather: WeatherData) -> float:
    """Calculate precipitation risk score (0-100, higher is better)."""
    if weather.precipitation_probability is None:
        return 50.0

    precip_prob = weather.precipitation_probability

    # Invert: 0% precip = 100 score, 100% precip = 0 score
    score = 100.0 - precip_prob

    return max(0.0, min(100.0, score))


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

    # Keep a small amount of recent history for UI charting (today-to-now).
    # Older historical hours can be dropped to keep the table bounded.
    if forecast_ts < now - timedelta(hours=36):
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


def fetch_hourly_weather_forecast(
    location: ObserverLocation,
    hours: int = 24,
    force_refresh: bool = False,
) -> list[HourlySeeingForecast]:
    """
    Fetch hourly weather forecast and calculate seeing conditions for each hour.

    Uses database cache first, then Open-Meteo API if data is stale or missing.
    Falls back gracefully if API is unavailable.
    """
    hours = min(hours, 168)
    forecast_days = min((hours + 23) // 24 + 1, 7)

    def _check_database_cache() -> tuple[list[WeatherForecastModel], datetime]:
        from sqlalchemy import and_, select, text
        from sqlalchemy.exc import SQLAlchemyError

        from celestron_nexstar.api.database.database import get_database
        from celestron_nexstar.api.database.models import Base, WeatherForecastModel, get_db_session

        db = get_database()
        try:
            with get_db_session() as session:
                try:
                    session.execute(text("SELECT 1 FROM weather_forecast LIMIT 1"))
                except (AttributeError, RuntimeError, ValueError, TypeError, SQLAlchemyError) as e:
                    logger.debug(f"weather_forecast table not found, creating it... (error: {e})")
                    Base.metadata.create_all(
                        db._engine,
                        tables=[WeatherForecastModel.__table__],  # type: ignore[list-item]
                        checkfirst=True,
                    )
        except (AttributeError, RuntimeError, ValueError, TypeError, OSError, SQLAlchemyError) as e:
            logger.debug(f"Could not check/create weather_forecast table: {e}")

        now = datetime.now(UTC)
        existing_forecasts: list[WeatherForecastModel] = []
        try:
            with get_db_session() as session:
                cutoff_time = (now - timedelta(hours=24)).replace(tzinfo=None)
                stmt = (
                    select(WeatherForecastModel)
                    .where(
                        and_(
                            WeatherForecastModel.latitude == location.latitude,
                            WeatherForecastModel.longitude == location.longitude,
                            WeatherForecastModel.fetched_at >= cutoff_time,
                        )
                    )
                    .order_by(WeatherForecastModel.forecast_timestamp)
                )
                result = session.execute(stmt)
                all_forecasts = result.scalars().all()
                existing_forecasts = [f for f in all_forecasts if not _is_forecast_stale(f, now)]
        except (AttributeError, RuntimeError, ValueError, TypeError, KeyError, IndexError, SQLAlchemyError) as e:
            logger.warning(f"Error checking database for weather forecasts: {e}")

        for f in existing_forecasts:
            if f.forecast_timestamp.tzinfo is None:
                f.forecast_timestamp = f.forecast_timestamp.replace(tzinfo=UTC)
            if f.fetched_at.tzinfo is None:
                f.fetched_at = f.fetched_at.replace(tzinfo=UTC)

        return existing_forecasts, now

    cached_fallback: list[WeatherForecastModel] = []

    try:
        existing_forecasts, now = _check_database_cache()
        cached_fallback = existing_forecasts

        if not force_refresh and existing_forecasts and len(existing_forecasts) >= hours:
            first_ts = existing_forecasts[0].forecast_timestamp
            last_ts = existing_forecasts[-1].forecast_timestamp
            if first_ts.tzinfo is None:
                first_ts = first_ts.replace(tzinfo=UTC)
            if last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=UTC)

            needed_end_time = now + timedelta(hours=hours)
            if first_ts <= now and last_ts >= needed_end_time - timedelta(hours=1):
                filtered_forecasts = [
                    f
                    for f in existing_forecasts
                    if f.forecast_timestamp >= now and f.forecast_timestamp <= needed_end_time
                ][:hours]
                return [
                    HourlySeeingForecast(
                        timestamp=forecast.forecast_timestamp,
                        seeing_score=forecast.seeing_score or 50.0,
                        temperature_f=forecast.temperature_f,
                        dew_point_f=forecast.dew_point_f,
                        humidity_percent=forecast.humidity_percent,
                        wind_speed_mph=forecast.wind_speed_mph,
                        cloud_cover_percent=forecast.cloud_cover_percent,
                    )
                    for forecast in filtered_forecasts
                ]
    except (AttributeError, RuntimeError, ValueError, TypeError, KeyError, IndexError) as e:
        logger.warning(f"Error checking database for weather forecasts: {e}")
        now = datetime.now(UTC)

    try:
        try:
            from sqlalchemy import func, select

            from celestron_nexstar.api.database.models import WeatherForecastModel, get_db_session

            with get_db_session() as session:
                last_fetch = session.execute(
                    select(func.max(WeatherForecastModel.fetched_at)).where(
                        WeatherForecastModel.latitude == location.latitude,
                        WeatherForecastModel.longitude == location.longitude,
                    )
                ).scalar_one_or_none()
            if not force_refresh and last_fetch is not None:
                if last_fetch.tzinfo is None:
                    last_fetch = last_fetch.replace(tzinfo=UTC)
                if (now - last_fetch) < timedelta(minutes=15):
                    cached, _now2 = _check_database_cache()
                    if cached:
                        needed_end_time = now + timedelta(hours=hours)
                        filtered = [
                            f for f in cached if f.forecast_timestamp >= now and f.forecast_timestamp <= needed_end_time
                        ][:hours]
                        return [
                            HourlySeeingForecast(
                                timestamp=f.forecast_timestamp,
                                seeing_score=f.seeing_score or 50.0,
                                temperature_f=f.temperature_f,
                                dew_point_f=f.dew_point_f,
                                humidity_percent=f.humidity_percent,
                                wind_speed_mph=f.wind_speed_mph,
                                cloud_cover_percent=f.cloud_cover_percent,
                            )
                            for f in filtered
                        ]
        except Exception:
            pass

        url = "https://api.open-meteo.com/v1/forecast"
        params: dict[str, str | int | float | list[str]] = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "hourly": [
                "temperature_2m",
                "dew_point_2m",
                "relative_humidity_2m",
                "cloud_cover",
                "wind_speed_10m",
                "cloud_cover_low",
                "cloud_cover_mid",
                "cloud_cover_high",
                "visibility",
                "precipitation_probability",
                "cape",
                "boundary_layer_height",
                "freezing_level_height",
                "vapour_pressure_deficit",
                "wind_speed_80m",
                "wind_speed_120m",
                "precipitation",
                "rain",
                "snowfall",
                "pressure_msl",
            ],
            "timezone": "auto",
            "forecast_days": forecast_days,
            "wind_speed_unit": "mph",
            "temperature_unit": "fahrenheit",
        }
        response = requests.get(url, params=params, timeout=30)
        if response.status_code != 200:
            logger.warning(f"Open-Meteo API returned status {response.status_code}")
            return []

        data = response.json()
        hourly = data.get("hourly", {})
        hourly_time = hourly.get("time", [])
        hourly_temperature_2m = hourly.get("temperature_2m", [])
        hourly_dew_point_2m = hourly.get("dew_point_2m", [])
        hourly_relative_humidity_2m = hourly.get("relative_humidity_2m", [])
        hourly_cloud_cover = hourly.get("cloud_cover", [])
        hourly_wind_speed_10m = hourly.get("wind_speed_10m", [])
        hourly_cloud_cover_low = hourly.get("cloud_cover_low", [])
        hourly_cloud_cover_mid = hourly.get("cloud_cover_mid", [])
        hourly_cloud_cover_high = hourly.get("cloud_cover_high", [])
        hourly_visibility = hourly.get("visibility", [])
        hourly_precip_probability = hourly.get("precipitation_probability", [])
        hourly_cape = hourly.get("cape", [])
        hourly_blh = hourly.get("boundary_layer_height", [])
        hourly_freezing = hourly.get("freezing_level_height", [])
        hourly_vpd = hourly.get("vapour_pressure_deficit", [])
        hourly_wind_80m = hourly.get("wind_speed_80m", [])
        hourly_wind_120m = hourly.get("wind_speed_120m", [])
        hourly_precip = hourly.get("precipitation", [])
        hourly_rain = hourly.get("rain", [])
        hourly_snow = hourly.get("snowfall", [])
        hourly_pressure = hourly.get("pressure_msl", [])

        def safe_float(value: float | None) -> float | None:
            if value is None:
                return None
            if np is not None and np.isnan(value):
                return None
            try:
                return float(value)
            except (ValueError, TypeError):
                return None

        forecasts: list[HourlySeeingForecast] = []
        prev_temp: float | None = None

        for i in range(min(len(hourly_time), hours)):
            try:
                timestamp_str = hourly_time[i]
                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=UTC)
            except (ValueError, IndexError, TypeError):
                continue

            temp_f = safe_float(hourly_temperature_2m[i] if i < len(hourly_temperature_2m) else None)
            dew_point_f = safe_float(hourly_dew_point_2m[i] if i < len(hourly_dew_point_2m) else None)
            humidity = safe_float(hourly_relative_humidity_2m[i] if i < len(hourly_relative_humidity_2m) else None)
            cloud_cover = safe_float(hourly_cloud_cover[i] if i < len(hourly_cloud_cover) else None)
            wind_speed_mph = safe_float(hourly_wind_speed_10m[i] if i < len(hourly_wind_speed_10m) else None)
            cloud_low = safe_float(hourly_cloud_cover_low[i] if i < len(hourly_cloud_cover_low) else None)
            cloud_mid = safe_float(hourly_cloud_cover_mid[i] if i < len(hourly_cloud_cover_mid) else None)
            cloud_high = safe_float(hourly_cloud_cover_high[i] if i < len(hourly_cloud_cover_high) else None)
            visibility_m = safe_float(hourly_visibility[i] if i < len(hourly_visibility) else None)
            precip_prob = safe_float(hourly_precip_probability[i] if i < len(hourly_precip_probability) else None)
            cape_val = safe_float(hourly_cape[i] if i < len(hourly_cape) else None)
            blh = safe_float(hourly_blh[i] if i < len(hourly_blh) else None)
            freezing = safe_float(hourly_freezing[i] if i < len(hourly_freezing) else None)
            vpd = safe_float(hourly_vpd[i] if i < len(hourly_vpd) else None)
            wind_80m = safe_float(hourly_wind_80m[i] if i < len(hourly_wind_80m) else None)
            wind_120m = safe_float(hourly_wind_120m[i] if i < len(hourly_wind_120m) else None)
            precip_mm = safe_float(hourly_precip[i] if i < len(hourly_precip) else None)
            rain_mm = safe_float(hourly_rain[i] if i < len(hourly_rain) else None)
            snow_cm = safe_float(hourly_snow[i] if i < len(hourly_snow) else None)
            pressure = safe_float(hourly_pressure[i] if i < len(hourly_pressure) else None)

            if temp_f is None:
                continue

            temp_change_per_hour = 0.0
            if prev_temp is not None:
                temp_change_per_hour = temp_f - prev_temp
            prev_temp = temp_f

            weather_data = WeatherData(
                temperature_c=temp_f,
                dew_point_f=dew_point_f,
                humidity_percent=humidity,
                cloud_cover_percent=cloud_cover,
                wind_speed_ms=wind_speed_mph,
                condition=None,
                cloud_cover_low=cloud_low,
                cloud_cover_mid=cloud_mid,
                cloud_cover_high=cloud_high,
                visibility_m=visibility_m,
                precipitation_probability=precip_prob,
                cape=cape_val,
                boundary_layer_height_m=blh,
                freezing_level_height_m=freezing,
                vapour_pressure_deficit=vpd,
                wind_speed_80m_mph=wind_80m,
                wind_speed_120m_mph=wind_120m,
                precipitation_mm=precip_mm,
                rain_mm=rain_mm,
                snowfall_cm=snow_cm,
                pressure_msl=pressure,
            )

            seeing_score_v1 = calculate_seeing_conditions(weather_data, temp_change_per_hour)
            seeing_score_v2, components = calculate_seeing_conditions_v2(weather_data, temp_change_per_hour)

            forecasts.append(
                HourlySeeingForecast(
                    timestamp=timestamp,
                    seeing_score=seeing_score_v1,
                    temperature_f=temp_f,
                    dew_point_f=dew_point_f,
                    humidity_percent=humidity,
                    wind_speed_mph=wind_speed_mph,
                    cloud_cover_percent=cloud_cover,
                    seeing_score_v2=seeing_score_v2,
                    seeing_components=components,
                    cloud_cover_low=cloud_low,
                    cloud_cover_mid=cloud_mid,
                    cloud_cover_high=cloud_high,
                    visibility_m=visibility_m,
                    precipitation_probability=precip_prob,
                    cape=cape_val,
                    boundary_layer_height_m=blh,
                    wind_speed_80m_mph=wind_80m,
                    wind_speed_120m_mph=wind_120m,
                )
            )

        def _store_forecasts_in_db(forecasts_to_store: list[HourlySeeingForecast]) -> None:
            from sqlalchemy import and_, delete, select

            from celestron_nexstar.api.database.database import get_database
            from celestron_nexstar.api.database.models import WeatherForecastModel, get_db_session
            from celestron_nexstar.api.location.geohash_utils import encode

            get_database()
            try:
                with get_db_session() as session:
                    if forecasts_to_store:
                        min_ts = min(f.timestamp for f in forecasts_to_store)
                        max_ts = max(f.timestamp for f in forecasts_to_store)
                        min_ts_naive = min_ts.replace(tzinfo=None) if min_ts.tzinfo else min_ts
                        max_ts_naive = max_ts.replace(tzinfo=None) if max_ts.tzinfo else max_ts
                        session.execute(
                            delete(WeatherForecastModel).where(
                                and_(
                                    WeatherForecastModel.latitude == location.latitude,
                                    WeatherForecastModel.longitude == location.longitude,
                                    WeatherForecastModel.forecast_timestamp >= min_ts_naive,
                                    WeatherForecastModel.forecast_timestamp <= max_ts_naive,
                                )
                            )
                        )

                    now_db = datetime.now(UTC)
                    stmt = select(WeatherForecastModel).where(
                        and_(
                            WeatherForecastModel.latitude == location.latitude,
                            WeatherForecastModel.longitude == location.longitude,
                        )
                    )
                    result = session.execute(stmt)
                    all_location_forecasts = result.scalars().all()

                    for f in all_location_forecasts:
                        if f.forecast_timestamp.tzinfo is None:
                            f.forecast_timestamp = f.forecast_timestamp.replace(tzinfo=UTC)
                        if f.fetched_at.tzinfo is None:
                            f.fetched_at = f.fetched_at.replace(tzinfo=UTC)

                    stale_ids = [f.id for f in all_location_forecasts if _is_forecast_stale(f, now_db)]
                    if stale_ids:
                        delete_stmt = delete(WeatherForecastModel).where(WeatherForecastModel.id.in_(stale_ids))
                        session.execute(delete_stmt)

                    for forecast_item in forecasts_to_store:
                        forecast_ts_naive = (
                            forecast_item.timestamp.replace(tzinfo=None)
                            if forecast_item.timestamp.tzinfo
                            else forecast_item.timestamp
                        )
                        stmt = (
                            select(WeatherForecastModel)
                            .where(
                                and_(
                                    WeatherForecastModel.latitude == location.latitude,
                                    WeatherForecastModel.longitude == location.longitude,
                                    WeatherForecastModel.forecast_timestamp == forecast_ts_naive,
                                )
                            )
                            .limit(1)
                        )
                        result = session.execute(stmt)
                        existing = result.scalar_one_or_none()
                        if existing:
                            session.execute(
                                delete(WeatherForecastModel).where(
                                    and_(
                                        WeatherForecastModel.latitude == location.latitude,
                                        WeatherForecastModel.longitude == location.longitude,
                                        WeatherForecastModel.forecast_timestamp == existing.forecast_timestamp,
                                        WeatherForecastModel.id != existing.id,
                                    )
                                )
                            )

                        location_geohash = encode(location.latitude, location.longitude, precision=9)
                        if existing:
                            now_db_naive = now_db.replace(tzinfo=None) if now_db.tzinfo else now_db
                            existing.geohash = location_geohash
                            existing.temperature_f = forecast_item.temperature_f
                            existing.dew_point_f = forecast_item.dew_point_f
                            existing.humidity_percent = forecast_item.humidity_percent
                            existing.cloud_cover_percent = forecast_item.cloud_cover_percent
                            existing.wind_speed_mph = forecast_item.wind_speed_mph
                            existing.seeing_score = forecast_item.seeing_score
                            existing.cloud_cover_low_percent = forecast_item.cloud_cover_low
                            existing.cloud_cover_mid_percent = forecast_item.cloud_cover_mid
                            existing.cloud_cover_high_percent = forecast_item.cloud_cover_high
                            existing.visibility_m = forecast_item.visibility_m
                            existing.precipitation_probability = forecast_item.precipitation_probability
                            existing.cape = forecast_item.cape
                            existing.boundary_layer_height_m = forecast_item.boundary_layer_height_m
                            existing.freezing_level_height_m = getattr(forecast_item, "freezing_level_height_m", None)
                            existing.vapour_pressure_deficit = getattr(forecast_item, "vapour_pressure_deficit", None)
                            existing.wind_speed_80m_mph = forecast_item.wind_speed_80m_mph
                            existing.wind_speed_120m_mph = forecast_item.wind_speed_120m_mph
                            existing.precipitation_mm = getattr(forecast_item, "precipitation_mm", None)
                            existing.rain_mm = getattr(forecast_item, "rain_mm", None)
                            existing.snowfall_cm = getattr(forecast_item, "snowfall_cm", None)
                            existing.pressure_msl = getattr(forecast_item, "pressure_msl", None)
                            existing.fetched_at = now_db_naive
                        else:
                            now_db_naive = now_db.replace(tzinfo=None) if now_db.tzinfo else now_db
                            db_forecast = WeatherForecastModel(
                                latitude=location.latitude,
                                longitude=location.longitude,
                                geohash=location_geohash,
                                forecast_timestamp=forecast_ts_naive,
                                temperature_f=forecast_item.temperature_f,
                                dew_point_f=forecast_item.dew_point_f,
                                humidity_percent=forecast_item.humidity_percent,
                                cloud_cover_percent=forecast_item.cloud_cover_percent,
                                wind_speed_mph=forecast_item.wind_speed_mph,
                                seeing_score=forecast_item.seeing_score,
                                cloud_cover_low_percent=forecast_item.cloud_cover_low,
                                cloud_cover_mid_percent=forecast_item.cloud_cover_mid,
                                cloud_cover_high_percent=forecast_item.cloud_cover_high,
                                visibility_m=forecast_item.visibility_m,
                                precipitation_probability=forecast_item.precipitation_probability,
                                cape=forecast_item.cape,
                                boundary_layer_height_m=forecast_item.boundary_layer_height_m,
                                freezing_level_height_m=getattr(forecast_item, "freezing_level_height_m", None),
                                vapour_pressure_deficit=getattr(forecast_item, "vapour_pressure_deficit", None),
                                wind_speed_80m_mph=forecast_item.wind_speed_80m_mph,
                                wind_speed_120m_mph=forecast_item.wind_speed_120m_mph,
                                precipitation_mm=getattr(forecast_item, "precipitation_mm", None),
                                rain_mm=getattr(forecast_item, "rain_mm", None),
                                snowfall_cm=getattr(forecast_item, "snowfall_cm", None),
                                pressure_msl=getattr(forecast_item, "pressure_msl", None),
                                fetched_at=now_db_naive,
                            )
                            session.add(db_forecast)

                    session.commit()
                    logger.debug(f"Stored {len(forecasts_to_store)} weather forecasts in database")
            except (AttributeError, RuntimeError, ValueError, TypeError, KeyError) as e:
                logger.warning(f"Error storing weather forecasts in database: {e}")

        if forecasts:
            _store_forecasts_in_db(forecasts)

    except (
        requests.RequestException,
        TimeoutError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        AttributeError,
        RuntimeError,
    ) as e:
        logger.warning(f"Error fetching hourly forecast from Open-Meteo: {e}")
        if cached_fallback:
            needed_end_time = now + timedelta(hours=hours)
            filtered = [
                f for f in cached_fallback if f.forecast_timestamp >= now and f.forecast_timestamp <= needed_end_time
            ][:hours]
            return [
                HourlySeeingForecast(
                    timestamp=f.forecast_timestamp,
                    seeing_score=f.seeing_score or 50.0,
                    temperature_f=f.temperature_f,
                    dew_point_f=f.dew_point_f,
                    humidity_percent=f.humidity_percent,
                    wind_speed_mph=f.wind_speed_mph,
                    cloud_cover_percent=f.cloud_cover_percent,
                )
                for f in filtered
            ]
        return []

    return forecasts


def fetch_weather_for_charts(
    location: ObserverLocation,
    future_hours: int = 24,
    force_refresh: bool = False,
) -> list[HourlySeeingForecast]:
    """
    Fetch weather data for charting: past 3 days + future hours.

    Uses Open-Meteo API with past_days=3 parameter to get historical observations
    combined with future forecast data.

    Args:
        location: Observer location with latitude and longitude
        future_hours: Number of future hours to include (default: 24)
        force_refresh: If True, bypass cache and fetch from Open-Meteo

    Returns:
        List of HourlySeeingForecast objects, sorted by timestamp (past to future)
    """
    now = datetime.now(UTC)
    past_start = now - timedelta(days=3)
    end_time = now + timedelta(hours=future_hours)

    # Prefer DB (cache) first. Only fetch if coverage is missing or cache is old.
    db_rows_fallback: list[WeatherForecastModel] = []
    try:
        from sqlalchemy import and_, func, select

        from celestron_nexstar.api.database.models import WeatherForecastModel, get_db_session

        with get_db_session() as session:
            rows = (
                session.execute(
                    select(WeatherForecastModel)
                    .where(
                        and_(
                            WeatherForecastModel.latitude == location.latitude,
                            WeatherForecastModel.longitude == location.longitude,
                            WeatherForecastModel.forecast_timestamp >= past_start.replace(tzinfo=None),
                            WeatherForecastModel.forecast_timestamp <= end_time.replace(tzinfo=None),
                        )
                    )
                    .order_by(WeatherForecastModel.forecast_timestamp)
                )
                .scalars()
                .all()
            )
            db_rows_fallback = list(rows)

            # Ensure timestamps are timezone-aware
            for row in db_rows_fallback:
                if row.forecast_timestamp.tzinfo is None:
                    row.forecast_timestamp = row.forecast_timestamp.replace(tzinfo=UTC)
                if row.fetched_at.tzinfo is None:
                    row.fetched_at = row.fetched_at.replace(tzinfo=UTC)

            last_fetch = session.execute(
                select(func.max(WeatherForecastModel.fetched_at)).where(
                    WeatherForecastModel.latitude == location.latitude,
                    WeatherForecastModel.longitude == location.longitude,
                )
            ).scalar_one_or_none()

        # If we have reasonable coverage and it was fetched recently, return DB data.
        fetched_recently = False
        if last_fetch is not None:
            # Normalize to UTC
            last_fetch = last_fetch if getattr(last_fetch, "tzinfo", None) else last_fetch.replace(tzinfo=UTC)
            fetched_recently = (now - last_fetch) < timedelta(minutes=30)

        if rows and fetched_recently and not force_refresh:
            return [
                HourlySeeingForecast(
                    timestamp=(
                        r.forecast_timestamp.replace(tzinfo=UTC)
                        if getattr(r.forecast_timestamp, "tzinfo", None) is None
                        else r.forecast_timestamp.astimezone(UTC)
                    ),
                    seeing_score=r.seeing_score or 50.0,
                    temperature_f=r.temperature_f,
                    dew_point_f=r.dew_point_f,
                    humidity_percent=r.humidity_percent,
                    wind_speed_mph=r.wind_speed_mph,
                    cloud_cover_percent=r.cloud_cover_percent,
                    # New advanced fields from database
                    cloud_cover_low=r.cloud_cover_low_percent,
                    cloud_cover_mid=r.cloud_cover_mid_percent,
                    cloud_cover_high=r.cloud_cover_high_percent,
                    visibility_m=r.visibility_m,
                    precipitation_probability=r.precipitation_probability,
                    cape=r.cape,
                    boundary_layer_height_m=r.boundary_layer_height_m,
                    wind_speed_80m_mph=r.wind_speed_80m_mph,
                    wind_speed_120m_mph=r.wind_speed_120m_mph,
                )
                for r in rows
            ]
    except Exception:
        # DB cache is best-effort; proceed to fetch path
        pass

    # Fetch from API with past_days parameter, then persist so subsequent views don't re-hit API.
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        # Add 1 to ensure we get enough future data even if we're late in the current day
        # forecast_days counts calendar days, not 24-hour periods from now
        forecast_days = min((future_hours + 23) // 24 + 1, 7)  # Round up to days + 1 buffer, max 7
        params: dict[str, str | int | float | list[str]] = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "hourly": [
                # Current metrics
                "temperature_2m",
                "dew_point_2m",
                "relative_humidity_2m",
                "cloud_cover",
                "wind_speed_10m",
                # Cloud layer breakdown
                "cloud_cover_low",
                "cloud_cover_mid",
                "cloud_cover_high",
                # Atmospheric quality
                "visibility",
                "precipitation_probability",
                # Atmospheric stability
                "cape",
                "boundary_layer_height",
                "freezing_level_height",
                "vapour_pressure_deficit",
                # Upper atmosphere winds
                "wind_speed_80m",
                "wind_speed_120m",
                # Precipitation & pressure
                "precipitation",
                "rain",
                "snowfall",
                "pressure_msl",
            ],
            "timezone": "auto",
            "forecast_days": forecast_days,
            "past_days": 3,
            "wind_speed_unit": "mph",
            "temperature_unit": "fahrenheit",
        }

        response = requests.get(url, params=params, timeout=30)
        if response.status_code != 200:
            logger.warning(f"Open-Meteo API returned status {response.status_code} for chart data")
            return []

        data = response.json()

        # Process hourly data from JSON response
        hourly = data.get("hourly", {})
        hourly_time = hourly.get("time", [])
        # Current metrics
        hourly_temperature_2m = hourly.get("temperature_2m", [])
        hourly_dew_point_2m = hourly.get("dew_point_2m", [])
        hourly_relative_humidity_2m = hourly.get("relative_humidity_2m", [])
        hourly_cloud_cover = hourly.get("cloud_cover", [])
        hourly_wind_speed_10m = hourly.get("wind_speed_10m", [])
        # Cloud layers
        hourly_cloud_cover_low = hourly.get("cloud_cover_low", [])
        hourly_cloud_cover_mid = hourly.get("cloud_cover_mid", [])
        hourly_cloud_cover_high = hourly.get("cloud_cover_high", [])
        # Atmospheric quality
        hourly_visibility = hourly.get("visibility", [])
        hourly_precip_probability = hourly.get("precipitation_probability", [])
        # Atmospheric stability
        hourly_cape = hourly.get("cape", [])
        hourly_blh = hourly.get("boundary_layer_height", [])
        hourly_freezing = hourly.get("freezing_level_height", [])
        hourly_vpd = hourly.get("vapour_pressure_deficit", [])
        # Upper winds
        hourly_wind_80m = hourly.get("wind_speed_80m", [])
        hourly_wind_120m = hourly.get("wind_speed_120m", [])
        # Precipitation & pressure
        hourly_precip = hourly.get("precipitation", [])
        hourly_rain = hourly.get("rain", [])
        hourly_snow = hourly.get("snowfall", [])
        hourly_pressure = hourly.get("pressure_msl", [])

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

        forecasts: list[HourlySeeingForecast] = []
        prev_temp: float | None = None

        # Process all hours (past + future)
        for i in range(len(hourly_time)):
            # Parse timestamp from ISO format string
            try:
                timestamp_str = hourly_time[i]
                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=UTC)
            except (ValueError, IndexError, TypeError):
                continue

            # Only include data from past 3 days onwards
            if timestamp < past_start:
                continue

            # Extract weather data (handle NaN values)
            # Current metrics
            temp_f = safe_float(hourly_temperature_2m[i] if i < len(hourly_temperature_2m) else None)
            dew_point_f = safe_float(hourly_dew_point_2m[i] if i < len(hourly_dew_point_2m) else None)
            humidity = safe_float(hourly_relative_humidity_2m[i] if i < len(hourly_relative_humidity_2m) else None)
            cloud_cover = safe_float(hourly_cloud_cover[i] if i < len(hourly_cloud_cover) else None)
            wind_speed_mph = safe_float(hourly_wind_speed_10m[i] if i < len(hourly_wind_speed_10m) else None)
            # Cloud layers
            cloud_low = safe_float(hourly_cloud_cover_low[i] if i < len(hourly_cloud_cover_low) else None)
            cloud_mid = safe_float(hourly_cloud_cover_mid[i] if i < len(hourly_cloud_cover_mid) else None)
            cloud_high = safe_float(hourly_cloud_cover_high[i] if i < len(hourly_cloud_cover_high) else None)
            # Atmospheric quality
            visibility_m = safe_float(hourly_visibility[i] if i < len(hourly_visibility) else None)
            precip_prob = safe_float(hourly_precip_probability[i] if i < len(hourly_precip_probability) else None)
            # Atmospheric stability
            cape_val = safe_float(hourly_cape[i] if i < len(hourly_cape) else None)
            blh = safe_float(hourly_blh[i] if i < len(hourly_blh) else None)
            freezing = safe_float(hourly_freezing[i] if i < len(hourly_freezing) else None)
            vpd = safe_float(hourly_vpd[i] if i < len(hourly_vpd) else None)
            # Upper winds
            wind_80m = safe_float(hourly_wind_80m[i] if i < len(hourly_wind_80m) else None)
            wind_120m = safe_float(hourly_wind_120m[i] if i < len(hourly_wind_120m) else None)
            # Precipitation & pressure
            precip_mm = safe_float(hourly_precip[i] if i < len(hourly_precip) else None)
            rain_mm = safe_float(hourly_rain[i] if i < len(hourly_rain) else None)
            snow_cm = safe_float(hourly_snow[i] if i < len(hourly_snow) else None)
            pressure = safe_float(hourly_pressure[i] if i < len(hourly_pressure) else None)

            # Skip if essential data is missing
            if temp_f is None:
                continue

            # Calculate temperature change per hour (for stability)
            temp_change_per_hour = 0.0
            if prev_temp is not None and temp_f is not None:
                temp_change_per_hour = temp_f - prev_temp
            prev_temp = temp_f

            # Create enhanced WeatherData for seeing calculation
            weather_data = WeatherData(
                # Current metrics
                temperature_c=temp_f,
                dew_point_f=dew_point_f,
                humidity_percent=humidity,
                cloud_cover_percent=cloud_cover,
                wind_speed_ms=wind_speed_mph,  # Field name is misleading, but value is in mph
                condition=None,
                # New metrics
                cloud_cover_low=cloud_low,
                cloud_cover_mid=cloud_mid,
                cloud_cover_high=cloud_high,
                visibility_m=visibility_m,
                precipitation_probability=precip_prob,
                cape=cape_val,
                boundary_layer_height_m=blh,
                freezing_level_height_m=freezing,
                vapour_pressure_deficit=vpd,
                wind_speed_80m_mph=wind_80m,
                wind_speed_120m_mph=wind_120m,
                precipitation_mm=precip_mm,
                rain_mm=rain_mm,
                snowfall_cm=snow_cm,
                pressure_msl=pressure,
            )

            # Calculate BOTH seeing scores (old and new algorithms)
            seeing_score_v1 = calculate_seeing_conditions(weather_data, temp_change_per_hour)
            seeing_score_v2, components = calculate_seeing_conditions_v2(weather_data, temp_change_per_hour)

            forecasts.append(
                HourlySeeingForecast(
                    timestamp=timestamp,
                    seeing_score=seeing_score_v1,  # Old algorithm
                    temperature_f=temp_f,
                    dew_point_f=dew_point_f,
                    humidity_percent=humidity,
                    wind_speed_mph=wind_speed_mph,
                    cloud_cover_percent=cloud_cover,
                    # New fields
                    seeing_score_v2=seeing_score_v2,
                    seeing_components=components,
                    cloud_cover_low=cloud_low,
                    cloud_cover_mid=cloud_mid,
                    cloud_cover_high=cloud_high,
                    visibility_m=visibility_m,
                    precipitation_probability=precip_prob,
                    cape=cape_val,
                    boundary_layer_height_m=blh,
                    wind_speed_80m_mph=wind_80m,
                    wind_speed_120m_mph=wind_120m,
                )
            )

        # Sort by timestamp (past to future)
        forecasts.sort(key=lambda x: x.timestamp)

        # Persist to DB so repeated chart views don't re-hit the API.
        if forecasts:
            try:
                from sqlalchemy import and_, delete

                from celestron_nexstar.api.database.models import WeatherForecastModel, get_db_session
                from celestron_nexstar.api.location.geohash_utils import encode

                location_geohash = encode(location.latitude, location.longitude, precision=9)
                now_db = datetime.now(UTC)
                min_ts = forecasts[0].timestamp
                max_ts = forecasts[-1].timestamp
                # Convert to naive UTC for database comparison
                min_ts_naive = min_ts.replace(tzinfo=None) if min_ts.tzinfo else min_ts
                max_ts_naive = max_ts.replace(tzinfo=None) if max_ts.tzinfo else max_ts
                current_hour_start = now_db.replace(minute=0, second=0, microsecond=0)
                current_hour_end = current_hour_start + timedelta(hours=1)
                current_hour_start_naive = (
                    current_hour_start.replace(tzinfo=None) if current_hour_start.tzinfo else current_hour_start
                )
                current_hour_end_naive = (
                    current_hour_end.replace(tzinfo=None) if current_hour_end.tzinfo else current_hour_end
                )

                with get_db_session() as session:
                    # De-dupe the range we're about to insert.
                    session.execute(
                        delete(WeatherForecastModel).where(
                            and_(
                                WeatherForecastModel.latitude == location.latitude,
                                WeatherForecastModel.longitude == location.longitude,
                                WeatherForecastModel.forecast_timestamp >= min_ts_naive,
                                WeatherForecastModel.forecast_timestamp <= max_ts_naive,
                                WeatherForecastModel.forecast_timestamp < current_hour_start_naive,
                            )
                        )
                    )
                    session.execute(
                        delete(WeatherForecastModel).where(
                            and_(
                                WeatherForecastModel.latitude == location.latitude,
                                WeatherForecastModel.longitude == location.longitude,
                                WeatherForecastModel.forecast_timestamp >= current_hour_end_naive,
                                WeatherForecastModel.forecast_timestamp <= max_ts_naive,
                            )
                        )
                    )

                    # Store timestamps as naive UTC
                    now_db_naive = now_db.replace(tzinfo=None) if now_db.tzinfo else now_db
                    for f in forecasts:
                        forecast_ts_naive = f.timestamp.replace(tzinfo=None) if f.timestamp.tzinfo else f.timestamp
                        if current_hour_start_naive <= forecast_ts_naive < current_hour_end_naive:
                            continue
                        session.add(
                            WeatherForecastModel(
                                latitude=location.latitude,
                                longitude=location.longitude,
                                geohash=location_geohash,
                                forecast_timestamp=forecast_ts_naive,
                                temperature_f=f.temperature_f,
                                dew_point_f=f.dew_point_f,
                                humidity_percent=f.humidity_percent,
                                cloud_cover_percent=f.cloud_cover_percent,
                                wind_speed_mph=f.wind_speed_mph,
                                seeing_score=f.seeing_score,
                                fetched_at=now_db_naive,
                            )
                        )
                    session.commit()
            except Exception:
                # Persistence is best-effort; charts still work with in-memory list.
                pass

        return forecasts

    except Exception as e:
        logger.warning(f"Error fetching weather data for charts from Open-Meteo: {e}")
        # Fall back to DB if available (offline / DNS issues).
        if db_rows_fallback:
            return [
                HourlySeeingForecast(
                    timestamp=(
                        r.forecast_timestamp.replace(tzinfo=UTC)
                        if getattr(r.forecast_timestamp, "tzinfo", None) is None
                        else r.forecast_timestamp.astimezone(UTC)
                    ),
                    seeing_score=r.seeing_score or 50.0,
                    temperature_f=r.temperature_f,
                    dew_point_f=r.dew_point_f,
                    humidity_percent=r.humidity_percent,
                    wind_speed_mph=r.wind_speed_mph,
                    cloud_cover_percent=r.cloud_cover_percent,
                )
                for r in db_rows_fallback
            ]
        return []


def fetch_weather(
    location: ObserverLocation,
    force_refresh: bool = False,
    max_cache_age: timedelta | None = timedelta(hours=2),
) -> WeatherData:
    """
    Fetch current weather data for the observer location.

    Checks database first using current location and current time.
    If not found, stale, or beyond the cache age threshold, fetches from Open-Meteo API and stores in database.
    """
    now = datetime.now(UTC)
    current_hour_start = now.replace(minute=0, second=0, microsecond=0)
    current_hour_end = current_hour_start + timedelta(hours=1)

    def _check_database_cache() -> WeatherForecastModel | None:
        from sqlalchemy import and_, select, text
        from sqlalchemy.exc import SQLAlchemyError

        from celestron_nexstar.api.database.database import get_database
        from celestron_nexstar.api.database.models import Base, WeatherForecastModel, get_db_session

        db = get_database()
        try:
            with get_db_session() as session:
                try:
                    session.execute(text("SELECT 1 FROM weather_forecast LIMIT 1"))
                except (AttributeError, RuntimeError, ValueError, TypeError, SQLAlchemyError) as e:
                    logger.debug(f"weather_forecast table not found, creating it... (error: {e})")
                    Base.metadata.create_all(
                        db._engine,
                        tables=[WeatherForecastModel.__table__],  # type: ignore[list-item]
                    )
        except (AttributeError, RuntimeError, ValueError, TypeError, OSError, SQLAlchemyError) as e:
            logger.debug(f"Could not check/create weather_forecast table: {e}")

        try:
            with get_db_session() as session:
                stmt = (
                    select(WeatherForecastModel)
                    .where(
                        and_(
                            WeatherForecastModel.latitude == location.latitude,
                            WeatherForecastModel.longitude == location.longitude,
                            WeatherForecastModel.forecast_timestamp >= current_hour_start.replace(tzinfo=None),
                            WeatherForecastModel.forecast_timestamp < current_hour_end.replace(tzinfo=None),
                        )
                    )
                    .order_by(WeatherForecastModel.fetched_at.desc(), WeatherForecastModel.forecast_timestamp.desc())
                )
                result = session.execute(stmt)
                candidates = result.scalars().all()

            for candidate in candidates:
                if candidate.forecast_timestamp.tzinfo is None:
                    candidate.forecast_timestamp = candidate.forecast_timestamp.replace(tzinfo=UTC)
                if candidate.fetched_at.tzinfo is None:
                    candidate.fetched_at = candidate.fetched_at.replace(tzinfo=UTC)

            for candidate in candidates:
                if not _is_forecast_stale(candidate, now):
                    if max_cache_age is not None:
                        fetched_at = candidate.fetched_at
                        if fetched_at.tzinfo is None:
                            fetched_at = fetched_at.replace(tzinfo=UTC)
                        elif fetched_at.tzinfo != UTC:
                            fetched_at = fetched_at.astimezone(UTC)
                        if (now - fetched_at) > max_cache_age:
                            continue
                    return candidate
        except (AttributeError, RuntimeError, ValueError, TypeError, KeyError, IndexError, SQLAlchemyError) as e:
            logger.debug(f"Error checking database for current weather: {e}")

        return None

    def _infer_condition_from_cache(forecast: WeatherForecastModel) -> str | None:
        try:
            if forecast.snowfall_cm is not None and forecast.snowfall_cm > 0:
                return "Snow"
            if forecast.rain_mm is not None and forecast.rain_mm > 0:
                return "Rain"
            if forecast.precipitation_mm is not None and forecast.precipitation_mm > 0:
                return "Rain"
            if forecast.visibility_m is not None and forecast.visibility_m < 1000:
                return "Foggy"
            cloud_cover = forecast.cloud_cover_percent
            if cloud_cover is None:
                return None
            if cloud_cover < 20:
                return "Clear"
            if cloud_cover < 60:
                return "Partly Cloudy"
            return "Cloudy"
        except Exception:
            return None

    try:
        existing = None if force_refresh else _check_database_cache()

        if existing:
            logger.debug("Using cached weather data from database")
            return WeatherData(
                temperature_c=existing.temperature_f,
                dew_point_f=existing.dew_point_f,
                humidity_percent=existing.humidity_percent,
                cloud_cover_percent=existing.cloud_cover_percent,
                wind_speed_ms=existing.wind_speed_mph,
                visibility_km=None,
                condition=_infer_condition_from_cache(existing),
                last_updated=existing.fetched_at.isoformat() if existing.fetched_at else None,
                cloud_cover_low=existing.cloud_cover_low_percent,
                cloud_cover_mid=existing.cloud_cover_mid_percent,
                cloud_cover_high=existing.cloud_cover_high_percent,
                visibility_m=existing.visibility_m,
                precipitation_probability=existing.precipitation_probability,
                cape=existing.cape,
                boundary_layer_height_m=existing.boundary_layer_height_m,
                freezing_level_height_m=existing.freezing_level_height_m,
                vapour_pressure_deficit=existing.vapour_pressure_deficit,
                wind_speed_80m_mph=existing.wind_speed_80m_mph,
                wind_speed_120m_mph=existing.wind_speed_120m_mph,
                precipitation_mm=existing.precipitation_mm,
                rain_mm=existing.rain_mm,
                snowfall_cm=existing.snowfall_cm,
                pressure_msl=existing.pressure_msl,
            )
    except (AttributeError, RuntimeError, ValueError, TypeError, KeyError, IndexError) as e:
        logger.debug(f"Error checking database for current weather: {e}")

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
                "cloud_cover_low",
                "cloud_cover_mid",
                "cloud_cover_high",
                "visibility",
                "precipitation_probability",
                "cape",
                "boundary_layer_height",
                "freezing_level_height",
                "vapour_pressure_deficit",
                "wind_speed_80m",
                "wind_speed_120m",
                "precipitation",
                "rain",
                "snowfall",
                "pressure_msl",
            ],
            "timezone": "auto",
            "wind_speed_unit": "mph",
            "temperature_unit": "fahrenheit",
            "forecast_days": 1,
        }

        response = requests.get(url, params=params, timeout=30)
        if response.status_code != 200:
            return WeatherData(error=f"HTTP {response.status_code}")

        data = response.json()
        current = data.get("current", {})
        hourly = data.get("hourly", {})

        def safe_float(value: float | None) -> float | None:
            if value is None:
                return None
            if np is not None and np.isnan(value):
                return None
            try:
                return float(value)
            except (ValueError, TypeError):
                return None

        temp_f = safe_float(current.get("temperature_2m"))
        humidity = safe_float(current.get("relative_humidity_2m"))
        cloud_cover = safe_float(current.get("cloud_cover"))
        wind_speed_mph = safe_float(current.get("wind_speed_10m"))
        weather_code = current.get("weather_code")

        hourly_time = hourly.get("time", [])
        hourly_index = 0
        current_time_str = current.get("time")
        if hourly_time and current_time_str:
            try:
                current_dt = datetime.fromisoformat(current_time_str.replace("Z", "+00:00"))
                if current_dt.tzinfo is None:
                    current_dt = current_dt.replace(tzinfo=UTC)
                hourly_dts = []
                for time_str in hourly_time:
                    try:
                        t = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                        if t.tzinfo is None:
                            t = t.replace(tzinfo=UTC)
                        hourly_dts.append(t)
                    except (ValueError, TypeError):
                        hourly_dts.append(None)
                diffs = [abs((t - current_dt).total_seconds()) if t is not None else float("inf") for t in hourly_dts]
                hourly_index = diffs.index(min(diffs)) if diffs else 0
            except (ValueError, TypeError):
                hourly_index = 0

        dew_point_values = hourly.get("dew_point_2m", [])
        dew_point_f = safe_float(dew_point_values[hourly_index]) if dew_point_values else None
        if dew_point_f is None and temp_f is not None and humidity is not None:
            dew_point_f = calculate_dew_point_fahrenheit(temp_f, humidity)

        cloud_low = safe_float(
            hourly.get("cloud_cover_low", [])[hourly_index] if hourly.get("cloud_cover_low") else None
        )
        cloud_mid = safe_float(
            hourly.get("cloud_cover_mid", [])[hourly_index] if hourly.get("cloud_cover_mid") else None
        )
        cloud_high = safe_float(
            hourly.get("cloud_cover_high", [])[hourly_index] if hourly.get("cloud_cover_high") else None
        )
        visibility_m = safe_float(hourly.get("visibility", [])[hourly_index] if hourly.get("visibility") else None)
        precip_prob = safe_float(
            hourly.get("precipitation_probability", [])[hourly_index]
            if hourly.get("precipitation_probability")
            else None
        )
        cape_val = safe_float(hourly.get("cape", [])[hourly_index] if hourly.get("cape") else None)
        blh = safe_float(
            hourly.get("boundary_layer_height", [])[hourly_index] if hourly.get("boundary_layer_height") else None
        )
        freezing = safe_float(
            hourly.get("freezing_level_height", [])[hourly_index] if hourly.get("freezing_level_height") else None
        )
        vpd = safe_float(
            hourly.get("vapour_pressure_deficit", [])[hourly_index] if hourly.get("vapour_pressure_deficit") else None
        )
        wind_80m = safe_float(hourly.get("wind_speed_80m", [])[hourly_index] if hourly.get("wind_speed_80m") else None)
        wind_120m = safe_float(
            hourly.get("wind_speed_120m", [])[hourly_index] if hourly.get("wind_speed_120m") else None
        )
        precip_mm = safe_float(hourly.get("precipitation", [])[hourly_index] if hourly.get("precipitation") else None)
        rain_mm = safe_float(hourly.get("rain", [])[hourly_index] if hourly.get("rain") else None)
        snow_cm = safe_float(hourly.get("snowfall", [])[hourly_index] if hourly.get("snowfall") else None)
        pressure = safe_float(hourly.get("pressure_msl", [])[hourly_index] if hourly.get("pressure_msl") else None)

        condition = None
        if weather_code is not None:
            code = int(weather_code)
            match code:
                case 0:
                    condition = "Clear"
                case 1 | 2 | 3:
                    condition = "Partly Cloudy"
                case 45 | 48:
                    condition = "Foggy"
                case 51 | 53 | 55 | 56 | 57:
                    condition = "Drizzle"
                case 61 | 63 | 65 | 66 | 67:
                    condition = "Rain"
                case 71 | 73 | 75 | 77:
                    condition = "Snow"
                case 80 | 81 | 82:
                    condition = "Rain Showers"
                case 85 | 86:
                    condition = "Snow Showers"
                case 95 | 96 | 99:
                    condition = "Thunderstorm"
                case _:
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
            cloud_cover_low=cloud_low,
            cloud_cover_mid=cloud_mid,
            cloud_cover_high=cloud_high,
            visibility_m=visibility_m,
            precipitation_probability=precip_prob,
            cape=cape_val,
            boundary_layer_height_m=blh,
            freezing_level_height_m=freezing,
            vapour_pressure_deficit=vpd,
            wind_speed_80m_mph=wind_80m,
            wind_speed_120m_mph=wind_120m,
            precipitation_mm=precip_mm,
            rain_mm=rain_mm,
            snowfall_cm=snow_cm,
            pressure_msl=pressure,
        )

        if not weather_data.error:

            def _store_weather_in_db(weather_to_store: WeatherData) -> None:
                from sqlalchemy import and_, delete, select
                from sqlalchemy.exc import SQLAlchemyError

                from celestron_nexstar.api.database.database import get_database
                from celestron_nexstar.api.database.models import Base, WeatherForecastModel, get_db_session
                from celestron_nexstar.api.location.geohash_utils import encode

                db = get_database()
                try:
                    Base.metadata.create_all(
                        db._engine,
                        tables=[WeatherForecastModel.__table__],  # type: ignore[list-item]
                        checkfirst=True,
                    )

                    location_geohash = encode(location.latitude, location.longitude, precision=9)
                    now_db = datetime.now(UTC)
                    current_hour_start_db = now_db.replace(minute=0, second=0, microsecond=0)
                    current_hour_end_db = current_hour_start_db + timedelta(hours=1)

                    with get_db_session() as session:
                        stmt = (
                            select(WeatherForecastModel)
                            .where(
                                and_(
                                    WeatherForecastModel.latitude == location.latitude,
                                    WeatherForecastModel.longitude == location.longitude,
                                    WeatherForecastModel.forecast_timestamp
                                    >= current_hour_start_db.replace(tzinfo=None),
                                    WeatherForecastModel.forecast_timestamp < current_hour_end_db.replace(tzinfo=None),
                                )
                            )
                            .limit(1)
                        )
                        result = session.execute(stmt)
                        current_hour_start_naive = (
                            current_hour_start_db.replace(tzinfo=None)
                            if current_hour_start_db.tzinfo
                            else current_hour_start_db
                        )
                        now_db_naive = now_db.replace(tzinfo=None) if now_db.tzinfo else now_db

                        existing = result.scalar_one_or_none()
                        if existing:
                            session.execute(
                                delete(WeatherForecastModel).where(
                                    and_(
                                        WeatherForecastModel.latitude == location.latitude,
                                        WeatherForecastModel.longitude == location.longitude,
                                        WeatherForecastModel.forecast_timestamp == existing.forecast_timestamp,
                                        WeatherForecastModel.id != existing.id,
                                    )
                                )
                            )
                        else:
                            session.execute(
                                delete(WeatherForecastModel).where(
                                    and_(
                                        WeatherForecastModel.latitude == location.latitude,
                                        WeatherForecastModel.longitude == location.longitude,
                                        WeatherForecastModel.forecast_timestamp == current_hour_start_naive,
                                    )
                                )
                            )

                        seeing_score = calculate_seeing_conditions(weather_to_store)

                        if existing:
                            existing.geohash = location_geohash
                            existing.temperature_f = weather_to_store.temperature_c
                            existing.dew_point_f = weather_to_store.dew_point_f
                            existing.humidity_percent = weather_to_store.humidity_percent
                            existing.cloud_cover_percent = weather_to_store.cloud_cover_percent
                            existing.wind_speed_mph = weather_to_store.wind_speed_ms
                            existing.seeing_score = seeing_score
                            existing.fetched_at = now_db_naive
                            existing.cloud_cover_low_percent = weather_to_store.cloud_cover_low
                            existing.cloud_cover_mid_percent = weather_to_store.cloud_cover_mid
                            existing.cloud_cover_high_percent = weather_to_store.cloud_cover_high
                            existing.visibility_m = weather_to_store.visibility_m
                            existing.precipitation_probability = weather_to_store.precipitation_probability
                            existing.cape = weather_to_store.cape
                            existing.boundary_layer_height_m = weather_to_store.boundary_layer_height_m
                            existing.freezing_level_height_m = weather_to_store.freezing_level_height_m
                            existing.vapour_pressure_deficit = weather_to_store.vapour_pressure_deficit
                            existing.wind_speed_80m_mph = weather_to_store.wind_speed_80m_mph
                            existing.wind_speed_120m_mph = weather_to_store.wind_speed_120m_mph
                            existing.precipitation_mm = weather_to_store.precipitation_mm
                            existing.rain_mm = weather_to_store.rain_mm
                            existing.snowfall_cm = weather_to_store.snowfall_cm
                            existing.pressure_msl = weather_to_store.pressure_msl
                        else:
                            db_forecast = WeatherForecastModel(
                                latitude=location.latitude,
                                longitude=location.longitude,
                                geohash=location_geohash,
                                forecast_timestamp=current_hour_start_naive,
                                temperature_f=weather_to_store.temperature_c,
                                dew_point_f=weather_to_store.dew_point_f,
                                humidity_percent=weather_to_store.humidity_percent,
                                cloud_cover_percent=weather_to_store.cloud_cover_percent,
                                wind_speed_mph=weather_to_store.wind_speed_ms,
                                seeing_score=seeing_score,
                                fetched_at=now_db_naive,
                                cloud_cover_low_percent=weather_to_store.cloud_cover_low,
                                cloud_cover_mid_percent=weather_to_store.cloud_cover_mid,
                                cloud_cover_high_percent=weather_to_store.cloud_cover_high,
                                visibility_m=weather_to_store.visibility_m,
                                precipitation_probability=weather_to_store.precipitation_probability,
                                cape=weather_to_store.cape,
                                boundary_layer_height_m=weather_to_store.boundary_layer_height_m,
                                freezing_level_height_m=weather_to_store.freezing_level_height_m,
                                vapour_pressure_deficit=weather_to_store.vapour_pressure_deficit,
                                wind_speed_80m_mph=weather_to_store.wind_speed_80m_mph,
                                wind_speed_120m_mph=weather_to_store.wind_speed_120m_mph,
                                precipitation_mm=weather_to_store.precipitation_mm,
                                rain_mm=weather_to_store.rain_mm,
                                snowfall_cm=weather_to_store.snowfall_cm,
                                pressure_msl=weather_to_store.pressure_msl,
                            )
                            session.add(db_forecast)

                        session.commit()
                        logger.debug("Stored current weather in database")
                except (AttributeError, RuntimeError, ValueError, TypeError, KeyError, SQLAlchemyError) as e:
                    logger.warning(f"Error storing current weather in database: {e}")

            _store_weather_in_db(weather_data)

        return weather_data

    except (
        requests.RequestException,
        TimeoutError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        AttributeError,
        RuntimeError,
    ) as e:
        logger.exception("Error fetching weather from Open-Meteo")
        return WeatherData(error=f"Error fetching weather: {e}")


def fetch_weather_batch(locations: list[ObserverLocation]) -> dict[ObserverLocation, WeatherData]:
    """
    Fetch weather data for multiple locations.

    Args:
        locations: List of observer locations

    Returns:
        Dictionary mapping locations to WeatherData
    """
    data_map: dict[ObserverLocation, WeatherData] = {}
    for location in locations:
        try:
            result = fetch_weather(location)
            if isinstance(result, WeatherData):
                data_map[location] = result
            else:
                data_map[location] = WeatherData(error=f"Unexpected weather result: {type(result).__name__}")
        except Exception as e:
            logger.error(f"Error fetching weather for {location}: {e}")
            data_map[location] = WeatherData(error=f"Error: {e}")

    return data_map


def fetch_historical_weather_climatology(
    location: ObserverLocation,
    start_year: int = 2000,
    end_year: int | None = None,
    required_months: set[int] | None = None,
) -> dict[int, dict[str, float | None]] | None:
    """
    Fetch historical weather climatology data from Open-Meteo Historical API.

    Retrieves monthly average cloud cover statistics for a location.
    Data is cached in the database for future use. Only fetches from API if
    required months are missing from the database.

    Args:
        location: Observer location
        start_year: Start year for historical data (default: 2000)
        end_year: End year for historical data (default: current year - 1)
        required_months: Set of month numbers (1-12) that are required. If None, all 12 months are required.
                        Only fetches from API if any required months are missing from database.

    Returns:
        Dictionary mapping month (1-12) to cloud cover statistics, or None if fetch fails
        Statistics include: avg, min, max, p25, p75
    """
    if end_year is None:
        end_year = datetime.now(UTC).year - 1  # Use last complete year

    if required_months is None:
        required_months = set(range(1, 13))  # All 12 months

    # Check database first
    from sqlalchemy import and_, select

    from celestron_nexstar.api.database.database import get_database
    from celestron_nexstar.api.location.geohash_utils import encode

    get_database()
    monthly_stats: dict[int, dict[str, float | None]] = {}
    months_in_db: set[int] = set()

    try:
        from celestron_nexstar.api.database.models import get_db_session

        with get_db_session() as session:
            # Check what months we have in the database
            stmt = (
                select(HistoricalWeatherModel)
                .where(
                    and_(
                        HistoricalWeatherModel.latitude == location.latitude,
                        HistoricalWeatherModel.longitude == location.longitude,
                    )
                )
                .order_by(HistoricalWeatherModel.month)
            )
            result = session.execute(stmt)
            existing_data = result.scalars().all()

            # Build dictionary of months we have
            for record in existing_data:
                months_in_db.add(record.month)
                monthly_stats[record.month] = {
                    "avg": record.avg_cloud_cover_percent,
                    "min": record.min_cloud_cover_percent,
                    "max": record.max_cloud_cover_percent,
                    "p25": record.p25_cloud_cover_percent,
                    "p40": record.p40_cloud_cover_percent,
                    "p60": record.p60_cloud_cover_percent,
                    "p75": record.p75_cloud_cover_percent,
                    "std_dev": record.std_dev_cloud_cover_percent,
                }

            # Check if we have all required months
            missing_months = required_months - months_in_db
            if not missing_months:
                # We have all required months in the database
                logger.debug(
                    f"Using cached historical weather data for location {location.latitude}, {location.longitude} "
                    f"(all {len(required_months)} required months available)"
                )
                return monthly_stats

            # We're missing some months - need to fetch from API
            logger.debug(
                f"Missing {len(missing_months)} months in database for location {location.latitude}, {location.longitude}. "
                f"Fetching from API (will get all 12 months)."
            )
    except (AttributeError, RuntimeError, ValueError, TypeError, KeyError, IndexError) as e:
        # AttributeError: missing database/model attributes
        # RuntimeError: database connection errors
        # ValueError: invalid data format
        # TypeError: wrong argument types
        # KeyError: missing keys in data
        # IndexError: missing array indices
        logger.debug(f"Error checking database for historical weather: {e}")
        # If database check fails, proceed to fetch from API

    # Fetch from Open-Meteo Historical API
    # Note: The API returns all 12 months in one call, so we fetch all months even if we only need some.
    # This is more efficient than making multiple API calls, and we cache all months for future use.
    logger.debug(f"Fetching historical weather data from Open-Meteo for {location.latitude}, {location.longitude}")
    try:
        url = "https://archive-api.open-meteo.com/v1/archive"
        params: dict[str, str | int | float] = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "start_date": f"{start_year}-01-01",
            "end_date": f"{end_year}-12-31",
            "hourly": "cloud_cover",
            "timezone": "auto",
        }

        response = requests.get(url, params=params, timeout=30)
        if response.status_code != 200:
            logger.warning(f"Open-Meteo Historical API returned status {response.status_code}")
            return None

        data = response.json()

        # Process hourly data to calculate monthly statistics
        hourly = data.get("hourly", {})
        hourly_time = hourly.get("time", [])
        hourly_cloud_cover = hourly.get("cloud_cover", [])

        if not hourly_time or not hourly_cloud_cover:
            logger.warning("No hourly data in Open-Meteo Historical API response")
            return None

        # Group data by month and calculate statistics
        monthly_data: dict[int, list[float]] = {month: [] for month in range(1, 13)}

        for i, time_str in enumerate(hourly_time):
            if i >= len(hourly_cloud_cover):
                break

            try:
                time_dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                month = time_dt.month
                cloud_cover = hourly_cloud_cover[i]

                if cloud_cover is not None and not (np is not None and np.isnan(cloud_cover)):
                    monthly_data[month].append(float(cloud_cover))
            except (ValueError, TypeError, IndexError):
                continue

        # Calculate statistics for each month
        # Note: monthly_stats may already contain some months from the database
        # We'll update/add all months from the API, but preserve existing database data if API fails for a month
        now_db = datetime.now(UTC)
        years_of_data = end_year - start_year + 1
        geohash = encode(location.latitude, location.longitude, precision=9)

        for month in range(1, 13):
            values = monthly_data[month]
            if not values:
                # No data for this month from API
                # If we don't have it in database either, use None
                if month not in monthly_stats:
                    monthly_stats[month] = {
                        "avg": None,
                        "min": None,
                        "max": None,
                        "p25": None,
                        "p40": None,
                        "p60": None,
                        "p75": None,
                        "std_dev": None,
                    }
                # Otherwise, keep the existing database data
                continue

            # Calculate statistics
            values_sorted = sorted(values)
            n = len(values_sorted)

            avg = sum(values) / n
            min_val = values_sorted[0]
            max_val = values_sorted[-1]

            # Calculate percentiles
            p25_idx = int(n * 0.25)
            p40_idx = int(n * 0.40)
            p60_idx = int(n * 0.60)
            p75_idx = int(n * 0.75)
            p25 = values_sorted[p25_idx] if p25_idx < n else None
            p40 = values_sorted[p40_idx] if p40_idx < n else None
            p60 = values_sorted[p60_idx] if p60_idx < n else None
            p75 = values_sorted[p75_idx] if p75_idx < n else None

            # Calculate standard deviation
            if n > 1:
                variance = sum((x - avg) ** 2 for x in values) / (n - 1)
                std_dev = variance**0.5
            else:
                std_dev = None

            # Update/add this month's statistics (overwrite database data with fresh API data)
            monthly_stats[month] = {
                "avg": avg,
                "min": min_val,
                "max": max_val,
                "p25": p25,
                "p40": p40,
                "p60": p60,
                "p75": p75,
                "std_dev": std_dev,
            }

            # Store in database
            try:
                from celestron_nexstar.api.database.models import get_db_session

                with get_db_session() as session:
                    # Check if record exists
                    stmt = (
                        select(HistoricalWeatherModel)
                        .where(
                            and_(
                                HistoricalWeatherModel.latitude == location.latitude,
                                HistoricalWeatherModel.longitude == location.longitude,
                                HistoricalWeatherModel.month == month,
                            )
                        )
                        .limit(1)
                    )
                    result = session.execute(stmt)
                    existing = result.scalar_one_or_none()

                    if existing:
                        # Update existing record
                        existing.geohash = geohash
                        existing.avg_cloud_cover_percent = avg
                        existing.min_cloud_cover_percent = min_val
                        existing.max_cloud_cover_percent = max_val
                        existing.p25_cloud_cover_percent = p25
                        existing.p40_cloud_cover_percent = p40
                        existing.p60_cloud_cover_percent = p60
                        existing.p75_cloud_cover_percent = p75
                        existing.std_dev_cloud_cover_percent = std_dev
                        existing.years_of_data = years_of_data
                        existing.fetched_at = now_db
                    else:
                        # Insert new record
                        new_record = HistoricalWeatherModel(
                            latitude=location.latitude,
                            longitude=location.longitude,
                            geohash=geohash,
                            month=month,
                            avg_cloud_cover_percent=avg,
                            min_cloud_cover_percent=min_val,
                            max_cloud_cover_percent=max_val,
                            p25_cloud_cover_percent=p25,
                            p40_cloud_cover_percent=p40,
                            p60_cloud_cover_percent=p60,
                            p75_cloud_cover_percent=p75,
                            std_dev_cloud_cover_percent=std_dev,
                            years_of_data=years_of_data,
                            fetched_at=now_db,
                        )
                        session.add(new_record)

                    session.commit()
            except (AttributeError, RuntimeError, ValueError, TypeError, KeyError) as e:
                # AttributeError: missing database/model attributes
                # RuntimeError: database connection/commit errors
                # ValueError: invalid data format
                # TypeError: wrong argument types
                # KeyError: missing keys in data
                logger.warning(f"Error storing historical weather data for month {month}: {e}")

        logger.debug(f"Fetched and stored historical weather data for {years_of_data} years")
        return monthly_stats

    except (
        requests.RequestException,
        TimeoutError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        AttributeError,
        RuntimeError,
    ) as e:
        # requests.RequestException: HTTP/network errors
        # TimeoutError: request timeout
        # ValueError: invalid JSON or data format
        # TypeError: wrong data types
        # KeyError: missing keys in response
        # IndexError: missing array indices
        # AttributeError: missing attributes in response
        # RuntimeError: other errors
        logger.warning(f"Error fetching historical weather from Open-Meteo: {e}")
        return None


def get_historical_cloud_cover_for_month(
    location: ObserverLocation,
    month: int,
    use_tighter_range: bool = True,
) -> tuple[float | None, float | None, float | None] | None:
    """
    Get historical cloud cover statistics for a specific month.

    Checks database first, fetches from API if not available.

    Args:
        location: Observer location
        month: Month (1-12)
        use_tighter_range: If True, use p40-p60 (tighter range). If False, use p25-p75 (wider range).

    Returns:
        Tuple of (best_case_cloud_cover, worst_case_cloud_cover, std_dev) percentages, or None if unavailable
        Uses p40-p60 (tighter) or p25-p75 (wider) based on use_tighter_range parameter
    """
    # Check database first
    from sqlalchemy import and_, select

    from celestron_nexstar.api.database.database import get_database

    get_database()
    try:
        from celestron_nexstar.api.database.models import get_db_session

        with get_db_session() as session:
            stmt = (
                select(HistoricalWeatherModel)
                .where(
                    and_(
                        HistoricalWeatherModel.latitude == location.latitude,
                        HistoricalWeatherModel.longitude == location.longitude,
                        HistoricalWeatherModel.month == month,
                    )
                )
                .limit(1)
            )
            result = session.execute(stmt)
            record = result.scalar_one_or_none()

            if record:
                if use_tighter_range:
                    # Use p40-p60 for tighter range, but fall back to p25-p75 if not available
                    # Check if p40/p60 exist (might not if migration hasn't been run or data is old)
                    try:
                        p40 = getattr(record, "p40_cloud_cover_percent", None)
                        p60 = getattr(record, "p60_cloud_cover_percent", None)
                        if p40 is not None and p60 is not None:
                            std_dev = getattr(record, "std_dev_cloud_cover_percent", None)
                            return (p40, p60, std_dev)
                    except AttributeError:
                        pass  # Columns don't exist, fall through to p25-p75

                    # Fall back to p25-p75 if p40-p60 not available (e.g., old data before migration)
                    if record.p25_cloud_cover_percent is not None and record.p75_cloud_cover_percent is not None:
                        logger.debug(f"Using p25-p75 for month {month} (p40-p60 not available)")
                        std_dev = getattr(record, "std_dev_cloud_cover_percent", None)
                        return (record.p25_cloud_cover_percent, record.p75_cloud_cover_percent, std_dev)
                else:
                    # Use p25-p75 for wider range
                    if record.p25_cloud_cover_percent is not None and record.p75_cloud_cover_percent is not None:
                        std_dev = getattr(record, "std_dev_cloud_cover_percent", None)
                        return (record.p25_cloud_cover_percent, record.p75_cloud_cover_percent, std_dev)
    except (AttributeError, ValueError, TypeError) as e:
        # AttributeError: missing database attributes
        # ValueError: invalid month or location data
        # TypeError: wrong argument types
        logger.debug(f"Error checking database for historical weather month {month}: {e}")

    # If not in database, try to fetch all months (more efficient than fetching one at a time)
    monthly_stats = fetch_historical_weather_climatology(location)
    if monthly_stats and month in monthly_stats:
        stats = monthly_stats[month]
        if use_tighter_range:
            p40 = stats.get("p40")
            p60 = stats.get("p60")
            if p40 is not None and p60 is not None:
                return (p40, p60, stats.get("std_dev"))
            # Fall back to p25-p75 if p40-p60 not available
            p25 = stats.get("p25")
            p75 = stats.get("p75")
            if p25 is not None and p75 is not None:
                logger.debug(f"Using p25-p75 for month {month} (p40-p60 not available)")
                return (p25, p75, stats.get("std_dev"))
        else:
            p25 = stats.get("p25")
            p75 = stats.get("p75")
            if p25 is not None and p75 is not None:
                return (p25, p75, stats.get("std_dev"))

    return None

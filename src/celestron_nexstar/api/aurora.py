"""
Aurora Borealis (Northern Lights) Visibility

Provides aurora visibility forecasts based on geomagnetic activity (Kp index),
location, weather conditions, and moon phase. Includes long-term probabilistic
forecasting based on solar cycle and historical patterns.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import requests_cache
from retry_requests import retry


if TYPE_CHECKING:
    from .observer import ObserverLocation

logger = logging.getLogger(__name__)

__all__ = [
    "AuroraForecast",
    "AuroraProbability",
    "check_aurora_visibility",
    "get_aurora_forecast",
    "get_aurora_visibility_windows",
    "get_next_aurora_opportunity",
    "get_solar_cycle_info",
]


@dataclass
class AuroraForecast:
    """Aurora visibility forecast for a specific time."""

    timestamp: datetime
    kp_index: float  # Geomagnetic Kp index (0-9)
    visibility_level: str  # "none", "low", "moderate", "high", "very_high"
    latitude_required: float  # Minimum latitude where visible (auroral boundary)
    is_visible: bool  # Whether aurora is visible at observer's location
    visibility_probability: float  # Probability of visibility (0.0-1.0) using AgentCalc algorithm
    cloud_cover_percent: float | None = None
    moon_illumination: float | None = None
    bortle_class: int | None = None  # Bortle class (1-9) for light pollution adjustment
    sqm_value: float | None = None  # SQM value (mag/arcsec²) for verification
    is_dark: bool = True  # Whether it's dark enough (after sunset, before sunrise)
    peak_viewing_start: datetime | None = None  # Start of best viewing window
    peak_viewing_end: datetime | None = None  # End of best viewing window
    is_forecasted: bool = False  # Whether Kp is forecasted (vs observed)


@dataclass
class AuroraProbability:
    """Probabilistic aurora forecast for a future time period."""

    start_date: datetime
    end_date: datetime
    month: int  # 1-12
    season: str  # "Spring", "Summer", "Fall", "Winter"
    probability_kp_5: float  # Probability of Kp ≥ 5 (moderate activity)
    probability_kp_6: float  # Probability of Kp ≥ 6 (high activity)
    probability_kp_7: float  # Probability of Kp ≥ 7 (very high activity)
    probability_kp_8: float  # Probability of Kp ≥ 8 (extreme activity)
    expected_max_kp: float  # Expected maximum Kp during period
    solar_cycle_factor: float  # Solar cycle activity multiplier (0.0-1.0)
    seasonal_factor: float  # Seasonal activity multiplier (0.0-1.0)
    confidence: str  # "low", "medium", "high" - confidence in prediction
    notes: str  # Additional context about the prediction


@dataclass
class SolarCycleInfo:
    """Information about the current solar cycle."""

    cycle_number: int  # Current cycle (e.g., 25)
    cycle_start: datetime  # When cycle started
    cycle_peak: datetime  # Estimated peak of cycle
    cycle_end: datetime  # Estimated end of cycle
    current_phase: float  # 0.0 (start) to 1.0 (end)
    activity_level: str  # "minimum", "rising", "maximum", "declining"
    years_since_peak: float  # Years since/until peak
    activity_multiplier: float  # 0.0-1.0 multiplier for aurora activity


def _get_kp_forecast(days: int = 3) -> list[tuple[datetime, float]] | None:
    """
    Fetch Kp index forecast from NOAA Space Weather Prediction Center.

    Args:
        days: Number of days to forecast (default: 3, max: 3)

    Returns:
        List of (datetime, kp_value) tuples, or None if unavailable
    """
    try:
        # Setup cached session
        cache_dir = Path.home() / ".cache" / "celestron-nexstar"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_session = requests_cache.CachedSession(
            str(cache_dir / "aurora_cache"),
            expire_after=1800,  # 30 minutes
        )
        retry_session = retry(cache_session, retries=3, backoff_factor=0.2)

        # NOAA Space Weather Prediction Center - 3-day forecast
        url = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"
        response = retry_session.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Format: First row is header ["time_tag","kp","observed","noaa_scale"]
        # Subsequent rows: ["YYYY-MM-DD HH:MM:SS", "kp_value", "observed/predicted", "noaa_scale"]
        forecast_data = []
        if data and len(data) > 1:  # First row is header
            now = datetime.now(UTC)
            cutoff_time = now + timedelta(days=days)

            for row in data[1:]:  # Skip header
                if len(row) >= 2:
                    try:
                        time_str = row[0]
                        kp_str = row[1]

                        # Parse time (format: "YYYY-MM-DD HH:MM:SS")
                        forecast_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)

                        # Only include future predictions
                        if forecast_time > now and forecast_time <= cutoff_time:
                            kp_value = float(kp_str)
                            forecast_data.append((forecast_time, kp_value))
                    except (ValueError, IndexError, TypeError) as e:
                        logger.debug(f"Error parsing NOAA Kp forecast row: {e}")
                        continue

            if forecast_data:
                # Sort by time
                forecast_data.sort(key=lambda x: x[0])
                return forecast_data

        return None
    except Exception as e:
        logger.error(f"Error fetching Kp forecast: {e}")
        return None


def _get_kp_index() -> float | None:
    """
    Fetch current Kp index from NOAA Space Weather Prediction Center.

    Returns:
        Current Kp index (0-9) or None if unavailable
    """
    try:
        # Setup cached session
        cache_dir = Path.home() / ".cache" / "celestron-nexstar"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_session = requests_cache.CachedSession(
            str(cache_dir / "aurora_cache"),
            expire_after=1800,  # 30 minutes
        )
        retry_session = retry(cache_session, retries=3, backoff_factor=0.2)

        # Try NOAA SWPC API first (most reliable)
        try:
            # NOAA Space Weather Prediction Center - 3-day forecast
            url = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"
            response = retry_session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Format: First row is header ["time_tag","kp","observed","noaa_scale"]
            # Subsequent rows: ["YYYY-MM-DD HH:MM:SS", "kp_value", "observed/predicted", "noaa_scale"]
            if data and len(data) > 1:  # First row is header
                # Find the most recent forecast entry (prefer observed, then predicted)
                latest_observed = None
                latest_observed_time = None
                latest_predicted = None
                latest_predicted_time = None

                for row in data[1:]:  # Skip header
                    if len(row) >= 3:
                        try:
                            # Format: ["YYYY-MM-DD HH:MM:SS", "kp_value", "observed/predicted", "noaa_scale"]
                            time_str = row[0]
                            kp_str = row[1]
                            status = row[2] if len(row) > 2 else "predicted"

                            # Parse time (format: "YYYY-MM-DD HH:MM:SS")
                            forecast_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
                            kp_value = float(kp_str)

                            if status == "observed":
                                if latest_observed_time is None or forecast_time > latest_observed_time:
                                    latest_observed_time = forecast_time
                                    latest_observed = kp_value
                            else:  # predicted
                                if latest_predicted_time is None or forecast_time > latest_predicted_time:
                                    latest_predicted_time = forecast_time
                                    latest_predicted = kp_value
                        except (ValueError, IndexError, TypeError) as e:
                            logger.debug(f"Error parsing NOAA Kp data row: {e}")
                            continue

                # Prefer observed data, fall back to predicted
                if latest_observed is not None:
                    return latest_observed
                elif latest_predicted is not None:
                    return latest_predicted
        except Exception as e:
            logger.debug(f"NOAA SWPC API failed: {e}, trying alternative")

        # Fallback: Try alternative NOAA endpoint (current Kp)
        try:
            url = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
            response = retry_session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Format: Header ["time_tag","Kp","a_running","station_count"]
            # Data rows: ["YYYY-MM-DD HH:MM:SS.000", "Kp_value", "a_running", "station_count"]
            if data and len(data) > 1:
                # Get the most recent entry (last row)
                last_row = data[-1]
                if len(last_row) >= 2:
                    try:
                        kp_str = last_row[1]
                        return float(kp_str)
                    except (ValueError, IndexError, TypeError):
                        pass
        except Exception as e:
            logger.debug(f"NOAA current Kp API failed: {e}")

        logger.warning("Could not fetch Kp index from any source")
        return None

    except Exception as e:
        logger.error(f"Error fetching Kp index: {e}")
        return None


def _kp_to_auroral_boundary(kp: float) -> float:
    """
    Calculate auroral boundary latitude using AgentCalc formula.

    Uses the continuous formula: φ_b = 66 - 3K
    where K is the Kp index (0-9) and φ_b is the equatorward boundary
    of the auroral oval in degrees latitude.

    Reference: https://agentcalc.com/aurora-visibility-calculator

    Args:
        kp: Kp index (0-9)

    Returns:
        Auroral boundary latitude in degrees (absolute value)
    """
    # Clamp Kp to valid range
    kp = max(0.0, min(9.0, kp))

    # AgentCalc formula: φ_b = 66 - 3K
    boundary_lat = 66.0 - (3.0 * kp)

    # Clamp to reasonable bounds (aurora can't go below ~30° even at Kp 9)
    return max(30.0, min(75.0, boundary_lat))


def _calculate_aurora_probability(
    observer_lat: float,
    kp: float,
    cloud_cover_percent: float | None = None,
    bortle_class: int | None = None,
    moon_illumination: float | None = None,
) -> float:
    """
    Calculate aurora visibility probability using AgentCalc logistic model.

    Uses the logistic probability function:
    P = 1 / (1 + e^(-(φ - φ_b)))

    Then applies multiplicative adjustments for:
    - Cloud cover: (1 - C/100)
    - Light pollution (Bortle): (1 - B/12)
    - Moon illumination: (1 - M/200)

    Reference: https://agentcalc.com/aurora-visibility-calculator

    Args:
        observer_lat: Observer latitude in degrees (absolute value used)
        kp: Kp index (0-9)
        cloud_cover_percent: Cloud cover percentage (0-100), None if unknown
        bortle_class: Bortle class (1-9), None if unknown
        moon_illumination: Moon illumination fraction (0.0-1.0), None if unknown

    Returns:
        Probability of visibility (0.0-1.0)
    """
    import math

    # Use absolute latitude
    observer_lat = abs(observer_lat)

    # Calculate auroral boundary
    boundary_lat = _kp_to_auroral_boundary(kp)

    # Calculate latitude difference (how far north of boundary)
    lat_diff = observer_lat - boundary_lat

    # Logistic probability function: P = 1 / (1 + e^(-(φ - φ_b)))
    # This gives high probability when observer is well north of boundary
    base_probability = 1.0 / (1.0 + math.exp(-lat_diff))

    # Apply multiplicative adjustments
    adjusted_probability = base_probability

    # Cloud cover adjustment: (1 - C/100)
    if cloud_cover_percent is not None:
        cloud_factor = 1.0 - (cloud_cover_percent / 100.0)
        adjusted_probability *= max(0.0, cloud_factor)

    # Light pollution (Bortle class) adjustment: (1 - B/12)
    if bortle_class is not None:
        bortle_factor = 1.0 - (bortle_class / 12.0)
        adjusted_probability *= max(0.0, bortle_factor)

    # Moon illumination adjustment: (1 - M/200)
    # Convert moon illumination fraction (0.0-1.0) to percentage
    if moon_illumination is not None:
        moon_percent = moon_illumination * 100.0
        moon_factor = 1.0 - (moon_percent / 200.0)
        adjusted_probability *= max(0.0, moon_factor)

    # Clamp to [0, 1]
    return max(0.0, min(1.0, adjusted_probability))


def _kp_to_visibility_level(kp: float) -> str:
    """
    Get visibility level description based on Kp index.

    Args:
        kp: Kp index (0-9)

    Returns:
        Visibility level string
    """
    if kp >= 8.0:
        return "very_high"
    elif kp >= 6.0:
        return "high"
    elif kp >= 5.0:
        return "moderate"
    elif kp >= 3.0:
        return "low"
    else:
        return "none"


def get_aurora_forecast(
    location: ObserverLocation,
    dt: datetime | None = None,
    cloud_cover_percent: float | None = None,
    moon_illumination: float | None = None,
    bortle_class: int | None = None,
    is_dark: bool = True,
) -> AuroraForecast | None:
    """
    Get aurora visibility forecast for a specific location and time.

    Args:
        location: Observer location with latitude and longitude
        dt: Datetime to check (default: now)
        cloud_cover_percent: Current cloud cover percentage (0-100)
        moon_illumination: Moon illumination fraction (0.0-1.0)
        is_dark: Whether it's dark enough (after sunset, before sunrise)

    Returns:
        AuroraForecast object or None if Kp index unavailable
    """
    if dt is None:
        dt = datetime.now(UTC)

    # Normalize dt to UTC
    dt_utc = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    now_utc = datetime.now(UTC)

    # Try to get forecasted Kp if checking future time, or if checking "tonight"
    # (even if current time is during the day, we want tonight's forecast)
    kp = None
    peak_viewing_start = None
    peak_viewing_end = None
    is_forecasted = False
    is_future = dt_utc > now_utc
    is_tonight_check = not is_future and is_dark  # Current time is during nighttime
    is_tonight_forecast = not is_future and not is_dark  # Current time is daytime, checking tonight

    if is_future or is_tonight_check or is_tonight_forecast:
        # For future times or "tonight" checks, try to get forecasted Kp
        forecast_data = _get_kp_forecast(days=3)
        if forecast_data:
            # If checking "tonight" (current nighttime or tonight's forecast), get max Kp during nighttime period
            if is_dark or is_tonight_forecast:
                try:
                    from .sun_moon import calculate_sun_times

                    # For "tonight" forecast during daytime, use today's sunset/sunrise
                    # For current nighttime, use current dt
                    check_time = dt_utc if is_dark else now_utc
                    sun_times = calculate_sun_times(location.latitude, location.longitude, check_time)
                    sunset = sun_times.get("sunset")
                    sunrise = sun_times.get("sunrise")

                    if sunset and sunrise:
                        sunset_utc = sunset.replace(tzinfo=UTC) if sunset.tzinfo is None else sunset.astimezone(UTC)
                        sunrise_utc = sunrise.replace(tzinfo=UTC) if sunrise.tzinfo is None else sunrise.astimezone(UTC)

                        # For "tonight" forecast during daytime, sunrise might be next day
                        if is_tonight_forecast and sunrise_utc < sunset_utc:
                            sunrise_utc = sunrise_utc + timedelta(days=1)

                        # Find max Kp during nighttime period (tonight)
                        max_kp = None
                        for forecast_time, forecast_kp in forecast_data:
                            # Check if forecast time is during tonight's nighttime period
                            if sunset_utc <= sunrise_utc:  # Normal case
                                if (sunset_utc <= forecast_time <= sunrise_utc) and (
                                    max_kp is None or forecast_kp > max_kp
                                ):
                                    max_kp = forecast_kp
                            else:  # Polar regions (sunset after sunrise)
                                if (forecast_time >= sunset_utc or forecast_time <= sunrise_utc) and (
                                    max_kp is None or forecast_kp > max_kp
                                ):
                                    max_kp = forecast_kp

                        if max_kp is not None:
                            kp = max_kp
                            logger.debug(
                                f"Using max forecasted Kp {kp:.1f} during tonight's nighttime period (sunset: {sunset_utc}, sunrise: {sunrise_utc})"
                            )

                            # Find time window when Kp is highest (peak viewing window)
                            # Look for consecutive hours with Kp >= max_kp - 0.5
                            high_kp_periods = []
                            current_start = None
                            for forecast_time, forecast_kp in forecast_data:
                                if sunset_utc <= forecast_time <= sunrise_utc and forecast_kp >= max_kp - 0.5:
                                    if current_start is None:
                                        current_start = forecast_time
                                else:
                                    if current_start is not None:
                                        high_kp_periods.append((current_start, forecast_time))
                                        current_start = None
                            if current_start is not None:
                                high_kp_periods.append((current_start, sunrise_utc))

                            if high_kp_periods:
                                # Use the longest period, or the one closest to midnight
                                best_period = max(high_kp_periods, key=lambda p: (p[1] - p[0]).total_seconds())
                                peak_viewing_start = best_period[0]
                                peak_viewing_end = best_period[1]
                                is_forecasted = True
                            else:
                                peak_viewing_start = None
                                peak_viewing_end = None
                                is_forecasted = False
                        else:
                            peak_viewing_start = None
                            peak_viewing_end = None
                            is_forecasted = False
                    else:
                        peak_viewing_start = None
                        peak_viewing_end = None
                        is_forecasted = False
                except Exception as e:
                    logger.debug(f"Could not calculate nighttime Kp max: {e}")
                    peak_viewing_start = None
                    peak_viewing_end = None
                    is_forecasted = False

            # If we don't have a nighttime max, try to get Kp closest to the target time
            if kp is None:
                # Find forecast entry closest to target time
                closest_time = None
                closest_kp = None
                min_diff = None
                for forecast_time, forecast_kp in forecast_data:
                    diff = abs((forecast_time - dt_utc).total_seconds())
                    if min_diff is None or diff < min_diff:
                        min_diff = diff
                        closest_time = forecast_time
                        closest_kp = forecast_kp

                if closest_kp is not None:
                    kp = closest_kp
                    logger.debug(f"Using forecasted Kp {kp:.1f} for {dt_utc} (closest forecast: {closest_time})")

    # Fall back to current Kp if no forecast available
    if kp is None:
        kp = _get_kp_index()
        if kp is None:
            return None

    # Calculate auroral boundary using AgentCalc formula
    boundary_lat = _kp_to_auroral_boundary(kp)
    visibility_level = _kp_to_visibility_level(kp)

    # Calculate visibility probability using AgentCalc logistic model
    visibility_probability = _calculate_aurora_probability(
        observer_lat=location.latitude,
        kp=kp,
        cloud_cover_percent=cloud_cover_percent,
        bortle_class=bortle_class,  # Use provided bortle_class if available
        moon_illumination=moon_illumination,
    )

    # Determine binary visibility (probability > 0.5 = visible)
    is_visible = visibility_probability > 0.5

    # If checking "tonight" during daytime, we need to check if it will be dark tonight
    # and adjust visibility accordingly
    will_be_dark_tonight = is_dark
    if is_tonight_forecast:
        # We're checking for tonight during the day, so calculate if it will be dark tonight
        try:
            from .sun_moon import calculate_sun_times

            check_time = now_utc
            sun_times = calculate_sun_times(location.latitude, location.longitude, check_time)
            sunset = sun_times.get("sunset")
            sunrise = sun_times.get("sunrise")

            if sunset and sunrise:
                sunset_utc = sunset.replace(tzinfo=UTC) if sunset.tzinfo is None else sunset.astimezone(UTC)
                sunrise_utc = sunrise.replace(tzinfo=UTC) if sunrise.tzinfo is None else sunrise.astimezone(UTC)
                if sunrise_utc < sunset_utc:
                    sunrise_utc = sunrise_utc + timedelta(days=1)
                # It will be dark tonight (after sunset, before sunrise)
                will_be_dark_tonight = True
        except Exception as e:
            logger.debug(f"Could not calculate if it will be dark tonight: {e}")
            # Assume it will be dark tonight
            will_be_dark_tonight = True

    # Adjust visibility based on conditions
    # Even if geomagnetically active, need dark skies
    # Note: Cloud cover, moon, and light pollution are already factored into probability
    if not will_be_dark_tonight:
        is_visible = False
        visibility_level = "none"
        # Set probability to 0 if not dark
        visibility_probability = 0.0
    else:
        # Probability already accounts for clouds, moon, and light pollution
        # Just ensure visibility matches probability threshold
        is_visible = visibility_probability > 0.5

    return AuroraForecast(
        timestamp=dt,
        kp_index=kp,
        visibility_level=visibility_level,
        latitude_required=boundary_lat,
        is_visible=is_visible,
        visibility_probability=visibility_probability,
        cloud_cover_percent=cloud_cover_percent,
        moon_illumination=moon_illumination,
        bortle_class=bortle_class,
        sqm_value=None,  # Set by caller if available
        is_dark=will_be_dark_tonight if is_tonight_forecast else is_dark,
        peak_viewing_start=peak_viewing_start,
        peak_viewing_end=peak_viewing_end,
        is_forecasted=is_forecasted,
    )


def check_aurora_visibility(
    location: ObserverLocation,
    dt: datetime | None = None,
) -> AuroraForecast | None:
    """
    Check aurora visibility with automatic weather and moon data.

    Args:
        location: Observer location
        dt: Datetime to check (default: now)

    Returns:
        AuroraForecast object or None if unavailable
    """
    if dt is None:
        dt = datetime.now(UTC)

    # Normalize dt to UTC
    dt_utc = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    now_utc = datetime.now(UTC)

    # Check if it's dark (after sunset, before sunrise) - needed for weather logic
    is_dark = False
    try:
        from .sun_moon import calculate_sun_times

        sun_times = calculate_sun_times(location.latitude, location.longitude, dt_utc)
        sunset = sun_times.get("sunset")
        sunrise = sun_times.get("sunrise")

        if sunset and sunrise:
            # Normalize to same day for comparison
            sunset_utc = sunset.replace(tzinfo=UTC) if sunset.tzinfo is None else sunset.astimezone(UTC)
            sunrise_utc = sunrise.replace(tzinfo=UTC) if sunrise.tzinfo is None else sunrise.astimezone(UTC)

            # Check if current time is after sunset or before sunrise
            # Handle case where sunrise is next day
            if sunset_utc <= sunrise_utc:  # Normal case
                is_dark = sunset_utc <= dt_utc <= sunrise_utc
            else:  # Sunrise is next day (polar regions)
                is_dark = dt_utc >= sunset_utc or dt_utc <= sunrise_utc
    except Exception as e:
        logger.debug(f"Could not calculate sun times for is_dark check: {e}")
        # Assume dark if we can't determine
        is_dark = True

    # Get weather and moon data in parallel for better performance
    cloud_cover = None
    moon_illumination = None
    bortle_class = None
    sqm_value = None

    try:
        import asyncio

        from .light_pollution import get_light_pollution_data
        from .solar_system import get_moon_info
        from .weather import fetch_hourly_weather_forecast, fetch_weather

        # Determine which weather time to use:
        # - If daytime: use weather at sunset
        # - If nighttime: use weather at current hour (rounded down)
        target_weather_time: datetime | None = None
        if not is_dark:
            # Daytime: use sunset weather
            try:
                sun_times = calculate_sun_times(location.latitude, location.longitude, dt_utc)
                sunset = sun_times.get("sunset")
                if sunset:
                    target_weather_time = (
                        sunset.replace(tzinfo=UTC) if sunset.tzinfo is None else sunset.astimezone(UTC)
                    )
                    # Round down to the hour
                    target_weather_time = target_weather_time.replace(minute=0, second=0, microsecond=0)
                    logger.debug(f"Daytime: using weather at sunset ({target_weather_time})")
            except Exception as e:
                logger.debug(f"Could not get sunset time: {e}")
        else:
            # Nighttime: use current hour weather (rounded down)
            target_weather_time = now_utc.replace(minute=0, second=0, microsecond=0)
            logger.debug(f"Nighttime: using weather at current hour ({target_weather_time})")

        # Get hourly forecast and find the forecast closest to target time
        if target_weather_time:
            try:
                from .weather import HourlySeeingForecast, fetch_hourly_weather_forecast

                # Get enough hours to cover from now to target time + buffer
                hours_ahead = max(24, int((target_weather_time - now_utc).total_seconds() / 3600) + 2)
                # Run async function - this is a sync entry point, so asyncio.run() is safe
                hourly_forecasts: list[HourlySeeingForecast] = asyncio.run(
                    fetch_hourly_weather_forecast(location, hours=hours_ahead)
                )

                if hourly_forecasts:
                    # Find the forecast closest to target time
                    closest_forecast: HourlySeeingForecast | None = None
                    min_time_diff = timedelta.max
                    for f in hourly_forecasts:
                        if f.timestamp is not None:
                            time_diff = abs(f.timestamp - target_weather_time)
                            if time_diff < min_time_diff:
                                min_time_diff = time_diff
                                closest_forecast = f

                    if closest_forecast and closest_forecast.cloud_cover_percent is not None:
                        cloud_cover = closest_forecast.cloud_cover_percent
                        logger.debug(
                            f"Using cloud cover from hourly forecast at {closest_forecast.timestamp}: {cloud_cover:.1f}%"
                        )

                    # Get moon phase for the target time
                    try:
                        moon_info = get_moon_info(location.latitude, location.longitude, target_weather_time)
                        if moon_info:
                            moon_illumination = moon_info.illumination
                            logger.debug(f"Using moon phase at {target_weather_time}: {moon_illumination * 100:.1f}%")
                    except Exception as e:
                        logger.debug(f"Could not get moon phase for target time: {e}")
            except Exception as e:
                logger.debug(f"Could not get hourly weather forecast: {e}")

        # Fall back to current weather if we don't have forecasted data
        if cloud_cover is None or moon_illumination is None or bortle_class is None:
            # Fetch weather, moon, and light pollution data in parallel
            async def fetch_all() -> tuple[Any, Any, Any]:
                weather_task = fetch_weather(location)
                moon_task = asyncio.to_thread(get_moon_info, location.latitude, location.longitude, dt)
                lp_task = get_light_pollution_data(location.latitude, location.longitude)
                weather, moon_info, lp_data = await asyncio.gather(
                    weather_task, moon_task, lp_task, return_exceptions=True
                )
                return weather, moon_info, lp_data

            # Run async function - this is a sync entry point, so asyncio.run() is safe
            weather, moon_info, lp_data = asyncio.run(fetch_all())

            if cloud_cover is None:
                if isinstance(weather, Exception):
                    logger.warning(f"Weather fetch error: {weather}")
                else:
                    # Check for error attribute
                    if hasattr(weather, "error") and getattr(weather, "error", False):
                        logger.warning(f"Weather fetch error: {getattr(weather, 'error', 'unknown')}")
                    # Try to get cloud_cover_percent if it exists
                    cloud_cover_value = getattr(weather, "cloud_cover_percent", None)
                    if cloud_cover_value is not None:
                        cloud_cover = cloud_cover_value
                        logger.debug(f"Using current cloud cover: {cloud_cover:.1f}%")

            if moon_illumination is None:
                # moon_info can be Exception | MoonInfo | None due to return_exceptions=True
                # Mypy has trouble with type narrowing here, so we use explicit checks
                if isinstance(moon_info, Exception):
                    logger.warning(f"Could not fetch moon info: {moon_info}")
                elif moon_info is not None:
                    # moon_info is MoonInfo here
                    moon_illumination = moon_info.illumination
                    logger.debug(f"Using current moon phase: {moon_illumination * 100:.1f}%")

            if bortle_class is None:
                if isinstance(lp_data, Exception):
                    logger.debug(f"Could not fetch light pollution data: {lp_data}")
                elif lp_data:
                    bortle_class = lp_data.bortle_class.value
                    sqm_value = lp_data.sqm_value
                    logger.debug(f"Using Bortle class: {bortle_class} (SQM: {sqm_value:.2f})")
    except Exception as e:
        logger.warning(f"Could not fetch weather/moon/light-pollution for aurora check: {e}", exc_info=True)

    # Note: is_dark is already calculated above for weather logic
    # Note: cloud_cover and moon_illumination are now fetched above

    forecast = get_aurora_forecast(
        location=location,
        dt=dt,
        cloud_cover_percent=cloud_cover,
        moon_illumination=moon_illumination,
        bortle_class=bortle_class,
        is_dark=is_dark,
    )

    # Update Bortle class and SQM if they were fetched but weren't available when forecast was created
    if forecast and bortle_class is not None and forecast.bortle_class is None:
        forecast.bortle_class = bortle_class
        forecast.sqm_value = sqm_value
        # Recalculate probability with all factors including Bortle class
        forecast.visibility_probability = _calculate_aurora_probability(
            observer_lat=location.latitude,
            kp=forecast.kp_index,
            cloud_cover_percent=cloud_cover,
            bortle_class=bortle_class,
            moon_illumination=moon_illumination,
        )
        # Update visibility based on recalculated probability
        forecast.is_visible = forecast.visibility_probability > 0.5
    elif forecast and sqm_value is not None:
        # Set SQM value even if Bortle class was already set
        forecast.sqm_value = sqm_value

    return forecast


def get_aurora_visibility_windows(
    location: ObserverLocation,
    days: int = 3,
) -> list[tuple[datetime, datetime, float, str]]:
    """
    Find time windows when aurora will be visible from the observer's location.

    Args:
        location: Observer location
        days: Number of days to check (default: 3, max: 3)

    Returns:
        List of (start_time, end_time, max_kp, visibility_level) tuples
    """
    forecast = _get_kp_forecast(days)
    if not forecast:
        return []

    min_lat = abs(location.latitude)
    visibility_windows: list[tuple[datetime, datetime, float, str]] = []

    # Group consecutive periods where aurora is visible
    current_window_start: datetime | None = None
    current_window_end: datetime | None = None
    current_max_kp = 0.0
    current_visibility = "none"

    for forecast_time, kp_value in forecast:
        min_required_lat = _kp_to_auroral_boundary(kp_value)
        visibility_level = _kp_to_visibility_level(kp_value)

        # Check if aurora is visible at this location
        is_visible = min_lat >= min_required_lat

        if is_visible:
            # Start or extend window
            if current_window_start is None:
                current_window_start = forecast_time
                current_window_end = forecast_time
                current_max_kp = kp_value
                current_visibility = visibility_level
            else:
                current_window_end = forecast_time
            current_max_kp = max(current_max_kp, kp_value)
            # Update visibility to highest level in window
            if visibility_level in ["very_high", "high"] or (
                visibility_level == "moderate" and current_visibility not in ["very_high", "high"]
            ):
                current_visibility = visibility_level
        else:
            # End current window if exists
            window_start = current_window_start
            window_end = current_window_end
            if window_start is not None and window_end is not None:
                visibility_windows.append((window_start, window_end, current_max_kp, current_visibility))
                current_window_start = None
                current_window_end = None
                current_max_kp = 0.0
                current_visibility = "none"

    # Add final window if still open
    window_start = current_window_start
    window_end = current_window_end
    if window_start is not None and window_end is not None:
        visibility_windows.append((window_start, window_end, current_max_kp, current_visibility))

    return visibility_windows


# Solar Cycle 25 data (December 2019 - ~2030)
# Peak estimated around late 2024 - early 2025
SOLAR_CYCLE_25_START = datetime(2019, 12, 1, tzinfo=UTC)
SOLAR_CYCLE_25_PEAK = datetime(2024, 10, 1, tzinfo=UTC)  # Estimated peak
SOLAR_CYCLE_25_END = datetime(2030, 12, 1, tzinfo=UTC)  # Estimated end (~11 years)
SOLAR_CYCLE_NUMBER = 25


def get_solar_cycle_info(dt: datetime | None = None) -> SolarCycleInfo:
    """
    Get information about the current solar cycle.

    Args:
        dt: Datetime to check (default: now)

    Returns:
        SolarCycleInfo with cycle phase and activity level
    """
    if dt is None:
        dt = datetime.now(UTC)

    cycle_start = SOLAR_CYCLE_25_START
    cycle_peak = SOLAR_CYCLE_25_PEAK
    cycle_end = SOLAR_CYCLE_25_END

    # Calculate phase (0.0 = start, 1.0 = end)
    total_duration = (cycle_end - cycle_start).total_seconds()
    elapsed = (dt - cycle_start).total_seconds()
    current_phase = min(1.0, max(0.0, elapsed / total_duration))

    # Calculate years since/until peak
    years_since_peak = (dt - cycle_peak).total_seconds() / (365.25 * 24 * 3600)

    # Determine activity level
    if current_phase < 0.2:
        activity_level = "minimum"
        activity_multiplier = 0.3
    elif current_phase < 0.4:
        activity_level = "rising"
        # Rising phase: linear increase from 0.3 to 1.0
        activity_multiplier = 0.3 + (current_phase - 0.2) / 0.2 * 0.7
    elif current_phase < 0.6:
        activity_level = "maximum"
        # Peak phase: high activity with some variation
        peak_distance = abs(years_since_peak)
        activity_multiplier = (
            1.0 if peak_distance < 0.5 else max(0.8, 1.0 - (peak_distance - 0.5) * 0.4)
        )  # Within 6 months of peak
    elif current_phase < 0.8:
        activity_level = "declining"
        # Declining phase: linear decrease from 1.0 to 0.5
        decline_phase = (current_phase - 0.6) / 0.2
        activity_multiplier = 1.0 - decline_phase * 0.5
    else:
        activity_level = "minimum"
        # Approaching minimum: low activity
        activity_multiplier = 0.5 - (current_phase - 0.8) / 0.2 * 0.2

    return SolarCycleInfo(
        cycle_number=SOLAR_CYCLE_NUMBER,
        cycle_start=cycle_start,
        cycle_peak=cycle_peak,
        cycle_end=cycle_end,
        current_phase=current_phase,
        activity_level=activity_level,
        years_since_peak=years_since_peak,
        activity_multiplier=activity_multiplier,
    )


def _get_seasonal_factor(month: int) -> float:
    """
    Get seasonal activity multiplier for aurora.

    Equinox months (March, September, October) have higher activity.
    Summer months have lower activity due to shorter nights and less geomagnetic activity.

    Args:
        month: Month number (1-12)

    Returns:
        Seasonal multiplier (0.0-1.0)
    """
    # Historical data shows equinox months have ~30% more geomagnetic activity
    # March, September, October are best
    # Summer months (June, July, August) are worst
    # Winter months (December, January, February) are good but not as good as equinox

    seasonal_factors = {
        1: 0.85,  # January - good
        2: 0.80,  # February - good
        3: 1.15,  # March - equinox, excellent
        4: 0.90,  # April - good
        5: 0.75,  # May - moderate
        6: 0.60,  # June - summer, poor
        7: 0.55,  # July - summer, poor
        8: 0.65,  # August - summer, poor
        9: 1.20,  # September - equinox, excellent
        10: 1.15,  # October - equinox, excellent
        11: 0.90,  # November - good
        12: 0.85,  # December - good
    }

    return seasonal_factors.get(month, 0.80)


def _get_historical_kp_probabilities(month: int, solar_cycle_factor: float, seasonal_factor: float) -> dict[str, float]:
    """
    Get historical probability distributions for Kp index based on month and solar cycle.

    Based on historical data from past solar cycles, adjusted for current cycle phase.

    Args:
        month: Month number (1-12)
        solar_cycle_factor: Solar cycle activity multiplier (0.0-1.0)
        seasonal_factor: Seasonal activity multiplier (0.0-1.0)

    Returns:
        Dictionary with probabilities for different Kp thresholds
    """
    # Base probabilities (from historical data, average solar cycle)
    # These represent typical probabilities during solar maximum
    base_prob_kp_5 = 0.25  # 25% chance of Kp ≥ 5 in any given month during max
    base_prob_kp_6 = 0.12  # 12% chance of Kp ≥ 6
    base_prob_kp_7 = 0.05  # 5% chance of Kp ≥ 7
    base_prob_kp_8 = 0.015  # 1.5% chance of Kp ≥ 8

    # Apply solar cycle multiplier
    # During solar minimum, probabilities are much lower
    # During solar maximum, use base probabilities
    prob_kp_5 = base_prob_kp_5 * solar_cycle_factor
    prob_kp_6 = base_prob_kp_6 * solar_cycle_factor
    prob_kp_7 = base_prob_kp_7 * solar_cycle_factor
    prob_kp_8 = base_prob_kp_8 * solar_cycle_factor

    # Apply seasonal multiplier
    # Equinox months boost probabilities
    prob_kp_5 = min(0.50, prob_kp_5 * seasonal_factor)
    prob_kp_6 = min(0.30, prob_kp_6 * seasonal_factor)
    prob_kp_7 = min(0.15, prob_kp_7 * seasonal_factor)
    prob_kp_8 = min(0.05, prob_kp_8 * seasonal_factor)

    # Calculate expected max Kp
    # Weighted average based on probabilities
    expected_max_kp = (
        3.0 * (1.0 - prob_kp_5)  # Below Kp 5
        + 5.5 * (prob_kp_5 - prob_kp_6)  # Kp 5-6
        + 6.5 * (prob_kp_6 - prob_kp_7)  # Kp 6-7
        + 7.5 * (prob_kp_7 - prob_kp_8)  # Kp 7-8
        + 8.5 * prob_kp_8  # Kp 8+
    )

    return {
        "kp_5": prob_kp_5,
        "kp_6": prob_kp_6,
        "kp_7": prob_kp_7,
        "kp_8": prob_kp_8,
        "expected_max": expected_max_kp,
    }


def get_next_aurora_opportunity(
    location: ObserverLocation,
    months_ahead: int = 24,
    min_probability: float = 0.10,
) -> list[AuroraProbability]:
    """
    Find the next likely aurora viewing opportunities using probabilistic models.

    Uses solar cycle phase, seasonal patterns, and historical data to predict
    when aurora is most likely to be visible.

    Args:
        location: Observer location
        months_ahead: How many months ahead to search (default: 24)
        min_probability: Minimum probability threshold to include (default: 0.10 = 10%)

    Returns:
        List of AuroraProbability objects, sorted by probability
    """
    now = datetime.now(UTC)
    min_lat = abs(location.latitude)

    # Determine what Kp index is needed for this latitude
    needed_kp = None
    if min_lat < 40.0:
        needed_kp = 9.0
    elif min_lat < 45.0:
        needed_kp = 8.0
    elif min_lat < 50.0:
        needed_kp = 7.0
    elif min_lat < 55.0:
        needed_kp = 6.0
    elif min_lat < 60.0:
        needed_kp = 5.0
    elif min_lat < 65.0:
        needed_kp = 4.0
    elif min_lat < 70.0:
        needed_kp = 3.0
    else:
        needed_kp = 2.0

    opportunities = []

    # Get current solar cycle info
    get_solar_cycle_info(now)

    # Check each month for the next N months
    for month_offset in range(months_ahead):
        check_date = now + timedelta(days=30 * month_offset)
        month = check_date.month
        year = check_date.year

        # Get seasonal factor
        seasonal_factor = _get_seasonal_factor(month)

        # Project solar cycle factor forward
        # Assume gradual decline from current level
        future_cycle_info = get_solar_cycle_info(check_date)
        solar_cycle_factor = future_cycle_info.activity_multiplier

        # Get historical probabilities
        probs = _get_historical_kp_probabilities(month, solar_cycle_factor, seasonal_factor)

        # Determine which Kp threshold we need
        if needed_kp >= 9.0:
            # Kp 9 is extremely rare - estimate as ~10% of Kp 8 probability
            target_prob = probs["kp_8"] * 0.1
            # But ensure we show something if it's above threshold
            if target_prob < min_probability and probs["kp_8"] > 0:
                # Still include if Kp 8 has any probability (for extreme events)
                target_prob = probs["kp_8"] * 0.05  # Very conservative estimate
            confidence = "low"
        elif needed_kp >= 8.0:
            target_prob = probs["kp_8"]
            confidence = "medium" if target_prob > 0.02 else "low"
        elif needed_kp >= 7.0:
            target_prob = probs["kp_7"]
            confidence = "medium" if target_prob > 0.05 else "low"
        elif needed_kp >= 6.0:
            target_prob = probs["kp_6"]
            confidence = "high" if target_prob > 0.15 else "medium" if target_prob > 0.08 else "low"
        elif needed_kp >= 5.0:
            target_prob = probs["kp_5"]
            confidence = "high" if target_prob > 0.25 else "medium" if target_prob > 0.15 else "low"
        else:
            target_prob = 0.50  # High probability for low Kp requirements
            confidence = "high"

        # Only include if probability meets threshold
        if target_prob >= min_probability:
            # Determine season
            if month in [12, 1, 2]:
                season = "Winter"
            elif month in [3, 4, 5]:
                season = "Spring"
            elif month in [6, 7, 8]:
                season = "Summer"
            else:
                season = "Fall"

            # Create start and end dates for the month
            start_date = datetime(year, month, 1, tzinfo=UTC)
            if month == 12:
                end_date = datetime(year + 1, 1, 1, tzinfo=UTC) - timedelta(seconds=1)
            else:
                end_date = datetime(year, month + 1, 1, tzinfo=UTC) - timedelta(seconds=1)

            # Generate notes
            notes_parts = []
            if seasonal_factor > 1.1:
                notes_parts.append("Equinox month - historically higher activity")
            if solar_cycle_factor > 0.8:
                notes_parts.append("Near solar maximum - increased activity expected")
            elif solar_cycle_factor < 0.5:
                notes_parts.append("Solar minimum approaching - lower activity expected")

            if needed_kp >= 8.0:
                notes_parts.append(f"Requires extreme geomagnetic activity (Kp ≥ {needed_kp:.0f})")
            elif needed_kp >= 6.0:
                notes_parts.append(f"Requires high geomagnetic activity (Kp ≥ {needed_kp:.0f})")

            notes = ". ".join(notes_parts) if notes_parts else "Typical aurora viewing conditions"

            opportunity = AuroraProbability(
                start_date=start_date,
                end_date=end_date,
                month=month,
                season=season,
                probability_kp_5=probs["kp_5"],
                probability_kp_6=probs["kp_6"],
                probability_kp_7=probs["kp_7"],
                probability_kp_8=probs["kp_8"],
                expected_max_kp=probs["expected_max"],
                solar_cycle_factor=solar_cycle_factor,
                seasonal_factor=seasonal_factor,
                confidence=confidence,
                notes=notes,
            )

            opportunities.append(opportunity)

    # Sort by target probability (highest first)
    # For each opportunity, use the appropriate Kp threshold probability
    def sort_key(opp: AuroraProbability) -> float:
        if needed_kp >= 8.0:
            return opp.probability_kp_8
        elif needed_kp >= 7.0:
            return opp.probability_kp_7
        elif needed_kp >= 6.0:
            return opp.probability_kp_6
        elif needed_kp >= 5.0:
            return opp.probability_kp_5
        else:
            return 0.5  # High probability for low requirements

    opportunities.sort(key=sort_key, reverse=True)

    return opportunities

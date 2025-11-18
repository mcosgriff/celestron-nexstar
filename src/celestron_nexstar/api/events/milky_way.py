"""
Milky Way Visibility

Provides Milky Way visibility forecasts based on dark sky conditions,
moon phase, weather, and galactic center position.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from celestron_nexstar.api.location.observer import ObserverLocation

logger = logging.getLogger(__name__)

__all__ = [
    "MilkyWayForecast",
    "MilkyWayOpportunity",
    "check_milky_way_visibility",
    "get_milky_way_visibility_windows",
    "get_next_milky_way_opportunity",
]

# Galactic center coordinates (Sagittarius A*)
GALACTIC_CENTER_RA = 17.7611  # hours
GALACTIC_CENTER_DEC = -29.0078  # degrees
MIN_GALACTIC_CENTER_ALTITUDE = 10.0  # Minimum altitude for visibility (degrees)


@dataclass
class MilkyWayForecast:
    """Milky Way visibility forecast for a specific time."""

    timestamp: datetime
    is_visible: bool  # Whether Milky Way is visible
    visibility_score: float  # 0.0-1.0, higher is better
    visibility_level: str  # "excellent", "good", "fair", "poor", "none"
    cloud_cover_percent: float | None = None
    moon_illumination: float | None = None
    moon_altitude: float | None = None  # Moon altitude in degrees
    moonrise_time: datetime | None = None  # Next moonrise
    moonset_time: datetime | None = None  # Next moonset
    bortle_class: int | None = None  # Bortle class (1-9) for light pollution
    sqm_value: float | None = None  # SQM value (mag/arcsec²)
    is_dark: bool = True  # Whether it's dark enough (after sunset, before sunrise)
    galactic_center_altitude: float | None = None  # Galactic center altitude in degrees
    galactic_center_visible: bool = False  # Whether galactic center is above horizon
    peak_viewing_start: datetime | None = None  # Start of best viewing window
    peak_viewing_end: datetime | None = None  # End of best viewing window


@dataclass
class MilkyWayOpportunity:
    """Milky Way viewing opportunity for a future time period."""

    start_date: datetime
    end_date: datetime
    month: int  # 1-12
    season: str  # "Spring", "Summer", "Fall", "Winter"
    expected_visibility_score: float  # Expected visibility score (0.0-1.0) - best case
    moon_phase_factor: float  # Moon phase quality (0.0-1.0, higher is better)
    galactic_center_factor: float  # Galactic center visibility factor (0.0-1.0)
    confidence: str  # "low", "medium", "high" - confidence in prediction
    notes: str  # Additional context about the opportunity
    min_visibility_score: float | None = None  # Minimum visibility score (worst case cloud cover)
    max_visibility_score: float | None = None  # Maximum visibility score (best case cloud cover)


def _estimate_cloud_cover_for_season(
    month: int,
    location: ObserverLocation | None = None,
    use_tighter_range: bool = True,
) -> tuple[float, float, bool, float | None]:
    """
    Estimate cloud cover range for a given month/season.

    Uses historical weather data from Open-Meteo if available, otherwise falls back to
    simplified climatological assumptions based on season.
    Returns (best_case_cloud_cover, worst_case_cloud_cover, used_historical_data, std_dev) tuple.

    Args:
        month: Month (1-12)
        location: Optional location for location-specific climatology
        use_tighter_range: If True, use p40-p60 (tighter range). If False, use p25-p75 (wider range).

    Returns:
        Tuple of (best_case, worst_case, used_historical_data, std_dev) where:
        - best_case: Best case cloud cover percentage
        - worst_case: Worst case cloud cover percentage
        - used_historical_data: True if historical data was used, False if seasonal estimates were used
        - std_dev: Standard deviation (None if not available)
    """
    # Try to get historical data if location is provided
    if location:
        try:
            import asyncio

            from celestron_nexstar.api.location.weather import get_historical_cloud_cover_for_month

            # Try to get historical data (this will fetch from API if not in database)
            # Use tighter range (p40-p60) by default for more accurate predictions
            historical_data = asyncio.run(
                get_historical_cloud_cover_for_month(location, month, use_tighter_range=use_tighter_range)
            )
            if historical_data and historical_data[0] is not None and historical_data[1] is not None:
                logger.debug(
                    f"Using historical weather data for month {month}: "
                    f"best={historical_data[0]:.1f}%, worst={historical_data[1]:.1f}%, std_dev={historical_data[2]}"
                )
                return (historical_data[0], historical_data[1], True, historical_data[2])
        except Exception as e:
            logger.debug(f"Could not get historical weather data for month {month}: {e}")

    # Fall back to seasonal cloud cover estimates (simplified model)
    # Best case = typically clearer months, Worst case = typically cloudier months
    # These are rough estimates - used when historical data is unavailable

    # Winter (Dec, Jan, Feb) - often clearer in many regions
    if month in [12, 1, 2]:
        return (15.0, 60.0, False, None)  # Best: Clear, Worst: Partly Cloudy to Cloudy
    # Spring (Mar, Apr, May) - variable
    elif month in [3, 4, 5]:
        return (25.0, 70.0, False, None)  # Best: Partly Cloudy, Worst: Cloudy
    # Summer (Jun, Jul, Aug) - often clearer in many regions (monsoon season varies by location)
    elif month in [6, 7, 8]:
        return (20.0, 65.0, False, None)  # Best: Clear to Partly Cloudy, Worst: Cloudy
    # Fall (Sep, Oct, Nov) - variable
    else:  # 9, 10, 11
        return (20.0, 65.0, False, None)  # Best: Clear to Partly Cloudy, Worst: Cloudy


def _cloud_cover_category_to_percent(category: str) -> float:
    """
    Convert cloud cover category to percentage.

    Args:
        category: "Clear", "Partly Cloudy", "Cloudy", or "Unknown"

    Returns:
        Cloud cover percentage (0-100)
    """
    category_lower = category.lower().strip()
    if category_lower == "clear":
        return 10.0  # Average of 0-20%
    elif category_lower in ["partly cloudy", "partly_cloudy"]:
        return 35.0  # Average of 20-50%
    elif category_lower == "cloudy":
        return 75.0  # Average of 50-100%
    else:  # Unknown
        return 50.0  # Conservative estimate


def _calculate_visibility_score(
    bortle_class: int | None = None,
    moon_illumination: float | None = None,
    moon_altitude: float | None = None,
    cloud_cover_percent: float | None = None,
    galactic_center_altitude: float | None = None,
) -> float:
    """
    Calculate Milky Way visibility score (0.0-1.0).

    Factors:
    - Light pollution (Bortle class): Most important
    - Moon phase and altitude: Very important (New Moon ideal, moon below horizon = no impact)
    - Cloud cover: Important
    - Galactic center altitude: Moderate importance

    Args:
        bortle_class: Bortle class (1-9), None if unknown
        moon_illumination: Moon illumination fraction (0.0-1.0), None if unknown
        moon_altitude: Moon altitude in degrees, None if unknown (negative = below horizon)
        cloud_cover_percent: Cloud cover percentage (0-100), None if unknown
        galactic_center_altitude: Galactic center altitude in degrees, None if unknown

    Returns:
        Visibility score (0.0-1.0)
    """
    score = 1.0

    # Light pollution factor (most important)
    # Bortle 1-3: Excellent (score = 1.0)
    # Bortle 4: Good (score = 0.7)
    # Bortle 5: Fair (score = 0.4)
    # Bortle 6+: Poor (score = 0.1)
    if bortle_class is not None:
        if bortle_class <= 3:
            bortle_factor = 1.0
        elif bortle_class == 4:
            bortle_factor = 0.7
        elif bortle_class == 5:
            bortle_factor = 0.4
        else:
            bortle_factor = 0.1
        score *= bortle_factor
    else:
        # Unknown - assume moderate light pollution
        score *= 0.5

    # Moon phase and altitude factor (very important)
    # If moon is below horizon, it doesn't affect visibility
    # If moon is above horizon, apply penalty based on illumination and altitude
    if moon_illumination is not None:
        if moon_altitude is not None and moon_altitude < 0:
            # Moon is below horizon - no impact
            moon_factor = 1.0
        else:
            # Moon is above horizon - apply penalty
            # Base penalty from illumination
            if moon_illumination < 0.01:
                base_moon_factor = 1.0  # New Moon
            elif moon_illumination < 0.30:
                base_moon_factor = 0.8  # Crescent
            elif moon_illumination < 0.70:
                base_moon_factor = 0.5  # Quarter
            else:
                base_moon_factor = 0.2  # Gibbous/Full

            # Adjust based on moon altitude (higher moon = more impact)
            if moon_altitude is not None and moon_altitude >= 0:
                # Moon altitude factor: low moon (<10°) = less impact, high moon (>30°) = full impact
                if moon_altitude < 10:
                    altitude_adjustment = 0.3 + 0.7 * (moon_altitude / 10.0)  # 0.3 to 1.0
                elif moon_altitude < 30:
                    altitude_adjustment = 1.0 - 0.2 * ((30 - moon_altitude) / 20.0)  # 0.8 to 1.0
                else:
                    altitude_adjustment = 1.0  # Full impact for high moon

                # Combine: start with base factor, then apply altitude adjustment
                # Lower altitude = less penalty (closer to 1.0)
                moon_factor = base_moon_factor + (1.0 - base_moon_factor) * (1.0 - altitude_adjustment * 0.5)
            else:
                # Unknown altitude - use base factor
                moon_factor = base_moon_factor
        score *= moon_factor
    else:
        # Unknown - assume moderate moon
        score *= 0.6

    # Cloud cover factor
    # Clear (<20%): score = 1.0
    # Partly cloudy (20-50%): score = 0.7
    # Cloudy (>50%): score = 0.3
    if cloud_cover_percent is not None:
        if cloud_cover_percent < 20:
            cloud_factor = 1.0
        elif cloud_cover_percent < 50:
            cloud_factor = 0.7
        else:
            cloud_factor = 0.3
        score *= cloud_factor
    else:
        # Unknown - assume clear
        score *= 0.9

    # Galactic center altitude factor (moderate importance)
    # Above 30°: score = 1.0
    # 10-30°: score = 0.8
    # Below 10°: score = 0.5
    if galactic_center_altitude is not None:
        if galactic_center_altitude >= 30:
            altitude_factor = 1.0
        elif galactic_center_altitude >= MIN_GALACTIC_CENTER_ALTITUDE:
            altitude_factor = 0.8
        else:
            altitude_factor = 0.5
        score *= altitude_factor
    else:
        # Unknown - assume moderate altitude
        score *= 0.8

    return max(0.0, min(1.0, score))


def _score_to_visibility_level(score: float) -> str:
    """
    Convert visibility score to level description.

    Args:
        score: Visibility score (0.0-1.0)

    Returns:
        Visibility level string
    """
    if score >= 0.7:
        return "excellent"
    elif score >= 0.5:
        return "good"
    elif score >= 0.3:
        return "fair"
    elif score >= 0.1:
        return "poor"
    else:
        return "none"


def check_milky_way_visibility(
    location: ObserverLocation,
    dt: datetime | None = None,
) -> MilkyWayForecast | None:
    """
    Check Milky Way visibility with automatic weather, moon, and position data.

    Args:
        location: Observer location
        dt: Datetime to check (default: now)

    Returns:
        MilkyWayForecast object or None if calculation fails
    """
    if dt is None:
        dt = datetime.now(UTC)

    # Normalize dt to UTC
    dt_utc = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    now_utc = datetime.now(UTC)

    # Check if it's dark (after sunset, before sunrise)
    is_dark = False
    sunset_time = None
    sunrise_time = None
    try:
        from celestron_nexstar.api.astronomy.sun_moon import calculate_sun_times

        sun_times = calculate_sun_times(location.latitude, location.longitude, dt_utc)
        sunset = sun_times.get("sunset")
        sunrise = sun_times.get("sunrise")

        if sunset and sunrise:
            # Normalize to same day for comparison
            sunset_utc = sunset.replace(tzinfo=UTC) if sunset.tzinfo is None else sunset.astimezone(UTC)
            sunrise_utc = sunrise.replace(tzinfo=UTC) if sunrise.tzinfo is None else sunrise.astimezone(UTC)

            sunset_time = sunset_utc
            sunrise_time = sunrise_utc

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

    # Get weather, moon, and light pollution data
    cloud_cover = None
    moon_illumination = None
    moon_altitude = None
    moonrise_time = None
    moonset_time = None
    bortle_class = None
    sqm_value = None
    galactic_center_altitude = None
    galactic_center_visible = False
    peak_viewing_start = None
    peak_viewing_end = None

    try:
        import asyncio

        from celestron_nexstar.api.astronomy.solar_system import get_moon_info
        from celestron_nexstar.api.core.utils import ra_dec_to_alt_az
        from celestron_nexstar.api.location.light_pollution import get_light_pollution_data
        from celestron_nexstar.api.location.weather import fetch_hourly_weather_forecast

        # Determine which weather time to use:
        # - If daytime: use weather at sunset
        # - If nighttime: use weather at current hour (rounded down)
        target_weather_time: datetime | None = None
        if not is_dark and sunset_time:
            # Daytime: use sunset weather
            target_weather_time = sunset_time.replace(minute=0, second=0, microsecond=0)
            logger.debug(f"Daytime: using weather at sunset ({target_weather_time})")
        else:
            # Nighttime: use current hour weather (rounded down)
            target_weather_time = now_utc.replace(minute=0, second=0, microsecond=0)
            logger.debug(f"Nighttime: using weather at current hour ({target_weather_time})")

        # Get hourly forecast and find the forecast closest to target time
        if target_weather_time:
            try:
                from celestron_nexstar.api.location.weather import HourlySeeingForecast

                # Get enough hours to cover from now to target time + buffer
                hours_ahead = max(24, int((target_weather_time - now_utc).total_seconds() / 3600) + 2)
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

                    # Get moon phase and position for the target time
                    try:
                        moon_info = get_moon_info(location.latitude, location.longitude, target_weather_time)
                        if moon_info:
                            moon_illumination = moon_info.illumination
                            moon_altitude = moon_info.altitude_deg
                            moonrise_time = moon_info.moonrise_time
                            moonset_time = moon_info.moonset_time
                            logger.debug(
                                f"Using moon phase at {target_weather_time}: {moon_illumination * 100:.1f}% "
                                f"(altitude: {moon_altitude:.1f}°)"
                            )
                    except Exception as e:
                        logger.debug(f"Could not get moon phase for target time: {e}")
            except Exception as e:
                logger.debug(f"Could not get hourly weather forecast: {e}")

        # Fall back to current weather if we don't have forecasted data
        if cloud_cover is None or moon_illumination is None or bortle_class is None:
            # Fetch weather, moon, and light pollution data in parallel
            async def fetch_all() -> tuple[Any, Any, Any]:
                from celestron_nexstar.api.database.models import get_db_session
                from celestron_nexstar.api.location.weather import fetch_weather

                weather_task = fetch_weather(location)
                moon_task = asyncio.to_thread(get_moon_info, location.latitude, location.longitude, dt)
                async with get_db_session() as db_session:
                    lp_task = get_light_pollution_data(db_session, location.latitude, location.longitude)
                    weather, moon_info, lp_data = await asyncio.gather(
                        weather_task, moon_task, lp_task, return_exceptions=True
                    )
                return weather, moon_info, lp_data

            # Run async function
            weather, moon_info, lp_data = asyncio.run(fetch_all())

            if cloud_cover is None:
                if isinstance(weather, Exception):
                    logger.warning(f"Weather fetch error: {weather}")
                else:
                    if hasattr(weather, "error") and getattr(weather, "error", False):
                        logger.warning(f"Weather fetch error: {getattr(weather, 'error', 'unknown')}")
                    cloud_cover_value = getattr(weather, "cloud_cover_percent", None)
                    if cloud_cover_value is not None:
                        cloud_cover = cloud_cover_value
                        logger.debug(f"Using current cloud cover: {cloud_cover:.1f}%")

            if moon_illumination is None or moon_altitude is None:
                if isinstance(moon_info, Exception):
                    logger.warning(f"Could not fetch moon info: {moon_info}")
                elif moon_info is not None:
                    if moon_illumination is None:
                        moon_illumination = moon_info.illumination
                    if moon_altitude is None:
                        moon_altitude = moon_info.altitude_deg
                    if moonrise_time is None:
                        moonrise_time = moon_info.moonrise_time
                    if moonset_time is None:
                        moonset_time = moon_info.moonset_time
                    logger.debug(
                        f"Using current moon phase: {moon_illumination * 100:.1f}% (altitude: {moon_altitude:.1f}°)"
                    )

            if bortle_class is None:
                if isinstance(lp_data, Exception):
                    logger.debug(f"Could not fetch light pollution data: {lp_data}")
                elif lp_data:
                    bortle_class = lp_data.bortle_class.value
                    sqm_value = lp_data.sqm_value
                    logger.debug(f"Using Bortle class: {bortle_class} (SQM: {sqm_value:.2f})")

        # Calculate galactic center altitude
        try:
            alt, _az = ra_dec_to_alt_az(
                GALACTIC_CENTER_RA, GALACTIC_CENTER_DEC, location.latitude, location.longitude, dt_utc
            )
            galactic_center_altitude = alt
            galactic_center_visible = alt >= MIN_GALACTIC_CENTER_ALTITUDE
            logger.debug(f"Galactic center altitude: {alt:.1f}° (visible: {galactic_center_visible})")
        except Exception as e:
            logger.debug(f"Could not calculate galactic center altitude: {e}")

        # Calculate peak viewing window (when galactic center is highest and moon is down/low)
        if sunset_time and sunrise_time and galactic_center_visible:
            try:
                # Sample from sunset to sunrise to find best viewing time
                check_time = sunset_time
                end_time = sunrise_time + timedelta(days=1) if sunrise_time < sunset_time else sunrise_time
                best_score = 0.0
                best_time = None

                while check_time <= end_time:
                    try:
                        # Get galactic center altitude
                        gc_alt, _az = ra_dec_to_alt_az(
                            GALACTIC_CENTER_RA, GALACTIC_CENTER_DEC, location.latitude, location.longitude, check_time
                        )

                        # Get moon info at this time
                        moon_info_at_time = get_moon_info(location.latitude, location.longitude, check_time)
                        moon_alt_at_time = moon_info_at_time.altitude_deg if moon_info_at_time else None
                        moon_illum_at_time = moon_info_at_time.illumination if moon_info_at_time else None

                        # Calculate a combined score: galactic center altitude + moon avoidance
                        # Higher galactic center = better, lower/below-horizon moon = better
                        gc_score = max(0.0, gc_alt / 90.0)  # Normalize to 0-1

                        # Moon penalty: moon below horizon = no penalty, moon above = penalty
                        moon_penalty = 0.0
                        if (
                            moon_alt_at_time is not None
                            and moon_alt_at_time >= 0
                            and moon_illum_at_time is not None
                            and moon_illum_at_time > 0.3
                        ):
                            # Moon is above horizon - apply penalty based on altitude and illumination
                            # Higher moon = more penalty, brighter moon = more penalty
                            altitude_factor = min(1.0, moon_alt_at_time / 90.0)
                            brightness_factor = moon_illum_at_time
                            moon_penalty = altitude_factor * brightness_factor * 0.5  # Max 50% penalty

                        combined_score = gc_score * (1.0 - moon_penalty)

                        if combined_score > best_score:
                            best_score = combined_score
                            best_time = check_time
                    except Exception:
                        pass
                    check_time += timedelta(hours=1)

                if best_time:
                    # Peak viewing window is ±2 hours around best time
                    peak_viewing_start = best_time - timedelta(hours=2)
                    peak_viewing_end = best_time + timedelta(hours=2)
                    # Clamp to sunset/sunrise
                    if peak_viewing_start < sunset_time:
                        peak_viewing_start = sunset_time
                    if peak_viewing_end > end_time:
                        peak_viewing_end = end_time
            except Exception as e:
                logger.debug(f"Could not calculate peak viewing window: {e}")

    except Exception as e:
        logger.warning(f"Could not fetch weather/moon/light-pollution for Milky Way check: {e}", exc_info=True)

    # Calculate visibility score
    visibility_score = _calculate_visibility_score(
        bortle_class=bortle_class,
        moon_illumination=moon_illumination,
        moon_altitude=moon_altitude,
        cloud_cover_percent=cloud_cover,
        galactic_center_altitude=galactic_center_altitude,
    )

    # Determine visibility level
    visibility_level = _score_to_visibility_level(visibility_score)

    # Milky Way is visible if score > 0.3 and it's dark
    is_visible = visibility_score > 0.3 and is_dark

    return MilkyWayForecast(
        timestamp=dt,
        is_visible=is_visible,
        visibility_score=visibility_score,
        visibility_level=visibility_level,
        cloud_cover_percent=cloud_cover,
        moon_illumination=moon_illumination,
        moon_altitude=moon_altitude,
        moonrise_time=moonrise_time,
        moonset_time=moonset_time,
        bortle_class=bortle_class,
        sqm_value=sqm_value,
        is_dark=is_dark,
        galactic_center_altitude=galactic_center_altitude,
        galactic_center_visible=galactic_center_visible,
        peak_viewing_start=peak_viewing_start,
        peak_viewing_end=peak_viewing_end,
    )


def get_milky_way_visibility_windows(
    location: ObserverLocation,
    days: int = 7,
) -> list[tuple[datetime, datetime, float, str]]:
    """
    Find time windows when Milky Way will be visible from the observer's location.

    Args:
        location: Observer location
        days: Number of days to check (default: 7, max: 14)

    Returns:
        List of (start_time, end_time, max_score, visibility_level) tuples
    """
    days = min(days, 14)  # Limit to 14 days for performance
    now = datetime.now(UTC)
    end_time = now + timedelta(days=days)

    visibility_windows: list[tuple[datetime, datetime, float, str]] = []

    # Fetch all data once upfront to avoid repeated API calls
    import asyncio

    from celestron_nexstar.api.database.models import get_db_session
    from celestron_nexstar.api.location.light_pollution import get_light_pollution_data
    from celestron_nexstar.api.location.weather import HourlySeeingForecast, fetch_hourly_weather_forecast

    # Get light pollution data once (doesn't change)
    bortle_class = None
    sqm_value = None
    try:

        async def fetch_lp() -> Any:
            async with get_db_session() as db_session:
                return await get_light_pollution_data(db_session, location.latitude, location.longitude)

        lp_data = asyncio.run(fetch_lp())
        if lp_data and not isinstance(lp_data, Exception):
            bortle_class = lp_data.bortle_class.value
            sqm_value = lp_data.sqm_value
    except Exception as e:
        logger.debug(f"Could not fetch light pollution data: {e}")

    # Fetch hourly weather forecast for first 7 days (Open-Meteo limit)
    # For days 8-14, use historical monthly averages
    forecast_days = min(days, 7)  # Open-Meteo forecast limit is 7 days
    hours_ahead = forecast_days * 24
    hourly_forecasts: list[HourlySeeingForecast] = []
    try:
        hourly_forecasts = asyncio.run(fetch_hourly_weather_forecast(location, hours=hours_ahead))
        logger.debug(f"Fetched {len(hourly_forecasts)} hourly weather forecasts for first {forecast_days} days")
    except Exception as e:
        logger.warning(f"Could not fetch hourly weather forecast: {e}")

    # Create a lookup dict for weather by hour (rounded to nearest hour) for forecast data
    weather_by_hour: dict[datetime, float | None] = {}
    for forecast in hourly_forecasts:
        if forecast.timestamp and forecast.cloud_cover_percent is not None:
            # Round to hour for lookup
            hour_key = forecast.timestamp.replace(minute=0, second=0, microsecond=0)
            weather_by_hour[hour_key] = forecast.cloud_cover_percent

    # Get historical data for days beyond forecast (8-14 days)
    historical_data_by_month: dict[int, tuple[float, float] | None] = {}
    if days > 7:
        from celestron_nexstar.api.location.weather import get_historical_cloud_cover_for_month

        # Pre-fetch historical data for months we'll need
        months_needed = set()
        check_date = now
        while check_date <= end_time:
            months_needed.add(check_date.month)
            check_date += timedelta(days=1)

        for month in months_needed:
            try:
                hist_data = asyncio.run(get_historical_cloud_cover_for_month(location, month, use_tighter_range=False))
                # hist_data is (best, worst, std_dev) or None
                if hist_data and hist_data[0] is not None and hist_data[1] is not None:
                    # Store as tuple for compatibility with existing code
                    historical_data_by_month[month] = (hist_data[0], hist_data[1])
                else:
                    historical_data_by_month[month] = None
            except Exception as e:
                logger.debug(f"Could not get historical data for month {month}: {e}")
                historical_data_by_month[month] = None

    def _get_cloud_cover_for_time(dt: datetime) -> float | None:
        """Get cloud cover for a specific time from forecast or historical data."""
        # Round to nearest hour
        hour_key = dt.replace(minute=0, second=0, microsecond=0)

        # Check if within forecast period (first 7 days)
        days_ahead = (dt - now).total_seconds() / 86400
        if days_ahead <= 7:
            # Use forecast data if available
            return weather_by_hour.get(hour_key)
        else:
            # Use historical monthly average for days 8-14
            month = dt.month
            hist_data = historical_data_by_month.get(month)
            if hist_data is not None and hist_data[0] is not None and hist_data[1] is not None:
                # Use average of p25 and p75 as estimate
                return (hist_data[0] + hist_data[1]) / 2.0
            return None

    # Group consecutive periods where Milky Way is visible
    current_window_start: datetime | None = None
    current_window_end: datetime | None = None
    current_max_score = 0.0
    current_visibility = "none"

    check_time = now
    while check_time <= end_time:
        # Check visibility at this time using optimized function
        forecast_result = _check_milky_way_visibility_optimized(
            location, check_time, bortle_class, sqm_value, _get_cloud_cover_for_time
        )

        if forecast_result and forecast_result.is_visible:
            # Start or extend window
            if current_window_start is None:
                current_window_start = check_time
                current_window_end = check_time
                current_max_score = forecast_result.visibility_score
                current_visibility = forecast_result.visibility_level
            else:
                current_window_end = check_time
            current_max_score = max(current_max_score, forecast_result.visibility_score)
            # Update visibility to highest level in window
            if current_visibility == "none" or (
                forecast_result.visibility_level in ["excellent", "good"]
                and current_visibility not in ["excellent", "good"]
            ):
                current_visibility = forecast_result.visibility_level
        else:
            # End current window if exists
            if current_window_start is not None and current_window_end is not None:
                # Only add window if it's at least 1 hour long
                duration = (current_window_end - current_window_start).total_seconds() / 3600
                if duration >= 1.0:
                    visibility_windows.append(
                        (current_window_start, current_window_end, current_max_score, current_visibility)
                    )
                current_window_start = None
                current_window_end = None
                current_max_score = 0.0
                current_visibility = "none"

        # Advance by 2 hours
        check_time += timedelta(hours=2)

    # Add final window if still open
    if current_window_start is not None and current_window_end is not None:
        duration = (current_window_end - current_window_start).total_seconds() / 3600
        if duration >= 1.0:
            visibility_windows.append((current_window_start, current_window_end, current_max_score, current_visibility))

    return visibility_windows


def _check_milky_way_visibility_optimized(
    location: ObserverLocation,
    dt: datetime,
    bortle_class: int | None,
    sqm_value: float | None,
    get_cloud_cover: Any,  # Callable[[datetime], float | None]
) -> MilkyWayForecast | None:
    """
    Optimized version of check_milky_way_visibility that uses pre-fetched data.

    This avoids repeated API calls when checking multiple time windows.

    Args:
        location: Observer location
        dt: Datetime to check
        bortle_class: Pre-fetched Bortle class
        sqm_value: Pre-fetched SQM value
        get_cloud_cover: Function to get cloud cover for a datetime

    Returns:
        MilkyWayForecast object or None if calculation fails
    """
    # Normalize dt to UTC
    dt_utc = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)

    # Check if it's dark (after sunset, before sunrise)
    is_dark = False
    try:
        from celestron_nexstar.api.astronomy.sun_moon import calculate_sun_times

        sun_times = calculate_sun_times(location.latitude, location.longitude, dt_utc)
        sunset = sun_times.get("sunset")
        sunrise = sun_times.get("sunrise")

        if sunset and sunrise:
            # Normalize to same day for comparison
            sunset_utc = sunset.replace(tzinfo=UTC) if sunset.tzinfo is None else sunset.astimezone(UTC)
            sunrise_utc = sunrise.replace(tzinfo=UTC) if sunrise.tzinfo is None else sunrise.astimezone(UTC)

            # Check if current time is after sunset or before sunrise
            if sunset_utc <= sunrise_utc:  # Normal case
                is_dark = sunset_utc <= dt_utc <= sunrise_utc
            else:  # Sunrise is next day (polar regions)
                is_dark = dt_utc >= sunset_utc or dt_utc <= sunrise_utc
    except Exception as e:
        logger.debug(f"Could not calculate sun times: {e}")
        is_dark = True

    # Get cloud cover from pre-fetched data
    cloud_cover = get_cloud_cover(dt_utc) if get_cloud_cover else None

    # Get moon info (this is fast, no API call)
    moon_illumination = None
    moon_altitude = None
    moonrise_time = None
    moonset_time = None
    try:
        from celestron_nexstar.api.astronomy.solar_system import get_moon_info

        moon_info = get_moon_info(location.latitude, location.longitude, dt_utc)
        if moon_info:
            moon_illumination = moon_info.illumination
            moon_altitude = moon_info.altitude_deg
            moonrise_time = moon_info.moonrise_time
            moonset_time = moon_info.moonset_time
    except Exception as e:
        logger.debug(f"Could not get moon info: {e}")

    # Calculate galactic center altitude
    galactic_center_altitude = None
    galactic_center_visible = False
    try:
        from celestron_nexstar.api.core.utils import ra_dec_to_alt_az

        alt, _az = ra_dec_to_alt_az(
            GALACTIC_CENTER_RA, GALACTIC_CENTER_DEC, location.latitude, location.longitude, dt_utc
        )
        galactic_center_altitude = alt
        galactic_center_visible = alt >= MIN_GALACTIC_CENTER_ALTITUDE
    except Exception as e:
        logger.debug(f"Could not calculate galactic center altitude: {e}")

    # Calculate visibility score
    visibility_score = _calculate_visibility_score(
        bortle_class=bortle_class,
        moon_illumination=moon_illumination,
        moon_altitude=moon_altitude,
        cloud_cover_percent=cloud_cover,
        galactic_center_altitude=galactic_center_altitude,
    )

    # Determine visibility level
    visibility_level = _score_to_visibility_level(visibility_score)

    # Milky Way is visible if score > 0.3 and it's dark
    is_visible = visibility_score > 0.3 and is_dark

    return MilkyWayForecast(
        timestamp=dt,
        is_visible=is_visible,
        visibility_score=visibility_score,
        visibility_level=visibility_level,
        cloud_cover_percent=cloud_cover,
        moon_illumination=moon_illumination,
        moon_altitude=moon_altitude,
        moonrise_time=moonrise_time,
        moonset_time=moonset_time,
        bortle_class=bortle_class,
        sqm_value=sqm_value,
        is_dark=is_dark,
        galactic_center_altitude=galactic_center_altitude,
        galactic_center_visible=galactic_center_visible,
        peak_viewing_start=None,  # Not calculated in optimized version
        peak_viewing_end=None,  # Not calculated in optimized version
    )


def get_next_milky_way_opportunity(
    location: ObserverLocation,
    months_ahead: int = 12,
    min_score: float = 0.5,
) -> tuple[list[MilkyWayOpportunity], dict[int, bool]]:
    """
    Find the next best Milky Way viewing opportunities.

    Uses moon phase cycles and seasonal patterns to predict when conditions
    will be optimal for Milky Way viewing.

    Args:
        location: Observer location
        months_ahead: Number of months ahead to search (default: 12)
        min_score: Minimum visibility score threshold to include (default: 0.5)

    Returns:
        Tuple of (list of MilkyWayOpportunity objects sorted by expected visibility score,
                  dict mapping month number (1-12) to bool indicating if historical data was used)
    """
    now = datetime.now(UTC)
    opportunities = []

    # Track which months used historical data vs seasonal estimates
    months_with_historical_data: set[int] = set()
    months_with_seasonal_estimates: set[int] = set()

    # Get light pollution data once
    bortle_class = None
    try:
        import asyncio

        from celestron_nexstar.api.database.models import get_db_session
        from celestron_nexstar.api.location.light_pollution import get_light_pollution_data

        async def fetch_lp() -> Any:
            async with get_db_session() as db_session:
                return await get_light_pollution_data(db_session, location.latitude, location.longitude)

        lp_data = asyncio.run(fetch_lp())
        if lp_data and not isinstance(lp_data, Exception):
            bortle_class = lp_data.bortle_class.value
    except Exception as e:
        logger.debug(f"Could not fetch light pollution data: {e}")

    # Pre-fetch historical weather data if needed
    # Determine which months we'll need
    months_needed: set[int] = set()
    for month_offset in range(months_ahead):
        check_date = now + timedelta(days=30 * month_offset)
        months_needed.add(check_date.month)

    # Check if we have historical data for any of the needed months
    # If not, proactively fetch it
    try:
        import asyncio

        from sqlalchemy import and_, select

        # Check database for needed months
        from celestron_nexstar.api.database.database import get_database
        from celestron_nexstar.api.database.models import HistoricalWeatherModel
        from celestron_nexstar.api.location.weather import fetch_historical_weather_climatology

        db = get_database()
        months_in_db: set[int] = set()
        try:

            async def check_db() -> set[int]:
                async with db._AsyncSession() as session:
                    stmt = (
                        select(HistoricalWeatherModel.month)
                        .where(
                            and_(
                                HistoricalWeatherModel.latitude == location.latitude,
                                HistoricalWeatherModel.longitude == location.longitude,
                                HistoricalWeatherModel.month.in_(list(months_needed)),
                            )
                        )
                        .distinct()
                    )
                    result = await session.execute(stmt)
                    return {row[0] for row in result.all()}

            months_in_db = asyncio.run(check_db())
        except Exception as e:
            logger.debug(f"Error checking database for historical weather: {e}")

        # If we're missing any months, fetch historical data
        missing_months = months_needed - months_in_db
        if missing_months:
            logger.debug(f"Missing historical data for months {missing_months}, fetching from API...")
            # Fetch all 12 months (API returns all at once, and we'll cache them)
            asyncio.run(fetch_historical_weather_climatology(location))
    except Exception as e:
        logger.debug(f"Could not pre-fetch historical weather data: {e}")

    # Check each month for the next N months
    for month_offset in range(months_ahead):
        check_date = now + timedelta(days=30 * month_offset)
        month = check_date.month
        year = check_date.year

        # Determine season
        if month in [12, 1, 2]:
            season = "Winter"
        elif month in [3, 4, 5]:
            season = "Spring"
        elif month in [6, 7, 8]:
            season = "Summer"
        else:
            season = "Fall"

        # Find New Moon dates in this month (approximate - moon cycle is ~29.5 days)
        # New Moon occurs roughly every 29.5 days
        # We'll check around the middle of the month for New Moon
        month_start = datetime(year, month, 1, tzinfo=UTC)
        if month == 12:
            month_end = datetime(year + 1, 1, 1, tzinfo=UTC) - timedelta(seconds=1)
        else:
            month_end = datetime(year, month + 1, 1, tzinfo=UTC) - timedelta(seconds=1)

        # Check a few dates around expected New Moon (every ~29.5 days from a known New Moon)
        # Use approximate calculation: New Moon dates are roughly predictable
        # We'll sample 3-4 dates in the month to find the best conditions
        sample_dates = []
        days_in_month = (month_end - month_start).days
        # Sample at 1/4, 1/2, 3/4 of the month
        for fraction in [0.25, 0.5, 0.75]:
            sample_date = month_start + timedelta(days=int(days_in_month * fraction))
            sample_dates.append(sample_date)

        best_score = 0.0
        best_date = None
        best_moon_illumination = None
        best_gc_altitude = None
        best_score_range: tuple[float, float] | None = None  # (min, max)

        for sample_date in sample_dates:
            try:
                from celestron_nexstar.api.astronomy.solar_system import get_moon_info
                from celestron_nexstar.api.core.utils import ra_dec_to_alt_az

                # Get moon phase
                moon_info = get_moon_info(location.latitude, location.longitude, sample_date)
                moon_illumination = moon_info.illumination if moon_info else 0.5

                # Get galactic center altitude (at midnight local time)
                # Use sample_date at midnight UTC as approximation
                midnight_utc = sample_date.replace(hour=0, minute=0, second=0, microsecond=0)
                try:
                    gc_alt, _ = ra_dec_to_alt_az(
                        GALACTIC_CENTER_RA, GALACTIC_CENTER_DEC, location.latitude, location.longitude, midnight_utc
                    )
                except Exception:
                    gc_alt = None

                # Calculate expected visibility score
                # Use seasonal cloud cover estimates instead of assuming clear
                # Get moon altitude for better prediction
                moon_alt = moon_info.altitude_deg if moon_info else None

                # Check if this opportunity is within 14 days - if so, try to use weather forecast
                days_until_opportunity = (sample_date - now).days
                cloud_cover_from_forecast = None

                if days_until_opportunity <= 14 and days_until_opportunity >= 0:
                    # Try to get actual weather forecast for this date
                    try:
                        from celestron_nexstar.api.location.weather import (
                            HourlySeeingForecast,
                            fetch_hourly_weather_forecast,
                        )

                        # Get forecast for the date (round to nearest hour)
                        target_hour = sample_date.replace(minute=0, second=0, microsecond=0)
                        hourly_forecasts: list[HourlySeeingForecast] = asyncio.run(
                            fetch_hourly_weather_forecast(location, hours=days_until_opportunity * 24 + 24)
                        )

                        # Find forecast closest to target time
                        if hourly_forecasts:
                            closest_forecast: HourlySeeingForecast | None = None
                            min_time_diff = float("inf")
                            for forecast in hourly_forecasts:
                                if forecast.timestamp:
                                    time_diff = abs((forecast.timestamp - target_hour).total_seconds())
                                    if time_diff < min_time_diff:
                                        min_time_diff = time_diff
                                        closest_forecast = forecast

                            if closest_forecast and closest_forecast.cloud_cover_percent is not None:
                                cloud_cover_from_forecast = closest_forecast.cloud_cover_percent
                                logger.debug(
                                    f"Using weather forecast for {sample_date}: {cloud_cover_from_forecast:.1f}%"
                                )
                    except Exception as e:
                        logger.debug(f"Could not get weather forecast for {sample_date}: {e}")

                # Estimate cloud cover based on season (use best case for scoring)
                # Use tighter range (p40-p60) by default for more accurate predictions
                best_cloud, worst_cloud, used_historical, std_dev = _estimate_cloud_cover_for_season(  # noqa: RUF059
                    month, location, use_tighter_range=True
                )

                # If we have a weather forecast, use it instead of historical/seasonal estimates
                if cloud_cover_from_forecast is not None:
                    # Use forecast value for both best and worst (narrow range since we have actual forecast)
                    best_cloud = cloud_cover_from_forecast
                    worst_cloud = cloud_cover_from_forecast
                    used_historical = True  # Mark as using forecast data
                    logger.debug(f"Using weather forecast instead of historical data for {sample_date}")

                # Track data source for summary
                if used_historical:
                    months_with_historical_data.add(month)
                else:
                    months_with_seasonal_estimates.add(month)
                # Calculate score range: best case (clearer) and worst case (cloudier)
                best_case_score = _calculate_visibility_score(
                    bortle_class=bortle_class,
                    moon_illumination=moon_illumination,
                    moon_altitude=moon_alt,
                    cloud_cover_percent=best_cloud,  # Best-case seasonal estimate
                    galactic_center_altitude=gc_alt,
                )
                worst_case_score = _calculate_visibility_score(
                    bortle_class=bortle_class,
                    moon_illumination=moon_illumination,
                    moon_altitude=moon_alt,
                    cloud_cover_percent=worst_cloud,  # Worst-case seasonal estimate
                    galactic_center_altitude=gc_alt,
                )
                # Use best case as expected score (optimistic but realistic)
                expected_score = best_case_score

                if expected_score > best_score:
                    best_score = expected_score
                    best_date = sample_date
                    best_moon_illumination = moon_illumination
                    best_gc_altitude = gc_alt
                    best_score_range = (worst_case_score, best_case_score)  # Store range
            except Exception as e:
                logger.debug(f"Error checking date {sample_date}: {e}")
                continue

        # Only include if score meets threshold
        if best_score >= min_score and best_date:
            # Calculate moon phase factor
            moon_factor = 1.0
            if best_moon_illumination is not None:
                if best_moon_illumination < 0.01:
                    moon_factor = 1.0  # New Moon
                elif best_moon_illumination < 0.30:
                    moon_factor = 0.8  # Crescent
                elif best_moon_illumination < 0.70:
                    moon_factor = 0.5  # Quarter
                else:
                    moon_factor = 0.2  # Gibbous/Full

            # Calculate galactic center factor
            gc_factor = 0.5
            if best_gc_altitude is not None:
                if best_gc_altitude >= 30:
                    gc_factor = 1.0
                elif best_gc_altitude >= MIN_GALACTIC_CENTER_ALTITUDE:
                    gc_factor = 0.8
                else:
                    gc_factor = 0.5

            # Determine confidence
            if best_score >= 0.7:
                confidence = "high"
            elif best_score >= 0.5:
                confidence = "medium"
            else:
                confidence = "low"

            # Generate notes
            notes_parts = []
            if best_moon_illumination is not None and best_moon_illumination < 0.01:
                notes_parts.append("New Moon - ideal dark sky conditions")
            elif best_moon_illumination is not None and best_moon_illumination < 0.30:
                notes_parts.append("Crescent moon - good conditions")
            if season == "Summer" and location.latitude > 0:
                notes_parts.append("Summer months offer best galactic center visibility in Northern Hemisphere")
            if bortle_class and bortle_class > 4:
                notes_parts.append(f"Light pollution (Bortle {bortle_class}) may limit visibility")

            # Add note about cloud cover estimates
            best_cloud, worst_cloud, used_historical, _std_dev = _estimate_cloud_cover_for_season(
                month, location, use_tighter_range=True
            )
            if worst_cloud > 50:
                if used_historical:
                    notes_parts.append(
                        f"Historical cloud cover: {best_cloud:.0f}%-{worst_cloud:.0f}% (check weather forecast closer to date)"
                    )
                else:
                    notes_parts.append(
                        f"Seasonal cloud cover estimates: {best_cloud:.0f}%-{worst_cloud:.0f}% (check weather forecast closer to date)"
                    )

            notes = ". ".join(notes_parts) if notes_parts else "Good Milky Way viewing conditions expected"

            # Set score range if available
            min_score_val = best_score_range[0] if best_score_range else None
            max_score_val = best_score_range[1] if best_score_range else None

            opportunity = MilkyWayOpportunity(
                start_date=month_start,
                end_date=month_end,
                month=month,
                season=season,
                expected_visibility_score=best_score,
                min_visibility_score=min_score_val,
                max_visibility_score=max_score_val,
                moon_phase_factor=moon_factor,
                galactic_center_factor=gc_factor,
                confidence=confidence,
                notes=notes,
            )

            opportunities.append(opportunity)

    # Sort by expected visibility score (highest first)
    opportunities.sort(key=lambda opp: opp.expected_visibility_score, reverse=True)

    # Build month data source map (combine historical and seasonal sets)
    month_data_source: dict[int, bool] = {}
    for month in months_with_historical_data:
        month_data_source[month] = True
    for month in months_with_seasonal_estimates:
        month_data_source[month] = False

    return opportunities, month_data_source

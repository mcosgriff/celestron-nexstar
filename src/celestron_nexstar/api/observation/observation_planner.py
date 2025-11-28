"""
Observation Session Planner

Combines weather, light pollution, object visibility, and telescope
capabilities to recommend what to observe tonight.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from celestron_nexstar.api.astronomy.solar_system import (
    calculate_astronomical_twilight,
    calculate_blue_hour,
    calculate_golden_hour,
    get_moon_info,
    get_sun_info,
)
from celestron_nexstar.api.catalogs.catalogs import CelestialObject
from celestron_nexstar.api.core.enums import CelestialObjectType, MoonPhase, SkyBrightness
from celestron_nexstar.api.core.exceptions import LocationNotSetError
from celestron_nexstar.api.core.utils import angular_separation, calculate_lst, ra_dec_to_alt_az
from celestron_nexstar.api.database.database import get_database
from celestron_nexstar.api.location.light_pollution import LightPollutionData, get_light_pollution_data
from celestron_nexstar.api.location.observer import ObserverLocation, get_observer_location
from celestron_nexstar.api.location.weather import (
    HourlySeeingForecast,
    WeatherData,
    assess_observing_conditions,
    calculate_seeing_conditions,
    fetch_weather,
)
from celestron_nexstar.api.observation.optics import calculate_limiting_magnitude, get_current_configuration
from celestron_nexstar.api.observation.visibility import VisibilityInfo, filter_visible_objects


logger = logging.getLogger(__name__)

__all__ = [
    "ObservationPlanner",
    "ObservingConditions",
    "ObservingTarget",
    "RecommendedObject",
    "get_tonight_plan",
]


class ObservingTarget(StrEnum):
    """Types of observing targets."""

    PLANETS = "planets"
    MOON = "moon"
    DEEP_SKY = "deep_sky"
    DOUBLE_STARS = "double_stars"
    VARIABLE_STARS = "variable_stars"
    MESSIER = "messier"  # Popular curated catalog (still useful as separate category)


@dataclass(frozen=True)
class ObservingConditions:
    """Complete observing conditions for a session."""

    # Time and location
    timestamp: datetime
    latitude: float
    longitude: float
    location_name: str | None

    # Weather
    weather: WeatherData
    is_weather_suitable: bool

    # Light pollution
    light_pollution: LightPollutionData

    # Telescope
    limiting_magnitude: float
    aperture_mm: float

    # Moon
    moon_illumination: float  # 0.0-1.0
    moon_altitude: float  # degrees
    moon_phase: MoonPhase | None  # Phase name (e.g., "New Moon", "Waxing Crescent")

    # Overall assessment
    observing_quality_score: float  # 0.0-1.0
    seeing_score: float  # 0.0-100.0 (astronomical seeing conditions)
    recommendations: tuple[str, ...]
    warnings: tuple[str, ...]

    # Time windows
    best_seeing_windows: tuple[tuple[datetime, datetime], ...] = ()  # Discrete time windows with excellent/good seeing

    # Hourly forecast (if available)
    hourly_seeing_forecast: tuple[HourlySeeingForecast, ...] = ()  # Hourly seeing conditions

    # Sun and Moon events for current day
    sunrise_time: datetime | None = None
    sunset_time: datetime | None = None
    moonrise_time: datetime | None = None
    moonset_time: datetime | None = None
    golden_hour_evening_start: datetime | None = None
    golden_hour_evening_end: datetime | None = None
    golden_hour_morning_start: datetime | None = None
    golden_hour_morning_end: datetime | None = None
    blue_hour_evening_start: datetime | None = None
    blue_hour_evening_end: datetime | None = None
    blue_hour_morning_start: datetime | None = None
    blue_hour_morning_end: datetime | None = None
    astronomical_twilight_evening_start: datetime | None = None  # When astronomical twilight begins (evening)
    astronomical_twilight_evening_end: datetime | None = None  # When true night begins (evening)
    astronomical_twilight_morning_start: datetime | None = None  # When true night ends (morning)
    astronomical_twilight_morning_end: datetime | None = None  # When astronomical twilight ends (morning)
    galactic_center_start: datetime | None = None  # When galactic center becomes visible
    galactic_center_end: datetime | None = None  # When galactic center becomes too low

    # Space weather
    space_weather_alerts: tuple[str, ...] = ()  # Space weather alerts/warnings
    geomagnetic_storm_level: int | None = None  # G-scale level (0-5)
    aurora_opportunity: bool = False  # Enhanced aurora opportunity (G3+)


@dataclass(frozen=True)
class RecommendedObject:
    """An object recommended for observation tonight."""

    obj: CelestialObject

    # Visibility
    altitude: float
    azimuth: float
    best_viewing_time: datetime
    visible_duration_hours: float

    # Conditions
    apparent_magnitude: float
    observability_score: float  # 0.0-1.0
    visibility_probability: float  # 0.0-1.0, probability of actually seeing it given current conditions

    # Recommendations
    priority: int  # 1 (highest) to 5 (lowest)
    reason: str
    viewing_tips: tuple[str, ...]

    # Additional info
    moon_separation_deg: float | None = None  # Angular distance from moon


class ObservationPlanner:
    """Plan what to observe based on all conditions."""

    def get_tonight_conditions(
        self,
        lat: float | None = None,
        lon: float | None = None,
        start_time: datetime | None = None,
    ) -> ObservingConditions:
        """
        Get complete observing conditions for tonight.

        Args:
            lat: Observer latitude (default: from saved location)
            lon: Observer longitude (default: from saved location)
            start_time: Session start time (default: now)

        Returns:
            Complete observing conditions assessment
        """
        # Get location
        if lat is None or lon is None:
            location = get_observer_location()
            if location is None:
                raise LocationNotSetError("No location set. Use 'nexstar location set' command.")
            lat, lon = location.latitude, location.longitude
            location_name = location.name
        else:
            location_name = None

        # Get weather forecast
        if start_time is None:
            start_time = datetime.now(UTC)
        elif start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=UTC)

        # Create location object for weather API
        observer_location = ObserverLocation(
            name=location_name or "Current Location",
            latitude=lat,
            longitude=lon,
            elevation=0.0,
        )

        # Determine which weather time to use:
        # - If daytime: use weather at sunset
        # - If nighttime: use weather at current hour (rounded down)
        now_utc = datetime.now(UTC)
        target_weather_time: datetime | None = None
        sunset: datetime | None = None

        # Check if it's dark (after sunset, before sunrise)
        is_dark = False
        try:
            from celestron_nexstar.api.astronomy.sun_moon import calculate_sun_times

            sun_times = calculate_sun_times(lat, lon, start_time)
            sunset = sun_times.get("sunset")
            sunrise = sun_times.get("sunrise")

            if sunset and sunrise:
                sunset_utc = sunset.replace(tzinfo=UTC) if sunset.tzinfo is None else sunset.astimezone(UTC)
                sunrise_utc = sunrise.replace(tzinfo=UTC) if sunrise.tzinfo is None else sunrise.astimezone(UTC)
                if sunrise_utc < sunset_utc:
                    sunrise_utc = sunrise_utc + timedelta(days=1)

                if sunset_utc <= sunrise_utc:
                    is_dark = sunset_utc <= now_utc <= sunrise_utc
                else:
                    is_dark = now_utc >= sunset_utc or now_utc <= sunrise_utc
        except Exception:
            is_dark = True  # Assume dark if we can't determine

        if not is_dark:
            # Daytime: use sunset weather
            if sunset:
                target_weather_time = sunset.replace(tzinfo=UTC) if sunset.tzinfo is None else sunset.astimezone(UTC)
                target_weather_time = target_weather_time.replace(minute=0, second=0, microsecond=0)
        else:
            # Nighttime: use current hour weather (rounded down)
            target_weather_time = now_utc.replace(minute=0, second=0, microsecond=0)

        # Determine if we should use current weather (if after sunset and checking for "now")
        use_current_weather = False
        if is_dark and target_weather_time:
            # If it's nighttime and we're checking for current hour (within 1 hour), use current weather
            time_diff_hours = abs((target_weather_time - now_utc).total_seconds() / 3600)
            if time_diff_hours <= 1.0:
                use_current_weather = True

        # Try to get weather from database first (if after sunset and checking for "now")
        # Otherwise, use hourly forecast
        weather = None
        if use_current_weather:
            # Check database for current weather first, then API if needed
            # fetch_weather already checks database and stores if missing
            with contextlib.suppress(Exception):
                weather = asyncio.run(fetch_weather(observer_location))

        # If not using current weather, try hourly forecast
        if weather is None and target_weather_time:
            try:
                from celestron_nexstar.api.location.weather import WeatherData, fetch_hourly_weather_forecast

                hours_ahead = max(24, int((target_weather_time - now_utc).total_seconds() / 3600) + 2)
                # Run async function - this is a sync entry point, so asyncio.run() is safe
                hourly_forecasts: list[HourlySeeingForecast] = asyncio.run(
                    fetch_hourly_weather_forecast(observer_location, hours=hours_ahead)
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

                    if closest_forecast:
                        # Create WeatherData from hourly forecast
                        weather = WeatherData(
                            temperature_c=closest_forecast.temperature_f,  # Note: WeatherData uses C but we're passing F
                            dew_point_f=closest_forecast.dew_point_f,
                            humidity_percent=closest_forecast.humidity_percent,
                            cloud_cover_percent=closest_forecast.cloud_cover_percent,
                            wind_speed_ms=closest_forecast.wind_speed_mph,  # Note: WeatherData uses m/s but we're passing mph
                        )
            except Exception:
                pass

        # Fall back to current weather if we don't have forecast data
        # Also prefer current weather if it's significantly different and more recent
        if weather is None:
            # Run async function - this is a sync entry point, so asyncio.run() is safe
            weather = asyncio.run(fetch_weather(observer_location))
        elif not use_current_weather:
            # Get current weather to compare - if current weather shows clear skies (0-20%)
            # and forecast shows heavy clouds (>80%), prefer current weather
            # This handles cases where forecast data is stale or incorrect
            try:
                current_weather = asyncio.run(fetch_weather(observer_location))
                if (
                    current_weather
                    and current_weather.cloud_cover_percent is not None
                    and weather.cloud_cover_percent is not None
                ):
                    # If current weather is clear (0-20%) and forecast is very cloudy (>80%),
                    # prefer current weather (forecast may be stale or incorrect)
                    # Also check if we're checking for "now" or very near future (within 6 hours)
                    time_diff_hours = 0.0
                    if target_weather_time is not None:
                        time_diff_hours = abs((target_weather_time - now_utc).total_seconds() / 3600)

                    # Prefer current weather if:
                    # 1. Current is clear (0-20%) and forecast is very cloudy (>80%), OR
                    # 2. Current is clear (0-20%) and forecast is cloudy (>60%) and we're checking for near-term (within 6 hours)
                    if (current_weather.cloud_cover_percent <= 20 and weather.cloud_cover_percent > 80) or (
                        current_weather.cloud_cover_percent <= 20
                        and weather.cloud_cover_percent > 60
                        and time_diff_hours <= 6
                    ):
                        # Use current weather instead of forecast
                        logger.info(
                            f"Using current weather ({current_weather.cloud_cover_percent:.0f}% clouds) "
                            f"instead of forecast ({weather.cloud_cover_percent:.0f}% clouds) "
                            f"for time {time_diff_hours:.1f} hours away"
                        )
                        weather = current_weather
            except Exception:
                pass

        weather_status, weather_warning = assess_observing_conditions(weather)
        is_weather_suitable = weather_status in ("excellent", "good", "fair")

        # Get light pollution
        # Run async function - this is a sync entry point, so asyncio.run() is safe
        from typing import Any

        async def _get_light_data() -> Any:
            from celestron_nexstar.api.database.models import get_db_session

            async with get_db_session() as db_session:
                return await get_light_pollution_data(db_session, lat, lon)

        lp_data = asyncio.run(_get_light_data())

        # Get telescope configuration
        config = get_current_configuration()
        # Map Bortle class to SkyBrightness
        bortle_to_sky_brightness = {
            1: SkyBrightness.EXCELLENT,
            2: SkyBrightness.EXCELLENT,
            3: SkyBrightness.GOOD,
            4: SkyBrightness.FAIR,
            5: SkyBrightness.FAIR,
            6: SkyBrightness.POOR,
            7: SkyBrightness.URBAN,
            8: SkyBrightness.URBAN,
            9: SkyBrightness.URBAN,
        }
        sky_brightness = bortle_to_sky_brightness.get(lp_data.bortle_class.value, SkyBrightness.FAIR)

        if config:
            limiting_mag = calculate_limiting_magnitude(
                config.telescope.effective_aperture_mm,
                sky_brightness=sky_brightness,
            )
            aperture = config.telescope.effective_aperture_mm
        else:
            limiting_mag = lp_data.naked_eye_limiting_magnitude
            aperture = 0.0

        # Calculate moon position and illumination
        moon_info = get_moon_info(lat, lon, start_time)
        if moon_info:
            moon_illum = moon_info.illumination
            moon_alt = moon_info.altitude_deg
            moon_phase = moon_info.phase_name
        else:
            moon_illum = 0.5  # Default to half moon if calculation fails
            moon_alt = 0.0
            moon_phase = None

        # Assess overall quality
        quality_score = self._calculate_quality_score(weather, lp_data, moon_illum, weather_status)

        # Calculate seeing conditions
        # Note: Temperature stability requires historical data
        # For now, assume stable conditions (0.0 change/hour)
        # This can be enhanced later with temperature history tracking
        seeing_score = calculate_seeing_conditions(weather, temperature_change_per_hour=0.0)

        recommendations, warnings = self._generate_recommendations(
            weather, lp_data, moon_illum, quality_score, weather_status, weather_warning
        )

        # Get sun and moon event times first to calculate how many hours of forecast we need
        sun_info = get_sun_info(lat, lon, start_time)
        sunrise_time = sun_info.sunrise_time if sun_info else None
        sunset_time = sun_info.sunset_time if sun_info else None

        # Fetch 3-day forecast (72 hours) to ensure we have enough data
        # This covers from 1 hour before sunset to sunrise with plenty of buffer
        hours_needed = 72  # 3 days

        # Fetch hourly seeing forecast (if available - requires Pro subscription)
        # Run async function - this is a sync entry point, so asyncio.run() is safe
        hourly_forecast = asyncio.run(fetch_hourly_weather_forecast(observer_location, hours=hours_needed))
        hourly_forecast_tuple = tuple(hourly_forecast)

        # Calculate best seeing time windows from hourly forecast
        best_seeing_windows = self._calculate_best_seeing_windows(hourly_forecast, sunset_time, sunrise_time)

        # Get moonrise/moonset from moon_info
        moonrise_time = moon_info.moonrise_time if moon_info else None
        moonset_time = moon_info.moonset_time if moon_info else None

        # Calculate golden hour, blue hour, and astronomical twilight
        golden_hour = calculate_golden_hour(lat, lon, start_time)
        blue_hour = calculate_blue_hour(lat, lon, start_time)
        astronomical_twilight = calculate_astronomical_twilight(lat, lon, start_time)

        # Calculate galactic center visibility
        gc_start, gc_end = self._calculate_galactic_center_visibility(lat, lon, start_time, sunset_time, sunrise_time)

        # Get space weather conditions
        space_weather_alerts_list: list[str] = []
        geomagnetic_storm_level: int | None = None
        aurora_opportunity = False
        try:
            from celestron_nexstar.api.events.space_weather import get_space_weather_conditions

            # Run async function - this is a sync entry point, so asyncio.run() is safe
            swx = asyncio.run(get_space_weather_conditions())
            if swx.alerts:
                space_weather_alerts_list.extend(swx.alerts)

            if swx.g_scale:
                geomagnetic_storm_level = swx.g_scale.level
                if swx.g_scale.level >= 3:
                    aurora_opportunity = True
                    space_weather_alerts_list.append(
                        f"G{swx.g_scale.level} geomagnetic storm - Enhanced aurora possible"
                    )

            if swx.r_scale and swx.r_scale.level >= 3:
                space_weather_alerts_list.append(
                    f"R{swx.r_scale.level} radio blackout - GPS/communications may be affected"
                )

            if swx.solar_wind_bz is not None and swx.solar_wind_bz < -5:
                space_weather_alerts_list.append("Favorable solar wind conditions for aurora (negative Bz)")

        except Exception:
            # Space weather data unavailable, continue without it
            pass

        return ObservingConditions(
            timestamp=start_time,
            latitude=lat,
            longitude=lon,
            location_name=location_name,
            weather=weather,
            is_weather_suitable=is_weather_suitable,
            light_pollution=lp_data,
            limiting_magnitude=limiting_mag,
            aperture_mm=aperture,
            moon_illumination=moon_illum,
            moon_altitude=moon_alt,
            moon_phase=moon_phase,
            observing_quality_score=quality_score,
            seeing_score=seeing_score,
            recommendations=recommendations,
            warnings=warnings,
            best_seeing_windows=best_seeing_windows,
            hourly_seeing_forecast=hourly_forecast_tuple,
            sunrise_time=sunrise_time,
            sunset_time=sunset_time,
            moonrise_time=moonrise_time,
            moonset_time=moonset_time,
            golden_hour_evening_start=golden_hour[0],
            golden_hour_evening_end=golden_hour[1],
            golden_hour_morning_start=golden_hour[2],
            golden_hour_morning_end=golden_hour[3],
            blue_hour_evening_start=blue_hour[0],
            blue_hour_evening_end=blue_hour[1],
            blue_hour_morning_start=blue_hour[2],
            blue_hour_morning_end=blue_hour[3],
            astronomical_twilight_evening_start=astronomical_twilight[0],
            astronomical_twilight_evening_end=astronomical_twilight[1],
            astronomical_twilight_morning_start=astronomical_twilight[2],
            astronomical_twilight_morning_end=astronomical_twilight[3],
            galactic_center_start=gc_start,
            galactic_center_end=gc_end,
            space_weather_alerts=tuple(space_weather_alerts_list),
            geomagnetic_storm_level=geomagnetic_storm_level,
            aurora_opportunity=aurora_opportunity,
        )

    def get_recommended_objects(
        self,
        conditions: ObservingConditions | None = None,
        target_types: list[ObservingTarget] | CelestialObjectType | None = None,
        max_results: int = 20,
        best_for_seeing: bool = False,
        constellation: str | None = None,
    ) -> list[RecommendedObject]:
        """
        Get recommended objects to observe tonight.

        Args:
            conditions: Observing conditions (default: calculate now)
            target_types: Types of targets to include (default: all)
            max_results: Maximum number of recommendations
            best_for_seeing: Filter to only objects ideal for current seeing conditions

        Returns:
            List of recommended objects, sorted by priority
        """
        if conditions is None:
            conditions = self.get_tonight_conditions()

        # Pre-calculate moon position once (used for all objects)
        moon_info = get_moon_info(conditions.latitude, conditions.longitude, conditions.timestamp)
        moon_ra = moon_info.ra_hours if moon_info else None
        moon_dec = moon_info.dec_degrees if moon_info else None

        # Get objects from database with smart pre-filtering
        db = get_database()
        # Pre-filter by magnitude to reduce load:
        # - For poor seeing: only bright objects (mag < 10)
        # - For good seeing: reasonable limit (mag < 15)
        # - For excellent seeing: can go fainter (mag < 18)
        if conditions.seeing_score < 50:
            max_mag = 10.0  # Poor seeing: only bright objects
        elif conditions.seeing_score >= 80:
            max_mag = 18.0  # Excellent seeing: can see fainter
        else:
            max_mag = 15.0  # Good seeing: reasonable limit

        # Limit initial query to reduce memory usage
        # We'll get more than max_results to account for filtering
        initial_limit = min(5000, max_results * 50)  # Get up to 5k or 50x requested results

        import asyncio

        # If filtering by a specific object type, pass it to filter_objects
        # This ensures objects without magnitudes are still included for that type
        filter_object_type = None
        if target_types:
            from celestron_nexstar.api.core.enums import CelestialObjectType

            if isinstance(target_types, CelestialObjectType):
                filter_object_type = target_types

        all_objects = asyncio.run(
            db.filter_objects(
                object_type=filter_object_type,
                max_magnitude=max_mag,
                limit=initial_limit,
                constellation=constellation,
            )
        )

        # Filter by target types if specified
        if target_types:
            from celestron_nexstar.api.core.enums import CelestialObjectType

            filtered_objects = []
            seen_coordinates = set()  # Track seen coordinates to avoid duplicates
            seen_names = set()  # Track seen names to avoid duplicates

            # Check if target_types is a direct CelestialObjectType (not a list)
            is_direct_object_type = isinstance(target_types, CelestialObjectType)

            for obj in all_objects:
                # Create a unique key for deduplication based on coordinates
                # Objects at the same coordinates (within 0.01 hours RA, 0.1 degrees Dec) are considered duplicates
                # This handles cases like M31 = NGC 224 = Andromeda Galaxy
                coord_key = (round(obj.ra_hours, 2), round(obj.dec_degrees, 1))

                # Also check by name (normalized) to catch exact duplicates
                name_key = (obj.name.lower().strip(), obj.common_name.lower().strip() if obj.common_name else None)

                if coord_key in seen_coordinates or name_key[0] in seen_names:
                    continue  # Skip duplicate (same object, different catalog entry)

                # Handle direct object type filtering (e.g., "galaxy", "star", "planet")
                if is_direct_object_type:
                    if obj.object_type == target_types:
                        # Additional validation: exclude DSO catalog objects when filtering for stars
                        # This fixes cases where DSOs were incorrectly imported as type "star"
                        if target_types == CelestialObjectType.STAR and obj.catalog in (
                            "celestial_dsos",
                            "celestial_messier",
                            "celestial_local_group",
                        ):
                            continue  # Skip DSO catalog objects when filtering for stars
                        # Note: Double stars are automatically excluded from the star tab
                        # because obj.object_type == target_types requires exact match,
                        # and DOUBLE_STAR != STAR
                        filtered_objects.append(obj)
                        seen_coordinates.add(coord_key)
                        seen_names.add(name_key[0])
                        if name_key[1]:
                            seen_names.add(name_key[1])
                # Handle ObservingTarget category filtering
                elif isinstance(target_types, list) and (
                    (ObservingTarget.PLANETS in target_types and obj.object_type.value == "planet")
                    or (ObservingTarget.MESSIER in target_types and obj.catalog == "messier")
                    or (
                        ObservingTarget.DEEP_SKY in target_types
                        and obj.object_type.value in ("galaxy", "nebula", "cluster")
                    )
                    or (ObservingTarget.DOUBLE_STARS in target_types and obj.object_type.value == "double_star")
                ):
                    filtered_objects.append(obj)
                    seen_coordinates.add(coord_key)
                    seen_names.add(name_key[0])
                    if name_key[1]:
                        seen_names.add(name_key[1])
            all_objects = filtered_objects

        # Filter by visibility
        # Limit processing to reasonable number - we only need max_results * 2 for good candidates
        # This prevents processing thousands of objects when we only need 20
        processing_limit = max(max_results * 10, 500)  # Process up to 10x requested or 500, whichever is larger
        objects_to_process = all_objects[:processing_limit]

        config = get_current_configuration()
        visible_pairs = filter_visible_objects(
            objects_to_process,
            config=config,
            min_altitude_deg=20.0,
            observer_lat=conditions.latitude,
            observer_lon=conditions.longitude,
            dt=conditions.timestamp,
        )

        # Filter out objects that are never visible from this location
        # (objects whose transit altitude is below the horizon)
        from celestron_nexstar.api.observation.planning_utils import get_object_visibility_timeline

        truly_visible_pairs = []
        for obj, vis_info in visible_pairs:
            try:
                timeline = get_object_visibility_timeline(
                    obj,
                    observer_lat=conditions.latitude,
                    observer_lon=conditions.longitude,
                    start_time=conditions.timestamp,
                    days=1,
                )
                # Skip objects that are never visible (transit altitude below horizon)
                if timeline.is_never_visible:
                    continue
            except Exception:
                # If timeline calculation fails, keep the object (don't filter it out)
                pass
            truly_visible_pairs.append((obj, vis_info))

        visible_pairs = truly_visible_pairs

        # Filter by seeing conditions if poor seeing
        # Poor seeing (<50): Exclude very faint objects that require excellent seeing
        if conditions.seeing_score < 50:
            filtered_pairs = []
            for obj, vis_info in visible_pairs:
                # Keep bright objects, planets, and double stars
                # For very faint objects (mag > 10), skip if seeing is poor
                if obj.object_type.value in ("planet", "moon", "double_star") or (
                    obj.magnitude is not None and obj.magnitude < 10
                ):
                    filtered_pairs.append((obj, vis_info))
            visible_pairs = filtered_pairs

        # Score and rank objects (with cached moon position)
        recommendations = []
        seen_recommendations = set()  # Track seen objects to avoid duplicates in recommendations
        for obj, vis_info in visible_pairs:
            # Additional deduplication check - use name as key
            obj_key = obj.name.lower().strip()
            if obj_key in seen_recommendations:
                continue  # Skip if we've already added this object
            seen_recommendations.add(obj_key)

            rec = self._score_object(obj, conditions, vis_info, moon_ra=moon_ra, moon_dec=moon_dec)
            if rec:
                recommendations.append(rec)

        # Filter for best-for-seeing if requested
        if best_for_seeing:
            seeing = conditions.seeing_score
            if seeing >= 80:
                # Excellent seeing: prioritize faint deep-sky, double stars, planets
                recommendations = [
                    r
                    for r in recommendations
                    if (
                        (r.obj.object_type.value in ("galaxy", "nebula") and r.apparent_magnitude > 10)
                        or r.obj.object_type.value == "double_star"
                        or r.obj.object_type.value == "planet"
                    )
                ]
            elif seeing < 50:
                # Poor seeing: prioritize bright objects, planets
                recommendations = [
                    r
                    for r in recommendations
                    if (
                        r.obj.object_type.value == "planet"
                        or (r.apparent_magnitude < 6)
                        or (r.obj.object_type.value == "double_star" and r.apparent_magnitude < 5)
                    )
                ]

        # Sort by priority, then by visibility probability (when conditions are poor),
        # then by magnitude (brighter first), then by observability score
        # Lower magnitude = brighter = better, so we sort ascending by magnitude
        # When conditions are poor (quality < 0.5), prioritize visibility probability
        if conditions.observing_quality_score < 0.5:
            # Poor conditions: prioritize objects you're most likely to actually see
            recommendations.sort(
                key=lambda r: (
                    r.priority,
                    -r.visibility_probability,  # Higher probability first
                    r.apparent_magnitude
                    if r.apparent_magnitude is not None
                    else 999.0,  # Put objects without magnitude last
                    -r.observability_score,
                )
            )
        else:
            # Good conditions: standard sorting
            recommendations.sort(
                key=lambda r: (
                    r.priority,
                    r.apparent_magnitude
                    if r.apparent_magnitude is not None
                    else 999.0,  # Put objects without magnitude last
                    -r.observability_score,
                )
            )

        return recommendations[:max_results]

    def _calculate_visibility_probability(
        self,
        obj: CelestialObject,
        conditions: ObservingConditions,
        vis_info: VisibilityInfo,
    ) -> float | tuple[float, list[str]]:
        """
        Calculate the probability (0.0-1.0) of actually seeing an object given current conditions.

        This factors in:
        - Daytime/nighttime (objects not visible during day except Sun)
        - Seeing conditions (0-100)
        - Cloud cover
        - Overall quality score
        - Object type sensitivity to conditions
        - Object brightness relative to limiting magnitude
        """
        # Check if it's daytime - stars and most objects are not visible during the day
        # (Sun is the only exception, but we don't typically check visibility for it)
        is_daytime = False
        try:
            sun_info = get_sun_info(conditions.latitude, conditions.longitude, conditions.timestamp)
            if sun_info:
                is_daytime = sun_info.is_daytime
        except Exception:
            # If we can't determine, assume nighttime (conservative)
            is_daytime = False

        # During daytime, most celestial objects are not visible (sky is too bright)
        # Only the Sun itself would be visible, but we don't check visibility for it
        if is_daytime and obj.object_type.value != "sun":
            daytime_explanations = ["Daytime - object not visible (sky too bright)"]
            return (0.0, daytime_explanations)

        # Start with observability score (altitude, magnitude, etc.)
        prob = vis_info.observability_score

        # Factor 1: Seeing conditions (0-100)
        # Poor seeing (<50) significantly reduces probability, especially for faint objects
        seeing = conditions.seeing_score
        seeing_factor = 1.0

        if seeing < 20:
            # Very poor seeing (0-20): Only bright objects visible
            if obj.magnitude and obj.magnitude > 4.0:
                seeing_factor = 0.1  # Very faint objects almost impossible
            elif obj.magnitude and obj.magnitude > 2.0:
                seeing_factor = 0.3  # Moderate objects very difficult
            else:
                seeing_factor = 0.6  # Bright objects still somewhat visible
        elif seeing < 50:
            # Poor seeing (20-50): Bright objects OK, faint objects difficult
            if obj.magnitude and obj.magnitude > 6.0:
                seeing_factor = 0.3
            elif obj.magnitude and obj.magnitude > 4.0:
                seeing_factor = 0.6
            else:
                seeing_factor = 0.8
        elif seeing < 70:
            # Fair seeing (50-70): Most objects visible
            seeing_factor = 0.85 + 0.15 * (seeing - 50) / 20
        else:
            # Good to excellent seeing (70-100)
            seeing_factor = 1.0

        # Factor 2: Cloud cover
        cloud_factor = 1.0
        if conditions.weather.cloud_cover_percent is not None:
            cloud_cover = conditions.weather.cloud_cover_percent
            if cloud_cover > 80:
                cloud_factor = 0.1  # Heavy clouds, almost impossible
            elif cloud_cover > 60:
                cloud_factor = 0.3  # Mostly cloudy, very difficult
            elif cloud_cover > 40:
                cloud_factor = 0.6  # Partly cloudy, challenging
            elif cloud_cover > 20:
                cloud_factor = 0.8  # Some clouds, mostly OK
            else:
                cloud_factor = 1.0  # Clear skies

        # Factor 3: Overall quality score (already factors weather, light pollution, moon)
        # Convert from 0.0-1.0 scale to probability impact
        quality_factor = 0.3 + 0.7 * conditions.observing_quality_score  # Minimum 30% even in poor conditions

        # Factor 4: Object type sensitivity
        # Some objects are more sensitive to conditions than others
        type_factor = 1.0
        if obj.object_type.value == "planet":
            # Planets are bright and less affected by seeing (though detail is)
            type_factor = 0.9  # Still visible even in poor conditions
        elif obj.object_type.value == "star":
            # Stars are point sources, less affected by seeing than extended objects
            type_factor = 0.95 if obj.magnitude and obj.magnitude < 3.0 else 0.85
        elif obj.object_type.value in ("galaxy", "nebula"):
            # Extended objects very sensitive to seeing and transparency
            if seeing < 50:
                type_factor = 0.3  # Very difficult in poor seeing
            elif seeing < 70:
                type_factor = 0.6
            else:
                type_factor = 1.0
        elif obj.object_type.value == "cluster":
            # Clusters are somewhat sensitive
            type_factor = 0.7 if seeing < 50 else 0.9

        # Combine all factors
        final_prob = prob * seeing_factor * cloud_factor * quality_factor * type_factor

        # Build explanations for why probability might be low
        explanations: list[str] = []

        # Seeing explanations
        if seeing < 20:
            if obj.magnitude and obj.magnitude > 4.0:
                explanations.append(
                    f"Very poor seeing ({seeing:.0f}/100) makes faint objects (mag >4) nearly impossible"
                )
            elif obj.magnitude and obj.magnitude > 2.0:
                explanations.append(
                    f"Very poor seeing ({seeing:.0f}/100) makes moderate objects (mag 2-4) very difficult"
                )
            else:
                explanations.append(f"Very poor seeing ({seeing:.0f}/100) limits visibility even for bright objects")
        elif seeing < 50:
            if obj.object_type.value in ("galaxy", "nebula"):
                explanations.append(
                    f"Poor seeing conditions ({seeing:.0f}/100) - galaxies/nebulae are extended objects "
                    f"that require good seeing for clear views"
                )
            elif obj.magnitude and obj.magnitude > 4.0:
                explanations.append(
                    f"Poor seeing conditions ({seeing:.0f}/100) make faint objects (mag {obj.magnitude:.1f}) difficult to see"
                )
            else:
                explanations.append(f"Poor seeing conditions ({seeing:.0f}/100) reduce visibility")
        elif seeing < 70:
            explanations.append(f"Fair seeing conditions ({seeing:.0f}/100) - acceptable but not ideal")

        # Cloud cover explanations
        if conditions.weather.cloud_cover_percent is not None:
            cloud_cover = conditions.weather.cloud_cover_percent
            if cloud_cover > 80:
                explanations.append(f"Heavy cloud cover ({cloud_cover:.0f}%) blocks most observations")
            elif cloud_cover > 60:
                explanations.append(f"Mostly cloudy ({cloud_cover:.0f}%) makes observation very difficult")
            elif cloud_cover > 40:
                explanations.append(f"Partly cloudy ({cloud_cover:.0f}%) may obscure the object")

        # Quality score explanations
        if conditions.observing_quality_score < 0.5:
            explanations.append(
                f"Poor overall conditions (quality score: {conditions.observing_quality_score:.0%}) "
                f"due to weather, light pollution, or moon brightness"
            )

        # Object type sensitivity
        if obj.object_type.value in ("galaxy", "nebula") and seeing < 70:
            explanations.append(
                "Extended objects (galaxies/nebulae) are more sensitive to seeing conditions than point sources"
            )

        # Add summary if probability is much lower than observability
        if vis_info.observability_score > 0.8 and final_prob < 0.3:
            explanations.append(
                f"While the object is well-positioned (observability: {vis_info.observability_score:.0%}), "
                f"current conditions reduce the chance of actually seeing it to {final_prob:.0%}"
            )

        # Clamp to 0.0-1.0
        final_prob_clamped = max(0.0, min(1.0, final_prob))

        # Return tuple with explanations if probability is low, otherwise just the probability
        if final_prob_clamped < 0.5 and explanations:
            return (final_prob_clamped, explanations)
        return final_prob_clamped

    def _calculate_quality_score(
        self,
        weather: WeatherData,
        lp_data: LightPollutionData,
        moon_illum: float,
        weather_status: str,
    ) -> float:
        """Calculate overall observing quality score (0.0-1.0)."""
        # Weather component (0.0-0.5 of total)
        weather_scores = {
            "excellent": 0.5,  # 50% of total score
            "good": 0.4,  # 40% of total score
            "fair": 0.25,  # 25% of total score
            "poor": 0.1,  # 10% of total score
            "unavailable": 0.2,  # 20% of total score (assume decent if unknown)
        }
        weather_score = weather_scores.get(weather_status, 0.2)

        # Light pollution component (0.0-0.3 of total)
        # Bortle 1-3 = excellent (0.3), Bortle 4-6 = fair (0.15), Bortle 7-9 = poor (0.0)
        if lp_data.bortle_class.value <= 3:
            lp_score = 0.3
        elif lp_data.bortle_class.value <= 6:
            lp_score = 0.15
        else:
            lp_score = 0.0

        # Moon component (0.0-0.2 of total)
        # New moon = excellent (0.2), Full moon = poor (0.0)
        moon_score = (1.0 - moon_illum) * 0.2

        return weather_score + lp_score + moon_score

    def _generate_recommendations(
        self,
        weather: WeatherData,
        lp_data: LightPollutionData,
        moon_illum: float,
        quality_score: float,
        weather_status: str,
        weather_warning: str,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Generate recommendations and warnings."""
        recommendations = []
        warnings = []

        # Weather-based
        if weather.cloud_cover_percent is not None:
            if weather.cloud_cover_percent < 10:
                recommendations.append("Excellent night for deep-sky observing")
            elif weather.cloud_cover_percent < 30:
                recommendations.append("Good conditions for most objects")
            else:
                warnings.append(f"High cloud cover ({weather.cloud_cover_percent:.0f}%)")

        # Note: WeatherData doesn't have precipitation_probability in current implementation
        # This would need to be added to weather.py if needed

        # Only add weather warning if it's an actual warning (not "Good observing conditions")
        if weather_warning and weather_status != "unavailable" and weather_warning != "Good observing conditions":
            warnings.append(weather_warning)

        # Light pollution
        if lp_data.bortle_class.value <= 3:
            recommendations.append("Dark skies excellent for faint objects")
        elif lp_data.bortle_class.value >= 7:
            recommendations.append("Focus on bright objects (planets, Moon, bright clusters)")

        # Moon
        if moon_illum > 0.8:
            warnings.append("Bright moon will wash out faint objects")
            recommendations.append("Good night for planetary observing")
        elif moon_illum < 0.2:
            recommendations.append("New moon ideal for deep-sky objects")

        return tuple(recommendations), tuple(warnings)

    def _score_object(
        self,
        obj: CelestialObject,
        conditions: ObservingConditions,
        vis_info: VisibilityInfo,
        moon_ra: float | None = None,
        moon_dec: float | None = None,
    ) -> RecommendedObject | None:
        """Score an object for recommendation."""
        if not vis_info.is_visible:
            return None

        # Determine priority based on conditions
        priority = self._determine_priority(obj, conditions, vis_info)

        # Generate viewing tips
        tips = self._generate_viewing_tips(obj, conditions)

        # Find best viewing time (when highest in sky)
        best_time = self._calculate_best_viewing_time(
            obj, conditions.latitude, conditions.longitude, conditions.timestamp
        )

        # Calculate moon separation (using cached moon position)
        moon_separation = self._calculate_moon_separation_fast(obj, moon_ra, moon_dec)

        # Calculate visibility probability based on current conditions
        visibility_prob_result = self._calculate_visibility_probability(obj, conditions, vis_info)
        # Handle both tuple (prob, explanations) and float return types
        if isinstance(visibility_prob_result, tuple):
            visibility_prob, _ = visibility_prob_result
        else:
            visibility_prob = visibility_prob_result

        return RecommendedObject(
            obj=obj,
            altitude=vis_info.altitude_deg or 0.0,
            azimuth=vis_info.azimuth_deg or 0.0,
            best_viewing_time=best_time,
            visible_duration_hours=8.0,  # Simplified
            apparent_magnitude=obj.magnitude or 0.0,
            observability_score=vis_info.observability_score,
            visibility_probability=visibility_prob,
            priority=priority,
            reason=f"Well positioned at {vis_info.altitude_deg:.0f}° altitude" if vis_info.altitude_deg else "Visible",
            viewing_tips=tips,
            moon_separation_deg=moon_separation,
        )

    def _determine_priority(
        self,
        obj: CelestialObject,
        conditions: ObservingConditions,
        vis_info: VisibilityInfo,
    ) -> int:
        """Determine observation priority (1=highest, 5=lowest) based on conditions."""
        seeing = conditions.seeing_score

        # Priority 1: Objects that benefit from current seeing conditions
        # Excellent seeing (>=80): Prioritize faint deep-sky, high-magnification targets
        if seeing >= 80:
            if obj.object_type.value in ("galaxy", "nebula") and obj.magnitude and obj.magnitude > 10:
                return 1
            if obj.object_type.value == "double_star":
                return 1
            if obj.object_type.value == "planet":
                return 1  # Planets always good with excellent seeing

        # Poor seeing (<50): Prioritize bright objects, planets, double stars
        elif seeing < 50:
            if obj.object_type.value == "planet":
                return 1
            if obj.object_type.value == "double_star" and obj.magnitude and obj.magnitude < 5:
                return 1
            if obj.magnitude and obj.magnitude < 6:  # Bright objects
                return 2

        # Good seeing (50-79): Balanced recommendations
        else:
            if obj.object_type.value == "planet":
                return 1
            # For good seeing, prioritize based on object type and brightness
            if obj.object_type.value == "double_star":
                return 1
            if (
                conditions.light_pollution.bortle_class.value <= 3
                and obj.magnitude
                and obj.magnitude < 8
                and obj.object_type.value != "star"
            ):
                # Only apply to non-stars here (stars handled below)
                return 2

        # Priority 3: Objects well positioned (high altitude) - check before star-specific logic
        if vis_info.altitude_deg and vis_info.altitude_deg > 60:
            return 3

        # Priority 2-3: Bright stars (navigation stars, bright named stars)
        # Handle stars separately with more granular priority
        if obj.object_type.value == "star":
            # Check for bright stars in dark skies first (priority 2)
            if conditions.light_pollution.bortle_class.value <= 3 and obj.magnitude and obj.magnitude < 8:
                return 2
            if obj.magnitude and obj.magnitude < 2.0:  # Very bright stars (1st magnitude and brighter)
                return 2
            elif (obj.magnitude and obj.magnitude < 4.0) or obj.common_name:  # Bright stars (2nd-3rd magnitude)
                return 3
            elif obj.magnitude and obj.magnitude < 6.0:  # Moderately bright stars
                return 4
            else:
                # Faint stars or stars without magnitude
                return 5

        # Priority 2: Bright objects in dark skies (non-stars)
        if conditions.light_pollution.bortle_class.value <= 3 and obj.magnitude and obj.magnitude < 8:
            return 2

        # Priority 4: Messier objects
        if obj.catalog == "messier":
            return 4

        # Priority 5: Everything else
        return 5

    def _generate_viewing_tips(
        self,
        obj: CelestialObject,
        conditions: ObservingConditions,
    ) -> tuple[str, ...]:
        """Generate viewing tips for an object."""
        tips = []
        seeing = conditions.seeing_score

        # Seeing-based recommendations
        if seeing >= 80:
            if obj.object_type.value == "planet":
                tips.append("Excellent seeing - ideal for high-magnification planetary detail")
            elif obj.object_type.value == "double_star":
                tips.append("Excellent seeing - perfect for splitting close doubles")
            elif obj.object_type.value in ("galaxy", "nebula"):
                tips.append("Excellent seeing - good for faint detail")
        elif seeing < 50:
            if obj.object_type.value in ("galaxy", "nebula", "cluster"):
                tips.append("Poor seeing - focus on bright, low-power objects")
            elif obj.object_type.value == "planet":
                tips.append("Poor seeing - detail may be limited")
        else:
            if obj.object_type.value == "planet":
                tips.append("Good seeing - moderate magnification recommended")

        # Eyepiece recommendations
        if obj.object_type.value in ("galaxy", "nebula", "cluster"):
            tips.append("Use low power for widefield view")
        elif obj.object_type.value == "planet":
            tips.append("Use high power (2-3mm eyepiece)")

        # Filter recommendations
        if conditions.moon_illumination > 0.5 and obj.object_type.value == "nebula":
            tips.append("Consider UHC or OIII filter to reduce moon glare")

        # Light pollution
        if conditions.light_pollution.bortle_class.value >= 6:
            tips.append("Light pollution will reduce contrast")

        return tuple(tips)

    def _calculate_best_viewing_time(
        self,
        obj: CelestialObject,
        lat: float,
        lon: float,
        start_time: datetime,
    ) -> datetime:
        """Calculate when object is highest in sky (transit)."""
        # Calculate Local Sidereal Time
        lst_hours = calculate_lst(lon, start_time)

        # Object's RA in hours
        obj_ra = obj.ra_hours

        # Hour angle at transit is 0 (object is on meridian)
        # LST = RA at transit
        # Calculate time difference needed to reach transit
        ha_hours = lst_hours - obj_ra

        # Normalize hour angle to -12 to +12 hours
        if ha_hours > 12:
            ha_hours -= 24
        elif ha_hours < -12:
            ha_hours += 24

        # Convert hour angle to time difference
        # 1 hour angle = 1 hour of sidereal time ≈ 0.9973 hours of solar time
        time_diff_hours = ha_hours * 0.9973

        transit_time = start_time + timedelta(hours=time_diff_hours)

        # If transit is more than 12 hours away, use next transit
        if abs(time_diff_hours) > 12:
            if time_diff_hours > 0:
                transit_time -= timedelta(hours=24)
            else:
                transit_time += timedelta(hours=24)

        return transit_time

    def _calculate_moon_separation(
        self,
        obj: CelestialObject,
        conditions: ObservingConditions,
    ) -> float | None:
        """Calculate angular separation between object and moon."""
        try:
            moon_info = get_moon_info(conditions.latitude, conditions.longitude, conditions.timestamp)
            if not moon_info:
                return None

            # Calculate angular separation
            separation = angular_separation(
                obj.ra_hours,
                obj.dec_degrees,
                moon_info.ra_hours,
                moon_info.dec_degrees,
            )

            return separation
        except Exception:
            return None

    def _calculate_moon_separation_fast(
        self,
        obj: CelestialObject,
        moon_ra: float | None,
        moon_dec: float | None,
    ) -> float | None:
        """Calculate angular separation using pre-calculated moon position (faster)."""
        if moon_ra is None or moon_dec is None:
            return None

        try:
            separation = angular_separation(
                obj.ra_hours,
                obj.dec_degrees,
                moon_ra,
                moon_dec,
            )
            return separation
        except Exception:
            return None

    def _calculate_best_seeing_windows(
        self,
        hourly_forecast: list[HourlySeeingForecast],
        sunset_time: datetime | None,
        sunrise_time: datetime | None,
    ) -> tuple[tuple[datetime, datetime], ...]:
        """
        Calculate discrete time windows with excellent or good seeing conditions.

        Analyzes hourly forecast to find contiguous periods where seeing is:
        - Excellent (>= 80): Preferred for high-quality observations
        - Good (>= 60): Used if no excellent periods found

        Returns:
            Tuple of (start_time, end_time) tuples for each window
        """
        if not hourly_forecast or sunset_time is None or sunrise_time is None:
            return ()

        try:
            # Filter forecasts to observing window (sunset to sunrise)
            # Ensure times are UTC
            if sunset_time.tzinfo is None:
                sunset_time = sunset_time.replace(tzinfo=UTC)
            if sunrise_time.tzinfo is None:
                sunrise_time = sunrise_time.replace(tzinfo=UTC)

            # Extend to next sunrise if needed
            if sunrise_time < sunset_time:
                sunrise_time = sunrise_time + timedelta(days=1)

            # Filter forecasts within the observing window
            observing_forecasts = []
            for forecast in hourly_forecast:
                forecast_ts = forecast.timestamp
                if forecast_ts.tzinfo is None:
                    forecast_ts = forecast_ts.replace(tzinfo=UTC)
                elif forecast_ts.tzinfo != UTC:
                    forecast_ts = forecast_ts.astimezone(UTC)

                if sunset_time <= forecast_ts <= sunrise_time:
                    observing_forecasts.append(forecast)

            if not observing_forecasts:
                return ()

            # First, try to find excellent seeing periods (>= 80)
            windows = self._find_seeing_windows(observing_forecasts, min_score=80.0)

            # If no excellent periods, fall back to good seeing (>= 60)
            if not windows:
                windows = self._find_seeing_windows(observing_forecasts, min_score=60.0)

            return tuple(windows)
        except Exception as e:
            logger.error(f"Failed to calculate best seeing windows: {e}")
            return ()

    def _find_seeing_windows(
        self,
        forecasts: list[HourlySeeingForecast],
        min_score: float,
    ) -> list[tuple[datetime, datetime]]:
        """
        Find contiguous time windows where seeing score is at least min_score.

        Args:
            forecasts: List of hourly forecasts, sorted by timestamp
            min_score: Minimum seeing score threshold (e.g., 80 for excellent, 60 for good)

        Returns:
            List of (start_time, end_time) tuples for contiguous windows
        """
        if not forecasts:
            return []

        windows = []
        window_start = None

        # Sort forecasts by timestamp to ensure chronological order
        sorted_forecasts = sorted(
            forecasts, key=lambda f: f.timestamp if f.timestamp.tzinfo else f.timestamp.replace(tzinfo=UTC)
        )

        for _i, forecast in enumerate(sorted_forecasts):
            forecast_ts = forecast.timestamp
            if forecast_ts.tzinfo is None:
                forecast_ts = forecast_ts.replace(tzinfo=UTC)
            elif forecast_ts.tzinfo != UTC:
                forecast_ts = forecast_ts.astimezone(UTC)

            if forecast.seeing_score >= min_score:
                if window_start is None:
                    # Start of a new window - use this forecast's timestamp
                    window_start = forecast_ts
            else:
                # Seeing dropped below threshold - end window at current forecast's timestamp
                # (which represents the start of this hour, i.e., end of previous hour)
                if window_start is not None:
                    # Only add window if it's at least 1 hour long
                    if (forecast_ts - window_start).total_seconds() >= 3600:
                        windows.append((window_start, forecast_ts))
                    window_start = None

        # Close any open window at the end
        if window_start is not None:
            last_forecast = sorted_forecasts[-1]
            last_ts = last_forecast.timestamp
            if last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=UTC)
            elif last_ts.tzinfo != UTC:
                last_ts = last_ts.astimezone(UTC)
            # Only add window if it's at least 1 hour long
            if (last_ts - window_start).total_seconds() >= 3600:
                windows.append((window_start, last_ts))

        return windows

    def _calculate_galactic_center_visibility(
        self,
        lat: float,
        lon: float,
        start_time: datetime,
        sunset_time: datetime | None,
        sunrise_time: datetime | None,
    ) -> tuple[datetime | None, datetime | None]:
        """
        Calculate when the galactic center is visible.

        The galactic center (Sagittarius A*) is at approximately:
        RA: 17h 45m 40s (17.7611 hours)
        Dec: -29° 00' 28" (-29.0078 degrees)

        Returns:
            Tuple of (start_time, end_time) when galactic center is above 10° altitude
            and between sunset and sunrise, or (None, None) if not visible
        """
        # Galactic center coordinates
        gc_ra = 17.7611  # hours
        gc_dec = -29.0078  # degrees
        min_altitude = 10.0  # Minimum altitude for visibility (degrees)

        if sunset_time is None or sunrise_time is None:
            return (None, None)

        try:
            # Sample from sunset to sunrise at 5-minute intervals
            gc_start = None
            gc_end = None
            prev_alt = None

            # Start from sunset
            check_time = sunset_time
            # Extend to next sunrise if needed
            end_time = sunrise_time + timedelta(days=1) if sunrise_time < sunset_time else sunrise_time

            while check_time <= end_time:
                alt, _az = ra_dec_to_alt_az(gc_ra, gc_dec, lat, lon, check_time)

                # Check if we're crossing the minimum altitude threshold
                if prev_alt is not None:
                    # Rising above minimum altitude
                    if prev_alt < min_altitude and alt >= min_altitude and gc_start is None:
                        # Interpolate to find exact time
                        gc_start = check_time - timedelta(minutes=2.5)  # Approximate midpoint
                        if gc_start.tzinfo is None:
                            gc_start = gc_start.replace(tzinfo=UTC)
                    # Falling below minimum altitude
                    elif prev_alt >= min_altitude and alt < min_altitude and gc_start is not None:
                        # Interpolate to find exact time
                        gc_end = check_time - timedelta(minutes=2.5)  # Approximate midpoint
                        if gc_end.tzinfo is None:
                            gc_end = gc_end.replace(tzinfo=UTC)
                        break  # Found both start and end

                prev_alt = alt
                check_time += timedelta(minutes=5)

            return (gc_start, gc_end)
        except Exception:
            return (None, None)


# Singleton
_planner = ObservationPlanner()


def get_tonight_plan(
    lat: float | None = None,
    lon: float | None = None,
    target_types: list[ObservingTarget] | None = None,
) -> tuple[ObservingConditions, list[RecommendedObject]]:
    """
    Get complete observing plan for tonight.

    Returns:
        (conditions, recommended_objects)
    """
    conditions = _planner.get_tonight_conditions(lat, lon)
    objects = _planner.get_recommended_objects(conditions, target_types)
    return conditions, objects

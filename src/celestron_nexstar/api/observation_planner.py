"""
Observation Session Planner

Combines weather, light pollution, object visibility, and telescope
capabilities to recommend what to observe tonight.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from .catalogs import CelestialObject
from .database import get_database
from .enums import SkyBrightness
from .light_pollution import LightPollutionData, get_light_pollution_data
from .observer import ObserverLocation, get_observer_location
from .optics import calculate_limiting_magnitude, get_current_configuration
from .solar_system import calculate_blue_hour, calculate_golden_hour, get_moon_info, get_sun_info
from .utils import angular_separation, calculate_lst
from .visibility import VisibilityInfo, filter_visible_objects
from .weather import (
    HourlySeeingForecast,
    WeatherData,
    assess_observing_conditions,
    calculate_seeing_conditions,
    fetch_hourly_weather_forecast,
    fetch_weather,
)


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
    MESSIER = "messier"
    CALDWELL = "caldwell"
    NGC_IC = "ngc_ic"


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
    moon_phase: str | None  # Phase name (e.g., "New Moon", "Waxing Crescent")

    # Overall assessment
    observing_quality_score: float  # 0.0-1.0
    seeing_score: float  # 0.0-100.0 (astronomical seeing conditions)
    recommendations: tuple[str, ...]
    warnings: tuple[str, ...]

    # Time windows
    best_seeing_window_start: datetime | None = None  # When seeing typically improves
    best_seeing_window_end: datetime | None = None  # When seeing typically degrades

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
                raise ValueError("No location set. Use 'nexstar location set' command.")
            lat, lon = location.latitude, location.longitude
            location_name = location.name
        else:
            location_name = None

        # Get weather forecast
        if start_time is None:
            start_time = datetime.now(UTC)
        elif start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=UTC)

        # Fetch weather (synchronous for now)
        # Create location object for weather API
        observer_location = ObserverLocation(
            name=location_name or "Current Location",
            latitude=lat,
            longitude=lon,
            elevation=0.0,
        )

        weather = fetch_weather(observer_location)
        weather_status, weather_warning = assess_observing_conditions(weather)
        is_weather_suitable = weather_status in ("excellent", "good", "fair")

        # Get light pollution
        lp_data = get_light_pollution_data(lat, lon)

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

        # Calculate best seeing time window (typically 2-3 hours after sunset, before sunrise)
        best_seeing_start, best_seeing_end = self._calculate_best_seeing_window(lat, lon, start_time)

        # Get sun and moon event times first to calculate how many hours of forecast we need
        sun_info = get_sun_info(lat, lon, start_time)
        sunrise_time = sun_info.sunrise_time if sun_info else None
        sunset_time = sun_info.sunset_time if sun_info else None
        
        # Fetch 3-day forecast (72 hours) to ensure we have enough data
        # This covers from 1 hour before sunset to sunrise with plenty of buffer
        hours_needed = 72  # 3 days

        # Fetch hourly seeing forecast (if available - requires Pro subscription)
        hourly_forecast = fetch_hourly_weather_forecast(observer_location, hours=hours_needed)
        hourly_forecast_tuple = tuple(hourly_forecast)

        # Get moonrise/moonset from moon_info
        moonrise_time = moon_info.moonrise_time if moon_info else None
        moonset_time = moon_info.moonset_time if moon_info else None

        # Calculate golden hour and blue hour
        golden_hour = calculate_golden_hour(lat, lon, start_time)
        blue_hour = calculate_blue_hour(lat, lon, start_time)

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
            best_seeing_window_start=best_seeing_start,
            best_seeing_window_end=best_seeing_end,
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
        )

    def get_recommended_objects(
        self,
        conditions: ObservingConditions | None = None,
        target_types: list[ObservingTarget] | None = None,
        max_results: int = 20,
        best_for_seeing: bool = False,
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

        all_objects = db.filter_objects(max_magnitude=max_mag, limit=initial_limit)

        # Filter by target types if specified
        if target_types:
            filtered_objects = []
            for obj in all_objects:
                if (
                    (ObservingTarget.PLANETS in target_types and obj.object_type.value == "planet")
                    or (ObservingTarget.MESSIER in target_types and obj.catalog == "messier")
                    or (ObservingTarget.CALDWELL in target_types and obj.catalog == "caldwell")
                    or (ObservingTarget.NGC_IC in target_types and obj.catalog in ("ngc", "ic"))
                    or (
                        ObservingTarget.DEEP_SKY in target_types
                        and obj.object_type.value in ("galaxy", "nebula", "cluster")
                    )
                    or (ObservingTarget.DOUBLE_STARS in target_types and obj.object_type.value == "double_star")
                ):
                    filtered_objects.append(obj)
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

        # Filter by seeing conditions if poor seeing
        # Poor seeing (<50): Exclude very faint objects that require excellent seeing
        if conditions.seeing_score < 50:
            filtered_pairs = []
            for obj, vis_info in visible_pairs:
                # Keep bright objects, planets, and double stars
                # For very faint objects (mag > 10), skip if seeing is poor
                if (
                    obj.object_type.value in ("planet", "moon", "double_star")
                    or (obj.magnitude is not None and obj.magnitude < 10)
                ):
                    filtered_pairs.append((obj, vis_info))
            visible_pairs = filtered_pairs

        # Score and rank objects (with cached moon position)
        recommendations = []
        for obj, vis_info in visible_pairs:
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

        # Sort by priority and observability score
        recommendations.sort(key=lambda r: (r.priority, -r.observability_score))

        return recommendations[:max_results]

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

        return RecommendedObject(
            obj=obj,
            altitude=vis_info.altitude_deg or 0.0,
            azimuth=vis_info.azimuth_deg or 0.0,
            best_viewing_time=best_time,
            visible_duration_hours=8.0,  # Simplified
            apparent_magnitude=obj.magnitude or 0.0,
            observability_score=vis_info.observability_score,
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
            if conditions.light_pollution.bortle_class.value <= 3 and obj.magnitude and obj.magnitude < 8:
                return 2

        # Priority 2: Bright objects in dark skies
        if conditions.light_pollution.bortle_class.value <= 3 and obj.magnitude and obj.magnitude < 8:
            return 2

        # Priority 3: Objects well positioned (high altitude)
        if vis_info.altitude_deg and vis_info.altitude_deg > 60:
            return 3

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

    def _calculate_best_seeing_window(
        self,
        lat: float,
        lon: float,
        start_time: datetime,
    ) -> tuple[datetime | None, datetime | None]:
        """
        Calculate best seeing time window.

        Typically, seeing improves 2-3 hours after sunset (when ground cools)
        and degrades 1-2 hours before sunrise (when ground warms).

        Returns:
            Tuple of (start_time, end_time) or (None, None) if calculation fails
        """
        try:
            sun_info = get_sun_info(lat, lon, start_time)
            if not sun_info or not sun_info.sunset_time or not sun_info.sunrise_time:
                return (None, None)

            # Best seeing typically starts 2-3 hours after sunset
            best_start = sun_info.sunset_time + timedelta(hours=2.5)

            # Best seeing typically ends 1-2 hours before sunrise
            best_end = sun_info.sunrise_time - timedelta(hours=1.5)

            # Ensure times are in UTC
            if best_start.tzinfo is None:
                best_start = best_start.replace(tzinfo=UTC)
            if best_end.tzinfo is None:
                best_end = best_end.replace(tzinfo=UTC)

            # If end is before start, it means we're past midnight
            # In that case, extend to next sunrise
            if best_end < best_start:
                best_end = sun_info.sunrise_time + timedelta(days=1) - timedelta(hours=1.5)

            return (best_start, best_end)
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

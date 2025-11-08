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
from .solar_system import get_moon_info
from .visibility import VisibilityInfo, filter_visible_objects
from .weather import WeatherData, assess_observing_conditions, fetch_weather


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
    recommendations: tuple[str, ...]
    warnings: tuple[str, ...]


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

        recommendations, warnings = self._generate_recommendations(
            weather, lp_data, moon_illum, quality_score, weather_status, weather_warning
        )

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
            recommendations=recommendations,
            warnings=warnings,
        )

    def get_recommended_objects(
        self,
        conditions: ObservingConditions | None = None,
        target_types: list[ObservingTarget] | None = None,
        max_results: int = 20,
    ) -> list[RecommendedObject]:
        """
        Get recommended objects to observe tonight.

        Args:
            conditions: Observing conditions (default: calculate now)
            target_types: Types of targets to include (default: all)
            max_results: Maximum number of recommendations

        Returns:
            List of recommended objects, sorted by priority
        """
        if conditions is None:
            conditions = self.get_tonight_conditions()

        # Get all objects from database (prefer database over YAML catalogs)
        db = get_database()
        all_objects = db.filter_objects(limit=10000)  # Get up to 10k objects

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
        config = get_current_configuration()
        visible_pairs = filter_visible_objects(
            all_objects,
            config=config,
            min_altitude_deg=20.0,
            observer_lat=conditions.latitude,
            observer_lon=conditions.longitude,
            dt=conditions.timestamp,
        )

        # Score and rank objects
        recommendations = []
        for obj, vis_info in visible_pairs:
            rec = self._score_object(obj, conditions, vis_info)
            if rec:
                recommendations.append(rec)

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
        )

    def _determine_priority(
        self,
        obj: CelestialObject,
        conditions: ObservingConditions,
        vis_info: VisibilityInfo,
    ) -> int:
        """Determine observation priority (1=highest, 5=lowest)."""
        # Priority 1: Planets (always interesting)
        if obj.object_type.value == "planet":
            return 1

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
        # Simplified: assume transit is when RA = LST
        # In reality, calculate when altitude is maximum
        # For now, return 2 hours from start
        return start_time + timedelta(hours=2)


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

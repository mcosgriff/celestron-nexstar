# "What's Visible Tonight?" Feature Plan

## Overview

Create an intelligent observing planner that answers "What can I see tonight?" by combining:
- **Date/Time**: Current or future observing session
- **Location**: GPS coordinates or saved location
- **Weather**: Cloud cover, rain, fog forecasts
- **Light Pollution**: Bortle scale / SQM values
- **Telescope Capabilities**: Aperture, limiting magnitude
- **Object Database**: 40,000+ objects from catalog expansion

## Current Capabilities (Already Built!)

### ✅ Existing Infrastructure

**Location Management** (`observer.py`):
- GPS coordinates (lat/lon)
- Saved locations with names
- Geocoding support (address → coordinates)

**Visibility Calculations** (`visibility.py`):
- Altitude/azimuth calculations
- Atmospheric extinction
- Limiting magnitude
- Observability scoring (0.0-1.0)
- Filter visible objects

**Optical Configuration** (`optics.py`):
- Telescope aperture
- Eyepiece focal lengths
- Limiting magnitude calculations
- Field of view

**Ephemeris** (`ephemeris.py`):
- Planetary positions
- Moon positions
- Dynamic object tracking

---

## New Components Needed

### 1. Weather Integration Module

**File**: `src/celestron_nexstar/api/weather.py`

```python
"""
Astronomy Weather Forecast Integration

Provides cloud cover, precipitation, and seeing forecasts
specifically for astronomical observations.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

class CloudCover(StrEnum):
    """Cloud cover levels."""
    CLEAR = "clear"              # 0-10% clouds
    MOSTLY_CLEAR = "mostly_clear" # 10-30% clouds
    PARTLY_CLOUDY = "partly_cloudy" # 30-70% clouds
    MOSTLY_CLOUDY = "mostly_cloudy" # 70-90% clouds
    OVERCAST = "overcast"        # 90-100% clouds

class SeeingCondition(StrEnum):
    """Atmospheric seeing quality."""
    EXCELLENT = "excellent"  # <1 arcsec (planetary observing)
    GOOD = "good"           # 1-2 arcsec
    AVERAGE = "average"     # 2-3 arcsec
    POOR = "poor"          # 3-4 arcsec
    VERY_POOR = "very_poor" # >4 arcsec

class Transparency(StrEnum):
    """Atmospheric transparency."""
    EXCELLENT = "excellent"  # Limiting mag +0.5
    GOOD = "good"           # Limiting mag normal
    AVERAGE = "average"     # Limiting mag -0.5
    POOR = "poor"          # Limiting mag -1.0
    VERY_POOR = "very_poor" # Limiting mag -2.0

@dataclass(frozen=True)
class WeatherForecast:
    """Weather forecast for astronomy."""

    timestamp: datetime
    cloud_cover: CloudCover
    cloud_cover_percent: float

    # Precipitation
    precipitation_probability: float  # 0.0-1.0
    precipitation_type: str | None    # rain, snow, fog, etc.

    # Conditions
    temperature_celsius: float
    humidity_percent: float
    wind_speed_kmh: float

    # Astronomy-specific (if available)
    seeing: SeeingCondition | None
    transparency: Transparency | None

    # Forecast quality
    is_suitable_for_observing: bool
    suitability_score: float  # 0.0-1.0
    warnings: tuple[str, ...]

class WeatherProvider:
    """Base class for weather data providers."""

    def get_forecast(
        self,
        lat: float,
        lon: float,
        start_time: datetime,
        hours: int = 12
    ) -> list[WeatherForecast]:
        """Get hourly weather forecast."""
        raise NotImplementedError

class OpenMeteoProvider(WeatherProvider):
    """
    Weather provider using Open-Meteo API.

    Free, no API key required, good coverage.
    https://open-meteo.com/
    """

    async def get_forecast(
        self,
        lat: float,
        lon: float,
        start_time: datetime,
        hours: int = 12
    ) -> list[WeatherForecast]:
        """Fetch weather from Open-Meteo API."""
        # API endpoint: https://api.open-meteo.com/v1/forecast
        # Parameters: latitude, longitude, hourly
        # hourly: temperature_2m, cloud_cover, precipitation_probability,
        #         precipitation, wind_speed_10m, relative_humidity_2m
        pass

class WeatherAPIProvider(WeatherProvider):
    """
    Weather provider using WeatherAPI.com.

    Includes astronomy data (moon phase, sunrise/sunset).
    Free tier: 1M calls/month
    https://www.weatherapi.com/
    """

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def get_forecast(
        self,
        lat: float,
        lon: float,
        start_time: datetime,
        hours: int = 12
    ) -> list[WeatherForecast]:
        """Fetch weather from WeatherAPI.com."""
        # Endpoint: http://api.weatherapi.com/v1/forecast.json
        # Includes: astronomy data, alerts
        pass

# Singleton instance
_weather_provider: WeatherProvider | None = None

def set_weather_provider(provider: WeatherProvider) -> None:
    """Set the global weather provider."""
    global _weather_provider
    _weather_provider = provider

async def get_weather_forecast(
    lat: float,
    lon: float,
    start_time: datetime | None = None,
    hours: int = 12
) -> list[WeatherForecast]:
    """
    Get weather forecast for observing.

    Args:
        lat: Latitude in degrees
        lon: Longitude in degrees
        start_time: Start time (default: now)
        hours: Hours to forecast (default: 12)

    Returns:
        List of hourly forecasts
    """
    if _weather_provider is None:
        # Default to Open-Meteo (no API key required)
        set_weather_provider(OpenMeteoProvider())

    if start_time is None:
        start_time = datetime.now(UTC)

    return await _weather_provider.get_forecast(lat, lon, start_time, hours)
```

### 2. Light Pollution Module

**File**: `src/celestron_nexstar/api/light_pollution.py`

```python
"""
Light Pollution Data Integration

Provides Bortle scale and SQM (Sky Quality Meter) values
for assessing sky darkness at observing locations.
"""

from dataclasses import dataclass
from enum import IntEnum
import json
from pathlib import Path
import math

class BortleClass(IntEnum):
    """
    Bortle Dark-Sky Scale (1-9).

    Class 1: Excellent dark-sky site
    Class 2: Typical truly dark site
    Class 3: Rural sky
    Class 4: Rural/suburban transition
    Class 5: Suburban sky
    Class 6: Bright suburban sky
    Class 7: Suburban/urban transition
    Class 8: City sky
    Class 9: Inner-city sky
    """
    CLASS_1 = 1  # Excellent (21.99-22.00 mag/arcsec²)
    CLASS_2 = 2  # Typical dark (21.89-21.99)
    CLASS_3 = 3  # Rural (21.69-21.89)
    CLASS_4 = 4  # Rural/suburban (20.49-21.69)
    CLASS_5 = 5  # Suburban (19.50-20.49)
    CLASS_6 = 6  # Bright suburban (18.94-19.50)
    CLASS_7 = 7  # Suburban/urban (18.38-18.94)
    CLASS_8 = 8  # City (below 18.38)
    CLASS_9 = 9  # Inner-city (severely light polluted)

@dataclass(frozen=True)
class LightPollutionData:
    """Light pollution information for a location."""

    bortle_class: BortleClass
    sqm_value: float  # Sky Quality Meter (mag/arcsec²)

    # Impact on observing
    naked_eye_limiting_magnitude: float
    milky_way_visible: bool
    airglow_visible: bool
    zodiacal_light_visible: bool

    # Description
    description: str
    recommendations: tuple[str, ...]

# Bortle class characteristics
BORTLE_CHARACTERISTICS = {
    BortleClass.CLASS_1: {
        "sqm_range": (21.99, 22.00),
        "naked_eye_mag": 7.6,
        "milky_way": True,
        "airglow": True,
        "zodiacal_light": True,
        "description": "Excellent dark-sky site. Zodiacal light, gegenschein, and zodiacal band visible.",
        "recommendations": ("Perfect for all types of observing", "Ideal for deep-sky imaging"),
    },
    BortleClass.CLASS_2: {
        "sqm_range": (21.89, 21.99),
        "naked_eye_mag": 7.1,
        "milky_way": True,
        "airglow": True,
        "zodiacal_light": True,
        "description": "Typical truly dark site. Airglow weakly visible near horizon.",
        "recommendations": ("Excellent for all deep-sky objects", "Good for Milky Way photography"),
    },
    BortleClass.CLASS_3: {
        "sqm_range": (21.69, 21.89),
        "naked_eye_mag": 6.6,
        "milky_way": True,
        "airglow": False,
        "zodiacal_light": True,
        "description": "Rural sky. Some light pollution evident at horizon.",
        "recommendations": ("Very good for deep-sky observing", "Milky Way structure visible"),
    },
    BortleClass.CLASS_4: {
        "sqm_range": (20.49, 21.69),
        "naked_eye_mag": 6.1,
        "milky_way": True,
        "airglow": False,
        "zodiacal_light": False,
        "description": "Rural/suburban transition. Light domes visible in several directions.",
        "recommendations": ("Good for most deep-sky objects", "Brighter galaxies and nebulae visible"),
    },
    BortleClass.CLASS_5: {
        "sqm_range": (19.50, 20.49),
        "naked_eye_mag": 5.6,
        "milky_way": True,
        "airglow": False,
        "zodiacal_light": False,
        "description": "Suburban sky. Milky Way washed out near horizon.",
        "recommendations": ("Focus on brighter deep-sky objects", "Planets and Moon excellent"),
    },
    BortleClass.CLASS_6: {
        "sqm_range": (18.94, 19.50),
        "naked_eye_mag": 5.1,
        "milky_way": False,
        "airglow": False,
        "zodiacal_light": False,
        "description": "Bright suburban sky. Milky Way barely visible.",
        "recommendations": ("Bright objects only", "Excellent for planets and Moon"),
    },
    BortleClass.CLASS_7: {
        "sqm_range": (18.38, 18.94),
        "naked_eye_mag": 4.6,
        "milky_way": False,
        "airglow": False,
        "zodiacal_light": False,
        "description": "Suburban/urban transition. Sky grayish white.",
        "recommendations": ("Messier objects still visible", "Focus on planets, Moon, double stars"),
    },
    BortleClass.CLASS_8: {
        "sqm_range": (0, 18.38),
        "naked_eye_mag": 4.1,
        "milky_way": False,
        "airglow": False,
        "zodiacal_light": False,
        "description": "City sky. Bright objects only.",
        "recommendations": ("Planets, Moon, brightest clusters", "Consider narrowband filters"),
    },
    BortleClass.CLASS_9: {
        "sqm_range": (0, 17.5),
        "naked_eye_mag": 4.0,
        "milky_way": False,
        "airglow": False,
        "zodiacal_light": False,
        "description": "Inner-city sky. Severely light polluted.",
        "recommendations": ("Moon and planets only", "Consider remote observing"),
    },
}

def sqm_to_bortle(sqm: float) -> BortleClass:
    """Convert SQM value to Bortle class."""
    if sqm >= 21.99:
        return BortleClass.CLASS_1
    elif sqm >= 21.89:
        return BortleClass.CLASS_2
    elif sqm >= 21.69:
        return BortleClass.CLASS_3
    elif sqm >= 20.49:
        return BortleClass.CLASS_4
    elif sqm >= 19.50:
        return BortleClass.CLASS_5
    elif sqm >= 18.94:
        return BortleClass.CLASS_6
    elif sqm >= 18.38:
        return BortleClass.CLASS_7
    elif sqm >= 17.5:
        return BortleClass.CLASS_8
    else:
        return BortleClass.CLASS_9

def get_light_pollution_data(lat: float, lon: float) -> LightPollutionData:
    """
    Get light pollution data for a location.

    Uses bundled light pollution map data (offline).
    Data from: World Atlas 2015 / VIIRS satellite imagery.

    Args:
        lat: Latitude in degrees
        lon: Longitude in degrees

    Returns:
        Light pollution data
    """
    # Load bundled light pollution grid
    # Format: GeoJSON with SQM values per lat/lon grid
    data_path = Path(__file__).parent / "data" / "light_pollution.json"

    if not data_path.exists():
        # Fallback to estimated value based on population density
        # This is a rough approximation
        sqm = estimate_sqm_from_location(lat, lon)
    else:
        with open(data_path) as f:
            lp_data = json.load(f)
            sqm = interpolate_sqm(lp_data, lat, lon)

    bortle = sqm_to_bortle(sqm)
    chars = BORTLE_CHARACTERISTICS[bortle]

    return LightPollutionData(
        bortle_class=bortle,
        sqm_value=sqm,
        naked_eye_limiting_magnitude=chars["naked_eye_mag"],
        milky_way_visible=chars["milky_way"],
        airglow_visible=chars["airglow"],
        zodiacal_light_visible=chars["zodiacal_light"],
        description=chars["description"],
        recommendations=chars["recommendations"],
    )

def estimate_sqm_from_location(lat: float, lon: float) -> float:
    """
    Estimate SQM value without data file (fallback).

    Uses simple heuristic based on major cities.
    Not very accurate but better than nothing.
    """
    # Major city coordinates and typical SQM values
    # In reality, you'd want a proper lookup table or API
    # For now, default to Bortle 5 (suburban)
    return 20.0

def interpolate_sqm(data: dict, lat: float, lon: float) -> float:
    """Interpolate SQM value from grid data."""
    # Bilinear interpolation from nearest grid points
    # Implementation depends on data format
    pass

# Data preparation script
def download_light_pollution_data():
    """
    Download and prepare light pollution map data.

    Sources:
    - World Atlas 2015 (https://cires.colorado.edu/artificial-sky)
    - VIIRS DNB satellite data
    - Light Pollution Map API (if available)

    Generates: src/celestron_nexstar/api/data/light_pollution.json
    Grid resolution: ~1km or city-level aggregation
    File size target: <5MB
    """
    pass
```

### 3. Observation Planner Module

**File**: `src/celestron_nexstar/api/observation_planner.py`

```python
"""
Observation Session Planner

Combines weather, light pollution, object visibility, and telescope
capabilities to recommend what to observe tonight.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, UTC
from enum import StrEnum

from .catalogs import CelestialObject, get_all_objects
from .light_pollution import get_light_pollution_data, LightPollutionData
from .observer import get_observer_location
from .optics import get_current_configuration, calculate_limiting_magnitude
from .visibility import assess_visibility, filter_visible_objects
from .weather import get_weather_forecast, WeatherForecast

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
    weather: WeatherForecast
    is_weather_suitable: bool

    # Light pollution
    light_pollution: LightPollutionData

    # Telescope
    limiting_magnitude: float
    aperture_mm: float

    # Moon
    moon_illumination: float  # 0.0-1.0
    moon_altitude: float      # degrees

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

    async def get_tonight_conditions(
        self,
        lat: float | None = None,
        lon: float | None = None,
        start_time: datetime | None = None
    ) -> ObservingConditions:
        """
        Get complete observing conditions for tonight.

        Args:
            lat: Observer latitude (default: from saved location)
            lon: Observer longitude (default: from saved location)
            start_time: Session start time (default: now or sunset)

        Returns:
            Complete observing conditions assessment
        """
        # Get location
        if lat is None or lon is None:
            location = get_observer_location()
            if location is None:
                raise ValueError("No location set. Use 'location set' command.")
            lat, lon = location.latitude_deg, location.longitude_deg
            location_name = location.name
        else:
            location_name = None

        # Get weather forecast
        if start_time is None:
            start_time = datetime.now(UTC)

        forecasts = await get_weather_forecast(lat, lon, start_time, hours=12)
        current_weather = forecasts[0] if forecasts else None

        # Get light pollution
        lp_data = get_light_pollution_data(lat, lon)

        # Get telescope configuration
        config = get_current_configuration()
        if config:
            limiting_mag = calculate_limiting_magnitude(
                config.telescope.aperture_mm,
                lp_data.naked_eye_limiting_magnitude
            )
            aperture = config.telescope.aperture_mm
        else:
            limiting_mag = lp_data.naked_eye_limiting_magnitude
            aperture = 0

        # Calculate moon position and illumination
        # (Use existing ephemeris module)
        from .ephemeris import get_planetary_position, get_moon_illumination
        moon_alt, moon_az = get_planetary_position("Moon", dt=start_time)
        moon_illum = get_moon_illumination(start_time)

        # Assess overall quality
        quality_score = self._calculate_quality_score(
            current_weather, lp_data, moon_illum
        )

        recommendations, warnings = self._generate_recommendations(
            current_weather, lp_data, moon_illum, quality_score
        )

        return ObservingConditions(
            timestamp=start_time,
            latitude=lat,
            longitude=lon,
            location_name=location_name,
            weather=current_weather,
            is_weather_suitable=current_weather.is_suitable_for_observing,
            light_pollution=lp_data,
            limiting_magnitude=limiting_mag,
            aperture_mm=aperture,
            moon_illumination=moon_illum,
            moon_altitude=moon_alt,
            observing_quality_score=quality_score,
            recommendations=recommendations,
            warnings=warnings,
        )

    async def get_recommended_objects(
        self,
        conditions: ObservingConditions | None = None,
        target_types: list[ObservingTarget] | None = None,
        max_results: int = 20
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
            conditions = await self.get_tonight_conditions()

        # Get all objects from catalogs
        all_objects = get_all_objects()

        # Filter by visibility
        visible_objects = filter_visible_objects(
            all_objects,
            conditions.latitude,
            conditions.longitude,
            conditions.limiting_magnitude,
            min_altitude=20,  # At least 20° above horizon
        )

        # Score and rank objects
        recommendations = []
        for obj in visible_objects:
            rec = self._score_object(obj, conditions)
            if rec:
                recommendations.append(rec)

        # Sort by priority and observability score
        recommendations.sort(
            key=lambda r: (r.priority, -r.observability_score)
        )

        return recommendations[:max_results]

    def _calculate_quality_score(
        self,
        weather: WeatherForecast,
        lp_data: LightPollutionData,
        moon_illum: float
    ) -> float:
        """Calculate overall observing quality score (0.0-1.0)."""
        # Weather component (0.0-0.5)
        weather_score = weather.suitability_score * 0.5

        # Light pollution component (0.0-0.3)
        # Bortle 1-3 = good (0.3), Bortle 4-6 = ok (0.15), Bortle 7-9 = poor (0.0)
        if lp_data.bortle_class <= 3:
            lp_score = 0.3
        elif lp_data.bortle_class <= 6:
            lp_score = 0.15
        else:
            lp_score = 0.0

        # Moon component (0.0-0.2)
        # New moon = good (0.2), Full moon = poor (0.0)
        moon_score = (1.0 - moon_illum) * 0.2

        return weather_score + lp_score + moon_score

    def _generate_recommendations(
        self,
        weather: WeatherForecast,
        lp_data: LightPollutionData,
        moon_illum: float,
        quality_score: float
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Generate recommendations and warnings."""
        recommendations = []
        warnings = []

        # Weather-based
        if weather.cloud_cover_percent < 10:
            recommendations.append("Excellent night for deep-sky observing")
        elif weather.cloud_cover_percent < 30:
            recommendations.append("Good conditions for most objects")
        else:
            warnings.append(f"High cloud cover ({weather.cloud_cover_percent:.0f}%)")

        if weather.precipitation_probability > 0.3:
            warnings.append(f"Precipitation likely ({weather.precipitation_probability*100:.0f}%)")

        # Light pollution
        if lp_data.bortle_class <= 3:
            recommendations.append("Dark skies excellent for faint objects")
        elif lp_data.bortle_class >= 7:
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
        conditions: ObservingConditions
    ) -> RecommendedObject | None:
        """Score an object for recommendation."""
        # Calculate visibility
        vis_info = assess_visibility(
            obj,
            conditions.latitude,
            conditions.longitude,
            conditions.limiting_magnitude,
        )

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
            altitude=vis_info.altitude_deg,
            azimuth=vis_info.azimuth_deg,
            best_viewing_time=best_time,
            visible_duration_hours=8.0,  # Simplified
            apparent_magnitude=obj.magnitude or 0,
            observability_score=vis_info.observability_score,
            priority=priority,
            reason=f"Well positioned at {vis_info.altitude_deg:.0f}° altitude",
            viewing_tips=tips,
        )

    def _determine_priority(
        self,
        obj: CelestialObject,
        conditions: ObservingConditions,
        vis_info
    ) -> int:
        """Determine observation priority (1=highest, 5=lowest)."""
        # Priority 1: Planets (always interesting)
        if obj.object_type.value == "planet":
            return 1

        # Priority 2: Bright objects in dark skies
        if conditions.light_pollution.bortle_class <= 3:
            if obj.magnitude and obj.magnitude < 8:
                return 2

        # Priority 3: Objects well positioned (high altitude)
        if vis_info.altitude_deg > 60:
            return 3

        # Priority 4: Messier objects
        if obj.catalog == "messier":
            return 4

        # Priority 5: Everything else
        return 5

    def _generate_viewing_tips(
        self,
        obj: CelestialObject,
        conditions: ObservingConditions
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
        if conditions.light_pollution.bortle_class >= 6:
            tips.append("Light pollution will reduce contrast")

        return tuple(tips)

    def _calculate_best_viewing_time(
        self,
        obj: CelestialObject,
        lat: float,
        lon: float,
        start_time: datetime
    ) -> datetime:
        """Calculate when object is highest in sky (transit)."""
        # Simplified: assume transit is when RA = LST
        # In reality, calculate when altitude is maximum
        # For now, return 2 hours from start
        return start_time + timedelta(hours=2)

# Singleton
_planner = ObservationPlanner()

async def get_tonight_plan(
    lat: float | None = None,
    lon: float | None = None,
    target_types: list[ObservingTarget] | None = None
) -> tuple[ObservingConditions, list[RecommendedObject]]:
    """
    Get complete observing plan for tonight.

    Returns:
        (conditions, recommended_objects)
    """
    conditions = await _planner.get_tonight_conditions(lat, lon)
    objects = await _planner.get_recommended_objects(conditions, target_types)
    return conditions, objects
```

---

## CLI Integration

### New Command: `tonight`

**File**: `src/celestron_nexstar/cli/commands/tonight.py`

```python
"""
'What's Visible Tonight?' command

Shows observing conditions and recommended objects for tonight.
"""

import asyncio
from datetime import datetime
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from celestron_nexstar.api.observation_planner import (
    get_tonight_plan,
    ObservingTarget
)

app = typer.Typer(help="Tonight's observing plan")
console = Console()

@app.command("conditions")
def show_conditions():
    """Show tonight's observing conditions."""
    async def _show():
        from celestron_nexstar.api.observation_planner import ObservationPlanner
        planner = ObservationPlanner()
        conditions = await planner.get_tonight_conditions()

        # Display header
        console.print(f"\n[bold cyan]Observing Conditions for {conditions.location_name or 'Current Location'}[/bold cyan]")
        console.print(f"[dim]{conditions.timestamp.strftime('%Y-%m-%d %H:%M %Z')}[/dim]\n")

        # Overall quality
        quality = conditions.observing_quality_score
        if quality > 0.7:
            quality_text = "[green]Excellent[/green]"
        elif quality > 0.5:
            quality_text = "[yellow]Good[/yellow]"
        elif quality > 0.3:
            quality_text = "[yellow]Fair[/yellow]"
        else:
            quality_text = "[red]Poor[/red]"

        console.print(f"Overall Quality: {quality_text} ({quality*100:.0f}/100)\n")

        # Weather
        weather = conditions.weather
        console.print("[bold]Weather:[/bold]")
        console.print(f"  Cloud Cover: {weather.cloud_cover.value} ({weather.cloud_cover_percent:.0f}%)")
        console.print(f"  Temperature: {weather.temperature_celsius:.1f}°C")
        console.print(f"  Precipitation: {weather.precipitation_probability*100:.0f}% chance")
        if weather.seeing:
            console.print(f"  Seeing: {weather.seeing.value}")
        if weather.transparency:
            console.print(f"  Transparency: {weather.transparency.value}")
        console.print()

        # Light Pollution
        lp = conditions.light_pollution
        console.print("[bold]Sky Darkness:[/bold]")
        console.print(f"  Bortle Class: {lp.bortle_class} ({lp.description})")
        console.print(f"  SQM: {lp.sqm_value:.2f} mag/arcsec²")
        console.print(f"  Naked Eye Limit: {lp.naked_eye_limiting_magnitude:.1f} mag")
        console.print(f"  Telescope Limit: {conditions.limiting_magnitude:.1f} mag")
        console.print()

        # Moon
        console.print("[bold]Moon:[/bold]")
        console.print(f"  Illumination: {conditions.moon_illumination*100:.0f}%")
        console.print(f"  Altitude: {conditions.moon_altitude:.1f}°")
        console.print()

        # Recommendations
        if conditions.recommendations:
            console.print("[bold green]Recommendations:[/bold green]")
            for rec in conditions.recommendations:
                console.print(f"  ✓ {rec}")
            console.print()

        # Warnings
        if conditions.warnings:
            console.print("[bold yellow]Warnings:[/bold yellow]")
            for warn in conditions.warnings:
                console.print(f"  ⚠ {warn}")
            console.print()

    asyncio.run(_show())

@app.command("objects")
def show_objects(
    target_type: str = typer.Option(None, "--type", help="Filter by type (planets, deep_sky, etc.)"),
    limit: int = typer.Option(20, "--limit", help="Maximum objects to show")
):
    """Show recommended objects for tonight."""
    async def _show():
        # Parse target types
        target_types = None
        if target_type:
            target_types = [ObservingTarget(target_type)]

        conditions, objects = await get_tonight_plan(target_types=target_types)

        if not objects:
            console.print("[yellow]No objects currently visible with current conditions.[/yellow]")
            return

        # Create table
        table = Table(title=f"Recommended Objects for Tonight ({len(objects)} total)")
        table.add_column("Priority", style="cyan", width=3)
        table.add_column("Name", style="bold")
        table.add_column("Type", style="dim")
        table.add_column("Mag", justify="right")
        table.add_column("Alt", justify="right")
        table.add_column("Best Time")
        table.add_column("Reason")

        for obj_rec in objects[:limit]:
            priority_stars = "★" * obj_rec.priority
            obj = obj_rec.obj

            table.add_row(
                priority_stars,
                obj.common_name or obj.name,
                obj.object_type.value,
                f"{obj_rec.apparent_magnitude:.1f}" if obj_rec.apparent_magnitude else "-",
                f"{obj_rec.altitude:.0f}°",
                obj_rec.best_viewing_time.strftime("%H:%M"),
                obj_rec.reason
            )

        console.print(table)
        console.print(f"\n[dim]Showing top {min(limit, len(objects))} of {len(objects)} visible objects[/dim]")

    asyncio.run(_show())

@app.command("plan")
def show_plan():
    """Show complete observing plan for tonight (conditions + objects)."""
    show_conditions()
    console.print("\n" + "="*80 + "\n")
    show_objects()
```

### Shell Integration

Add to `main.py`:

```python
# Register tonight command
app.add_typer(tonight.app, name="tonight", help="Tonight's observing plan")
```

---

## CLI Usage Examples

```bash
# Show tonight's conditions
nexstar tonight conditions

# Output:
# Observing Conditions for Los Angeles, CA
# 2025-01-15 20:00 PST
#
# Overall Quality: Good (68/100)
#
# Weather:
#   Cloud Cover: mostly_clear (15%)
#   Temperature: 12.3°C
#   Precipitation: 5% chance
#   Seeing: good
#   Transparency: excellent
#
# Sky Darkness:
#   Bortle Class: 7 (Suburban/urban transition)
#   SQM: 18.50 mag/arcsec²
#   Naked Eye Limit: 4.6 mag
#   Telescope Limit: 12.8 mag
#
# Moon:
#   Illumination: 23%
#   Altitude: 15.2°
#
# Recommendations:
#   ✓ Good conditions for most objects
#   ✓ Thin crescent moon ideal for deep-sky
#   ✓ Focus on bright objects (planets, Moon, bright clusters)
#
# Warnings:
#   ⚠ Light pollution will reduce contrast

# Show recommended objects
nexstar tonight objects

# Show only planets
nexstar tonight objects --type planets

# Show everything
nexstar tonight plan
```

---

## Implementation Timeline

### Phase 1: Weather Integration (3-4 days)
1. Implement `weather.py` module
2. Integrate Open-Meteo API (free, no key)
3. Add WeatherAPI.com support (optional, requires key)
4. Test forecast accuracy

### Phase 2: Light Pollution (2-3 days)
1. Implement `light_pollution.py` module
2. Download and process World Atlas 2015 data
3. Create bundled light pollution grid (GeoJSON)
4. Test accuracy against known locations

### Phase 3: Observation Planner (3-4 days)
1. Implement `observation_planner.py` module
2. Integrate all data sources
3. Scoring and ranking algorithms
4. Best viewing time calculations

### Phase 4: CLI Commands (2 days)
1. Create `tonight` command group
2. Rich formatting for conditions/objects
3. Interactive mode updates
4. Documentation

### Phase 5: Testing & Polish (2-3 days)
1. End-to-end testing
2. Performance optimization
3. Error handling
4. User documentation

**Total: 12-16 days**

---

## Data Requirements

### Weather API
- **Free tier**: Open-Meteo (unlimited, no key)
- **Premium tier**: WeatherAPI.com (1M calls/month free)
- **Fallback**: Use last known good forecast

### Light Pollution Map
- **Source**: World Atlas 2015 (public domain)
- **Format**: GeoJSON grid
- **Resolution**: ~1km grid cells
- **File size**: ~3-5 MB (compressed)
- **Storage**: Bundle in package

### Dependencies
```toml
[project.optional-dependencies]
planning = [
    "aiohttp>=3.9.0",  # Async HTTP for weather APIs
]
```

---

## Expected User Experience

```
User: "Should I observe tonight?"

nexstar> tonight plan

[Shows conditions: Clear skies, Bortle 6, waning crescent moon]
[Lists 20 recommended objects with priorities]

User selects: "M42 Orion Nebula" (Priority ★★)

nexstar> goto object --name M42
[Telescope slews]
[Status bar shows: M42 at 45° altitude, best viewed now]
```

---

## Future Enhancements

1. **Cloud Cover Alerting**
   - Monitor forecast changes
   - Notify when clear window opens
   - Integration with Clear Sky Alarm Clock

2. **Multi-Night Planning**
   - "What's good this week?"
   - Compare nights for planning
   - Best night for specific object

3. **Learning System**
   - Track what you've observed
   - Suggest new objects
   - Achievement system

4. **Integration with Imaging**
   - Seeing forecast for planetary imaging
   - Transparency forecast for deep-sky
   - Suggest exposure times

5. **Social Features**
   - Share observing plans
   - Local astronomy club events
   - Star party weather forecasting

---

## Success Metrics

- ✅ Accurate weather forecast (< 10% error vs. reality)
- ✅ Light pollution data for 95%+ of locations
- ✅ Recommends 20+ visible objects per night
- ✅ < 2 second response time for full plan
- ✅ Works 100% offline (after initial weather fetch)
- ✅ Intuitive single-command interface

---

**Ready to implement!** This feature will make the NexStar CLI a complete observing companion.

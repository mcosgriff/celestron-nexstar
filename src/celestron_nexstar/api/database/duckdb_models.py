"""
DuckDB Dataclass Models

Dataclass models for use with DuckDB native queries.
These replace SQLAlchemy models while maintaining the same interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class UserPreference:
    """User preference model."""

    key: str
    value: str
    category: str
    description: str | None
    created_at: datetime
    updated_at: datetime


@dataclass
class Eyepiece:
    """Eyepiece model."""

    id: int
    name: str
    focal_length_mm: float
    apparent_fov_deg: float
    barrel_size_mm: float | None
    manufacturer: str | None
    model: str | None
    notes: str | None
    usage_count: int
    last_used_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass
class Filter:
    """Filter model."""

    id: int
    name: str
    filter_type: str
    barrel_size_mm: float | None
    manufacturer: str | None
    model: str | None
    transmission_percent: float | None
    notes: str | None
    usage_count: int
    last_used_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass
class Camera:
    """Camera model."""

    id: int
    name: str
    sensor_width_mm: float
    sensor_height_mm: float
    pixel_width_um: float | None
    pixel_height_um: float | None
    resolution_width: int | None
    resolution_height: int | None
    camera_type: str
    manufacturer: str | None
    model: str | None
    notes: str | None
    usage_count: int
    last_used_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass
class WeatherForecast:
    """Weather forecast model."""

    id: int
    latitude: float
    longitude: float
    geohash: str | None
    forecast_timestamp: datetime
    temperature_f: float | None
    dew_point_f: float | None
    humidity_percent: float | None
    cloud_cover_percent: float | None
    wind_speed_mph: float | None
    seeing_score: float | None
    fetched_at: datetime


@dataclass
class HistoricalWeather:
    """Historical weather model."""

    id: int
    latitude: float
    longitude: float
    geohash: str | None
    month: int
    avg_cloud_cover_percent: float | None
    min_cloud_cover_percent: float | None
    max_cloud_cover_percent: float | None
    p25_cloud_cover_percent: float | None
    p40_cloud_cover_percent: float | None
    p60_cloud_cover_percent: float | None
    p75_cloud_cover_percent: float | None
    std_dev_cloud_cover_percent: float | None
    years_of_data: int | None
    fetched_at: datetime


@dataclass
class LightPollutionGrid:
    """Light pollution grid model."""

    id: int
    latitude: float
    longitude: float
    geohash: str
    sqm_value: float
    region: str | None
    created_at: str | None


@dataclass
class ISSPass:
    """ISS pass model."""

    id: int
    latitude: float
    longitude: float
    geohash: str | None
    rise_time: datetime
    max_time: datetime
    set_time: datetime
    duration_seconds: int
    max_altitude_deg: float
    magnitude: float | None
    rise_azimuth_deg: float
    max_azimuth_deg: float
    set_azimuth_deg: float
    is_visible: bool
    fetched_at: datetime


@dataclass
class DarkSkySite:
    """Dark sky site model."""

    id: int
    name: str
    latitude: float
    longitude: float
    geohash: str | None
    bortle_class: int
    sqm_value: float
    description: str
    notes: str | None
    created_at: datetime
    updated_at: datetime


@dataclass
class SpaceEvent:
    """Space event model."""

    id: int
    name: str
    event_type: str
    date: datetime
    description: str
    min_latitude: float | None
    max_latitude: float | None
    min_longitude: float | None
    max_longitude: float | None
    dark_sky_required: bool
    min_bortle_class: int | None
    equipment_needed: str | None
    viewing_notes: str | None
    source: str
    url: str | None
    created_at: datetime
    updated_at: datetime


@dataclass
class EphemerisFile:
    """Ephemeris file model."""

    file_key: str
    filename: str
    display_name: str
    description: str
    coverage_start: int
    coverage_end: int
    size_mb: float
    file_type: str
    url: str
    contents: str
    use_case: str
    created_at: datetime
    updated_at: datetime


@dataclass
class StarNameMapping:
    """Star name mapping model."""

    hr_number: int
    common_name: str
    bayer_designation: str | None
    created_at: datetime
    updated_at: datetime


@dataclass
class TLE:
    """TLE (Two-Line Element) model."""

    norad_id: int
    satellite_name: str
    satellite_group: str | None
    line1: str
    line2: str
    epoch: datetime | None
    fetched_at: datetime


@dataclass
class VariableStar:
    """Variable star model."""

    id: int
    name: str
    designation: str
    variable_type: str
    period_days: float
    magnitude_min: float
    magnitude_max: float
    ra_hours: float
    dec_degrees: float
    notes: str
    created_at: datetime
    updated_at: datetime


@dataclass
class Comet:
    """Comet model."""

    id: int
    name: str
    designation: str
    perihelion_date: datetime
    perihelion_distance_au: float
    peak_magnitude: float
    peak_date: datetime
    is_periodic: bool
    period_years: float | None
    notes: str
    created_at: datetime
    updated_at: datetime


@dataclass
class Eclipse:
    """Eclipse model."""

    id: int
    eclipse_type: str
    date: datetime
    magnitude: float
    created_at: datetime
    updated_at: datetime


@dataclass
class BortleCharacteristics:
    """Bortle class characteristics model."""

    bortle_class: int
    sqm_min: float
    sqm_max: float
    naked_eye_mag: float
    milky_way: bool
    airglow: bool
    zodiacal_light: bool
    description: str
    recommendations: str
    created_at: datetime
    updated_at: datetime


@dataclass
class RSSFeed:
    """RSS feed model."""

    id: int
    title: str
    link: str
    guid: str | None
    description: str
    content: str | None
    published_date: datetime
    author: str | None
    categories: str | None
    source: str
    feed_url: str
    created_at: datetime
    updated_at: datetime
    fetched_at: datetime


@dataclass
class MeteorShower:
    """Meteor shower model."""

    id: int
    name: str
    code: str | None
    start_month: int
    start_day: int
    end_month: int
    end_day: int
    peak_month: int
    peak_day: int
    radiant_ra_hours: float
    radiant_dec_degrees: float
    radiant_constellation: str | None
    zhr_peak: int
    velocity_km_s: float | None
    parent_comet: str | None
    best_time: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    # Computed properties to match the MeteorShower dataclass in meteor_showers.py
    @property
    def activity_start_month(self) -> int:
        """Activity start month."""
        return self.start_month

    @property
    def activity_start_day(self) -> int:
        """Activity start day."""
        return self.start_day

    @property
    def activity_end_month(self) -> int:
        """Activity end month."""
        return self.end_month

    @property
    def activity_end_day(self) -> int:
        """Activity end day."""
        return self.end_day

    @property
    def peak_end_month(self) -> int:
        """Peak end month (same as peak_month for now)."""
        return self.peak_month

    @property
    def peak_end_day(self) -> int:
        """Peak end day (same as peak_day for now)."""
        return self.peak_day

    @property
    def description(self) -> str:
        """Description (from notes)."""
        return self.notes or ""

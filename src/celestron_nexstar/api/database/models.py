"""
SQLAlchemy Models for Celestial Objects Database

Defines the database schema using SQLAlchemy ORM for type-safe database operations
and automatic migration management with Alembic.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


if TYPE_CHECKING:
    from celestron_nexstar.api.astronomy.comets import Comet
    from celestron_nexstar.api.astronomy.constellations import Asterism, Constellation
    from celestron_nexstar.api.astronomy.meteor_showers import MeteorShower
    from celestron_nexstar.api.astronomy.variable_stars import VariableStar


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


class CelestialObjectModel(Base):
    """
    SQLAlchemy model for celestial objects.

    This model represents celestial objects in the database, including stars, planets,
    galaxies, nebulae, clusters, and other astronomical objects.
    """

    __tablename__ = "objects"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Object identification
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    common_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    catalog: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    catalog_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Position (J2000 epoch for fixed objects)
    ra_hours: Mapped[float] = mapped_column(Float, nullable=False)
    dec_degrees: Mapped[float] = mapped_column(Float, nullable=False)

    # Physical properties
    magnitude: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    object_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    size_arcmin: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Metadata
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    constellation: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    # Dynamic object support (planets/moons)
    is_dynamic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    ephemeris_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    parent_planet: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    # Relationships
    observations: Mapped[list[ObservationModel]] = relationship(
        "ObservationModel", back_populates="celestial_object", cascade="all, delete-orphan"
    )

    # Composite indexes
    __table_args__ = (
        Index("idx_catalog_number", "catalog", "catalog_number"),
        Index("idx_type_magnitude", "object_type", "magnitude"),
        Index("idx_parent_planet_type", "parent_planet", "object_type"),  # For moon queries
        Index("idx_position", "ra_hours", "dec_degrees"),  # For position-based queries
        Index("idx_ephemeris_name", "ephemeris_name"),  # For dynamic object lookups
    )

    def __repr__(self) -> str:
        """String representation of the object."""
        return f"<CelestialObject(id={self.id}, name='{self.name}', type='{self.object_type}')>"


class MetadataModel(Base):
    """
    SQLAlchemy model for database metadata.

    Stores version information and other database-level metadata.
    """

    __tablename__ = "metadata"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    def __repr__(self) -> str:
        """String representation of metadata."""
        return f"<Metadata(key='{self.key}', value='{self.value}')>"


class ObservationModel(Base):
    """
    SQLAlchemy model for observation logs.

    Tracks user observations of celestial objects including date, time,
    viewing conditions, and notes.
    """

    __tablename__ = "observations"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to celestial object
    object_id: Mapped[int] = mapped_column(Integer, ForeignKey("objects.id"), nullable=False, index=True)

    # Observation details
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    location_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_geohash: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)
    location_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Viewing conditions
    seeing_quality: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5 scale
    transparency: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5 scale
    sky_brightness: Mapped[float | None] = mapped_column(Float, nullable=True)  # SQM value
    weather_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Equipment used
    telescope: Mapped[str | None] = mapped_column(String(255), nullable=True)
    eyepiece: Mapped[str | None] = mapped_column(String(255), nullable=True)
    filters: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Observation notes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5 stars

    # Images/sketches
    image_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    sketch_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    # Relationships
    celestial_object: Mapped[CelestialObjectModel] = relationship("CelestialObjectModel", back_populates="observations")

    # Composite indexes
    __table_args__ = (
        Index("idx_object_observed", "object_id", "observed_at"),  # For querying observations by object and date
    )

    def __repr__(self) -> str:
        """String representation of observation."""
        return f"<Observation(id={self.id}, object_id={self.object_id}, observed_at='{self.observed_at}')>"


class UserPreferenceModel(Base):
    """
    SQLAlchemy model for user preferences.

    Stores user-specific settings and preferences for the application.
    """

    __tablename__ = "user_preferences"

    # Primary key
    key: Mapped[str] = mapped_column(String(255), primary_key=True)

    # Preference value (stored as JSON string for flexibility)
    value: Mapped[str] = mapped_column(Text, nullable=False)

    # Category for organizing preferences
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Description of what this preference controls
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    def __repr__(self) -> str:
        """String representation of preference."""
        return f"<UserPreference(key='{self.key}', category='{self.category}')>"


class LightPollutionGridModel(Base):
    """
    SQLAlchemy model for light pollution grid data.

    Stores light pollution SQM values for grid points across the world.
    Uses geohash for efficient spatial indexing and proximity searches.
    """

    __tablename__ = "light_pollution_grid"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Location
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    geohash: Mapped[str] = mapped_column(String(12), nullable=False, index=True)

    # Light pollution data
    sqm_value: Mapped[float] = mapped_column(Float, nullable=False)
    region: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Timestamps
    created_at: Mapped[str] = mapped_column(
        String, nullable=True, server_default=text("CURRENT_TIMESTAMP")
    )  # TEXT in SQLite

    # Composite indexes and constraints
    __table_args__ = (
        Index("idx_lp_geohash", "geohash"),
        Index("idx_lp_lat_lon", "latitude", "longitude"),
        Index("idx_lp_region", "region"),
        sa.UniqueConstraint("latitude", "longitude", name="uq_lp_lat_lon"),
    )

    def __repr__(self) -> str:
        """String representation of light pollution grid point."""
        return f"<LightPollutionGrid(id={self.id}, lat={self.latitude}, lon={self.longitude}, sqm={self.sqm_value})>"


class WeatherForecastModel(Base):
    """
    SQLAlchemy model for hourly weather forecasts.

    Stores hourly weather forecast data for a specific location and timestamp.
    Used to cache weather data and avoid unnecessary API calls.
    """

    __tablename__ = "weather_forecast"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Location (used to identify forecasts for a location)
    latitude: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    geohash: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)

    # Forecast timestamp (when this forecast is for)
    forecast_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    # Weather data
    temperature_f: Mapped[float | None] = mapped_column(Float, nullable=True)
    dew_point_f: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    cloud_cover_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_speed_mph: Mapped[float | None] = mapped_column(Float, nullable=True)
    seeing_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # When this data was fetched/updated
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    # Composite index for location + timestamp lookups
    __table_args__ = (
        Index("idx_location_timestamp", "latitude", "longitude", "forecast_timestamp"),
        Index("idx_location_fetched", "latitude", "longitude", "fetched_at"),
    )

    def __repr__(self) -> str:
        """String representation of weather forecast."""
        return f"<WeatherForecast(id={self.id}, lat={self.latitude}, lon={self.longitude}, timestamp='{self.forecast_timestamp}')>"


class HistoricalWeatherModel(Base):
    """
    SQLAlchemy model for historical weather climatology data.

    Stores monthly average cloud cover statistics by location for long-term predictions.
    Data is fetched from Open-Meteo Historical Weather API and cached indefinitely.
    """

    __tablename__ = "historical_weather"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Location (used to identify historical data for a location)
    latitude: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    geohash: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)

    # Month (1-12) for which this data applies
    month: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Historical cloud cover statistics (from Open-Meteo Historical API)
    avg_cloud_cover_percent: Mapped[float | None] = mapped_column(Float, nullable=True)  # Average cloud cover
    min_cloud_cover_percent: Mapped[float | None] = mapped_column(Float, nullable=True)  # Minimum (best case)
    max_cloud_cover_percent: Mapped[float | None] = mapped_column(Float, nullable=True)  # Maximum (worst case)
    p25_cloud_cover_percent: Mapped[float | None] = mapped_column(Float, nullable=True)  # 25th percentile
    p40_cloud_cover_percent: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # 40th percentile (tighter range)
    p60_cloud_cover_percent: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # 60th percentile (tighter range)
    p75_cloud_cover_percent: Mapped[float | None] = mapped_column(Float, nullable=True)  # 75th percentile
    std_dev_cloud_cover_percent: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # Standard deviation (confidence indicator)

    # Metadata
    years_of_data: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Number of years used for average
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    # Composite index for location + month lookups
    __table_args__ = (
        Index("idx_historical_location_month", "latitude", "longitude", "month"),
        Index("idx_historical_geohash_month", "geohash", "month"),
    )

    def __repr__(self) -> str:
        """String representation of historical weather."""
        return f"<HistoricalWeather(id={self.id}, lat={self.latitude}, lon={self.longitude}, month={self.month})>"


class ISSPassModel(Base):
    """
    SQLAlchemy model for cached ISS pass predictions.

    Stores predicted ISS passes for a specific location. Cached data expires
    after 24 hours since ISS orbits change frequently.
    """

    __tablename__ = "iss_passes"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Location (rounded to ~1km precision for cache key)
    latitude: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    geohash: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)

    # Pass timing
    rise_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    max_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    set_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Pass characteristics
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)  # Total pass duration
    max_altitude_deg: Mapped[float] = mapped_column(Float, nullable=False)  # Peak altitude above horizon
    magnitude: Mapped[float | None] = mapped_column(Float, nullable=True)  # Brightness (-4 to +4 scale)

    # Compass positions
    rise_azimuth_deg: Mapped[float] = mapped_column(Float, nullable=False)  # Where it appears
    max_azimuth_deg: Mapped[float] = mapped_column(Float, nullable=False)  # Peak position
    set_azimuth_deg: Mapped[float] = mapped_column(Float, nullable=False)  # Where it disappears

    # Visibility
    is_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # Sunlit or in shadow

    # Cache metadata
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )

    # Composite indexes
    __table_args__ = (
        Index("idx_location_rise_time", "latitude", "longitude", "rise_time"),
        Index("idx_location_fetched", "latitude", "longitude", "fetched_at"),
    )

    def __repr__(self) -> str:
        """String representation of ISS pass."""
        return f"<ISSPass(id={self.id}, rise='{self.rise_time}', max_alt={self.max_altitude_deg}°)>"


class ConstellationModel(Base):
    """
    SQLAlchemy model for constellation reference data.

    Stores the 88 official IAU constellations with their boundaries
    and visibility information. This is static reference data.
    """

    __tablename__ = "constellations"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Constellation identification
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)  # Latin name
    abbreviation: Mapped[str] = mapped_column(String(3), nullable=False, unique=True)  # 3-letter IAU code
    common_name: Mapped[str | None] = mapped_column(String(100), nullable=True)  # English name

    # Position (center of constellation)
    ra_hours: Mapped[float] = mapped_column(Float, nullable=False)  # RA of center
    dec_degrees: Mapped[float] = mapped_column(Float, nullable=False)  # Dec of center

    # Boundaries (for visibility calculations)
    ra_min_hours: Mapped[float] = mapped_column(Float, nullable=False)
    ra_max_hours: Mapped[float] = mapped_column(Float, nullable=False)
    dec_min_degrees: Mapped[float] = mapped_column(Float, nullable=False)
    dec_max_degrees: Mapped[float] = mapped_column(Float, nullable=False)

    # Metadata
    area_sq_deg: Mapped[float | None] = mapped_column(Float, nullable=True)  # Area in square degrees
    brightest_star: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Name of brightest star
    mythology: Mapped[str | None] = mapped_column(Text, nullable=True)  # Mythology/story
    season: Mapped[str | None] = mapped_column(String(20), nullable=True)  # Best viewing season (N hemisphere)

    # Composite indexes for position-based queries
    __table_args__ = (
        Index("idx_constellation_position", "ra_hours", "dec_degrees"),
        Index("idx_constellation_bounds", "ra_min_hours", "ra_max_hours", "dec_min_degrees", "dec_max_degrees"),
    )

    def to_constellation(self) -> Constellation:
        """
        Convert ConstellationModel to Constellation dataclass.

        Returns:
            Constellation dataclass instance
        """
        from celestron_nexstar.api.astronomy.constellations import Constellation

        # Calculate hemisphere from declination
        if self.dec_degrees > 30:
            hemisphere = "Northern"
        elif self.dec_degrees < -30:
            hemisphere = "Southern"
        else:
            hemisphere = "Equatorial"

        # Use mythology as description, or empty string
        description = self.mythology or ""

        # Magnitude not stored in model - use 0.0 as placeholder
        magnitude = 0.0

        return Constellation(
            name=self.name,
            abbreviation=self.abbreviation,
            ra_hours=self.ra_hours,
            dec_degrees=self.dec_degrees,
            area_sq_deg=self.area_sq_deg or 0.0,
            brightest_star=self.brightest_star or "",
            magnitude=magnitude,
            season=self.season or "",
            hemisphere=hemisphere,
            description=description,
        )

    def __repr__(self) -> str:
        """String representation of constellation."""
        return f"<Constellation(id={self.id}, name='{self.name}', abbr='{self.abbreviation}')>"


class AsterismModel(Base):
    """
    SQLAlchemy model for asterism reference data.

    Stores famous asterisms (star patterns) that are not official constellations
    but are well-known to observers (e.g., Big Dipper, Summer Triangle).
    """

    __tablename__ = "asterisms"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Asterism identification
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    alt_names: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Alternative names (comma-separated)

    # Position (center of asterism)
    ra_hours: Mapped[float] = mapped_column(Float, nullable=False)
    dec_degrees: Mapped[float] = mapped_column(Float, nullable=False)

    # Size
    size_degrees: Mapped[float | None] = mapped_column(Float, nullable=True)  # Approximate angular size

    # Metadata
    parent_constellation: Mapped[str | None] = mapped_column(String(50), nullable=True)  # Part of which constellation
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    stars: Mapped[str | None] = mapped_column(Text, nullable=True)  # Component stars (comma-separated)
    season: Mapped[str | None] = mapped_column(String(20), nullable=True)  # Best viewing season

    # Composite indexes for position-based queries
    __table_args__ = (
        Index("idx_asterism_position", "ra_hours", "dec_degrees"),
        Index("idx_asterism_parent", "parent_constellation"),
    )

    def to_asterism(self) -> Asterism:
        """
        Convert AsterismModel to Asterism dataclass.

        Returns:
            Asterism dataclass instance
        """
        from celestron_nexstar.api.astronomy.constellations import Asterism

        # Parse alt_names and stars (stored as comma-separated strings)
        alt_names = self.alt_names.split(",") if self.alt_names else []
        member_stars = self.stars.split(",") if self.stars else []

        # Calculate hemisphere from declination
        if self.dec_degrees > 30:
            hemisphere = "Northern"
        elif self.dec_degrees < -30:
            hemisphere = "Southern"
        else:
            hemisphere = "Equatorial"

        return Asterism(
            name=self.name,
            alt_names=alt_names,
            ra_hours=self.ra_hours,
            dec_degrees=self.dec_degrees,
            size_degrees=self.size_degrees or 0.0,
            parent_constellation=self.parent_constellation or "",
            season=self.season or "",
            hemisphere=hemisphere,
            member_stars=member_stars,
            description=self.description or "",
        )

    def __repr__(self) -> str:
        """String representation of asterism."""
        return f"<Asterism(id={self.id}, name='{self.name}')>"


class MeteorShowerModel(Base):
    """
    SQLAlchemy model for meteor shower calendar.

    Stores annual meteor shower data including peak dates, rates, and radiant positions.
    This is static reference data that repeats annually.
    """

    __tablename__ = "meteor_showers"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Shower identification
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    code: Mapped[str | None] = mapped_column(String(3), nullable=True)  # IAU 3-letter code

    # Activity period (month/day, year-independent)
    start_month: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-12
    start_day: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-31
    end_month: Mapped[int] = mapped_column(Integer, nullable=False)
    end_day: Mapped[int] = mapped_column(Integer, nullable=False)
    peak_month: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    peak_day: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Radiant position (where meteors appear to originate)
    radiant_ra_hours: Mapped[float] = mapped_column(Float, nullable=False)
    radiant_dec_degrees: Mapped[float] = mapped_column(Float, nullable=False)
    radiant_constellation: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Activity characteristics
    zhr_peak: Mapped[int] = mapped_column(Integer, nullable=False)  # Zenith Hourly Rate at peak
    velocity_km_s: Mapped[float | None] = mapped_column(Float, nullable=True)  # Meteor velocity
    parent_comet: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Source comet/asteroid

    # Observing notes
    best_time: Mapped[str | None] = mapped_column(String(50), nullable=True)  # "After midnight", "Pre-dawn", etc.
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Composite indexes
    __table_args__ = (
        Index("idx_peak_date", "peak_month", "peak_day"),
        Index("idx_radiant_constellation", "radiant_constellation"),  # For filtering by constellation
    )

    def to_meteor_shower(self) -> MeteorShower:
        """
        Convert MeteorShowerModel to MeteorShower dataclass.

        Returns:
            MeteorShower dataclass instance
        """
        from celestron_nexstar.api.astronomy.meteor_showers import MeteorShower

        # Handle velocity_km_s which may be None
        velocity = int(self.velocity_km_s) if self.velocity_km_s is not None else 0

        return MeteorShower(
            name=self.name,
            activity_start_month=self.start_month,
            activity_start_day=self.start_day,
            activity_end_month=self.end_month,
            activity_end_day=self.end_day,
            peak_month=self.peak_month,
            peak_day=self.peak_day,
            peak_end_month=self.peak_month,  # Use peak_month as fallback
            peak_end_day=self.peak_day,  # Use peak_day as fallback
            zhr_peak=self.zhr_peak,
            velocity_km_s=velocity,
            radiant_ra_hours=self.radiant_ra_hours,
            radiant_dec_degrees=self.radiant_dec_degrees,
            parent_comet=self.parent_comet,
            description=self.notes or "",
        )


class DarkSkySiteModel(Base):
    """
    SQLAlchemy model for dark sky viewing sites.

    Stores information about known dark sky locations including
    International Dark Sky Parks and other notable observing sites.
    """

    __tablename__ = "dark_sky_sites"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Site identification
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)

    # Location
    latitude: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    geohash: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)

    # Sky quality
    bortle_class: Mapped[int] = mapped_column(Integer, nullable=False, index=True)  # 1-9
    sqm_value: Mapped[float] = mapped_column(Float, nullable=False)  # Sky Quality Meter value

    # Description
    description: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    # Composite indexes for location queries
    __table_args__ = (
        Index("idx_location", "latitude", "longitude"),
        Index("idx_dark_sky_geohash", "geohash"),  # For efficient spatial proximity searches
    )

    def __repr__(self) -> str:
        """String representation of the site."""
        return f"<DarkSkySite(id={self.id}, name='{self.name}', bortle={self.bortle_class})>"


class SpaceEventModel(Base):
    """
    SQLAlchemy model for space events calendar.

    Stores space events from sources like The Planetary Society calendar,
    including eclipses, meteor showers, planetary events, and space missions.
    This is static reference data that can be updated periodically.
    """

    __tablename__ = "space_events"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Event identification
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    # Description
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Viewing requirements
    min_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    dark_sky_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    min_bortle_class: Mapped[int | None] = mapped_column(Integer, nullable=True)
    equipment_needed: Mapped[str | None] = mapped_column(String(50), nullable=True)
    viewing_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Source information
    source: Mapped[str] = mapped_column(String(100), nullable=False, default="Planetary Society")
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    # Composite indexes
    __table_args__ = (
        Index("idx_event_date_type", "date", "event_type"),
        Index("idx_event_source", "source"),  # For filtering by source
    )

    def __repr__(self) -> str:
        """String representation of the event."""
        return f"<SpaceEvent(id={self.id}, name='{self.name}', date={self.date})>"


class EphemerisFileModel(Base):
    """
    SQLAlchemy model for JPL ephemeris files.

    Stores information about available ephemeris files from NAIF,
    including file metadata, coverage dates, and contents.
    """

    __tablename__ = "ephemeris_files"

    # Primary key (file key like "de440s", "jup365")
    file_key: Mapped[str] = mapped_column(String(100), primary_key=True)

    # File identification
    filename: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Coverage
    coverage_start: Mapped[int] = mapped_column(Integer, nullable=False)  # Year
    coverage_end: Mapped[int] = mapped_column(Integer, nullable=False)  # Year

    # File properties
    size_mb: Mapped[float] = mapped_column(Float, nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # "planets" or "satellites"
    url: Mapped[str] = mapped_column(String(512), nullable=False)

    # Contents (stored as comma-separated string)
    contents: Mapped[str] = mapped_column(Text, nullable=False)  # Comma-separated list of objects

    # Use case description
    use_case: Mapped[str] = mapped_column(Text, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    # Indexes
    __table_args__ = (
        Index("idx_file_type", "file_type"),
        Index("idx_coverage", "coverage_start", "coverage_end"),
    )

    def __repr__(self) -> str:
        """String representation of the ephemeris file."""
        return f"<EphemerisFile(file_key='{self.file_key}', filename='{self.filename}')>"


class StarNameMappingModel(Base):
    """
    SQLAlchemy model for star name mappings.

    Maps catalog numbers (e.g., HR numbers) to common star names. This allows
    users to search for stars by their common names (e.g., "Capella") even though
    they're stored in the database as catalog numbers (e.g., "HR 1708").
    """

    __tablename__ = "star_name_mappings"

    # Primary key
    hr_number: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Common name
    common_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Optional: Bayer designation (e.g., "Alpha Aurigae")
    bayer_designation: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    def __repr__(self) -> str:
        """String representation of star name mapping."""
        return f"<StarNameMapping(hr_number={self.hr_number}, common_name='{self.common_name}')>"


class TLEModel(Base):
    """
    SQLAlchemy model for Two-Line Element (TLE) satellite data.

    Stores TLE data for satellites (e.g., Starlink) fetched from CelesTrak.
    TLE data is refreshed periodically as satellite orbits change.
    """

    __tablename__ = "tle_data"

    # Primary key - NORAD catalog number
    norad_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Satellite identification
    satellite_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    satellite_group: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)  # e.g., "starlink"

    # TLE data (two lines)
    line1: Mapped[str] = mapped_column(Text, nullable=False)  # First line of TLE
    line2: Mapped[str] = mapped_column(Text, nullable=False)  # Second line of TLE

    # Metadata
    epoch: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # TLE epoch time

    # Cache metadata
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )

    # Indexes
    __table_args__ = (
        Index("idx_satellite_group", "satellite_group"),
        Index("idx_fetched_at", "fetched_at"),
    )

    def __repr__(self) -> str:
        """String representation of TLE data."""
        return f"<TLE(norad_id={self.norad_id}, name='{self.satellite_name}', group='{self.satellite_group}')>"


class VariableStarModel(Base):
    """
    SQLAlchemy model for variable stars.

    Stores information about well-known variable stars including eclipsing binaries,
    Cepheids, and other variable star types.
    """

    __tablename__ = "variable_stars"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Star identification
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    designation: Mapped[str] = mapped_column(String(50), nullable=False)  # Bayer/Flamsteed designation

    # Variable star properties
    variable_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # "eclipsing_binary", "cepheid", etc.
    period_days: Mapped[float] = mapped_column(Float, nullable=False)
    magnitude_min: Mapped[float] = mapped_column(Float, nullable=False)  # Brightest
    magnitude_max: Mapped[float] = mapped_column(Float, nullable=False)  # Dimmest

    # Position
    ra_hours: Mapped[float] = mapped_column(Float, nullable=False)
    dec_degrees: Mapped[float] = mapped_column(Float, nullable=False)

    # Notes
    notes: Mapped[str] = mapped_column(Text, nullable=False)

    # Indexes
    __table_args__ = (
        Index("idx_variable_type", "variable_type"),
        Index("idx_position", "ra_hours", "dec_degrees"),
    )

    def to_variable_star(self) -> VariableStar:
        """
        Convert VariableStarModel to VariableStar dataclass.

        Returns:
            VariableStar dataclass instance
        """
        from celestron_nexstar.api.astronomy.variable_stars import VariableStar

        return VariableStar(
            name=self.name,
            designation=self.designation,
            variable_type=self.variable_type,
            period_days=self.period_days,
            magnitude_min=self.magnitude_min,
            magnitude_max=self.magnitude_max,
            ra_hours=self.ra_hours,
            dec_degrees=self.dec_degrees,
            notes=self.notes,
        )

    def __repr__(self) -> str:
        """String representation of variable star."""
        return f"<VariableStar(id={self.id}, name='{self.name}', type='{self.variable_type}')>"


class CometModel(Base):
    """
    SQLAlchemy model for comets.

    Stores information about known bright comets including periodic and non-periodic comets.
    """

    __tablename__ = "comets"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Comet identification
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    designation: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, index=True
    )  # Official designation

    # Orbital properties
    perihelion_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    perihelion_distance_au: Mapped[float] = mapped_column(Float, nullable=False)
    peak_magnitude: Mapped[float] = mapped_column(Float, nullable=False)
    peak_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    is_periodic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    period_years: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Notes
    notes: Mapped[str] = mapped_column(Text, nullable=False)

    # Indexes
    __table_args__ = (
        Index("idx_perihelion_date", "perihelion_date"),
        Index("idx_peak_date", "peak_date"),
        Index("idx_is_periodic", "is_periodic"),
    )

    def to_comet(self) -> Comet:
        """
        Convert CometModel to Comet dataclass.

        Returns:
            Comet dataclass instance
        """
        from celestron_nexstar.api.astronomy.comets import Comet

        return Comet(
            name=self.name,
            designation=self.designation,
            perihelion_date=self.perihelion_date,
            perihelion_distance_au=self.perihelion_distance_au,
            peak_magnitude=self.peak_magnitude,
            peak_date=self.peak_date,
            is_periodic=self.is_periodic,
            period_years=self.period_years,
            notes=self.notes,
        )

    def __repr__(self) -> str:
        """String representation of comet."""
        return f"<Comet(id={self.id}, name='{self.name}', designation='{self.designation}')>"


class EclipseModel(Base):
    """
    SQLAlchemy model for eclipses.

    Stores information about known upcoming lunar and solar eclipses.
    """

    __tablename__ = "eclipses"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Eclipse identification
    eclipse_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # "lunar_total", "solar_annular", etc.
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    magnitude: Mapped[float] = mapped_column(Float, nullable=False)  # Eclipse magnitude

    # Indexes
    __table_args__ = (
        Index("idx_eclipse_type", "eclipse_type"),
        Index("idx_eclipse_date", "date"),
        Index("idx_type_date", "eclipse_type", "date"),
    )

    def __repr__(self) -> str:
        """String representation of eclipse."""
        return f"<Eclipse(id={self.id}, type='{self.eclipse_type}', date={self.date})>"


class BortleCharacteristicsModel(Base):
    """
    SQLAlchemy model for Bortle class characteristics.

    Stores lookup data for Bortle scale sky quality classes.
    """

    __tablename__ = "bortle_characteristics"

    # Primary key - Bortle class (1-9)
    bortle_class: Mapped[int] = mapped_column(Integer, primary_key=True)

    # SQM range
    sqm_min: Mapped[float] = mapped_column(Float, nullable=False)
    sqm_max: Mapped[float] = mapped_column(Float, nullable=False)

    # Observing characteristics
    naked_eye_mag: Mapped[float] = mapped_column(Float, nullable=False)  # Naked eye limiting magnitude
    milky_way: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    airglow: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    zodiacal_light: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Description
    description: Mapped[str] = mapped_column(Text, nullable=False)
    recommendations: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array as string

    # Indexes
    __table_args__ = (Index("idx_sqm_range", "sqm_min", "sqm_max"),)

    def __repr__(self) -> str:
        """String representation of Bortle characteristics."""
        return f"<BortleCharacteristics(bortle_class={self.bortle_class}, sqm_range=({self.sqm_min}, {self.sqm_max}))>"


class RSSFeedModel(Base):
    """
    SQLAlchemy model for RSS feed articles from multiple astronomy sources.

    Stores astronomy news and night sky events from various RSS feed sources.
    """

    __tablename__ = "rss_feeds"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Article identification
    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    link: Mapped[str] = mapped_column(String(1000), nullable=False, unique=True, index=True)
    guid: Mapped[str | None] = mapped_column(String(500), nullable=True, unique=True, index=True)

    # Content
    description: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)  # Full content if available

    # Publication date
    published_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    # Author
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Categories/tags
    categories: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array as string

    # Source information
    source: Mapped[str] = mapped_column(String(100), nullable=False, default="Sky & Telescope")
    feed_url: Mapped[str] = mapped_column(String(1000), nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    # Composite indexes
    __table_args__ = (
        Index("idx_published_date", "published_date"),
        Index("idx_source_fetched", "source", "fetched_at"),
    )

    def __repr__(self) -> str:
        """String representation of the article."""
        return f"<RSSFeed(id={self.id}, title='{self.title[:50]}...', published={self.published_date})>"


@asynccontextmanager
async def get_db_session() -> AsyncIterator[AsyncSession]:
    """
    Get an async database session as a context manager.

    Yields an AsyncSession that is automatically closed when exiting the context.
    Use this for async database operations that need a session.

    Example:
        async with get_db_session() as db:
            # Use db session here
            result = await db.execute(select(...))
            await db.commit()
    """
    from celestron_nexstar.api.database.database import get_database

    db = get_database()
    async with db._AsyncSession() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

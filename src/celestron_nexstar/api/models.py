"""
SQLAlchemy Models for Celestial Objects Database

Defines the database schema using SQLAlchemy ORM for type-safe database operations
and automatic migration management with Alembic.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session


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

    # Composite index for finding active showers by date
    __table_args__ = (Index("idx_peak_date", "peak_month", "peak_day"),)


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

    # Composite index for location queries
    __table_args__ = (Index("idx_location", "latitude", "longitude"),)

    def __repr__(self) -> str:
        """String representation of the site."""
        return f"<DarkSkySite(id={self.id}, name='{self.name}', bortle={self.bortle_class})>"


@contextmanager
def get_db_session() -> Iterator[Session]:
    """
    Get a database session as a context manager.

    Yields a SQLAlchemy Session that is automatically closed when exiting the context.
    Use this for database operations that need a session.

    Example:
        with get_db_session() as db:
            # Use db session here
            pass
    """
    from .database import get_database

    db = get_database()
    session = db._get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

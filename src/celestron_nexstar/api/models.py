"""
SQLAlchemy Models for Celestial Objects Database

Defines the database schema using SQLAlchemy ORM for type-safe database operations
and automatic migration management with Alembic.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


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
    common_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    catalog: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    catalog_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Position (J2000 epoch for fixed objects)
    ra_hours: Mapped[float] = mapped_column(Float, nullable=False)
    dec_degrees: Mapped[float] = mapped_column(Float, nullable=False)

    # Physical properties
    magnitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True, index=True)
    object_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    size_arcmin: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Metadata
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    constellation: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)

    # Dynamic object support (planets/moons)
    is_dynamic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    ephemeris_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    parent_planet: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    # Relationships
    observations: Mapped[list["ObservationModel"]] = relationship(
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
    location_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    location_lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    location_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Viewing conditions
    seeing_quality: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1-5 scale
    transparency: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1-5 scale
    sky_brightness: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # SQM value
    weather_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Equipment used
    telescope: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    eyepiece: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    filters: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Observation notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1-5 stars

    # Images/sketches
    image_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    sketch_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    # Relationships
    celestial_object: Mapped["CelestialObjectModel"] = relationship("CelestialObjectModel", back_populates="observations")

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
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

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

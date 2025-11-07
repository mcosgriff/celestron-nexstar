"""
SQLAlchemy Models for Celestial Objects Database

Defines the database schema using SQLAlchemy ORM for type-safe database operations
and automatic migration management with Alembic.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


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

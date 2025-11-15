"""
Custom exception classes for Celestron NexStar telescope control.

This module defines specific exceptions for different types of errors
that can occur during telescope operations.
"""

from __future__ import annotations


__all__ = [
    "CatalogNotFoundError",
    # Telescope exceptions
    "CommandError",
    # Configuration exceptions
    "ConfigurationError",
    "ConfigurationNotFoundError",
    # Data import exceptions
    "DataImportError",
    "DataImportFailedError",
    "DatabaseBackupError",
    # Database exceptions
    "DatabaseError",
    "DatabaseMigrationError",
    "DatabaseNotFoundError",
    "DatabaseRebuildError",
    "DatabaseRestoreError",
    "EphemerisDownloadError",
    # Ephemeris exceptions
    "EphemerisError",
    "EphemerisFileNotFoundError",
    "GeocodingError",
    "ISSCalculationError",
    # ISS Tracking exceptions
    "ISSTrackingError",
    "InvalidCatalogFormatError",
    "InvalidConfigurationError",
    "InvalidCoordinateError",
    # Location/Observer exceptions
    "LocationError",
    "LocationNotFoundError",
    "LocationNotSetError",
    # Base exception
    "NexstarError",
    "NotConnectedError",
    "TLEFetchError",
    "TelescopeConnectionError",
    "TelescopeTimeoutError",
    "UnknownEphemerisObjectError",
]


class NexstarError(Exception):
    """
    Base exception for all NexStar telescope errors.

    All custom exceptions in this library inherit from this base class,
    making it easy to catch all telescope-related errors.
    """

    pass


class TelescopeConnectionError(NexstarError):
    """
    Raised when connection to the telescope fails.

    This can occur when:
    - Serial port cannot be opened
    - Port does not exist
    - Port is already in use by another application
    - USB cable is disconnected
    """

    pass


class TelescopeTimeoutError(NexstarError):
    """
    Raised when a telescope command times out.

    This indicates the telescope did not respond within the expected
    time window, which may mean:
    - Telescope is not powered on
    - Communication cable is faulty
    - Telescope is busy with another operation
    """

    pass


class InvalidCoordinateError(NexstarError):
    """
    Raised when coordinates are out of valid range.

    This occurs when attempting to use coordinates that are:
    - RA outside 0-24 hours range
    - Dec outside -90 to +90 degrees range
    - Azimuth outside 0-360 degrees range
    - Altitude outside -90 to +90 degrees range
    """

    pass


class CommandError(NexstarError):
    """
    Raised when a telescope command fails or returns an unexpected response.

    This can occur when:
    - Command returns invalid data format
    - Telescope reports an error condition
    - Response cannot be parsed
    """

    pass


class NotConnectedError(NexstarError):
    """
    Raised when attempting to send commands while not connected.

    This occurs when trying to control the telescope before calling
    connect() or after disconnect().
    """

    pass


# ============================================================================
# Database Exceptions
# ============================================================================


class DatabaseError(NexstarError):
    """Base exception for database-related errors."""

    pass


class DatabaseNotFoundError(DatabaseError):
    """Raised when database file doesn't exist."""

    pass


class DatabaseBackupError(DatabaseError):
    """Raised when backup operations fail."""

    pass


class DatabaseRestoreError(DatabaseError):
    """Raised when restore operations fail."""

    pass


class DatabaseRebuildError(DatabaseError):
    """Raised when database rebuild fails."""

    pass


class DatabaseMigrationError(DatabaseError):
    """Raised when Alembic migrations fail."""

    pass


# ============================================================================
# Data Import Exceptions
# ============================================================================


class DataImportError(NexstarError):
    """Base exception for data import errors."""

    pass


class CatalogNotFoundError(DataImportError):
    """Raised when a catalog file or source is not found."""

    pass


class InvalidCatalogFormatError(DataImportError):
    """Raised when catalog data format is invalid."""

    pass


class DataImportFailedError(DataImportError):
    """Raised when data import fails."""

    pass


# ============================================================================
# Ephemeris Exceptions
# ============================================================================


class EphemerisError(NexstarError):
    """Base exception for ephemeris-related errors."""

    pass


class EphemerisFileNotFoundError(EphemerisError):
    """Raised when ephemeris file doesn't exist."""

    pass


class EphemerisDownloadError(EphemerisError):
    """Raised when ephemeris download fails."""

    pass


class UnknownEphemerisObjectError(EphemerisError):
    """Raised when planet/moon name is unknown."""

    pass


# ============================================================================
# Location/Observer Exceptions
# ============================================================================


class LocationError(NexstarError):
    """Base exception for location-related errors."""

    pass


class LocationNotFoundError(LocationError):
    """Raised when location cannot be found via geocoding."""

    pass


class GeocodingError(LocationError):
    """Raised when geocoding API fails."""

    pass


class LocationNotSetError(LocationError):
    """Raised when location is required but not set."""

    pass


# ============================================================================
# ISS Tracking Exceptions
# ============================================================================


class ISSTrackingError(NexstarError):
    """Base exception for ISS tracking errors."""

    pass


class TLEFetchError(ISSTrackingError):
    """Raised when TLE data cannot be fetched."""

    pass


class ISSCalculationError(ISSTrackingError):
    """Raised when ISS position calculations fail."""

    pass


# ============================================================================
# Configuration Exceptions
# ============================================================================


class ConfigurationError(NexstarError):
    """Base exception for configuration errors."""

    pass


class InvalidConfigurationError(ConfigurationError):
    """Raised when configuration is invalid."""

    pass


class ConfigurationNotFoundError(ConfigurationError):
    """Raised when configuration file doesn't exist."""

    pass

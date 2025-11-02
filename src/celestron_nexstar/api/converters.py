"""
Coordinate conversion utilities for telescope operations.

This module provides helper functions for converting between different
coordinate representations used by the telescope API and protocol.
"""

from __future__ import annotations

from .constants import DEGREES_PER_HOUR_ANGLE


__all__ = ["CoordinateConverter"]


class CoordinateConverter:
    """Helper class for coordinate system conversions."""

    @staticmethod
    def ra_hours_to_degrees(ra_hours: float) -> float:
        """
        Convert Right Ascension from hours to degrees.

        Args:
            ra_hours: Right Ascension in hours (0-24)

        Returns:
            Right Ascension in degrees (0-360)

        Example:
            >>> CoordinateConverter.ra_hours_to_degrees(12.0)
            180.0
        """
        return ra_hours * DEGREES_PER_HOUR_ANGLE

    @staticmethod
    def ra_degrees_to_hours(ra_degrees: float) -> float:
        """
        Convert Right Ascension from degrees to hours.

        Args:
            ra_degrees: Right Ascension in degrees (0-360)

        Returns:
            Right Ascension in hours (0-24)

        Example:
            >>> CoordinateConverter.ra_degrees_to_hours(180.0)
            12.0
        """
        return ra_degrees / DEGREES_PER_HOUR_ANGLE

    @staticmethod
    def dec_to_unsigned(dec_degrees: float) -> float:
        """
        Convert Declination from signed (-90 to +90) to unsigned (0-360) format.

        The telescope protocol uses unsigned format where negative declinations
        are represented as values > 180 degrees.

        Args:
            dec_degrees: Declination in degrees (-90 to +90)

        Returns:
            Declination in unsigned format (0-360)

        Example:
            >>> CoordinateConverter.dec_to_unsigned(-30.0)
            330.0
            >>> CoordinateConverter.dec_to_unsigned(45.0)
            45.0
        """
        return dec_degrees + 360 if dec_degrees < 0 else dec_degrees

    @staticmethod
    def dec_to_signed(dec_degrees: float) -> float:
        """
        Convert Declination from unsigned (0-360) to signed (-90 to +90) format.

        Args:
            dec_degrees: Declination in unsigned format (0-360)

        Returns:
            Declination in signed format (-90 to +90)

        Example:
            >>> CoordinateConverter.dec_to_signed(330.0)
            -30.0
            >>> CoordinateConverter.dec_to_signed(45.0)
            45.0
        """
        return dec_degrees - 360 if dec_degrees > 180 else dec_degrees

    @staticmethod
    def altitude_to_unsigned(altitude: float) -> float:
        """
        Convert Altitude from signed (-90 to +90) to unsigned (0-360) format.

        Args:
            altitude: Altitude in degrees (-90 to +90)

        Returns:
            Altitude in unsigned format (0-360)

        Example:
            >>> CoordinateConverter.altitude_to_unsigned(-15.0)
            345.0
            >>> CoordinateConverter.altitude_to_unsigned(45.0)
            45.0
        """
        return altitude + 360 if altitude < 0 else altitude

    @staticmethod
    def altitude_to_signed(altitude: float) -> float:
        """
        Convert Altitude from unsigned (0-360) to signed (-90 to +90) format.

        Args:
            altitude: Altitude in unsigned format (0-360)

        Returns:
            Altitude in signed format (-90 to +90)

        Example:
            >>> CoordinateConverter.altitude_to_signed(345.0)
            -15.0
            >>> CoordinateConverter.altitude_to_signed(45.0)
            45.0
        """
        return altitude - 360 if altitude > 180 else altitude

    @staticmethod
    def location_to_unsigned(coordinate: float) -> float:
        """
        Convert geographic coordinate from signed to unsigned format.

        Used for both latitude and longitude when sending to telescope.

        Args:
            coordinate: Coordinate in signed format (-180 to +180)

        Returns:
            Coordinate in unsigned format (0-360)

        Example:
            >>> CoordinateConverter.location_to_unsigned(-74.0)
            286.0
            >>> CoordinateConverter.location_to_unsigned(40.0)
            40.0
        """
        return coordinate + 360 if coordinate < 0 else coordinate

    @staticmethod
    def location_to_signed(coordinate: float) -> float:
        """
        Convert geographic coordinate from unsigned to signed format.

        Used for both latitude and longitude when receiving from telescope.

        Args:
            coordinate: Coordinate in unsigned format (0-360)

        Returns:
            Coordinate in signed format (-180 to +180)

        Example:
            >>> CoordinateConverter.location_to_signed(286.0)
            -74.0
            >>> CoordinateConverter.location_to_signed(40.0)
            40.0
        """
        return coordinate - 360 if coordinate > 180 else coordinate

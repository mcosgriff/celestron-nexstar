"""
Celestron NexStar 6SE Telescope API

Provides high-level Python interface for controlling Celestron NexStar telescopes.

This module provides a user-friendly interface that wraps the low-level NexStarProtocol
for convenient telescope control operations.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

import deal
import serial

from .converters import CoordinateConverter
from .exceptions import InvalidCoordinateError, NotConnectedError, TelescopeConnectionError
from .protocol import NexStarProtocol
from .types import (
    EquatorialCoordinates,
    GeographicLocation,
    HorizontalCoordinates,
    TelescopeConfig,
    TelescopeInfo,
    TelescopeTime,
    TrackingMode,
)


__all__ = ["NexStarTelescope"]


logger = logging.getLogger(__name__)


class NexStarTelescope:
    """
    High-level interface for controlling Celestron NexStar 6SE telescope.

    This class provides convenient methods for telescope operations by wrapping
    the low-level NexStarProtocol. It handles coordinate conversions, provides
    user-friendly methods, and manages the connection lifecycle.

    Example:
        >>> from celestron_nexstar import NexStarTelescope, TelescopeConfig, TrackingMode
        >>> config = TelescopeConfig(port='/dev/ttyUSB0')
        >>> telescope = NexStarTelescope(config)
        >>> telescope.connect()
        >>> position = telescope.get_position_ra_dec()
        >>> print(position)
        >>> telescope.set_tracking_mode(TrackingMode.ALT_AZ)
        >>> telescope.disconnect()
    """

    def __init__(self, config: TelescopeConfig | str | None = None) -> None:
        """
        Initialize telescope interface.

        Args:
            config: TelescopeConfig object or port string.
                   If string, uses default configuration with specified port.
                   If None, uses default '/dev/ttyUSB0'

        Example:
            >>> telescope = NexStarTelescope('/dev/ttyUSB0')
            >>> # Or with full config:
            >>> config = TelescopeConfig(port='/dev/ttyUSB0', baudrate=9600, verbose=True)
            >>> telescope = NexStarTelescope(config)
        """
        # Handle different config input types
        if config is None:
            self.config = TelescopeConfig()
        elif isinstance(config, str):
            self.config = TelescopeConfig(port=config)
        else:
            self.config = config

        # Set up logging based on verbosity
        if self.config.verbose:
            logging.basicConfig(level=logging.DEBUG)

        # Create protocol instance
        self.protocol = NexStarProtocol(
            port=self.config.port, baudrate=self.config.baudrate, timeout=self.config.timeout
        )

        # Keep for backward compatibility with tests
        self.serial_conn: serial.Serial | None = None

        # Auto-connect if requested
        if self.config.auto_connect:
            self.connect()

    @deal.pre(lambda self: self.protocol.is_open(), message="Telescope must be connected")  # type: ignore[misc,arg-type]
    @deal.post(lambda result: result is True, message="Connection must succeed")
    @deal.raises(TelescopeConnectionError)
    def connect(self) -> bool:
        """
        Establish connection to telescope.

        Returns:
            True if connection successful

        Raises:
            TelescopeConnectionError: If connection fails

        Example:
            >>> telescope = NexStarTelescope('/dev/ttyUSB0')
            >>> telescope.connect()
            True
        """
        try:
            self.protocol.open()
            # Update serial_conn for backward compatibility
            self.serial_conn = self.protocol.serial_conn

            # Test connection with echo command
            if self.protocol.echo():
                logger.info(f"Successfully connected to telescope on {self.config.port}")
                return True
            else:
                logger.error("Echo test failed - telescope not responding properly")
                self.protocol.close()
                self.serial_conn = None
                raise TelescopeConnectionError("Echo test failed") from None

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            raise

    @deal.post(lambda result: result is None, message="Disconnect must complete")
    def disconnect(self) -> None:
        """
        Close telescope connection.

        Example:
            >>> telescope.disconnect()
        """
        self.protocol.close()
        self.serial_conn = None
        logger.info("Disconnected from telescope")

    def echo_test(self, char: str = "x") -> bool:
        """
        Test connection with echo command.

        Args:
            char: Single character to echo (default 'x')

        Returns:
            True if echo successful

        Example:
            >>> telescope.echo_test('A')
            True
        """
        return self.protocol.echo(char)

    def get_info(self) -> TelescopeInfo:
        """
        Get telescope hardware information.

        Returns:
            TelescopeInfo object with model and firmware version

        Example:
            >>> info = telescope.get_info()
            >>> print(info)
            Model 6, Firmware 4.21
        """
        major, minor = self.protocol.get_version()
        model = self.protocol.get_model()
        return TelescopeInfo(model=model, firmware_major=major, firmware_minor=minor)

    def get_version(self) -> tuple[int, int]:
        """
        Get telescope firmware version (legacy method).

        Returns:
            Tuple of (major_version, minor_version)

        Example:
            >>> telescope.get_version()
            (4, 21)
        """
        return self.protocol.get_version()

    def get_model(self) -> int:
        """
        Get telescope model number (legacy method).

        Returns:
            Model number (6 for NexStar 6SE)

        Example:
            >>> telescope.get_model()
            6
        """
        return self.protocol.get_model()

    @deal.pre(lambda self: self.protocol.is_open(), message="Telescope must be connected")  # type: ignore[misc,arg-type]
    @deal.post(lambda result: result is not None, message="Position must be returned")
    def get_position_ra_dec(self) -> EquatorialCoordinates:
        """
        Get current Right Ascension and Declination.

        Returns:
            EquatorialCoordinates object with RA in hours and Dec in degrees

        Raises:
            NotConnectedError: If not connected to telescope

        Example:
            >>> position = telescope.get_position_ra_dec()
            >>> print(f"RA: {position.ra_hours}h, Dec: {position.dec_degrees}°")
        """
        result = self.protocol.get_ra_dec_precise()

        # Handle Result type - unwrap or return default
        return result.map(
            lambda coords: EquatorialCoordinates(
                ra_hours=CoordinateConverter.ra_degrees_to_hours(coords[0]),
                dec_degrees=CoordinateConverter.dec_to_signed(coords[1]),
            )
        ).value_or(
            # Default value on failure
            EquatorialCoordinates(ra_hours=0.0, dec_degrees=0.0)
        )

    @deal.pre(lambda self: self.protocol.is_open(), message="Telescope must be connected")  # type: ignore[misc,arg-type]
    @deal.post(lambda result: result is not None, message="Position must be returned")
    def get_position_alt_az(self) -> HorizontalCoordinates:
        """
        Get current Altitude and Azimuth.

        Returns:
            HorizontalCoordinates object with azimuth and altitude in degrees

        Raises:
            NotConnectedError: If not connected to telescope

        Example:
            >>> position = telescope.get_position_alt_az()
            >>> print(f"Az: {position.azimuth}°, Alt: {position.altitude}°")
        """
        result = self.protocol.get_alt_az_precise()

        # Handle Result type - unwrap or return default
        return result.map(
            lambda coords: HorizontalCoordinates(
                azimuth=coords[0], altitude=CoordinateConverter.altitude_to_signed(coords[1])
            )
        ).value_or(
            # Default value on failure
            HorizontalCoordinates(azimuth=0.0, altitude=0.0)
        )

    # type: ignore[misc,arg-type]
    @deal.pre(lambda self, ra_hours, dec_degrees: self.protocol.is_open(), message="Telescope must be connected")
    @deal.pre(lambda self, ra_hours, dec_degrees: 0 <= ra_hours < 24, message="RA must be 0-24 hours")
    @deal.pre(lambda self, ra_hours, dec_degrees: -90 <= dec_degrees <= 90, message="Dec must be -90 to +90 degrees")
    @deal.post(lambda result: result is True, message="Goto must succeed")
    @deal.raises(NotConnectedError, InvalidCoordinateError)
    def goto_ra_dec(self, ra_hours: float, dec_degrees: float) -> bool:
        """
        Slew telescope to specific RA/Dec coordinates.

        Args:
            ra_hours: Right Ascension in hours (0-24)
            dec_degrees: Declination in degrees (-90 to +90)

        Returns:
            True if command successful

        Raises:
            NotConnectedError: If not connected to telescope

        Example:
            >>> # Slew to Polaris
            >>> telescope.goto_ra_dec(2.5303, 89.2641)
            True
        """
        # Convert to protocol format
        ra_deg = CoordinateConverter.ra_hours_to_degrees(ra_hours)
        dec_deg = CoordinateConverter.dec_to_unsigned(dec_degrees)

        logger.info(f"Slewing to RA {ra_hours:.4f}h, Dec {dec_degrees:.4f}°")
        return self.protocol.goto_ra_dec_precise(ra_deg, dec_deg)

    @deal.pre(lambda self, azimuth, altitude: self.protocol.is_open(), message="Telescope must be connected")  # type: ignore[misc,arg-type]
    @deal.pre(lambda self, azimuth, altitude: 0 <= azimuth < 360, message="Azimuth must be 0-360 degrees")  # type: ignore[misc,arg-type]
    @deal.pre(lambda self, azimuth, altitude: -90 <= altitude <= 90, message="Altitude must be -90 to +90 degrees")  # type: ignore[misc,arg-type]
    @deal.post(lambda result: result is True, message="Goto must succeed")
    @deal.raises(NotConnectedError, InvalidCoordinateError)
    def goto_alt_az(self, azimuth: float, altitude: float) -> bool:
        """
        Slew telescope to specific Alt/Az coordinates.

        Args:
            azimuth: Azimuth in degrees (0-360, where 0=North, 90=East)
            altitude: Altitude in degrees (-90 to +90, where 0=horizon, 90=zenith)

        Returns:
            True if command successful

        Raises:
            NotConnectedError: If not connected to telescope

        Example:
            >>> # Slew to zenith
            >>> telescope.goto_alt_az(0.0, 90.0)
            True
        """
        # Convert altitude to unsigned format
        alt_deg = CoordinateConverter.altitude_to_unsigned(altitude)

        logger.info(f"Slewing to Az {azimuth:.2f}°, Alt {altitude:.2f}°")
        return self.protocol.goto_alt_az_precise(azimuth, alt_deg)

    # type: ignore[misc,arg-type]
    @deal.pre(lambda self, ra_hours, dec_degrees: self.protocol.is_open(), message="Telescope must be connected")
    @deal.pre(lambda self, ra_hours, dec_degrees: 0 <= ra_hours < 24, message="RA must be 0-24 hours")
    @deal.pre(lambda self, ra_hours, dec_degrees: -90 <= dec_degrees <= 90, message="Dec must be -90 to +90 degrees")
    @deal.post(lambda result: result is True, message="Sync must succeed")
    @deal.raises(NotConnectedError, InvalidCoordinateError)
    def sync_ra_dec(self, ra_hours: float, dec_degrees: float) -> bool:
        """
        Sync telescope position to specified RA/Dec coordinates.

        This tells the telescope its current pointing position for alignment.

        Args:
            ra_hours: Right Ascension in hours (0-24)
            dec_degrees: Declination in degrees (-90 to +90)

        Returns:
            True if command successful

        Raises:
            NotConnectedError: If not connected to telescope

        Example:
            >>> # Sync on Polaris after manually centering it
            >>> telescope.sync_ra_dec(2.5303, 89.2641)
            True
        """
        # Convert to protocol format
        ra_deg = CoordinateConverter.ra_hours_to_degrees(ra_hours)
        dec_deg = CoordinateConverter.dec_to_unsigned(dec_degrees)

        logger.info(f"Syncing to RA {ra_hours:.4f}h, Dec {dec_degrees:.4f}°")
        return self.protocol.sync_ra_dec_precise(ra_deg, dec_deg)

    def is_slewing(self) -> bool:
        """
        Check if telescope is currently slewing (moving to target).

        Returns:
            True if slewing, False if stationary

        Example:
            >>> telescope.goto_ra_dec(12.0, 45.0)
            >>> while telescope.is_slewing():
            ...     print("Moving...")
            ...     time.sleep(1)
        """
        return self.protocol.is_goto_in_progress()

    def cancel_goto(self) -> bool:
        """
        Cancel current goto/slew operation.

        Returns:
            True if command successful

        Example:
            >>> telescope.cancel_goto()
            True
        """
        logger.info("Canceling goto operation")
        return self.protocol.cancel_goto()

    def move_fixed(self, direction: str, rate: int = 9) -> bool:
        """
        Move telescope in a fixed direction at specified rate.

        Args:
            direction: 'up', 'down', 'left', 'right'
            rate: Speed rate 0-9 (0=slowest, 9=fastest)

        Returns:
            True if command successful

        Raises:
            ValueError: If direction or rate is invalid

        Example:
            >>> telescope.move_fixed('up', rate=5)
            >>> time.sleep(2)
            >>> telescope.stop_motion('alt')
        """
        # Map directions to axis and direction codes
        direction_map = {
            "up": (2, 17),  # Altitude axis, positive
            "down": (2, 18),  # Altitude axis, negative
            "left": (1, 17),  # Azimuth axis, positive
            "right": (1, 18),  # Azimuth axis, negative
        }

        if direction.lower() not in direction_map:
            raise ValueError(f"Invalid direction: {direction}. Use 'up', 'down', 'left', or 'right'") from None

        if not 0 <= rate <= 9:
            raise ValueError(f"Invalid rate: {rate}. Must be 0-9") from None

        axis, cmd_dir = direction_map[direction.lower()]
        logger.debug(f"Moving {direction} at rate {rate}")
        return self.protocol.variable_rate_motion(axis, cmd_dir, rate)

    def stop_motion(self, axis: str = "both") -> bool:
        """
        Stop telescope motion on specified axis.

        Args:
            axis: 'az' (azimuth only), 'alt' (altitude only), or 'both' (default)

        Returns:
            True if command successful on all requested axes

        Example:
            >>> telescope.stop_motion('both')
            True
        """
        success = True

        if axis in ["az", "both"]:
            # Stop azimuth axis by setting rate to 0
            success = success and self.protocol.variable_rate_motion(1, 17, 0)

        if axis in ["alt", "both"]:
            # Stop altitude axis by setting rate to 0
            success = success and self.protocol.variable_rate_motion(2, 17, 0)

        logger.debug(f"Stopped motion on {axis} axis")
        return success

    def get_tracking_mode(self) -> TrackingMode:
        """
        Get current tracking mode.

        Returns:
            TrackingMode enum value

        Example:
            >>> mode = telescope.get_tracking_mode()
            >>> print(mode.name)
            'ALT_AZ'
        """
        mode_val = self.protocol.get_tracking_mode()
        return TrackingMode(mode_val)

    def set_tracking_mode(self, mode: TrackingMode) -> bool:
        """
        Set tracking mode.

        Args:
            mode: TrackingMode enum value

        Returns:
            True if command successful

        Example:
            >>> from celestron_nexstar import TrackingMode
            >>> telescope.set_tracking_mode(TrackingMode.ALT_AZ)
            True
        """
        logger.info(f"Setting tracking mode to {mode.name}")
        return self.protocol.set_tracking_mode(mode.value)

    def get_location(self) -> GeographicLocation:
        """
        Get observer location (latitude, longitude).

        Returns:
            GeographicLocation object with latitude and longitude

        Example:
            >>> location = telescope.get_location()
            >>> print(location)
            40.7128°N, 74.0060°W
        """
        result = self.protocol.get_location()
        if result is None:
            logger.warning("Failed to get location")
            return GeographicLocation(latitude=0.0, longitude=0.0)

        latitude, longitude = result

        # Convert to signed format
        latitude = CoordinateConverter.location_to_signed(latitude)
        longitude = CoordinateConverter.location_to_signed(longitude)

        return GeographicLocation(latitude=latitude, longitude=longitude)

    # type: ignore[misc,arg-type]
    @deal.pre(lambda self, latitude, longitude: self.protocol.is_open(), message="Telescope must be connected")
    @deal.pre(lambda self, latitude, longitude: -90 <= latitude <= 90, message="Latitude must be -90 to +90 degrees")
    @deal.pre(
        lambda self, latitude, longitude: -180 <= longitude <= 180, message="Longitude must be -180 to +180 degrees"
    )
    @deal.post(lambda result: result is True, message="Location must be set")
    def set_location(self, latitude: float, longitude: float) -> bool:
        """
        Set observer location.

        Args:
            latitude: Latitude in degrees (-90 to +90, positive=North)
            longitude: Longitude in degrees (-180 to +180, positive=East)

        Returns:
            True if command successful

        Example:
            >>> # New York City
            >>> telescope.set_location(40.7128, -74.0060)
            True
        """
        # Convert to unsigned format
        lat_deg = CoordinateConverter.location_to_unsigned(latitude)
        lon_deg = CoordinateConverter.location_to_unsigned(longitude)

        logger.info(f"Setting location to {latitude:.4f}°, {longitude:.4f}°")
        return self.protocol.set_location(lat_deg, lon_deg)

    def get_time(self) -> TelescopeTime:
        """
        Get date and time from telescope.

        Returns:
            TelescopeTime object with date and time information

        Example:
            >>> time_info = telescope.get_time()
            >>> print(time_info)
            2024-10-14 12:30:00
        """
        result = self.protocol.get_time()
        if result is None:
            logger.warning("Failed to get time")
            return TelescopeTime(0, 0, 0, 0, 0, 0)

        hour, minute, second, month, day, year_offset, timezone, daylight = result
        year = year_offset + 2000  # Convert year offset to actual year

        return TelescopeTime(
            hour=hour,
            minute=minute,
            second=second,
            month=month,
            day=day,
            year=year,
            timezone=timezone,
            daylight_savings=daylight,
        )

    def set_time(
        self,
        hour: int,
        minute: int,
        second: int,
        month: int,
        day: int,
        year: int,
        timezone: int = 0,
        daylight_savings: int = 0,
    ) -> bool:
        """
        Set date and time on telescope.

        Args:
            hour: Hour (0-23)
            minute: Minute (0-59)
            second: Second (0-59)
            month: Month (1-12)
            day: Day (1-31)
            year: Year (e.g., 2024)
            timezone: Timezone offset from GMT in hours
            daylight_savings: 0 or 1 for daylight savings

        Returns:
            True if command successful

        Example:
            >>> telescope.set_time(12, 30, 0, 10, 14, 2024)
            True
        """
        year_offset = year - 2000
        logger.info(f"Setting time to {year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}")
        return self.protocol.set_time(hour, minute, second, month, day, year_offset, timezone, daylight_savings)

    def __enter__(self) -> NexStarTelescope:
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: Any | None) -> Literal[False]:
        """Context manager exit."""
        self.disconnect()
        return False

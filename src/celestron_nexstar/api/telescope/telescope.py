"""
Celestron NexStar 6SE/8SE Telescope API

Provides high-level Python interface for controlling Celestron NexStar telescopes.

This module provides a user-friendly interface that wraps the low-level NexStarProtocol
for convenient telescope control operations.

Based on NexStar 6/8SE specifications:
- Motor Resolution: 0.26 arc seconds
- Software Precision: 16-bit, 20 arc second calculations
- Slew Speeds: Nine speeds (5°/sec, 3°/sec, 1°/sec, 0.5°/sec, 32x, 16x, 8x, 4x, 2x)
- Tracking Rates: Sidereal, Solar, Lunar, and King
- Tracking Modes: Alt-Az, EQ North, EQ South
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal

import deal
import serial

from celestron_nexstar.api.catalogs.converters import CoordinateConverter
from celestron_nexstar.api.core.enums import Direction
from celestron_nexstar.api.core.exceptions import InvalidCoordinateError, NotConnectedError, TelescopeConnectionError
from celestron_nexstar.api.core.types import (
    EquatorialCoordinates,
    GeographicLocation,
    HorizontalCoordinates,
    TelescopeConfig,
    TelescopeInfo,
    TelescopeTime,
    TrackingMode,
)
from celestron_nexstar.api.telescope.protocol import NexStarProtocol


__all__ = ["NexStarTelescope"]


logger = logging.getLogger(__name__)


class NexStarTelescope:
    """
    High-level interface for controlling Celestron NexStar 6SE/8SE telescope.

    This class provides convenient methods for telescope operations by wrapping
    the low-level NexStarProtocol. It handles coordinate conversions, provides
    user-friendly methods, and manages the connection lifecycle.

    Specifications (NexStar 6/8SE):
    - Motor Resolution: 0.26 arc seconds
    - Software Precision: 16-bit, 20 arc second calculations
    - Slew Speeds: Nine speeds available via variable rate motion (0-9)
    - Tracking Modes: Alt-Az, EQ North, EQ South

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
            port=self.config.port,
            baudrate=self.config.baudrate,
            timeout=self.config.timeout,
            connection_type=self.config.connection_type,
            host=self.config.host,
            tcp_port=self.config.tcp_port,
        )

        # Keep for backward compatibility with tests
        self.serial_conn: serial.Serial | None = None

        # Store reference to auto-connect task if created
        self._connect_task: asyncio.Task[bool] | None = None

        # Auto-connect if requested (async, but we can't await in __init__)
        # Users should call await telescope.connect() explicitly if auto_connect is needed
        if self.config.auto_connect:
            # Run async connect in a new event loop
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If loop is already running, schedule the connect and store the task
                    self._connect_task = asyncio.create_task(self.connect())
                else:
                    loop.run_until_complete(self.connect())
            except RuntimeError:
                # No event loop, create one
                asyncio.run(self.connect())

    async def _ensure_connected(self) -> None:
        """
        Ensure telescope is connected, attempting to reconnect if not open.

        This is called before operations that require a connection.
        If the connection is not open, attempts to reconnect using the saved config.

        Raises:
            TelescopeConnectionError: If reconnection fails
        """
        if not self.protocol.is_open():
            logger.info("Connection not open, attempting to reconnect...")
            await self.connect()

    @deal.pre(lambda self: True, message="Telescope protocol must exist")  # type: ignore[misc,arg-type]
    @deal.raises(TelescopeConnectionError)
    async def connect(self) -> bool:
        """
        Establish connection to telescope (async, non-blocking).

        Returns:
            True if connection successful

        Raises:
            TelescopeConnectionError: If connection fails

        Example:
            >>> telescope = NexStarTelescope('/dev/ttyUSB0')
            >>> await telescope.connect()
            True
        """
        try:
            await self.protocol.open()
            # serial_conn is no longer used (async serial), but keep for backward compatibility
            self.serial_conn = None

            # Test connection with echo command
            if await self.protocol.echo():
                logger.info(f"Successfully connected to telescope on {self.config.port}")
                return True
            else:
                logger.error("Echo test failed - telescope not responding properly")
                await self.protocol.close()
                self.serial_conn = None
                raise TelescopeConnectionError("Echo test failed") from None

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            raise

    @deal.post(lambda result: result is None, message="Disconnect must complete")
    async def disconnect(self) -> None:
        """
        Close telescope connection (async, non-blocking).

        Example:
            >>> await telescope.disconnect()
        """
        await self.protocol.close()
        self.serial_conn = None
        logger.info("Disconnected from telescope")

    @deal.pre(lambda self, char: len(char) == 1, message="Char must be single character")  # type: ignore[misc,arg-type]
    @deal.post(lambda result: isinstance(result, bool), message="Must return boolean")
    async def echo_test(self, char: str = "x") -> bool:
        """
        Test connection with echo command (async, non-blocking).

        Args:
            char: Single character to echo (default 'x')

        Returns:
            True if echo successful

        Example:
            >>> await telescope.echo_test('A')
            True
        """
        return await self.protocol.echo(char)

    @deal.pre(lambda self: True, message="Telescope protocol must exist")  # type: ignore[misc,arg-type]
    @deal.post(lambda result: result is not None, message="Info must be returned")
    async def get_info(self) -> TelescopeInfo:
        """
        Get telescope hardware information (async, non-blocking).

        Returns:
            TelescopeInfo object with model and firmware version

        Example:
            >>> info = await telescope.get_info()
            >>> print(info)
            Model 6, Firmware 4.21
        """
        major, minor = await self.protocol.get_version()
        model = await self.protocol.get_model()
        return TelescopeInfo(model=model, firmware_major=major, firmware_minor=minor)

    @deal.pre(lambda self: True, message="Telescope protocol must exist")  # type: ignore[misc,arg-type]
    @deal.post(
        lambda result: isinstance(result, tuple) and len(result) == 2, message="Must return tuple of (major, minor)"
    )
    async def get_version(self) -> tuple[int, int]:
        """
        Get telescope firmware version (legacy method, async).

        Returns:
            Tuple of (major_version, minor_version)

        Example:
            >>> await telescope.get_version()
            (4, 21)
        """
        return await self.protocol.get_version()

    @deal.pre(lambda self: True, message="Telescope protocol must exist")  # type: ignore[misc,arg-type]
    async def get_model(self) -> int:
        """
        Get telescope model number (legacy method, async).

        Returns:
            Model number (6 for NexStar 6SE)

        Example:
            >>> await telescope.get_model()
            6
        """
        return await self.protocol.get_model()

    @deal.pre(lambda self: True, message="Telescope protocol must exist")  # type: ignore[misc,arg-type]
    @deal.post(lambda result: result is not None, message="Position must be returned")
    async def get_position_ra_dec(self) -> EquatorialCoordinates:
        """
        Get current Right Ascension and Declination (async, non-blocking).

        Returns:
            EquatorialCoordinates object with RA in hours and Dec in degrees

        Raises:
            NotConnectedError: If not connected to telescope

        Example:
            >>> position = await telescope.get_position_ra_dec()
            >>> print(f"RA: {position.ra_hours}h, Dec: {position.dec_degrees}°")
        """
        await self._ensure_connected()
        result = await self.protocol.get_ra_dec_precise()

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

    @deal.pre(lambda self: True, message="Telescope protocol must exist")  # type: ignore[misc,arg-type]
    @deal.post(lambda result: result is not None, message="Position must be returned")
    async def get_position_alt_az(self) -> HorizontalCoordinates:
        """
        Get current Altitude and Azimuth (async, non-blocking).

        Returns:
            HorizontalCoordinates object with azimuth and altitude in degrees

        Raises:
            NotConnectedError: If not connected to telescope

        Example:
            >>> position = await telescope.get_position_alt_az()
            >>> print(f"Az: {position.azimuth}°, Alt: {position.altitude}°")
        """
        await self._ensure_connected()
        result = await self.protocol.get_alt_az_precise()

        # Handle Result type - unwrap or return default
        return result.map(
            lambda coords: HorizontalCoordinates(
                azimuth=coords[0], altitude=CoordinateConverter.altitude_to_signed(coords[1])
            )
        ).value_or(
            # Default value on failure
            HorizontalCoordinates(azimuth=0.0, altitude=0.0)
        )

    @deal.pre(lambda self, ra_hours, dec_degrees: 0 <= ra_hours < 24, message="RA must be 0-24 hours")  # type: ignore[misc,arg-type]
    @deal.pre(lambda self, ra_hours, dec_degrees: -90 <= dec_degrees <= 90, message="Dec must be -90 to +90 degrees")  # type: ignore[misc,arg-type]
    @deal.raises(NotConnectedError, InvalidCoordinateError, TelescopeConnectionError)
    async def goto_ra_dec(self, ra_hours: float, dec_degrees: float) -> bool:
        """
        Slew telescope to specific RA/Dec coordinates (async, non-blocking).

        Args:
            ra_hours: Right Ascension in hours (0-24)
            dec_degrees: Declination in degrees (-90 to +90)

        Returns:
            True if command successful

        Raises:
            NotConnectedError: If not connected to telescope and reconnection fails
            TelescopeConnectionError: If reconnection fails

        Example:
            >>> # Slew to Polaris
            >>> await telescope.goto_ra_dec(2.5303, 89.2641)
            True
        """
        # Ensure connection before operation
        await self._ensure_connected()

        # Convert to protocol format
        ra_deg = CoordinateConverter.ra_hours_to_degrees(ra_hours)
        dec_deg = CoordinateConverter.dec_to_unsigned(dec_degrees)

        logger.info(f"Slewing to RA {ra_hours:.4f}h, Dec {dec_degrees:.4f}°")
        return await self.protocol.goto_ra_dec_precise(ra_deg, dec_deg)

    @deal.pre(lambda self, azimuth, altitude: 0 <= azimuth < 360, message="Azimuth must be 0-360 degrees")  # type: ignore[misc,arg-type]
    @deal.pre(lambda self, azimuth, altitude: -90 <= altitude <= 90, message="Altitude must be -90 to +90 degrees")  # type: ignore[misc,arg-type]
    @deal.raises(NotConnectedError, InvalidCoordinateError, TelescopeConnectionError)
    async def goto_alt_az(self, azimuth: float, altitude: float) -> bool:
        """
        Slew telescope to specific Alt/Az coordinates (async, non-blocking).

        Args:
            azimuth: Azimuth in degrees (0-360, where 0=North, 90=East)
            altitude: Altitude in degrees (-90 to +90, where 0=horizon, 90=zenith)

        Returns:
            True if command successful

        Raises:
            NotConnectedError: If not connected to telescope and reconnection fails
            TelescopeConnectionError: If reconnection fails

        Example:
            >>> # Slew to zenith
            >>> await telescope.goto_alt_az(0.0, 90.0)
            True
        """
        # Ensure connection before operation
        await self._ensure_connected()

        # Convert altitude to unsigned format
        alt_deg = CoordinateConverter.altitude_to_unsigned(altitude)

        logger.info(f"Slewing to Az {azimuth:.2f}°, Alt {altitude:.2f}°")
        return await self.protocol.goto_alt_az_precise(azimuth, alt_deg)

    @deal.pre(lambda self, ra_hours, dec_degrees: 0 <= ra_hours < 24, message="RA must be 0-24 hours")  # type: ignore[misc,arg-type]
    @deal.pre(lambda self, ra_hours, dec_degrees: -90 <= dec_degrees <= 90, message="Dec must be -90 to +90 degrees")  # type: ignore[misc,arg-type]
    @deal.raises(NotConnectedError, InvalidCoordinateError)
    async def sync_ra_dec(self, ra_hours: float, dec_degrees: float) -> bool:
        """
        Sync telescope position to specified RA/Dec coordinates (async, non-blocking).

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
            >>> await telescope.sync_ra_dec(2.5303, 89.2641)
            True
        """
        await self._ensure_connected()
        # Convert to protocol format
        ra_deg = CoordinateConverter.ra_hours_to_degrees(ra_hours)
        dec_deg = CoordinateConverter.dec_to_unsigned(dec_degrees)

        logger.info(f"Syncing to RA {ra_hours:.4f}h, Dec {dec_degrees:.4f}°")
        return await self.protocol.sync_ra_dec_precise(ra_deg, dec_deg)

    @deal.pre(lambda self: True, message="Telescope protocol must exist")  # type: ignore[misc,arg-type]
    @deal.post(lambda result: isinstance(result, bool), message="Must return boolean")
    async def is_slewing(self) -> bool:
        """
        Check if telescope is currently slewing (moving to target) (async, non-blocking).

        Returns:
            True if slewing, False if stationary

        Example:
            >>> await telescope.goto_ra_dec(12.0, 45.0)
            >>> while await telescope.is_slewing():
            ...     print("Moving...")
            ...     await asyncio.sleep(1)
        """
        await self._ensure_connected()
        return await self.protocol.is_goto_in_progress()

    @deal.pre(lambda self: True, message="Telescope protocol must exist")  # type: ignore[misc,arg-type]
    @deal.post(lambda result: isinstance(result, bool), message="Must return boolean")
    async def cancel_goto(self) -> bool:
        """
        Cancel current goto/slew operation (async, non-blocking).

        Returns:
            True if command successful

        Example:
            >>> await telescope.cancel_goto()
            True
        """
        await self._ensure_connected()
        logger.info("Canceling goto operation")
        return await self.protocol.cancel_goto()

    @deal.pre(
        lambda self, direction, rate: isinstance(direction, (Direction, str)),
        message="Direction must be Direction enum or str",
    )  # type: ignore[misc,arg-type]
    @deal.pre(lambda self, direction, rate: 0 <= rate <= 9, message="Rate must be 0-9")  # type: ignore[misc,arg-type]
    @deal.post(lambda result: isinstance(result, bool), message="Must return boolean")
    @deal.raises(ValueError)
    async def move_fixed(self, direction: Direction | str, rate: int = 4) -> bool:
        """
        Move telescope in a fixed direction at specified rate.

        Slew speeds (NexStar 6/8SE):
        - Rate 9: 5°/sec (fastest)
        - Rate 8: 3°/sec
        - Rate 7: 1°/sec
        - Rate 6: 0.5°/sec
        - Rate 5: 32x sidereal
        - Rate 4: 16x sidereal
        - Rate 3: 8x sidereal
        - Rate 2: 4x sidereal
        - Rate 1: 2x sidereal
        - Rate 0: Stop

        Args:
            direction: Direction enum value (UP, DOWN, LEFT, RIGHT)
            rate: Speed rate 0-9 (0=stop, 9=fastest at 5°/sec)

        Returns:
            True if command successful

        Raises:
            ValueError: If direction or rate is invalid

        Example:
            >>> from celestron_nexstar.api.core.enums import Direction
            >>> telescope.move_fixed(Direction.UP, rate=5)
            >>> time.sleep(2)
            >>> telescope.stop_motion('alt')
        """
        # Convert string to enum if needed (for backward compatibility)
        if isinstance(direction, str):
            try:
                direction = Direction(direction.lower())
            except ValueError:
                raise ValueError(
                    f"Invalid direction: {direction}. Use Direction enum or 'up', 'down', 'left', 'right'"
                ) from None

        # Map directions to axis and direction codes (only single-axis directions)
        direction_map = {
            Direction.UP: (2, 17),  # Altitude axis, positive
            Direction.DOWN: (2, 18),  # Altitude axis, negative
            Direction.LEFT: (1, 17),  # Azimuth axis, positive
            Direction.RIGHT: (1, 18),  # Azimuth axis, negative
        }

        if direction not in direction_map:
            raise ValueError(
                f"Invalid direction for move_fixed: {direction}. Use UP, DOWN, LEFT, or RIGHT (not diagonal)"
            ) from None

        if not 0 <= rate <= 9:
            raise ValueError(f"Invalid rate: {rate}. Must be 0-9") from None

        await self._ensure_connected()
        axis, cmd_dir = direction_map[direction]
        logger.debug(f"Moving {direction.value} at rate {rate}")
        return await self.protocol.variable_rate_motion(axis, cmd_dir, rate)

    @deal.pre(lambda self, axis: axis in ["az", "alt", "both"], message="Axis must be az/alt/both")  # type: ignore[misc,arg-type]
    @deal.post(lambda result: isinstance(result, bool), message="Must return boolean")
    async def stop_motion(self, axis: str = "both") -> bool:
        """
        Stop telescope motion on specified axis (async, non-blocking).

        Args:
            axis: 'az' (azimuth only), 'alt' (altitude only), or 'both' (default)

        Returns:
            True if command successful on all requested axes

        Example:
            >>> await telescope.stop_motion('both')
            True
        """
        await self._ensure_connected()
        success = True

        if axis in ["az", "both"]:
            # Stop azimuth axis by setting rate to 0
            success = success and await self.protocol.variable_rate_motion(1, 17, 0)

        if axis in ["alt", "both"]:
            # Stop altitude axis by setting rate to 0
            success = success and await self.protocol.variable_rate_motion(2, 17, 0)

        logger.debug(f"Stopped motion on {axis} axis")
        return success

    @deal.pre(lambda self, direction, rate: self.protocol.is_open(), message="Telescope must be connected")  # type: ignore[misc,arg-type]
    @deal.pre(
        lambda self, direction, rate: isinstance(direction, (Direction, str)),
        message="Direction must be Direction enum or str",
    )  # type: ignore[misc,arg-type]
    @deal.pre(lambda self, direction, rate: 0 <= rate <= 9, message="Rate must be 0-9")  # type: ignore[misc,arg-type]
    @deal.post(lambda result: isinstance(result, bool), message="Must return boolean")
    @deal.raises(ValueError)
    async def move_step(self, direction: Direction | str, rate: int = 4) -> bool:
        """
        Move telescope one step in the specified direction.

        This mimics a single button press on the NexStar hand controller.
        The step size depends on the rate - faster rates result in larger steps
        in the same time duration (0.2 seconds).

        Step sizes (approximate, for 0.2 second duration):
        - Rate 9: ~1.0° (5°/sec * 0.2s)
        - Rate 8: ~0.6° (3°/sec * 0.2s)
        - Rate 7: ~0.2° (1°/sec * 0.2s)
        - Rate 6: ~0.1° (0.5°/sec * 0.2s)
        - Rate 5: ~0.07° (32x sidereal ≈ 0.35°/sec * 0.2s)
        - Rate 4: ~0.03° (16x sidereal ≈ 0.17°/sec * 0.2s)
        - Rate 3: ~0.02° (8x sidereal ≈ 0.08°/sec * 0.2s)
        - Rate 2: ~0.01° (4x sidereal ≈ 0.04°/sec * 0.2s)
        - Rate 1: ~0.005° (2x sidereal ≈ 0.02°/sec * 0.2s)

        Args:
            direction: Direction enum value or string (e.g., Direction.UP, 'up', Direction.UP_RIGHT, 'up-right')
            rate: Speed rate 0-9 (0=stop, 9=fastest at 5°/sec)

        Returns:
            True if command successful

        Raises:
            ValueError: If direction or rate is invalid

        Example:
            >>> from celestron_nexstar.api.core.enums import Direction
            >>> telescope.move_step(Direction.UP, rate=5)
            True
            >>> telescope.move_step(Direction.UP_RIGHT, rate=7)
            True
        """
        # Convert string to enum if needed (for backward compatibility)
        if isinstance(direction, str):
            try:
                direction = Direction(direction.lower())
            except ValueError:
                raise ValueError(f"Invalid direction: {direction}") from None

        if rate == 0:
            # Rate 0 means stop, so just stop motion
            return await self.stop_motion("both")

        # Handle diagonal movements
        if direction in [Direction.UP_LEFT, Direction.UP_RIGHT, Direction.DOWN_LEFT, Direction.DOWN_RIGHT]:
            # For diagonal, move both axes simultaneously
            if direction == Direction.UP_LEFT:
                alt_success = await self.move_fixed(Direction.UP, rate)
                az_success = await self.move_fixed(Direction.LEFT, rate)
            elif direction == Direction.UP_RIGHT:
                alt_success = await self.move_fixed(Direction.UP, rate)
                az_success = await self.move_fixed(Direction.RIGHT, rate)
            elif direction == Direction.DOWN_LEFT:
                alt_success = await self.move_fixed(Direction.DOWN, rate)
                az_success = await self.move_fixed(Direction.LEFT, rate)
            else:  # DOWN_RIGHT
                alt_success = await self.move_fixed(Direction.DOWN, rate)
                az_success = await self.move_fixed(Direction.RIGHT, rate)

            if not (alt_success and az_success):
                return False

            # Move for step duration (0.2 seconds)
            await asyncio.sleep(0.2)

            # Stop both axes
            return await self.stop_motion("both")

        # Handle single-axis movements
        success = await self.move_fixed(direction, rate)
        if not success:
            return False

        # Move for step duration (0.2 seconds)
        await asyncio.sleep(0.2)

        # Determine axis from direction and stop
        axis = "alt" if direction in [Direction.UP, Direction.DOWN] else "az"
        return await self.stop_motion(axis)

    @deal.pre(lambda self, direction, rate, duration: self.protocol.is_open(), message="Telescope must be connected")  # type: ignore[misc,arg-type]
    @deal.pre(
        lambda self, direction, rate, duration: isinstance(direction, (Direction, str)),
        message="Direction must be Direction enum or str",
    )  # type: ignore[misc,arg-type]
    @deal.pre(lambda self, direction, rate, duration: 0 <= rate <= 9, message="Rate must be 0-9")  # type: ignore[misc,arg-type]
    @deal.pre(lambda self, direction, rate, duration: duration > 0, message="Duration must be positive")  # type: ignore[misc,arg-type]
    @deal.post(lambda result: isinstance(result, bool), message="Must return boolean")
    @deal.raises(ValueError)
    async def move_for_time(self, direction: Direction | str, duration: float, rate: int = 4) -> bool:
        """
        Move telescope in specified direction for a set duration.

        Starts movement at the specified rate, waits for the duration,
        then automatically stops.

        Args:
            direction: Direction enum value or string (e.g., Direction.UP, 'up', Direction.UP_RIGHT, 'up-right')
            duration: Duration in seconds (must be positive)
            rate: Speed rate 0-9 (0=stop, 9=fastest at 5°/sec)

        Returns:
            True if command successful

        Raises:
            ValueError: If direction, rate, or duration is invalid

        Example:
            >>> from celestron_nexstar.api.core.enums import Direction
            >>> telescope.move_for_time(Direction.UP, duration=2.0, rate=5)
            True
            >>> telescope.move_for_time(Direction.UP_RIGHT, duration=1.5, rate=7)
            True
        """
        # Convert string to enum if needed (for backward compatibility)
        if isinstance(direction, str):
            try:
                direction = Direction(direction.lower())
            except ValueError:
                raise ValueError(f"Invalid direction: {direction}") from None

        if rate == 0:
            # Rate 0 means stop
            return await self.stop_motion("both")

        if duration <= 0:
            raise ValueError(f"Duration must be positive, got {duration}") from None

        # Handle diagonal movements
        if direction in [Direction.UP_LEFT, Direction.UP_RIGHT, Direction.DOWN_LEFT, Direction.DOWN_RIGHT]:
            # For diagonal, move both axes simultaneously
            if direction == Direction.UP_LEFT:
                alt_success = await self.move_fixed(Direction.UP, rate)
                az_success = await self.move_fixed(Direction.LEFT, rate)
            elif direction == Direction.UP_RIGHT:
                alt_success = await self.move_fixed(Direction.UP, rate)
                az_success = await self.move_fixed(Direction.RIGHT, rate)
            elif direction == Direction.DOWN_LEFT:
                alt_success = await self.move_fixed(Direction.DOWN, rate)
                az_success = await self.move_fixed(Direction.LEFT, rate)
            else:  # DOWN_RIGHT
                alt_success = await self.move_fixed(Direction.DOWN, rate)
                az_success = await self.move_fixed(Direction.RIGHT, rate)

            if not (alt_success and az_success):
                return False

            # Move for specified duration
            await asyncio.sleep(duration)

            # Stop both axes
            return await self.stop_motion("both")

        # Handle single-axis movements
        success = await self.move_fixed(direction, rate)
        if not success:
            return False

        # Move for specified duration
        await asyncio.sleep(duration)

        # Determine axis from direction and stop
        axis = "alt" if direction in [Direction.UP, Direction.DOWN] else "az"
        return await self.stop_motion(axis)

    @deal.pre(lambda self: True, message="Telescope protocol must exist")  # type: ignore[misc,arg-type]
    @deal.post(lambda result: result is not None, message="Tracking mode must be returned")
    async def get_tracking_mode(self) -> TrackingMode:
        """
        Get current tracking mode (async, non-blocking).

        Returns:
            TrackingMode enum value

        Example:
            >>> mode = await telescope.get_tracking_mode()
            >>> print(mode.name)
            'ALT_AZ'
        """
        await self._ensure_connected()
        mode_val = await self.protocol.get_tracking_mode()
        return TrackingMode(mode_val)

    @deal.pre(lambda self, mode: True, message="Telescope protocol must exist")  # type: ignore[misc,arg-type]
    async def set_tracking_mode(self, mode: TrackingMode) -> bool:
        """
        Set tracking mode (async, non-blocking).

        Args:
            mode: TrackingMode enum value

        Returns:
            True if command successful

        Example:
            >>> from celestron_nexstar import TrackingMode
            >>> await telescope.set_tracking_mode(TrackingMode.ALT_AZ)
            True
        """
        await self._ensure_connected()
        logger.info(f"Setting tracking mode to {mode.name}")
        return await self.protocol.set_tracking_mode(mode.value)

    @deal.pre(lambda self: True, message="Telescope protocol must exist")  # type: ignore[misc,arg-type]
    @deal.post(lambda result: result is not None, message="Location must be returned")
    async def get_location(self) -> GeographicLocation:
        """
        Get observer location (latitude, longitude) (async, non-blocking).

        Returns:
            GeographicLocation object with latitude and longitude

        Example:
            >>> location = await telescope.get_location()
            >>> print(location)
            40.7128°N, 74.0060°W
        """
        await self._ensure_connected()
        result = await self.protocol.get_location()
        if result is None:
            logger.warning("Failed to get location")
            return GeographicLocation(latitude=0.0, longitude=0.0)

        latitude, longitude = result

        # Convert to signed format
        latitude = CoordinateConverter.location_to_signed(latitude)
        longitude = CoordinateConverter.location_to_signed(longitude)

        return GeographicLocation(latitude=latitude, longitude=longitude)

    @deal.pre(lambda self, latitude, longitude: -90 <= latitude <= 90, message="Latitude must be -90 to +90 degrees")  # type: ignore[misc,arg-type]
    @deal.pre(
        lambda self, latitude, longitude: -180 <= longitude <= 180, message="Longitude must be -180 to +180 degrees"
    )  # type: ignore[misc,arg-type]
    async def set_location(self, latitude: float, longitude: float) -> bool:
        """
        Set observer location (async, non-blocking).

        Args:
            latitude: Latitude in degrees (-90 to +90, positive=North)
            longitude: Longitude in degrees (-180 to +180, positive=East)

        Returns:
            True if command successful

        Example:
            >>> # New York City
            >>> await telescope.set_location(40.7128, -74.0060)
            True
        """
        await self._ensure_connected()
        # Convert to unsigned format
        lat_deg = CoordinateConverter.location_to_unsigned(latitude)
        lon_deg = CoordinateConverter.location_to_unsigned(longitude)

        logger.info(f"Setting location to {latitude:.4f}°, {longitude:.4f}°")
        return await self.protocol.set_location(lat_deg, lon_deg)

    @deal.pre(lambda self: True, message="Telescope protocol must exist")  # type: ignore[misc,arg-type]
    @deal.post(lambda result: result is not None, message="Time must be returned")
    async def get_time(self) -> TelescopeTime:
        """
        Get date and time from telescope (async, non-blocking).

        Returns:
            TelescopeTime object with date and time information

        Example:
            >>> time_info = await telescope.get_time()
            >>> print(time_info)
            2024-10-14 12:30:00
        """
        await self._ensure_connected()
        result = await self.protocol.get_time()
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

    @deal.pre(
        lambda self, hour, minute, second, month, day, year, timezone, daylight_savings: 0 <= hour <= 23,
        message="Hour must be 0-23",
    )  # type: ignore[misc,arg-type]
    @deal.pre(
        lambda self, hour, minute, second, month, day, year, timezone, daylight_savings: 0 <= minute <= 59,
        message="Minute must be 0-59",
    )  # type: ignore[misc,arg-type]
    @deal.pre(
        lambda self, hour, minute, second, month, day, year, timezone, daylight_savings: 0 <= second <= 59,
        message="Second must be 0-59",
    )  # type: ignore[misc,arg-type]
    @deal.pre(
        lambda self, hour, minute, second, month, day, year, timezone, daylight_savings: 1 <= month <= 12,
        message="Month must be 1-12",
    )  # type: ignore[misc,arg-type]
    @deal.pre(
        lambda self, hour, minute, second, month, day, year, timezone, daylight_savings: 1 <= day <= 31,
        message="Day must be 1-31",
    )  # type: ignore[misc,arg-type]
    async def set_time(
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
        Set date and time on telescope (async, non-blocking).

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
            >>> await telescope.set_time(12, 30, 0, 10, 14, 2024)
            True
        """
        await self._ensure_connected()
        year_offset = year - 2000
        logger.info(f"Setting time to {year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}")
        return await self.protocol.set_time(hour, minute, second, month, day, year_offset, timezone, daylight_savings)

    async def __aenter__(self) -> NexStarTelescope:
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: Any | None) -> Literal[False]:
        """Async context manager exit."""
        await self.disconnect()
        return False

    def __enter__(self) -> NexStarTelescope:
        """Sync context manager entry (deprecated - use async context manager)."""
        import warnings

        warnings.warn(
            "Using sync context manager with async telescope. Use 'async with' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        # Try to run async connect in sync context
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                raise RuntimeError("Cannot use sync context manager in async context. Use 'async with' instead.")
            loop.run_until_complete(self.connect())
        except RuntimeError:
            asyncio.run(self.connect())
        return self

    def __exit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: Any | None) -> Literal[False]:
        """Sync context manager exit (deprecated - use async context manager)."""
        # Try to run async disconnect in sync context
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                raise RuntimeError("Cannot use sync context manager in async context. Use 'async with' instead.")
            loop.run_until_complete(self.disconnect())
        except RuntimeError:
            asyncio.run(self.disconnect())
        return False

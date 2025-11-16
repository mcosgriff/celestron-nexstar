"""
NexStar Communication Protocol Implementation

This module implements the low-level NexStar protocol for communicating
with Celestron telescopes. It handles both serial and TCP/IP communication,
command formatting, response parsing, and coordinate encoding/decoding.

Protocol Specification (based on NexStar 6/8SE manual):
- Serial: Baud Rate 9600, 8 data bits, no parity, 1 stop bit
- TCP/IP: Default port 4030 (SkyPortal WiFi Adapter)
- Terminator: '#' character
- Coordinate Format: 32-bit hexadecimal (0x00000000 to 0xFFFFFFFF = 0° to 360°)
- Motor Resolution: 0.26 arc seconds
- Software Precision: 16-bit, 20 arc second calculations
- Slew Speeds: Nine speeds available (5°/sec, 3°/sec, 1°/sec, 0.5°/sec, 32x, 16x, 8x, 4x, 2x)
- Tracking Rates: Sidereal, Solar, Lunar, and King
- Tracking Modes: Alt-Az, EQ North, EQ South
"""

from __future__ import annotations

import contextlib
import logging
import socket
import time

import deal
import serial
from returns.result import Failure, Result, Success

from celestron_nexstar.api.core.exceptions import NotConnectedError, TelescopeConnectionError, TelescopeTimeoutError


__all__ = ["NexStarProtocol"]


logger = logging.getLogger(__name__)


class NexStarProtocol:
    """
    Low-level implementation of the NexStar communication protocol.

    This class handles:
    - Serial port and TCP/IP socket management
    - Command transmission and response reception
    - Coordinate encoding/decoding (degrees <-> hex)
    - Protocol-level error handling

    Supports both serial and TCP/IP connections (e.g., via Celestron SkyPortal WiFi Adapter).
    """

    # Protocol constants
    TERMINATOR = "#"
    DEFAULT_BAUDRATE = 9600
    DEFAULT_TIMEOUT = 2.0
    DEFAULT_TCP_PORT = 4030
    DEFAULT_TCP_HOST = "192.168.4.1"

    def __init__(
        self,
        port: str | None = None,
        baudrate: int = DEFAULT_BAUDRATE,
        timeout: float = DEFAULT_TIMEOUT,
        connection_type: str = "serial",
        host: str = DEFAULT_TCP_HOST,
        tcp_port: int = DEFAULT_TCP_PORT,
    ):
        """
        Initialize protocol handler.

        Args:
            port: Serial port path (required for serial connections)
            baudrate: Communication speed (default 9600, only used for serial)
            timeout: Connection timeout in seconds
            connection_type: 'serial' or 'tcp' (default: 'serial')
            host: TCP/IP host address (default: '192.168.4.1' for SkyPortal WiFi Adapter)
            tcp_port: TCP/IP port number (default: 4030 for SkyPortal WiFi Adapter)
        """
        self.connection_type = connection_type
        self.port = port or "/dev/ttyUSB0"
        self.baudrate = baudrate
        self.timeout = timeout
        self.host = host
        self.tcp_port = tcp_port
        self.serial_conn: serial.Serial | None = None
        self.tcp_socket: socket.socket | None = None

    def open(self) -> bool:
        """
        Open connection to telescope (serial or TCP/IP).

        Returns:
            True if connection successful

        Raises:
            TelescopeConnectionError: If connection cannot be opened
        """
        if self.connection_type == "tcp":
            return self._open_tcp()
        else:
            return self._open_serial()

    def _open_serial(self) -> bool:
        """Open serial connection to telescope."""
        try:
            logger.debug(f"Opening serial connection to {self.port} at {self.baudrate} baud")
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
            )
            time.sleep(0.5)  # Allow connection to stabilize
            logger.info(f"Serial connection opened successfully on {self.port}")
            return True
        except serial.SerialException as e:
            logger.error(f"Failed to open serial port {self.port}: {e}")
            raise TelescopeConnectionError(f"Failed to open port {self.port}: {e}") from e

    def _open_tcp(self) -> bool:
        """Open TCP/IP connection to telescope (e.g., via SkyPortal WiFi Adapter)."""
        try:
            logger.debug(f"Opening TCP/IP connection to {self.host}:{self.tcp_port}")
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.settimeout(self.timeout)
            self.tcp_socket.connect((self.host, self.tcp_port))
            time.sleep(0.2)  # Allow connection to stabilize
            logger.info(f"TCP/IP connection opened successfully to {self.host}:{self.tcp_port}")
            return True
        except OSError as e:
            logger.error(f"Failed to open TCP/IP connection to {self.host}:{self.tcp_port}: {e}")
            if self.tcp_socket:
                with contextlib.suppress(Exception):
                    self.tcp_socket.close()
                self.tcp_socket = None
            raise TelescopeConnectionError(f"Failed to connect to {self.host}:{self.tcp_port}: {e}") from e

    def close(self) -> None:
        """Close connection (serial or TCP/IP)."""
        if self.connection_type == "tcp":
            if self.tcp_socket:
                try:
                    self.tcp_socket.close()
                    logger.info(f"TCP/IP connection closed to {self.host}:{self.tcp_port}")
                except Exception as e:
                    logger.warning(f"Error closing TCP/IP socket: {e}")
                self.tcp_socket = None
        else:
            if self.serial_conn and self.serial_conn.is_open:
                self.serial_conn.close()
                logger.info(f"Serial connection closed on {self.port}")

    def is_open(self) -> bool:
        """Check if connection is open."""
        if self.connection_type == "tcp":
            return self.tcp_socket is not None
        else:
            return self.serial_conn is not None and self.serial_conn.is_open

    def send_command(self, command: str) -> str:
        """
        Send a command and receive response.

        All NexStar commands are ASCII strings terminated with '#'.
        Responses are also terminated with '#'.

        Args:
            command: Command string to send (without terminator)

        Returns:
            Response string (without terminator)

        Raises:
            NotConnectedError: If not connected and reconnection fails
            TelescopeConnectionError: If reconnection fails
            TelescopeTimeoutError: If no response within timeout
        """
        if not self.is_open():
            logger.info("Connection not open, attempting to reconnect...")
            try:
                if not self.open():
                    logger.error("Failed to reconnect")
                    raise NotConnectedError("Connection not open and reconnection failed") from None
                logger.info("Reconnected successfully")
            except TelescopeConnectionError as e:
                logger.error(f"Reconnection failed: {e}")
                raise NotConnectedError("Connection not open and reconnection failed") from e

        if self.connection_type == "tcp":
            return self._send_command_tcp(command)
        else:
            return self._send_command_serial(command)

    def _send_command_serial(self, command: str) -> str:
        """Send command over serial connection."""
        # Type guard to ensure serial_conn is not None
        assert self.serial_conn is not None, "Serial connection should be open at this point"

        # Clear buffers to ensure clean communication
        self.serial_conn.reset_input_buffer()
        self.serial_conn.reset_output_buffer()

        # Send command with terminator
        full_command = command + self.TERMINATOR
        logger.debug(f"Sending command: {command!r}")
        self.serial_conn.write(full_command.encode("ascii"))

        # Read response until terminator
        response = b""
        start_time = time.time()

        while True:
            if time.time() - start_time > self.timeout:
                logger.error(f"Timeout waiting for response to command: {command!r}")
                raise TelescopeTimeoutError(f"Timeout waiting for response to: {command}") from None

            if self.serial_conn.in_waiting > 0:
                byte = self.serial_conn.read(1)
                response += byte
                if byte == self.TERMINATOR.encode("ascii"):
                    break

        # Decode and remove terminator
        response_str = response.decode("ascii").rstrip(self.TERMINATOR)
        logger.debug(f"Received response: {response_str!r}")
        return response_str

    def _send_command_tcp(self, command: str) -> str:
        """Send command over TCP/IP connection."""
        # Type guard to ensure tcp_socket is not None
        assert self.tcp_socket is not None, "TCP/IP connection should be open at this point"

        # Send command with terminator
        full_command = command + self.TERMINATOR
        logger.debug(f"Sending command: {command!r}")
        try:
            self.tcp_socket.sendall(full_command.encode("ascii"))
        except OSError as e:
            logger.error(f"Error sending command over TCP/IP: {e}")
            raise TelescopeConnectionError(f"Failed to send command: {e}") from e

        # Read response until terminator
        response = b""
        start_time = time.time()

        while True:
            if time.time() - start_time > self.timeout:
                logger.error(f"Timeout waiting for response to command: {command!r}")
                raise TelescopeTimeoutError(f"Timeout waiting for response to: {command}") from None

            try:
                # Set socket to non-blocking for timeout handling
                self.tcp_socket.settimeout(0.1)
                byte = self.tcp_socket.recv(1)
                if not byte:
                    # Connection closed
                    raise TelescopeConnectionError("Connection closed by remote host") from None
                response += byte
                if byte == self.TERMINATOR.encode("ascii"):
                    break
            except TimeoutError:
                # Continue waiting if timeout hasn't been exceeded
                continue
            except OSError as e:
                logger.error(f"Error receiving response over TCP/IP: {e}")
                raise TelescopeConnectionError(f"Failed to receive response: {e}") from e
            finally:
                # Restore original timeout
                self.tcp_socket.settimeout(self.timeout)

        # Decode and remove terminator
        response_str = response.decode("ascii").rstrip(self.TERMINATOR)
        logger.debug(f"Received response: {response_str!r}")
        return response_str

    # ========== Coordinate Encoding/Decoding ==========

    @staticmethod
    def degrees_to_hex(degrees: float) -> str:
        """
        Convert degrees to NexStar 32-bit hexadecimal format.

        The NexStar protocol uses a 32-bit unsigned integer to represent
        0° to 360°, where:
            0x00000000 = 0°
            0x80000000 = 180°
            0xFFFFFFFF = 360° (wraps to 0°)

        Args:
            degrees: Angle in degrees (0-360)

        Returns:
            8-character hexadecimal string (uppercase)
        """
        # Normalize to 0-360 range
        degrees = degrees % 360.0

        # Convert to 32-bit hex value
        hex_value = int((degrees / 360.0) * 0x100000000)

        return f"{hex_value:08X}"

    @staticmethod
    def hex_to_degrees(hex_str: str) -> float:
        """
        Convert NexStar 32-bit hexadecimal format to degrees.

        Args:
            hex_str: 8-character hexadecimal string

        Returns:
            Angle in degrees (0-360)
        """
        hex_value = int(hex_str, 16)
        return (hex_value / 0x100000000) * 360.0

    @staticmethod
    def encode_coordinate_pair(value1: float, value2: float) -> str:
        """
        Encode a pair of coordinates (RA/Dec or Az/Alt) to NexStar format.

        Args:
            value1: First coordinate in degrees (0-360)
            value2: Second coordinate in degrees (0-360)

        Returns:
            Formatted string: "XXXXXXXX,YYYYYYYY" (16 chars + comma)
        """
        hex1 = NexStarProtocol.degrees_to_hex(value1)
        hex2 = NexStarProtocol.degrees_to_hex(value2)
        return f"{hex1},{hex2}"

    @staticmethod
    def decode_coordinate_pair(response: str) -> Result[tuple[float, float], str]:
        """
        Decode a coordinate pair response from NexStar format.

        Args:
            response: Response string in format "XXXXXXXX,YYYYYYYY"

        Returns:
            Success with tuple of (value1_degrees, value2_degrees) or Failure with error message
        """
        if len(response) != 17 or response[8] != ",":
            return Failure(
                f"Invalid coordinate response format: expected 17 chars with comma at position 8, got {len(response)} chars"
            )

        try:
            value1 = NexStarProtocol.hex_to_degrees(response[:8])
            value2 = NexStarProtocol.hex_to_degrees(response[9:17])
            return Success((value1, value2))
        except ValueError as e:
            return Failure(f"Failed to decode coordinate values: {e}")

    # ========== Common Command Patterns ==========

    def get_single_byte(self, command: str) -> int | None:
        """
        Send command and receive single-byte response.

        Args:
            command: Command to send

        Returns:
            Byte value or None if invalid
        """
        response = self.send_command(command)
        if len(response) == 1:
            return ord(response[0])
        return None

    def get_two_bytes(self, command: str) -> tuple[int, int] | None:
        """
        Send command and receive two-byte response.

        Args:
            command: Command to send

        Returns:
            Tuple of (byte1, byte2) or None if invalid
        """
        response = self.send_command(command)
        if len(response) == 2:
            return ord(response[0]), ord(response[1])
        return None

    def send_empty_command(self, command: str) -> bool:
        """
        Send command expecting empty response (success indicator).

        Args:
            command: Command to send

        Returns:
            True if response was empty (success)
        """
        response = self.send_command(command)
        return response == ""

    # ========== Specific Protocol Commands ==========

    @deal.pre(lambda self, char: len(char) == 1)  # type: ignore[misc,arg-type]
    def echo(self, char: str = "x") -> bool:
        """
        Test connection with echo command.
        Command: K<char>#
        Response: <char>#

        Args:
            char: Single character to echo

        Returns:
            True if echo successful
        """
        try:
            response = self.send_command(f"K{char}")
            return response == char
        except (NotConnectedError, TelescopeTimeoutError, TelescopeConnectionError):
            return False
        except Exception:
            # Handle serial.SerialException for serial connections
            if self.connection_type == "serial":
                return False
            raise

    def get_version(self) -> tuple[int, int]:
        """
        Get firmware version.
        Command: V#
        Response: <major><minor>#

        Returns:
            Tuple of (major_version, minor_version)
        """
        result = self.get_two_bytes("V")
        return result if result else (0, 0)

    def get_model(self) -> int:
        """
        Get telescope model number.
        Command: m#
        Response: <model>#

        Returns:
            Model number (6 for NexStar 6SE)
        """
        result = self.get_single_byte("m")
        return result if result is not None else 0

    def get_ra_dec_precise(self) -> Result[tuple[float, float], str]:
        """
        Get precise RA/Dec position.
        Command: E#
        Response: RRRRRRR,DDDDDDDDD#

        Returns:
            Success with tuple of (RA_degrees, Dec_degrees) or Failure with error message
        """
        response = self.send_command("E")
        return self.decode_coordinate_pair(response)

    def get_alt_az_precise(self) -> Result[tuple[float, float], str]:
        """
        Get precise Alt/Az position.
        Command: Z#
        Response: AAAAAAAA,EEEEEEEE#

        Returns:
            Success with tuple of (Az_degrees, Alt_degrees) or Failure with error message
        """
        response = self.send_command("Z")
        return self.decode_coordinate_pair(response)

    @deal.pre(lambda self, ra_degrees, dec_degrees: 0.0 <= ra_degrees <= 360.0 and 0.0 <= dec_degrees <= 360.0)  # type: ignore[misc,arg-type]
    def goto_ra_dec_precise(self, ra_degrees: float, dec_degrees: float) -> bool:
        """
        Slew to RA/Dec coordinates.
        Command: R<RA>,<DEC>#
        Response: # (empty)

        Args:
            ra_degrees: Right Ascension in degrees (0-360)
            dec_degrees: Declination in degrees (0-360, use 360+deg for negative)

        Returns:
            True if command successful
        """
        coords = self.encode_coordinate_pair(ra_degrees, dec_degrees)
        return self.send_empty_command(f"R{coords}")

    @deal.pre(lambda self, az_degrees, alt_degrees: 0.0 <= az_degrees <= 360.0 and 0.0 <= alt_degrees <= 360.0)  # type: ignore[misc,arg-type]
    def goto_alt_az_precise(self, az_degrees: float, alt_degrees: float) -> bool:
        """
        Slew to Alt/Az coordinates.
        Command: B<AZ>,<ALT>#
        Response: # (empty)

        Args:
            az_degrees: Azimuth in degrees (0-360)
            alt_degrees: Altitude in degrees (0-360, use 360+deg for negative)

        Returns:
            True if command successful
        """
        coords = self.encode_coordinate_pair(az_degrees, alt_degrees)
        return self.send_empty_command(f"B{coords}")

    @deal.pre(lambda self, ra_degrees, dec_degrees: 0.0 <= ra_degrees <= 360.0 and 0.0 <= dec_degrees <= 360.0)  # type: ignore[misc,arg-type]
    def sync_ra_dec_precise(self, ra_degrees: float, dec_degrees: float) -> bool:
        """
        Sync to RA/Dec coordinates (for alignment).
        Command: S<RA>,<DEC>#
        Response: # (empty)

        Args:
            ra_degrees: Right Ascension in degrees (0-360)
            dec_degrees: Declination in degrees (0-360, use 360+deg for negative)

        Returns:
            True if command successful
        """
        coords = self.encode_coordinate_pair(ra_degrees, dec_degrees)
        return self.send_empty_command(f"S{coords}")

    def is_goto_in_progress(self) -> bool:
        """
        Check if goto is in progress.
        Command: L#
        Response: 0# or 1#

        Returns:
            True if slewing
        """
        response = self.send_command("L")
        return response == "1"

    def cancel_goto(self) -> bool:
        """
        Cancel current goto.
        Command: M#
        Response: # (empty)

        Returns:
            True if successful
        """
        return self.send_empty_command("M")

    @deal.pre(lambda self, axis, direction, rate: axis in [1, 2] and direction in [17, 18] and 0 <= rate <= 9)  # type: ignore[misc,arg-type]
    def variable_rate_motion(self, axis: int, direction: int, rate: int) -> bool:
        """
        Initiate variable rate motion.
        Command: P<axis><direction><rate><0><0><0>#

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
            axis: 1=azimuth, 2=altitude
            direction: 17=positive, 18=negative
            rate: 0-9 (0=stop, 9=fastest at 5°/sec)

        Returns:
            True if successful
        """
        command = f"P{chr(axis)}{chr(direction)}{chr(rate)}{chr(0)}{chr(0)}{chr(0)}"
        return self.send_empty_command(command)

    def get_tracking_mode(self) -> int:
        """
        Get tracking mode.
        Command: t#
        Response: <mode>#

        Returns:
            Tracking mode (0=off, 1=alt-az, 2=eq-north, 3=eq-south)
        """
        result = self.get_single_byte("t")
        return result if result is not None else 0

    @deal.pre(lambda self, mode: 0 <= mode <= 3)  # type: ignore[misc,arg-type]
    def set_tracking_mode(self, mode: int) -> bool:
        """
        Set tracking mode.
        Command: T<mode>#
        Response: # (empty)

        Args:
            mode: 0=off, 1=alt-az, 2=eq-north, 3=eq-south

        Returns:
            True if successful
        """
        return self.send_empty_command(f"T{chr(mode)}")

    def get_location(self) -> tuple[float, float] | None:
        """
        Get observer location.
        Command: w#
        Response: <lat><lon># (16 hex chars)

        Returns:
            Tuple of (latitude_degrees, longitude_degrees) or None
        """
        response = self.send_command("w")
        if len(response) == 16:
            try:
                lat = self.hex_to_degrees(response[:8])
                lon = self.hex_to_degrees(response[8:16])
                return lat, lon
            except ValueError:
                return None
        return None

    @deal.pre(
        lambda self, latitude_degrees, longitude_degrees: 0.0 <= latitude_degrees <= 360.0
        and 0.0 <= longitude_degrees <= 360.0
    )  # type: ignore[misc,arg-type]
    def set_location(self, latitude_degrees: float, longitude_degrees: float) -> bool:
        """
        Set observer location.
        Command: W<lat>,<lon>#
        Response: # (empty)

        Args:
            latitude_degrees: Latitude in degrees (0-360, use 360+deg for negative)
            longitude_degrees: Longitude in degrees (0-360, use 360+deg for negative)

        Returns:
            True if successful
        """
        coords = self.encode_coordinate_pair(latitude_degrees, longitude_degrees)
        return self.send_empty_command(f"W{coords}")

    def get_time(self) -> tuple[int, int, int, int, int, int, int, int] | None:
        """
        Get date and time.
        Command: h#
        Response: <H><M><S><month><day><year><tz><dst># (8 bytes)

        Returns:
            Tuple of (hour, minute, second, month, day, year_offset, timezone, dst)
            or None if invalid
        """
        response = self.send_command("h")
        if len(response) == 8:
            values = tuple(ord(c) for c in response)
            # Explicitly cast to the expected 8-tuple type
            return (values[0], values[1], values[2], values[3], values[4], values[5], values[6], values[7])
        return None

    @deal.pre(
        lambda self, hour, minute, second, month, day, year_offset, timezone, dst: 0 <= hour <= 23
        and 0 <= minute <= 59
        and 0 <= second <= 59
        and 1 <= month <= 12
        and 1 <= day <= 31
        and year_offset >= 0
        and dst in [0, 1]
    )  # type: ignore[misc,arg-type]
    def set_time(
        self, hour: int, minute: int, second: int, month: int, day: int, year_offset: int, timezone: int, dst: int
    ) -> bool:
        """
        Set date and time.
        Command: H<H><M><S><month><day><year><tz><dst>#
        Response: # (empty)

        Args:
            hour: Hour (0-23)
            minute: Minute (0-59)
            second: Second (0-59)
            month: Month (1-12)
            day: Day (1-31)
            year_offset: Years since 2000
            timezone: Timezone offset
            dst: Daylight savings (0 or 1)

        Returns:
            True if successful
        """
        command = (
            f"H{chr(hour)}{chr(minute)}{chr(second)}{chr(month)}{chr(day)}{chr(year_offset)}{chr(timezone)}{chr(dst)}"
        )
        return self.send_empty_command(command)

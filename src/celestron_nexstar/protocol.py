"""
NexStar Communication Protocol Implementation

This module implements the low-level NexStar serial protocol for communicating
with Celestron telescopes. It handles serial communication, command formatting,
response parsing, and coordinate encoding/decoding.

Protocol Specification:
- Baud Rate: 9600
- Data Bits: 8
- Parity: None
- Stop Bits: 1
- Terminator: '#' character
- Coordinate Format: 32-bit hexadecimal (0x00000000 to 0xFFFFFFFF = 0° to 360°)
"""

import logging
import serial
import time
from typing import Optional, Tuple

import deal

from .exceptions import (
    TelescopeConnectionError,
    TelescopeTimeoutError,
    NotConnectedError,
    CommandError
)

logger = logging.getLogger(__name__)


class NexStarProtocol:
    """
    Low-level implementation of the NexStar serial communication protocol.

    This class handles:
    - Serial port management
    - Command transmission and response reception
    - Coordinate encoding/decoding (degrees <-> hex)
    - Protocol-level error handling
    """

    # Protocol constants
    TERMINATOR = '#'
    DEFAULT_BAUDRATE = 9600
    DEFAULT_TIMEOUT = 2.0

    def __init__(self, port: str, baudrate: int = DEFAULT_BAUDRATE, timeout: float = DEFAULT_TIMEOUT):
        """
        Initialize protocol handler.

        Args:
            port: Serial port path
            baudrate: Communication speed (default 9600)
            timeout: Serial timeout in seconds
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_conn: Optional[serial.Serial] = None

    def open(self) -> bool:
        """
        Open serial connection to telescope.

        Returns:
            True if connection successful

        Raises:
            TelescopeConnectionError: If serial port cannot be opened
        """
        try:
            logger.debug(f"Opening serial connection to {self.port} at {self.baudrate} baud")
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE
            )
            time.sleep(0.5)  # Allow connection to stabilize
            logger.info(f"Serial connection opened successfully on {self.port}")
            return True
        except serial.SerialException as e:
            logger.error(f"Failed to open serial port {self.port}: {e}")
            raise TelescopeConnectionError(f"Failed to open port {self.port}: {e}") from e

    def close(self):
        """Close serial connection."""
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            logger.info(f"Serial connection closed on {self.port}")

    def is_open(self) -> bool:
        """Check if connection is open."""
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
            NotConnectedError: If not connected
            TelescopeTimeoutError: If no response within timeout
        """
        if not self.is_open():
            logger.error("Attempted to send command while not connected")
            raise NotConnectedError("Serial port not open")

        # Clear buffers to ensure clean communication
        self.serial_conn.reset_input_buffer()
        self.serial_conn.reset_output_buffer()

        # Send command with terminator
        full_command = command + self.TERMINATOR
        logger.debug(f"Sending command: {repr(command)}")
        self.serial_conn.write(full_command.encode('ascii'))

        # Read response until terminator
        response = b''
        start_time = time.time()

        while True:
            if time.time() - start_time > self.timeout:
                logger.error(f"Timeout waiting for response to command: {repr(command)}")
                raise TelescopeTimeoutError(f"Timeout waiting for response to: {command}")

            if self.serial_conn.in_waiting > 0:
                byte = self.serial_conn.read(1)
                response += byte
                if byte == self.TERMINATOR.encode('ascii'):
                    break

        # Decode and remove terminator
        response_str = response.decode('ascii').rstrip(self.TERMINATOR)
        logger.debug(f"Received response: {repr(response_str)}")
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
    def decode_coordinate_pair(response: str) -> Optional[Tuple[float, float]]:
        """
        Decode a coordinate pair response from NexStar format.

        Args:
            response: Response string in format "XXXXXXXX,YYYYYYYY"

        Returns:
            Tuple of (value1_degrees, value2_degrees) or None if invalid
        """
        if len(response) != 17 or response[8] != ',':
            return None

        try:
            value1 = NexStarProtocol.hex_to_degrees(response[:8])
            value2 = NexStarProtocol.hex_to_degrees(response[9:17])
            return (value1, value2)
        except ValueError:
            return None

    # ========== Common Command Patterns ==========

    def get_single_byte(self, command: str) -> Optional[int]:
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

    def get_two_bytes(self, command: str) -> Optional[Tuple[int, int]]:
        """
        Send command and receive two-byte response.

        Args:
            command: Command to send

        Returns:
            Tuple of (byte1, byte2) or None if invalid
        """
        response = self.send_command(command)
        if len(response) == 2:
            return (ord(response[0]), ord(response[1]))
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
        return response == ''

    # ========== Specific Protocol Commands ==========

    @deal.pre(lambda char: len(char) == 1)
    def echo(self, char: str = 'x') -> bool:
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
            response = self.send_command(f'K{char}')
            return response == char
        except Exception:
            return False

    def get_version(self) -> Tuple[int, int]:
        """
        Get firmware version.
        Command: V#
        Response: <major><minor>#

        Returns:
            Tuple of (major_version, minor_version)
        """
        result = self.get_two_bytes('V')
        return result if result else (0, 0)

    def get_model(self) -> int:
        """
        Get telescope model number.
        Command: m#
        Response: <model>#

        Returns:
            Model number (6 for NexStar 6SE)
        """
        result = self.get_single_byte('m')
        return result if result is not None else 0

    def get_ra_dec_precise(self) -> Optional[Tuple[float, float]]:
        """
        Get precise RA/Dec position.
        Command: E#
        Response: RRRRRRR,DDDDDDDDD#

        Returns:
            Tuple of (RA_degrees, Dec_degrees) or None if invalid
        """
        response = self.send_command('E')
        return self.decode_coordinate_pair(response)

    def get_alt_az_precise(self) -> Optional[Tuple[float, float]]:
        """
        Get precise Alt/Az position.
        Command: Z#
        Response: AAAAAAAA,EEEEEEEE#

        Returns:
            Tuple of (Az_degrees, Alt_degrees) or None if invalid
        """
        response = self.send_command('Z')
        return self.decode_coordinate_pair(response)

    @deal.pre(lambda ra_degrees, dec_degrees: 0.0 <= ra_degrees <= 360.0 and 0.0 <= dec_degrees <= 360.0)
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
        return self.send_empty_command(f'R{coords}')

    @deal.pre(lambda az_degrees, alt_degrees: 0.0 <= az_degrees <= 360.0 and 0.0 <= alt_degrees <= 360.0)
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
        return self.send_empty_command(f'B{coords}')

    @deal.pre(lambda ra_degrees, dec_degrees: 0.0 <= ra_degrees <= 360.0 and 0.0 <= dec_degrees <= 360.0)
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
        return self.send_empty_command(f'S{coords}')

    def is_goto_in_progress(self) -> bool:
        """
        Check if goto is in progress.
        Command: L#
        Response: 0# or 1#

        Returns:
            True if slewing
        """
        response = self.send_command('L')
        return response == '1'

    def cancel_goto(self) -> bool:
        """
        Cancel current goto.
        Command: M#
        Response: # (empty)

        Returns:
            True if successful
        """
        return self.send_empty_command('M')

    @deal.pre(lambda axis, direction, rate: axis in [1, 2] and direction in [17, 18] and 0 <= rate <= 9)
    def variable_rate_motion(self, axis: int, direction: int, rate: int) -> bool:
        """
        Initiate variable rate motion.
        Command: P<axis><direction><rate><0><0><0>#

        Args:
            axis: 1=azimuth, 2=altitude
            direction: 17=positive, 18=negative
            rate: 0-9 (0=stop, 9=fastest)

        Returns:
            True if successful
        """
        command = f'P{chr(axis)}{chr(direction)}{chr(rate)}{chr(0)}{chr(0)}{chr(0)}'
        return self.send_empty_command(command)

    def get_tracking_mode(self) -> int:
        """
        Get tracking mode.
        Command: t#
        Response: <mode>#

        Returns:
            Tracking mode (0=off, 1=alt-az, 2=eq-north, 3=eq-south)
        """
        result = self.get_single_byte('t')
        return result if result is not None else 0

    @deal.pre(lambda mode: 0 <= mode <= 3)
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
        return self.send_empty_command(f'T{chr(mode)}')

    def get_location(self) -> Optional[Tuple[float, float]]:
        """
        Get observer location.
        Command: w#
        Response: <lat><lon># (16 hex chars)

        Returns:
            Tuple of (latitude_degrees, longitude_degrees) or None
        """
        response = self.send_command('w')
        if len(response) == 16:
            try:
                lat = self.hex_to_degrees(response[:8])
                lon = self.hex_to_degrees(response[8:16])
                return (lat, lon)
            except ValueError:
                return None
        return None

    @deal.pre(lambda latitude_degrees, longitude_degrees: 0.0 <= latitude_degrees <= 360.0 and 0.0 <= longitude_degrees <= 360.0)
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
        return self.send_empty_command(f'W{coords}')

    def get_time(self) -> Optional[Tuple[int, int, int, int, int, int, int, int]]:
        """
        Get date and time.
        Command: h#
        Response: <H><M><S><month><day><year><tz><dst># (8 bytes)

        Returns:
            Tuple of (hour, minute, second, month, day, year_offset, timezone, dst)
            or None if invalid
        """
        response = self.send_command('h')
        if len(response) == 8:
            return tuple(ord(c) for c in response)
        return None

    @deal.pre(lambda hour, minute, second, month, day, year_offset, timezone, dst: 0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59 and 1 <= month <= 12 and 1 <= day <= 31 and year_offset >= 0 and dst in [0, 1])
    def set_time(self, hour: int, minute: int, second: int, month: int,
                 day: int, year_offset: int, timezone: int, dst: int) -> bool:
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
        command = (f'H{chr(hour)}{chr(minute)}{chr(second)}{chr(month)}'
                   f'{chr(day)}{chr(year_offset)}{chr(timezone)}{chr(dst)}')
        return self.send_empty_command(command)


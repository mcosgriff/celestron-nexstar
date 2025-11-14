"""
Unit tests for NexStar Protocol Layer
Provides comprehensive test coverage for the protocol module.
"""

import builtins
import contextlib
import unittest
from unittest.mock import MagicMock, patch

import serial
from returns.result import Failure

from celestron_nexstar.api.exceptions import (
    NotConnectedError,
    TelescopeConnectionError,
    TelescopeTimeoutError,
)
from celestron_nexstar.api.protocol import NexStarProtocol


class TestNexStarProtocol(unittest.TestCase):
    """Test suite for NexStarProtocol class"""

    def setUp(self):
        """Set up test fixtures before each test"""
        self.protocol = NexStarProtocol(port="/dev/ttyUSB0", baudrate=9600, timeout=2.0)

    def tearDown(self):
        """Clean up after each test"""
        if self.protocol.serial_conn:
            with contextlib.suppress(builtins.BaseException):
                self.protocol.close()

    # ========== Connection Tests ==========

    def test_init(self):
        """Test protocol initialization"""
        protocol = NexStarProtocol("/dev/ttyUSB1", baudrate=19200, timeout=3.0)
        self.assertEqual(protocol.port, "/dev/ttyUSB1")
        self.assertEqual(protocol.baudrate, 19200)
        self.assertEqual(protocol.timeout, 3.0)
        self.assertIsNone(protocol.serial_conn)

    @patch("celestron_nexstar.api.protocol.serial.Serial")
    @patch("celestron_nexstar.api.protocol.time.sleep")
    def test_open_success(self, mock_sleep, mock_serial):
        """Test successful serial port opening"""
        mock_conn = MagicMock()
        mock_serial.return_value = mock_conn

        result = self.protocol.open()

        self.assertTrue(result)
        mock_serial.assert_called_once_with(
            port="/dev/ttyUSB0",
            baudrate=9600,
            timeout=2.0,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
        )
        mock_sleep.assert_called_once_with(0.5)

    @patch("celestron_nexstar.api.protocol.serial.Serial")
    def test_open_failure(self, mock_serial):
        """Test serial port opening failure"""
        mock_serial.side_effect = serial.SerialException("Port not found")

        with self.assertRaises(TelescopeConnectionError) as context:
            self.protocol.open()

        self.assertIn("Port not found", str(context.exception))

    @patch("celestron_nexstar.api.protocol.serial.Serial")
    def test_close(self, mock_serial):
        """Test closing serial connection"""
        mock_conn = MagicMock()
        mock_conn.is_open = True
        mock_serial.return_value = mock_conn

        self.protocol.open()
        self.protocol.close()

        mock_conn.close.assert_called_once()

    def test_close_when_not_open(self):
        """Test closing when connection is not open"""
        # Should not raise an exception
        self.protocol.close()

    def test_is_open_true(self):
        """Test is_open when connection is active"""
        mock_conn = MagicMock()
        mock_conn.is_open = True
        self.protocol.serial_conn = mock_conn

        self.assertTrue(self.protocol.is_open())

    def test_is_open_false(self):
        """Test is_open when not connected"""
        self.assertFalse(self.protocol.is_open())

    # ========== Command Sending Tests ==========

    def test_send_command_not_connected(self):
        """Test sending command when not connected"""
        with self.assertRaises(NotConnectedError):
            self.protocol.send_command("V")

    @patch("celestron_nexstar.api.protocol.time.time")
    def test_send_command_success(self, mock_time):
        """Test successful command send and receive"""
        mock_conn = MagicMock()
        mock_conn.is_open = True
        mock_conn.in_waiting = 3
        mock_conn.read.side_effect = [b"4", b"\x15", b"#"]
        self.protocol.serial_conn = mock_conn

        # Mock time to avoid timeout
        mock_time.return_value = 0

        response = self.protocol.send_command("V")

        self.assertEqual(response, "4\x15")
        mock_conn.reset_input_buffer.assert_called()
        mock_conn.reset_output_buffer.assert_called()
        mock_conn.write.assert_called_once_with(b"V#")

    @patch("celestron_nexstar.api.protocol.time.time")
    def test_send_command_timeout(self, mock_time):
        """Test command timeout"""
        mock_conn = MagicMock()
        mock_conn.is_open = True
        mock_conn.in_waiting = 0
        self.protocol.serial_conn = mock_conn

        # Mock time to simulate timeout
        mock_time.side_effect = [0, 0.5, 1.0, 1.5, 2.0, 2.5]

        with self.assertRaises(TelescopeTimeoutError):
            self.protocol.send_command("V")

    # ========== Coordinate Encoding/Decoding Tests ==========

    def test_degrees_to_hex_zero(self):
        """Test converting 0 degrees to hex"""
        result = NexStarProtocol.degrees_to_hex(0.0)
        self.assertEqual(result, "00000000")

    def test_degrees_to_hex_180(self):
        """Test converting 180 degrees to hex"""
        result = NexStarProtocol.degrees_to_hex(180.0)
        self.assertEqual(result, "80000000")

    def test_degrees_to_hex_360(self):
        """Test converting 360 degrees to hex (wraps to 0)"""
        result = NexStarProtocol.degrees_to_hex(360.0)
        self.assertEqual(result, "00000000")

    def test_degrees_to_hex_90(self):
        """Test converting 90 degrees to hex"""
        result = NexStarProtocol.degrees_to_hex(90.0)
        self.assertEqual(result, "40000000")

    def test_hex_to_degrees_zero(self):
        """Test converting hex to 0 degrees"""
        result = NexStarProtocol.hex_to_degrees("00000000")
        self.assertAlmostEqual(result, 0.0, places=2)

    def test_hex_to_degrees_180(self):
        """Test converting hex to 180 degrees"""
        result = NexStarProtocol.hex_to_degrees("80000000")
        self.assertAlmostEqual(result, 180.0, places=2)

    def test_hex_to_degrees_90(self):
        """Test converting hex to 90 degrees"""
        result = NexStarProtocol.hex_to_degrees("40000000")
        self.assertAlmostEqual(result, 90.0, places=2)

    def test_encode_coordinate_pair(self):
        """Test encoding coordinate pair"""
        result = NexStarProtocol.encode_coordinate_pair(180.0, 90.0)
        self.assertEqual(result, "80000000,40000000")

    def test_decode_coordinate_pair_valid(self):
        """Test decoding valid coordinate pair"""
        result = NexStarProtocol.decode_coordinate_pair("80000000,40000000")
        self.assertIsNotNone(result)
        coords = result.unwrap()
        self.assertAlmostEqual(coords[0], 180.0, places=2)
        self.assertAlmostEqual(coords[1], 90.0, places=2)

    def test_decode_coordinate_pair_invalid_length(self):
        """Test decoding invalid coordinate pair (wrong length)"""
        result = NexStarProtocol.decode_coordinate_pair("12345")
        self.assertIsInstance(result, Failure)

    def test_decode_coordinate_pair_invalid_format(self):
        """Test decoding invalid coordinate pair (missing comma)"""
        result = NexStarProtocol.decode_coordinate_pair("1234567812345678")
        self.assertIsInstance(result, Failure)

    def test_decode_coordinate_pair_invalid_hex(self):
        """Test decoding coordinate pair with invalid hex"""
        result = NexStarProtocol.decode_coordinate_pair("XXXXXXXX,YYYYYYYY")
        self.assertIsInstance(result, Failure)

    # ========== Common Command Pattern Tests ==========

    @patch.object(NexStarProtocol, "send_command")
    def test_get_single_byte(self, mock_send):
        """Test get_single_byte helper"""
        mock_send.return_value = "A"
        result = self.protocol.get_single_byte("test")
        self.assertEqual(result, ord("A"))

    @patch.object(NexStarProtocol, "send_command")
    def test_get_single_byte_invalid(self, mock_send):
        """Test get_single_byte with invalid response"""
        mock_send.return_value = "AB"
        result = self.protocol.get_single_byte("test")
        self.assertIsNone(result)

    @patch.object(NexStarProtocol, "send_command")
    def test_get_two_bytes(self, mock_send):
        """Test get_two_bytes helper"""
        mock_send.return_value = "AB"
        result = self.protocol.get_two_bytes("test")
        self.assertEqual(result, (ord("A"), ord("B")))

    @patch.object(NexStarProtocol, "send_command")
    def test_get_two_bytes_invalid(self, mock_send):
        """Test get_two_bytes with invalid response"""
        mock_send.return_value = "A"
        result = self.protocol.get_two_bytes("test")
        self.assertIsNone(result)

    @patch.object(NexStarProtocol, "send_command")
    def test_send_empty_command_success(self, mock_send):
        """Test send_empty_command with empty response"""
        mock_send.return_value = ""
        result = self.protocol.send_empty_command("M")
        self.assertTrue(result)

    @patch.object(NexStarProtocol, "send_command")
    def test_send_empty_command_failure(self, mock_send):
        """Test send_empty_command with non-empty response"""
        mock_send.return_value = "ERROR"
        result = self.protocol.send_empty_command("M")
        self.assertFalse(result)

    # ========== Specific Protocol Commands Tests ==========

    @patch.object(NexStarProtocol, "send_command")
    def test_echo_success(self, mock_send):
        """Test successful echo command"""
        mock_send.return_value = "x"
        result = self.protocol.echo("x")
        self.assertTrue(result)
        mock_send.assert_called_once_with("Kx")

    @patch.object(NexStarProtocol, "send_command")
    def test_echo_failure(self, mock_send):
        """Test failed echo command"""
        mock_send.return_value = "y"
        result = self.protocol.echo("x")
        self.assertFalse(result)

    @patch.object(NexStarProtocol, "send_command")
    def test_echo_exception(self, mock_send):
        """Test echo command with exception"""
        mock_send.side_effect = NotConnectedError("Connection error")
        result = self.protocol.echo("x")
        self.assertFalse(result)

    @patch.object(NexStarProtocol, "get_two_bytes")
    def test_get_version(self, mock_get_two):
        """Test get firmware version"""
        mock_get_two.return_value = (4, 21)
        result = self.protocol.get_version()
        self.assertEqual(result, (4, 21))
        mock_get_two.assert_called_once_with("V")

    @patch.object(NexStarProtocol, "get_two_bytes")
    def test_get_version_invalid(self, mock_get_two):
        """Test get version with invalid response"""
        mock_get_two.return_value = None
        result = self.protocol.get_version()
        self.assertEqual(result, (0, 0))

    @patch.object(NexStarProtocol, "get_single_byte")
    def test_get_model(self, mock_get_single):
        """Test get telescope model"""
        mock_get_single.return_value = 6
        result = self.protocol.get_model()
        self.assertEqual(result, 6)
        mock_get_single.assert_called_once_with("m")

    @patch.object(NexStarProtocol, "get_single_byte")
    def test_get_model_invalid(self, mock_get_single):
        """Test get model with invalid response"""
        mock_get_single.return_value = None
        result = self.protocol.get_model()
        self.assertEqual(result, 0)

    @patch.object(NexStarProtocol, "send_command")
    @patch.object(NexStarProtocol, "decode_coordinate_pair")
    def test_get_ra_dec_precise(self, mock_decode, mock_send):
        """Test get RA/Dec precise command"""
        mock_send.return_value = "12345678,87654321"
        mock_decode.return_value = (180.0, 45.0)

        result = self.protocol.get_ra_dec_precise()

        self.assertEqual(result, (180.0, 45.0))
        mock_send.assert_called_once_with("E")

    @patch.object(NexStarProtocol, "send_command")
    @patch.object(NexStarProtocol, "decode_coordinate_pair")
    def test_get_alt_az_precise(self, mock_decode, mock_send):
        """Test get Alt/Az precise command"""
        mock_send.return_value = "12345678,87654321"
        mock_decode.return_value = (90.0, 45.0)

        result = self.protocol.get_alt_az_precise()

        self.assertEqual(result, (90.0, 45.0))
        mock_send.assert_called_once_with("Z")

    @patch.object(NexStarProtocol, "send_empty_command")
    @patch.object(NexStarProtocol, "encode_coordinate_pair")
    def test_goto_ra_dec_precise(self, mock_encode, mock_send_empty):
        """Test goto RA/Dec precise command"""
        mock_encode.return_value = "12345678,87654321"
        mock_send_empty.return_value = True

        result = self.protocol.goto_ra_dec_precise(180.0, 45.0)

        self.assertTrue(result)
        mock_encode.assert_called_once_with(180.0, 45.0)
        mock_send_empty.assert_called_once_with("R12345678,87654321")

    @patch.object(NexStarProtocol, "send_empty_command")
    @patch.object(NexStarProtocol, "encode_coordinate_pair")
    def test_goto_alt_az_precise(self, mock_encode, mock_send_empty):
        """Test goto Alt/Az precise command"""
        mock_encode.return_value = "12345678,87654321"
        mock_send_empty.return_value = True

        result = self.protocol.goto_alt_az_precise(90.0, 45.0)

        self.assertTrue(result)
        mock_encode.assert_called_once_with(90.0, 45.0)
        mock_send_empty.assert_called_once_with("B12345678,87654321")

    @patch.object(NexStarProtocol, "send_empty_command")
    @patch.object(NexStarProtocol, "encode_coordinate_pair")
    def test_sync_ra_dec_precise(self, mock_encode, mock_send_empty):
        """Test sync RA/Dec precise command"""
        mock_encode.return_value = "12345678,87654321"
        mock_send_empty.return_value = True

        result = self.protocol.sync_ra_dec_precise(180.0, 45.0)

        self.assertTrue(result)
        mock_encode.assert_called_once_with(180.0, 45.0)
        mock_send_empty.assert_called_once_with("S12345678,87654321")

    @patch.object(NexStarProtocol, "send_command")
    def test_is_goto_in_progress_true(self, mock_send):
        """Test is_goto_in_progress returns True"""
        mock_send.return_value = "1"
        result = self.protocol.is_goto_in_progress()
        self.assertTrue(result)

    @patch.object(NexStarProtocol, "send_command")
    def test_is_goto_in_progress_false(self, mock_send):
        """Test is_goto_in_progress returns False"""
        mock_send.return_value = "0"
        result = self.protocol.is_goto_in_progress()
        self.assertFalse(result)

    @patch.object(NexStarProtocol, "send_empty_command")
    def test_cancel_goto(self, mock_send_empty):
        """Test cancel goto command"""
        mock_send_empty.return_value = True
        result = self.protocol.cancel_goto()
        self.assertTrue(result)
        mock_send_empty.assert_called_once_with("M")

    @patch.object(NexStarProtocol, "send_empty_command")
    def test_variable_rate_motion(self, mock_send_empty):
        """Test variable rate motion command"""
        mock_send_empty.return_value = True

        result = self.protocol.variable_rate_motion(1, 17, 5)

        self.assertTrue(result)
        # Verify command format: P + axis + direction + rate + three zeros
        expected_cmd = f"P{chr(1)}{chr(17)}{chr(5)}{chr(0)}{chr(0)}{chr(0)}"
        mock_send_empty.assert_called_once_with(expected_cmd)

    @patch.object(NexStarProtocol, "get_single_byte")
    def test_get_tracking_mode(self, mock_get_single):
        """Test get tracking mode"""
        mock_get_single.return_value = 1
        result = self.protocol.get_tracking_mode()
        self.assertEqual(result, 1)
        mock_get_single.assert_called_once_with("t")

    @patch.object(NexStarProtocol, "get_single_byte")
    def test_get_tracking_mode_invalid(self, mock_get_single):
        """Test get tracking mode with invalid response"""
        mock_get_single.return_value = None
        result = self.protocol.get_tracking_mode()
        self.assertEqual(result, 0)

    @patch.object(NexStarProtocol, "send_empty_command")
    def test_set_tracking_mode(self, mock_send_empty):
        """Test set tracking mode"""
        mock_send_empty.return_value = True
        result = self.protocol.set_tracking_mode(1)
        self.assertTrue(result)
        mock_send_empty.assert_called_once_with(f"T{chr(1)}")

    @patch.object(NexStarProtocol, "send_command")
    def test_get_location(self, mock_send):
        """Test get observer location"""
        # 16 hex chars representing lat/lon
        mock_send.return_value = "123456787654321A"

        result = self.protocol.get_location()

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)

    @patch.object(NexStarProtocol, "send_command")
    def test_get_location_invalid_length(self, mock_send):
        """Test get location with invalid response length"""
        mock_send.return_value = "12345"
        result = self.protocol.get_location()
        self.assertIsNone(result)

    @patch.object(NexStarProtocol, "send_command")
    def test_get_location_invalid_hex(self, mock_send):
        """Test get location with invalid hex values"""
        mock_send.return_value = "XXXXXXXXXXXXXXXX"
        result = self.protocol.get_location()
        self.assertIsNone(result)

    @patch.object(NexStarProtocol, "send_empty_command")
    @patch.object(NexStarProtocol, "encode_coordinate_pair")
    def test_set_location(self, mock_encode, mock_send_empty):
        """Test set observer location"""
        mock_encode.return_value = "12345678,87654321"
        mock_send_empty.return_value = True

        result = self.protocol.set_location(40.7, 286.0)

        self.assertTrue(result)
        mock_encode.assert_called_once_with(40.7, 286.0)
        mock_send_empty.assert_called_once_with("W12345678,87654321")

    @patch.object(NexStarProtocol, "send_command")
    def test_get_time(self, mock_send):
        """Test get date and time"""
        # 8 bytes: hour, minute, second, month, day, year_offset, timezone, dst
        mock_send.return_value = "\x0c\x1e\x00\x0a\x0e\x18\x00\x00"

        result = self.protocol.get_time()

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 8)
        self.assertEqual(result[0], 12)  # hour
        self.assertEqual(result[1], 30)  # minute

    @patch.object(NexStarProtocol, "send_command")
    def test_get_time_invalid(self, mock_send):
        """Test get time with invalid response"""
        mock_send.return_value = "ABC"
        result = self.protocol.get_time()
        self.assertIsNone(result)

    @patch.object(NexStarProtocol, "send_empty_command")
    def test_set_time(self, mock_send_empty):
        """Test set date and time"""
        mock_send_empty.return_value = True

        result = self.protocol.set_time(12, 30, 0, 10, 14, 24, 0, 0)

        self.assertTrue(result)
        expected_cmd = f"H{chr(12)}{chr(30)}{chr(0)}{chr(10)}{chr(14)}{chr(24)}{chr(0)}{chr(0)}"
        mock_send_empty.assert_called_once_with(expected_cmd)


if __name__ == "__main__":
    unittest.main()

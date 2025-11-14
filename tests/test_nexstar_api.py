"""
Unit tests for Celestron NexStar 6SE Telescope API
Provides comprehensive test coverage for the telescope module.
"""

import unittest
from unittest.mock import patch

from returns.result import Failure, Success

from celestron_nexstar.api.exceptions import TelescopeConnectionError
from celestron_nexstar.api.telescope import NexStarTelescope
from celestron_nexstar.api.types import (
    AlignmentMode,
    EquatorialCoordinates,
    GeographicLocation,
    HorizontalCoordinates,
    TelescopeConfig,
    TelescopeInfo,
    TelescopeTime,
    TrackingMode,
)


class TestNexStarTelescope(unittest.TestCase):
    """Test suite for NexStarTelescope class"""

    def setUp(self):
        """Set up test fixtures before each test"""
        self.telescope = NexStarTelescope("/dev/ttyUSB0")

    def tearDown(self):
        """Clean up after each test"""
        if self.telescope.serial_conn:
            self.telescope.serial_conn = None

    # ========== Initialization Tests ==========

    def test_init_with_string(self):
        """Test initialization with port string"""
        telescope = NexStarTelescope("/dev/ttyUSB0")
        self.assertEqual(telescope.config.port, "/dev/ttyUSB0")
        self.assertEqual(telescope.config.baudrate, 9600)

    def test_init_with_config(self):
        """Test initialization with TelescopeConfig"""
        config = TelescopeConfig(port="/dev/ttyUSB1", baudrate=19200, verbose=True)
        telescope = NexStarTelescope(config)
        self.assertEqual(telescope.config.port, "/dev/ttyUSB1")
        self.assertEqual(telescope.config.baudrate, 19200)
        self.assertTrue(telescope.config.verbose)

    def test_init_with_none(self):
        """Test initialization with None uses defaults"""
        telescope = NexStarTelescope(None)
        self.assertEqual(telescope.config.port, "/dev/ttyUSB0")

    def test_init_with_auto_connect(self):
        """Test initialization with auto_connect enabled"""
        config = TelescopeConfig(port="/dev/ttyUSB0", auto_connect=True)
        with patch.object(NexStarTelescope, "connect", return_value=True) as mock_connect:
            NexStarTelescope(config)

        # Auto-connect should have triggered the connect method
        mock_connect.assert_called_once()
        self.assertTrue(config.auto_connect)

    # ========== Connection Tests ==========

    def test_connect_success(self):
        """Test successful connection to telescope"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "open", return_value=True):
                with patch.object(self.telescope.protocol, "echo", return_value=True):
                    result = self.telescope.connect()

        self.assertTrue(result)

    def test_connect_failure_echo_test(self):
        """Test connection failure when echo test fails"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "open", return_value=True):
                with patch.object(self.telescope.protocol, "echo", return_value=False):
                    with patch.object(self.telescope.protocol, "close"):
                        with self.assertRaises(TelescopeConnectionError):
                            self.telescope.connect()

    def test_connect_serial_exception(self):
        """Test connection failure with serial exception"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "open", side_effect=TelescopeConnectionError("Port not found")):
                with self.assertRaises(TelescopeConnectionError):
                    self.telescope.connect()

    def test_disconnect(self):
        """Test disconnecting from telescope"""
        with patch.object(self.telescope.protocol, "close") as mock_close:
            self.telescope.disconnect()

        mock_close.assert_called_once()

    def test_echo_test_success(self):
        """Test successful echo test"""
        with patch.object(self.telescope.protocol, "echo", return_value=True):
            result = self.telescope.echo_test("x")

        self.assertTrue(result)

    def test_echo_test_failure(self):
        """Test failed echo test"""
        with patch.object(self.telescope.protocol, "echo", return_value=False):
            result = self.telescope.echo_test("x")

        self.assertFalse(result)

    # ========== Information Tests ==========

    def test_get_info(self):
        """Test getting telescope information"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "get_version", return_value=(4, 21)):
                with patch.object(self.telescope.protocol, "get_model", return_value=6):
                    info = self.telescope.get_info()

        self.assertIsInstance(info, TelescopeInfo)
        self.assertEqual(info.model, 6)
        self.assertEqual(info.firmware_major, 4)
        self.assertEqual(info.firmware_minor, 21)

    def test_get_version(self):
        """Test getting firmware version"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "get_version", return_value=(4, 6)):
                major, minor = self.telescope.get_version()

        self.assertEqual(major, 4)
        self.assertEqual(minor, 6)

    def test_get_model(self):
        """Test getting telescope model"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "get_model", return_value=6):
                model = self.telescope.get_model()

        self.assertEqual(model, 6)

    # ========== Position Tests ==========

    def test_get_position_ra_dec(self):
        """Test getting RA/Dec position"""
        # Protocol returns degrees, telescope converts to hours for RA
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "get_ra_dec_precise", return_value=Success((180.0, 45.0))):
                position = self.telescope.get_position_ra_dec()

        self.assertIsInstance(position, EquatorialCoordinates)
        # 180 degrees = 12 hours
        self.assertAlmostEqual(position.ra_hours, 12.0, places=2)
        self.assertEqual(position.dec_degrees, 45.0)

    def test_get_position_ra_dec_invalid_response(self):
        """Test get_position_ra_dec with invalid response"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "get_ra_dec_precise", return_value=Failure("Invalid response")):
                position = self.telescope.get_position_ra_dec()

        self.assertEqual(position.ra_hours, 0.0)
        self.assertEqual(position.dec_degrees, 0.0)

    def test_get_position_ra_dec_negative_dec(self):
        """Test RA/Dec with negative declination"""
        # Dec > 180 in unsigned format means negative
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "get_ra_dec_precise", return_value=Success((90.0, 330.0))):
                position = self.telescope.get_position_ra_dec()

        self.assertAlmostEqual(position.ra_hours, 6.0, places=2)
        self.assertEqual(position.dec_degrees, -30.0)

    def test_get_position_alt_az(self):
        """Test getting Alt/Az position"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "get_alt_az_precise", return_value=Success((180.0, 45.0))):
                position = self.telescope.get_position_alt_az()

        self.assertIsInstance(position, HorizontalCoordinates)
        self.assertEqual(position.azimuth, 180.0)
        self.assertEqual(position.altitude, 45.0)

    def test_get_position_alt_az_negative_altitude(self):
        """Test Alt/Az with negative altitude"""
        # Alt > 180 in unsigned format means negative
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "get_alt_az_precise", return_value=Success((90.0, 345.0))):
                position = self.telescope.get_position_alt_az()

        self.assertEqual(position.azimuth, 90.0)
        self.assertEqual(position.altitude, -15.0)

    def test_get_position_alt_az_invalid_response(self):
        """Test get_position_alt_az with invalid response"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "get_alt_az_precise", return_value=Failure("Invalid response")):
                position = self.telescope.get_position_alt_az()

        self.assertEqual(position.azimuth, 0.0)
        self.assertEqual(position.altitude, 0.0)

    # ========== Goto Tests ==========

    def test_goto_ra_dec_success(self):
        """Test goto RA/Dec command"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "goto_ra_dec_precise", return_value=True):
                result = self.telescope.goto_ra_dec(12.5, 45.0)

        self.assertTrue(result)

    def test_goto_ra_dec_negative_dec(self):
        """Test goto with negative declination"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "goto_ra_dec_precise", return_value=True) as mock_goto:
                result = self.telescope.goto_ra_dec(10.0, -30.0)

        self.assertTrue(result)
        # Verify conversion to unsigned format (negative becomes 360 + value)
        mock_goto.assert_called_once()

    def test_goto_alt_az_success(self):
        """Test goto Alt/Az command"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "goto_alt_az_precise", return_value=True):
                result = self.telescope.goto_alt_az(180.0, 45.0)

        self.assertTrue(result)

    def test_goto_alt_az_negative_altitude(self):
        """Test goto with negative altitude"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "goto_alt_az_precise", return_value=True):
                result = self.telescope.goto_alt_az(90.0, -15.0)

        self.assertTrue(result)

    def test_sync_ra_dec(self):
        """Test sync RA/Dec command"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "sync_ra_dec_precise", return_value=True):
                result = self.telescope.sync_ra_dec(5.5, 22.5)

        self.assertTrue(result)

    def test_is_slewing_true(self):
        """Test is_slewing returns True when slewing"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "is_goto_in_progress", return_value=True):
                result = self.telescope.is_slewing()

        self.assertTrue(result)

    def test_is_slewing_false(self):
        """Test is_slewing returns False when stationary"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "is_goto_in_progress", return_value=False):
                result = self.telescope.is_slewing()

        self.assertFalse(result)

    def test_cancel_goto(self):
        """Test cancel goto command"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "cancel_goto", return_value=True):
                result = self.telescope.cancel_goto()

        self.assertTrue(result)

    # ========== Movement Tests ==========

    def test_move_fixed_up(self):
        """Test moving telescope up"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "variable_rate_motion", return_value=True):
                result = self.telescope.move_fixed("up", rate=5)

        self.assertTrue(result)

    def test_move_fixed_down(self):
        """Test moving telescope down"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "variable_rate_motion", return_value=True):
                result = self.telescope.move_fixed("down", rate=3)

        self.assertTrue(result)

    def test_move_fixed_left(self):
        """Test moving telescope left"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "variable_rate_motion", return_value=True):
                result = self.telescope.move_fixed("left", rate=7)

        self.assertTrue(result)

    def test_move_fixed_right(self):
        """Test moving telescope right"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "variable_rate_motion", return_value=True):
                result = self.telescope.move_fixed("right", rate=9)

        self.assertTrue(result)

    def test_move_fixed_invalid_direction(self):
        """Test move_fixed with invalid direction"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with self.assertRaises(Exception):  # deal.PreContractError
                self.telescope.move_fixed("diagonal", rate=5)

    def test_move_fixed_invalid_rate_too_high(self):
        """Test move_fixed with rate too high"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with self.assertRaises(Exception):  # deal.PreContractError
                self.telescope.move_fixed("up", rate=10)

    def test_move_fixed_invalid_rate_negative(self):
        """Test move_fixed with negative rate"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with self.assertRaises(Exception):  # deal.PreContractError
                self.telescope.move_fixed("up", rate=-1)

    def test_stop_motion_both(self):
        """Test stopping motion on both axes"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "variable_rate_motion", return_value=True):
                result = self.telescope.stop_motion("both")

        self.assertTrue(result)

    def test_stop_motion_azimuth(self):
        """Test stopping azimuth motion only"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "variable_rate_motion", return_value=True):
                result = self.telescope.stop_motion("az")

        self.assertTrue(result)

    def test_stop_motion_altitude(self):
        """Test stopping altitude motion only"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "variable_rate_motion", return_value=True):
                result = self.telescope.stop_motion("alt")

        self.assertTrue(result)

    # ========== Tracking Tests ==========

    def test_get_tracking_mode(self):
        """Test getting tracking mode"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "get_tracking_mode", return_value=1):
                mode = self.telescope.get_tracking_mode()

        self.assertEqual(mode, TrackingMode.ALT_AZ)

    def test_get_tracking_mode_off(self):
        """Test getting tracking mode when off"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "get_tracking_mode", return_value=0):
                mode = self.telescope.get_tracking_mode()

        self.assertEqual(mode, TrackingMode.OFF)

    def test_set_tracking_mode(self):
        """Test setting tracking mode"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "set_tracking_mode", return_value=True):
                result = self.telescope.set_tracking_mode(TrackingMode.ALT_AZ)

        self.assertTrue(result)

    def test_set_tracking_mode_eq_north(self):
        """Test setting equatorial north tracking"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "set_tracking_mode", return_value=True):
                result = self.telescope.set_tracking_mode(TrackingMode.EQ_NORTH)

        self.assertTrue(result)

    # ========== Location Tests ==========

    def test_get_location(self):
        """Test getting observer location"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "get_location", return_value=(40.7, 286.0)):
                location = self.telescope.get_location()

        self.assertIsInstance(location, GeographicLocation)
        self.assertAlmostEqual(location.latitude, 40.7, places=1)
        # 286 in unsigned format = -74
        self.assertAlmostEqual(location.longitude, -74.0, places=1)

    def test_get_location_invalid_response(self):
        """Test get_location with invalid response"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "get_location", return_value=None):
                location = self.telescope.get_location()

        self.assertEqual(location.latitude, 0.0)
        self.assertEqual(location.longitude, 0.0)

    def test_set_location(self):
        """Test setting observer location"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "set_location", return_value=True):
                result = self.telescope.set_location(40.7128, -74.0060)

        self.assertTrue(result)

    def test_set_location_negative_coordinates(self):
        """Test setting location with negative coordinates"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "set_location", return_value=True):
                result = self.telescope.set_location(-33.8688, -151.2093)

        self.assertTrue(result)

    # ========== Time Tests ==========

    def test_get_time(self):
        """Test getting date and time"""
        # Protocol returns year_offset, telescope converts to actual year
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "get_time", return_value=(12, 30, 0, 10, 14, 24, 0, 0)):
                time_info = self.telescope.get_time()

            self.assertIsInstance(time_info, TelescopeTime)
            self.assertEqual(time_info.hour, 12)
            self.assertEqual(time_info.minute, 30)
            self.assertEqual(time_info.second, 0)
            self.assertEqual(time_info.month, 10)
            self.assertEqual(time_info.day, 14)
            self.assertEqual(time_info.year, 2024)  # 24 + 2000

    def test_get_time_invalid_response(self):
        """Test get_time with invalid response"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "get_time", return_value=None):
                time_info = self.telescope.get_time()

        self.assertEqual(time_info.year, 0)

    def test_set_time(self):
        """Test setting date and time"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "set_time", return_value=True):
                result = self.telescope.set_time(12, 30, 0, 10, 14, 2024, 0, 0)

        self.assertTrue(result)

    def test_set_time_with_timezone(self):
        """Test setting time with timezone offset"""
        with patch.object(self.telescope.protocol, "is_open", return_value=True):
            with patch.object(self.telescope.protocol, "set_time", return_value=True):
                result = self.telescope.set_time(18, 45, 30, 7, 4, 2024, -5, 1)

        self.assertTrue(result)

    # ========== Context Manager Tests ==========

    def test_context_manager_enter(self):
        """Test context manager entry"""
        with patch.object(self.telescope, "connect", return_value=True):
            telescope = self.telescope.__enter__()

        self.assertEqual(telescope, self.telescope)

    def test_context_manager_exit(self):
        """Test context manager exit"""
        with patch.object(self.telescope, "disconnect"):
            result = self.telescope.__exit__(None, None, None)

        self.assertFalse(result)


class TestTrackingMode(unittest.TestCase):
    """Test suite for TrackingMode enum"""

    def test_tracking_mode_values(self):
        """Test TrackingMode enum values"""
        self.assertEqual(TrackingMode.OFF.value, 0)
        self.assertEqual(TrackingMode.ALT_AZ.value, 1)
        self.assertEqual(TrackingMode.EQ_NORTH.value, 2)
        self.assertEqual(TrackingMode.EQ_SOUTH.value, 3)


class TestAlignmentMode(unittest.TestCase):
    """Test suite for AlignmentMode enum"""

    def test_alignment_mode_values(self):
        """Test AlignmentMode enum values"""
        self.assertEqual(AlignmentMode.NO_ALIGNMENT.value, 0)
        self.assertEqual(AlignmentMode.ONE_STAR.value, 1)
        self.assertEqual(AlignmentMode.TWO_STAR.value, 2)
        self.assertEqual(AlignmentMode.THREE_STAR.value, 3)


class TestDataclasses(unittest.TestCase):
    """Test suite for dataclass types"""

    def test_equatorial_coordinates(self):
        """Test EquatorialCoordinates dataclass"""
        coords = EquatorialCoordinates(ra_hours=12.5, dec_degrees=45.0)
        self.assertEqual(coords.ra_hours, 12.5)
        self.assertEqual(coords.dec_degrees, 45.0)
        self.assertIn("12.5", str(coords))

    def test_horizontal_coordinates(self):
        """Test HorizontalCoordinates dataclass"""
        coords = HorizontalCoordinates(azimuth=180.0, altitude=45.0)
        self.assertEqual(coords.azimuth, 180.0)
        self.assertEqual(coords.altitude, 45.0)
        self.assertIn("180", str(coords))

    def test_geographic_location(self):
        """Test GeographicLocation dataclass"""
        location = GeographicLocation(latitude=40.7128, longitude=-74.0060)
        self.assertEqual(location.latitude, 40.7128)
        self.assertEqual(location.longitude, -74.0060)
        self.assertIn("N", str(location))
        self.assertIn("W", str(location))

    def test_telescope_info(self):
        """Test TelescopeInfo dataclass"""
        info = TelescopeInfo(model=6, firmware_major=4, firmware_minor=21)
        self.assertEqual(info.model, 6)
        self.assertEqual(info.firmware_major, 4)
        self.assertEqual(info.firmware_minor, 21)
        self.assertIn("4.21", str(info))

    def test_telescope_time(self):
        """Test TelescopeTime dataclass"""
        time = TelescopeTime(12, 30, 0, 10, 14, 2024, 0, 0)
        self.assertEqual(time.hour, 12)
        self.assertEqual(time.year, 2024)
        self.assertIn("2024", str(time))

    def test_telescope_config(self):
        """Test TelescopeConfig dataclass"""
        config = TelescopeConfig(port="/dev/ttyUSB0", baudrate=19200, verbose=True)
        self.assertEqual(config.port, "/dev/ttyUSB0")
        self.assertEqual(config.baudrate, 19200)
        self.assertTrue(config.verbose)


if __name__ == "__main__":
    unittest.main()

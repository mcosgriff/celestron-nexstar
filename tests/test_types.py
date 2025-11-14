"""
Unit tests for types module.

Tests all type definitions including enums and dataclasses.
"""

import unittest
from dataclasses import fields

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


class TestTrackingMode(unittest.TestCase):
    """Test suite for TrackingMode enum"""

    def test_enum_values(self):
        """Test all TrackingMode enum values"""
        self.assertEqual(TrackingMode.OFF.value, 0)
        self.assertEqual(TrackingMode.ALT_AZ.value, 1)
        self.assertEqual(TrackingMode.EQ_NORTH.value, 2)
        self.assertEqual(TrackingMode.EQ_SOUTH.value, 3)

    def test_enum_membership(self):
        """Test enum membership"""
        self.assertIn(TrackingMode.OFF, TrackingMode)
        self.assertIn(TrackingMode.ALT_AZ, TrackingMode)
        self.assertIn(TrackingMode.EQ_NORTH, TrackingMode)
        self.assertIn(TrackingMode.EQ_SOUTH, TrackingMode)


class TestAlignmentMode(unittest.TestCase):
    """Test suite for AlignmentMode enum"""

    def test_enum_values(self):
        """Test all AlignmentMode enum values"""
        self.assertEqual(AlignmentMode.NO_ALIGNMENT.value, 0)
        self.assertEqual(AlignmentMode.ONE_STAR.value, 1)
        self.assertEqual(AlignmentMode.TWO_STAR.value, 2)
        self.assertEqual(AlignmentMode.THREE_STAR.value, 3)

    def test_enum_membership(self):
        """Test enum membership"""
        self.assertIn(AlignmentMode.NO_ALIGNMENT, AlignmentMode)
        self.assertIn(AlignmentMode.ONE_STAR, AlignmentMode)
        self.assertIn(AlignmentMode.TWO_STAR, AlignmentMode)
        self.assertIn(AlignmentMode.THREE_STAR, AlignmentMode)


class TestEquatorialCoordinates(unittest.TestCase):
    """Test suite for EquatorialCoordinates dataclass"""

    def test_instantiation(self):
        """Test creating EquatorialCoordinates instance"""
        coords = EquatorialCoordinates(ra_hours=12.5, dec_degrees=45.0)
        self.assertEqual(coords.ra_hours, 12.5)
        self.assertEqual(coords.dec_degrees, 45.0)

    def test_string_representation_positive_dec(self):
        """Test string representation with positive declination"""
        coords = EquatorialCoordinates(ra_hours=12.5, dec_degrees=45.0)
        result = str(coords)
        self.assertIn("RA 12.5000h", result)
        self.assertIn("Dec +45.0000°", result)

    def test_string_representation_negative_dec(self):
        """Test string representation with negative declination"""
        coords = EquatorialCoordinates(ra_hours=6.25, dec_degrees=-30.5)
        result = str(coords)
        self.assertIn("RA 6.2500h", result)
        self.assertIn("Dec -30.5000°", result)

    def test_string_representation_zero_dec(self):
        """Test string representation with zero declination"""
        coords = EquatorialCoordinates(ra_hours=0.0, dec_degrees=0.0)
        result = str(coords)
        self.assertIn("RA 0.0000h", result)
        self.assertIn("Dec +0.0000°", result)


class TestHorizontalCoordinates(unittest.TestCase):
    """Test suite for HorizontalCoordinates dataclass"""

    def test_instantiation(self):
        """Test creating HorizontalCoordinates instance"""
        coords = HorizontalCoordinates(azimuth=180.0, altitude=45.0)
        self.assertEqual(coords.azimuth, 180.0)
        self.assertEqual(coords.altitude, 45.0)

    def test_string_representation(self):
        """Test string representation"""
        coords = HorizontalCoordinates(azimuth=180.5, altitude=45.75)
        result = str(coords)
        self.assertIn("Az 180.50°", result)
        self.assertIn("Alt 45.75°", result)

    def test_string_representation_negative_altitude(self):
        """Test string representation with negative altitude"""
        coords = HorizontalCoordinates(azimuth=0.0, altitude=-10.5)
        result = str(coords)
        self.assertIn("Az 0.00°", result)
        self.assertIn("Alt -10.50°", result)


class TestGeographicLocation(unittest.TestCase):
    """Test suite for GeographicLocation dataclass"""

    def test_instantiation(self):
        """Test creating GeographicLocation instance"""
        loc = GeographicLocation(latitude=40.7128, longitude=-74.0060)
        self.assertEqual(loc.latitude, 40.7128)
        self.assertEqual(loc.longitude, -74.0060)

    def test_string_representation_north_east(self):
        """Test string representation for North/East coordinates"""
        loc = GeographicLocation(latitude=40.7128, longitude=74.0060)
        result = str(loc)
        self.assertIn("40.7128°N", result)
        self.assertIn("74.0060°E", result)

    def test_string_representation_south_west(self):
        """Test string representation for South/West coordinates"""
        loc = GeographicLocation(latitude=-40.7128, longitude=-74.0060)
        result = str(loc)
        self.assertIn("40.7128°S", result)
        self.assertIn("74.0060°W", result)

    def test_string_representation_equator(self):
        """Test string representation for equator"""
        loc = GeographicLocation(latitude=0.0, longitude=0.0)
        result = str(loc)
        self.assertIn("0.0000°N", result)
        self.assertIn("0.0000°E", result)


class TestTelescopeInfo(unittest.TestCase):
    """Test suite for TelescopeInfo dataclass"""

    def test_instantiation(self):
        """Test creating TelescopeInfo instance"""
        info = TelescopeInfo(model=6, firmware_major=5, firmware_minor=23)
        self.assertEqual(info.model, 6)
        self.assertEqual(info.firmware_major, 5)
        self.assertEqual(info.firmware_minor, 23)

    def test_string_representation(self):
        """Test string representation"""
        info = TelescopeInfo(model=6, firmware_major=5, firmware_minor=23)
        result = str(info)
        self.assertEqual(result, "Model 6, Firmware 5.23")

    def test_string_representation_single_digit_minor(self):
        """Test string representation with single digit minor version"""
        info = TelescopeInfo(model=8, firmware_major=4, firmware_minor=5)
        result = str(info)
        self.assertEqual(result, "Model 8, Firmware 4.5")


class TestTelescopeTime(unittest.TestCase):
    """Test suite for TelescopeTime dataclass"""

    def test_instantiation_with_defaults(self):
        """Test creating TelescopeTime instance with default values"""
        time = TelescopeTime(hour=12, minute=30, second=45, month=6, day=15, year=2024)
        self.assertEqual(time.hour, 12)
        self.assertEqual(time.minute, 30)
        self.assertEqual(time.second, 45)
        self.assertEqual(time.month, 6)
        self.assertEqual(time.day, 15)
        self.assertEqual(time.year, 2024)
        self.assertEqual(time.timezone, 0)
        self.assertEqual(time.daylight_savings, 0)

    def test_instantiation_with_all_fields(self):
        """Test creating TelescopeTime instance with all fields"""
        time = TelescopeTime(hour=14, minute=30, second=0, month=12, day=25, year=2024, timezone=-5, daylight_savings=1)
        self.assertEqual(time.hour, 14)
        self.assertEqual(time.minute, 30)
        self.assertEqual(time.second, 0)
        self.assertEqual(time.month, 12)
        self.assertEqual(time.day, 25)
        self.assertEqual(time.year, 2024)
        self.assertEqual(time.timezone, -5)
        self.assertEqual(time.daylight_savings, 1)

    def test_string_representation(self):
        """Test string representation"""
        time = TelescopeTime(hour=12, minute=30, second=45, month=6, day=15, year=2024)
        result = str(time)
        self.assertEqual(result, "2024-06-15 12:30:45")

    def test_string_representation_single_digits(self):
        """Test string representation with single digit values"""
        time = TelescopeTime(hour=1, minute=5, second=3, month=1, day=1, year=2024)
        result = str(time)
        self.assertEqual(result, "2024-01-01 01:05:03")


class TestTelescopeConfig(unittest.TestCase):
    """Test suite for TelescopeConfig dataclass"""

    def test_instantiation_with_defaults(self):
        """Test creating TelescopeConfig instance with default values"""
        config = TelescopeConfig()
        self.assertEqual(config.port, "/dev/ttyUSB0")
        self.assertEqual(config.baudrate, 9600)
        self.assertEqual(config.timeout, 2.0)
        self.assertFalse(config.auto_connect)
        self.assertFalse(config.verbose)

    def test_instantiation_with_custom_values(self):
        """Test creating TelescopeConfig instance with custom values"""
        config = TelescopeConfig(port="/dev/ttyUSB1", baudrate=19200, timeout=3.0, auto_connect=True, verbose=True)
        self.assertEqual(config.port, "/dev/ttyUSB1")
        self.assertEqual(config.baudrate, 19200)
        self.assertEqual(config.timeout, 3.0)
        self.assertTrue(config.auto_connect)
        self.assertTrue(config.verbose)

    def test_instantiation_partial_override(self):
        """Test creating TelescopeConfig with partial override"""
        config = TelescopeConfig(port="COM3", baudrate=115200)
        self.assertEqual(config.port, "COM3")
        self.assertEqual(config.baudrate, 115200)
        self.assertEqual(config.timeout, 2.0)  # Default value
        self.assertFalse(config.auto_connect)  # Default value
        self.assertFalse(config.verbose)  # Default value


class TestDataclassFields(unittest.TestCase):
    """Test dataclass field definitions"""

    def test_equatorial_coordinates_fields(self):
        """Test EquatorialCoordinates has correct fields"""
        field_names = {f.name for f in fields(EquatorialCoordinates)}
        self.assertEqual(field_names, {"ra_hours", "dec_degrees"})

    def test_horizontal_coordinates_fields(self):
        """Test HorizontalCoordinates has correct fields"""
        field_names = {f.name for f in fields(HorizontalCoordinates)}
        self.assertEqual(field_names, {"azimuth", "altitude"})

    def test_geographic_location_fields(self):
        """Test GeographicLocation has correct fields"""
        field_names = {f.name for f in fields(GeographicLocation)}
        self.assertEqual(field_names, {"latitude", "longitude"})

    def test_telescope_info_fields(self):
        """Test TelescopeInfo has correct fields"""
        field_names = {f.name for f in fields(TelescopeInfo)}
        self.assertEqual(field_names, {"model", "firmware_major", "firmware_minor"})

    def test_telescope_time_fields(self):
        """Test TelescopeTime has correct fields"""
        field_names = {f.name for f in fields(TelescopeTime)}
        self.assertEqual(
            field_names,
            {
                "hour",
                "minute",
                "second",
                "month",
                "day",
                "year",
                "timezone",
                "daylight_savings",
            },
        )

    def test_telescope_config_fields(self):
        """Test TelescopeConfig has correct fields"""
        field_names = {f.name for f in fields(TelescopeConfig)}
        self.assertEqual(field_names, {"port", "baudrate", "timeout", "auto_connect", "verbose"})


if __name__ == "__main__":
    unittest.main()

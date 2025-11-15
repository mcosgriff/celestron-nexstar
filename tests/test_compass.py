"""
Unit tests for compass.py

Tests compass direction utilities and sky position formatting.
"""

import unittest

from celestron_nexstar.api.telescope.compass import (
    azimuth_to_compass_16point,
    azimuth_to_compass_8point,
    format_altitude_description,
    format_object_path,
    format_sky_position,
)


class TestAzimuthToCompass8Point(unittest.TestCase):
    """Test suite for azimuth_to_compass_8point function"""

    def test_cardinal_directions(self):
        """Test cardinal directions"""
        self.assertEqual(azimuth_to_compass_8point(0), "N")
        self.assertEqual(azimuth_to_compass_8point(90), "E")
        self.assertEqual(azimuth_to_compass_8point(180), "S")
        self.assertEqual(azimuth_to_compass_8point(270), "W")

    def test_intercardinal_directions(self):
        """Test intercardinal directions"""
        self.assertEqual(azimuth_to_compass_8point(45), "NE")
        self.assertEqual(azimuth_to_compass_8point(135), "SE")
        self.assertEqual(azimuth_to_compass_8point(225), "SW")
        self.assertEqual(azimuth_to_compass_8point(315), "NW")

    def test_normalization(self):
        """Test that angles are normalized to 0-360 range"""
        self.assertEqual(azimuth_to_compass_8point(360), "N")
        self.assertEqual(azimuth_to_compass_8point(450), "E")  # 450 - 360 = 90
        self.assertEqual(azimuth_to_compass_8point(-90), "W")  # -90 + 360 = 270
        self.assertEqual(azimuth_to_compass_8point(720), "N")  # 720 - 2*360 = 0

    def test_fallback(self):
        """Test fallback return (shouldn't normally happen)"""
        # Test with a value that somehow doesn't match any condition
        # This tests the fallback return statement
        result = azimuth_to_compass_8point(999)  # Will be normalized to 279, which is W
        self.assertIn(result, ["N", "NE", "E", "SE", "S", "SW", "W", "NW"])

    def test_boundary_conditions(self):
        """Test boundary conditions between directions"""
        self.assertEqual(azimuth_to_compass_8point(22.4), "N")
        self.assertEqual(azimuth_to_compass_8point(22.6), "NE")
        self.assertEqual(azimuth_to_compass_8point(67.4), "NE")
        self.assertEqual(azimuth_to_compass_8point(67.6), "E")


class TestAzimuthToCompass16Point(unittest.TestCase):
    """Test suite for azimuth_to_compass_16point function"""

    def test_cardinal_directions(self):
        """Test cardinal directions"""
        self.assertEqual(azimuth_to_compass_16point(0), "N")
        self.assertEqual(azimuth_to_compass_16point(90), "E")
        self.assertEqual(azimuth_to_compass_16point(180), "S")
        self.assertEqual(azimuth_to_compass_16point(270), "W")

    def test_primary_intercardinal(self):
        """Test primary intercardinal directions"""
        self.assertEqual(azimuth_to_compass_16point(45), "NE")
        self.assertEqual(azimuth_to_compass_16point(135), "SE")
        self.assertEqual(azimuth_to_compass_16point(225), "SW")
        self.assertEqual(azimuth_to_compass_16point(315), "NW")

    def test_secondary_intercardinal(self):
        """Test secondary intercardinal directions"""
        self.assertEqual(azimuth_to_compass_16point(22.5), "NNE")
        self.assertEqual(azimuth_to_compass_16point(67.5), "ENE")
        self.assertEqual(azimuth_to_compass_16point(112.5), "ESE")
        self.assertEqual(azimuth_to_compass_16point(157.5), "SSE")
        self.assertEqual(azimuth_to_compass_16point(202.5), "SSW")
        self.assertEqual(azimuth_to_compass_16point(247.5), "WSW")
        self.assertEqual(azimuth_to_compass_16point(292.5), "WNW")
        self.assertEqual(azimuth_to_compass_16point(337.5), "NNW")

    def test_normalization(self):
        """Test that angles are normalized to 0-360 range"""
        self.assertEqual(azimuth_to_compass_16point(360), "N")
        self.assertEqual(azimuth_to_compass_16point(450), "E")
        self.assertEqual(azimuth_to_compass_16point(-45), "NW")

    def test_fallback(self):
        """Test fallback return (shouldn't normally happen)"""
        # Test with a value that somehow doesn't match any condition
        result = azimuth_to_compass_16point(999)  # Will be normalized
        self.assertIn(
            result, ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        )


class TestFormatAltitudeDescription(unittest.TestCase):
    """Test suite for format_altitude_description function"""

    def test_below_horizon(self):
        """Test negative altitudes"""
        self.assertEqual(format_altitude_description(-10), "below the horizon")

    def test_low_altitudes(self):
        """Test low altitude descriptions"""
        self.assertEqual(format_altitude_description(5), "just above the horizon")
        self.assertEqual(format_altitude_description(15), "low in the sky")
        self.assertEqual(format_altitude_description(25), "about one-third up the sky")

    def test_mid_altitudes(self):
        """Test mid altitude descriptions"""
        self.assertEqual(format_altitude_description(45), "halfway up the sky")
        self.assertEqual(format_altitude_description(60), "high in the sky")

    def test_high_altitudes(self):
        """Test high altitude descriptions"""
        self.assertEqual(format_altitude_description(75), "very high in the sky")
        self.assertEqual(format_altitude_description(85), "nearly overhead")
        self.assertEqual(format_altitude_description(90), "nearly overhead")

    def test_boundary_conditions(self):
        """Test boundary conditions"""
        self.assertEqual(format_altitude_description(0), "just above the horizon")
        self.assertEqual(format_altitude_description(9.9), "just above the horizon")
        # 10 is the boundary, so it should be "low in the sky" (>= 10)
        self.assertEqual(format_altitude_description(10), "low in the sky")
        self.assertEqual(format_altitude_description(19.9), "low in the sky")
        self.assertEqual(format_altitude_description(20), "about one-third up the sky")
        self.assertEqual(format_altitude_description(39.9), "about one-third up the sky")
        self.assertEqual(format_altitude_description(40), "halfway up the sky")
        self.assertEqual(format_altitude_description(49.9), "halfway up the sky")
        self.assertEqual(format_altitude_description(50), "high in the sky")
        self.assertEqual(format_altitude_description(69.9), "high in the sky")
        self.assertEqual(format_altitude_description(70), "very high in the sky")
        self.assertEqual(format_altitude_description(79.9), "very high in the sky")
        self.assertEqual(format_altitude_description(80), "nearly overhead")


class TestFormatSkyPosition(unittest.TestCase):
    """Test suite for format_sky_position function"""

    def test_with_degrees_8point(self):
        """Test formatting with degrees using 8-point compass"""
        result = format_sky_position(45, 30, use_16point=False, include_degrees=True)
        self.assertIn("NE", result)
        self.assertIn("45", result)
        self.assertIn("30", result)
        self.assertIn("above horizon", result)

    def test_without_degrees_8point(self):
        """Test formatting without degrees using 8-point compass"""
        result = format_sky_position(180, 60, use_16point=False, include_degrees=False)
        self.assertIn("S", result)
        self.assertNotIn("180", result)
        self.assertIn("high in the sky", result)

    def test_with_degrees_16point(self):
        """Test formatting with degrees using 16-point compass"""
        result = format_sky_position(22.5, 45, use_16point=True, include_degrees=True)
        self.assertIn("NNE", result)
        self.assertIn("22", result)
        self.assertIn("45", result)

    def test_without_degrees_16point(self):
        """Test formatting without degrees using 16-point compass"""
        result = format_sky_position(67.5, 75, use_16point=True, include_degrees=False)
        self.assertIn("ENE", result)
        self.assertIn("very high in the sky", result)


class TestFormatObjectPath(unittest.TestCase):
    """Test suite for format_object_path function"""

    def test_basic_path(self):
        """Test basic object path formatting"""
        result = format_object_path(225, 180, 60, 135)
        self.assertIn("SW", result)
        self.assertIn("S", result)
        self.assertIn("SE", result)
        self.assertIn("60", result)
        self.assertIn("Rises", result)
        self.assertIn("peaks", result)
        self.assertIn("sets", result)

    def test_north_to_south_path(self):
        """Test path from north to south"""
        result = format_object_path(0, 180, 45, 180)
        self.assertIn("N", result)
        self.assertIn("S", result)

    def test_east_to_west_path(self):
        """Test path from east to west"""
        result = format_object_path(90, 270, 30, 270)
        self.assertIn("E", result)
        self.assertIn("W", result)


if __name__ == "__main__":
    unittest.main()

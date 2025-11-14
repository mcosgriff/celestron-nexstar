"""
Unit tests for converters module.

Tests coordinate conversion utilities.
"""

import unittest

from celestron_nexstar.api.catalogs.catalogs.converters import CoordinateConverter


class TestCoordinateConverter(unittest.TestCase):
    """Test suite for CoordinateConverter class"""

    def test_ra_hours_to_degrees(self):
        """Test Right Ascension hours to degrees conversion"""
        # Test standard conversion
        self.assertEqual(CoordinateConverter.ra_hours_to_degrees(12.0), 180.0)
        self.assertEqual(CoordinateConverter.ra_hours_to_degrees(0.0), 0.0)
        self.assertEqual(CoordinateConverter.ra_hours_to_degrees(24.0), 360.0)
        self.assertEqual(CoordinateConverter.ra_hours_to_degrees(6.0), 90.0)
        self.assertEqual(CoordinateConverter.ra_hours_to_degrees(18.0), 270.0)

        # Test fractional hours
        self.assertEqual(CoordinateConverter.ra_hours_to_degrees(12.5), 187.5)
        self.assertEqual(CoordinateConverter.ra_hours_to_degrees(1.5), 22.5)

    def test_ra_degrees_to_hours(self):
        """Test Right Ascension degrees to hours conversion"""
        # Test standard conversion
        self.assertEqual(CoordinateConverter.ra_degrees_to_hours(180.0), 12.0)
        self.assertEqual(CoordinateConverter.ra_degrees_to_hours(0.0), 0.0)
        self.assertEqual(CoordinateConverter.ra_degrees_to_hours(360.0), 24.0)
        self.assertEqual(CoordinateConverter.ra_degrees_to_hours(90.0), 6.0)
        self.assertEqual(CoordinateConverter.ra_degrees_to_hours(270.0), 18.0)

        # Test fractional degrees
        self.assertEqual(CoordinateConverter.ra_degrees_to_hours(187.5), 12.5)
        self.assertEqual(CoordinateConverter.ra_degrees_to_hours(22.5), 1.5)

    def test_ra_conversion_roundtrip(self):
        """Test that RA conversions are reversible"""
        test_values = [0.0, 6.0, 12.0, 18.0, 24.0, 12.5, 1.5, 23.75]
        for hours in test_values:
            degrees = CoordinateConverter.ra_hours_to_degrees(hours)
            back_to_hours = CoordinateConverter.ra_degrees_to_hours(degrees)
            self.assertAlmostEqual(hours, back_to_hours, places=10)

    def test_dec_to_unsigned_positive(self):
        """Test Declination to unsigned conversion for positive values"""
        self.assertEqual(CoordinateConverter.dec_to_unsigned(45.0), 45.0)
        self.assertEqual(CoordinateConverter.dec_to_unsigned(90.0), 90.0)
        self.assertEqual(CoordinateConverter.dec_to_unsigned(0.0), 0.0)

    def test_dec_to_unsigned_negative(self):
        """Test Declination to unsigned conversion for negative values"""
        self.assertEqual(CoordinateConverter.dec_to_unsigned(-30.0), 330.0)
        self.assertEqual(CoordinateConverter.dec_to_unsigned(-45.0), 315.0)
        self.assertEqual(CoordinateConverter.dec_to_unsigned(-90.0), 270.0)
        self.assertEqual(CoordinateConverter.dec_to_unsigned(-1.0), 359.0)

    def test_dec_to_signed_positive(self):
        """Test Declination to signed conversion for positive values"""
        self.assertEqual(CoordinateConverter.dec_to_signed(45.0), 45.0)
        self.assertEqual(CoordinateConverter.dec_to_signed(90.0), 90.0)
        self.assertEqual(CoordinateConverter.dec_to_signed(0.0), 0.0)
        self.assertEqual(CoordinateConverter.dec_to_signed(180.0), 180.0)

    def test_dec_to_signed_negative(self):
        """Test Declination to signed conversion for values > 180"""
        self.assertEqual(CoordinateConverter.dec_to_signed(330.0), -30.0)
        self.assertEqual(CoordinateConverter.dec_to_signed(315.0), -45.0)
        self.assertEqual(CoordinateConverter.dec_to_signed(270.0), -90.0)
        self.assertEqual(CoordinateConverter.dec_to_signed(359.0), -1.0)
        self.assertEqual(CoordinateConverter.dec_to_signed(181.0), -179.0)

    def test_dec_conversion_roundtrip(self):
        """Test that Declination conversions are reversible"""
        test_values = [-90.0, -45.0, -30.0, 0.0, 30.0, 45.0, 90.0]
        for signed in test_values:
            unsigned = CoordinateConverter.dec_to_unsigned(signed)
            back_to_signed = CoordinateConverter.dec_to_signed(unsigned)
            self.assertAlmostEqual(signed, back_to_signed, places=10)

    def test_altitude_to_unsigned_positive(self):
        """Test Altitude to unsigned conversion for positive values"""
        self.assertEqual(CoordinateConverter.altitude_to_unsigned(45.0), 45.0)
        self.assertEqual(CoordinateConverter.altitude_to_unsigned(90.0), 90.0)
        self.assertEqual(CoordinateConverter.altitude_to_unsigned(0.0), 0.0)

    def test_altitude_to_unsigned_negative(self):
        """Test Altitude to unsigned conversion for negative values"""
        self.assertEqual(CoordinateConverter.altitude_to_unsigned(-15.0), 345.0)
        self.assertEqual(CoordinateConverter.altitude_to_unsigned(-45.0), 315.0)
        self.assertEqual(CoordinateConverter.altitude_to_unsigned(-90.0), 270.0)
        self.assertEqual(CoordinateConverter.altitude_to_unsigned(-1.0), 359.0)

    def test_altitude_to_signed_positive(self):
        """Test Altitude to signed conversion for positive values"""
        self.assertEqual(CoordinateConverter.altitude_to_signed(45.0), 45.0)
        self.assertEqual(CoordinateConverter.altitude_to_signed(90.0), 90.0)
        self.assertEqual(CoordinateConverter.altitude_to_signed(0.0), 0.0)
        self.assertEqual(CoordinateConverter.altitude_to_signed(180.0), 180.0)

    def test_altitude_to_signed_negative(self):
        """Test Altitude to signed conversion for values > 180"""
        self.assertEqual(CoordinateConverter.altitude_to_signed(345.0), -15.0)
        self.assertEqual(CoordinateConverter.altitude_to_signed(315.0), -45.0)
        self.assertEqual(CoordinateConverter.altitude_to_signed(270.0), -90.0)
        self.assertEqual(CoordinateConverter.altitude_to_signed(359.0), -1.0)
        self.assertEqual(CoordinateConverter.altitude_to_signed(181.0), -179.0)

    def test_altitude_conversion_roundtrip(self):
        """Test that Altitude conversions are reversible"""
        test_values = [-90.0, -45.0, -15.0, 0.0, 15.0, 45.0, 90.0]
        for signed in test_values:
            unsigned = CoordinateConverter.altitude_to_unsigned(signed)
            back_to_signed = CoordinateConverter.altitude_to_signed(unsigned)
            self.assertAlmostEqual(signed, back_to_signed, places=10)

    def test_location_to_unsigned_positive(self):
        """Test geographic coordinate to unsigned conversion for positive values"""
        self.assertEqual(CoordinateConverter.location_to_unsigned(40.0), 40.0)
        self.assertEqual(CoordinateConverter.location_to_unsigned(180.0), 180.0)
        self.assertEqual(CoordinateConverter.location_to_unsigned(0.0), 0.0)

    def test_location_to_unsigned_negative(self):
        """Test geographic coordinate to unsigned conversion for negative values"""
        self.assertEqual(CoordinateConverter.location_to_unsigned(-74.0), 286.0)
        self.assertEqual(CoordinateConverter.location_to_unsigned(-90.0), 270.0)
        self.assertEqual(CoordinateConverter.location_to_unsigned(-180.0), 180.0)
        self.assertEqual(CoordinateConverter.location_to_unsigned(-1.0), 359.0)

    def test_location_to_signed_positive(self):
        """Test geographic coordinate to signed conversion for positive values"""
        self.assertEqual(CoordinateConverter.location_to_signed(40.0), 40.0)
        self.assertEqual(CoordinateConverter.location_to_signed(90.0), 90.0)
        self.assertEqual(CoordinateConverter.location_to_signed(0.0), 0.0)
        self.assertEqual(CoordinateConverter.location_to_signed(180.0), 180.0)

    def test_location_to_signed_negative(self):
        """Test geographic coordinate to signed conversion for values > 180"""
        self.assertEqual(CoordinateConverter.location_to_signed(286.0), -74.0)
        self.assertEqual(CoordinateConverter.location_to_signed(270.0), -90.0)
        self.assertEqual(CoordinateConverter.location_to_signed(359.0), -1.0)
        self.assertEqual(CoordinateConverter.location_to_signed(181.0), -179.0)

    def test_location_conversion_roundtrip(self):
        """Test that geographic coordinate conversions are reversible"""
        # Note: -180.0 and 180.0 are the same point, so roundtrip can't distinguish them
        test_values = [-179.9, -90.0, -74.0, 0.0, 40.0, 90.0, 180.0]
        for signed in test_values:
            unsigned = CoordinateConverter.location_to_unsigned(signed)
            back_to_signed = CoordinateConverter.location_to_signed(unsigned)
            self.assertAlmostEqual(signed, back_to_signed, places=10)

    def test_edge_cases(self):
        """Test edge cases for all conversion methods"""
        # RA edge cases
        self.assertEqual(CoordinateConverter.ra_hours_to_degrees(0.0), 0.0)
        self.assertEqual(CoordinateConverter.ra_degrees_to_hours(0.0), 0.0)

        # Declination edge cases
        self.assertEqual(CoordinateConverter.dec_to_unsigned(0.0), 0.0)
        self.assertEqual(CoordinateConverter.dec_to_signed(0.0), 0.0)
        self.assertEqual(CoordinateConverter.dec_to_unsigned(90.0), 90.0)
        self.assertEqual(CoordinateConverter.dec_to_unsigned(-90.0), 270.0)
        self.assertEqual(CoordinateConverter.dec_to_signed(270.0), -90.0)

        # Altitude edge cases
        self.assertEqual(CoordinateConverter.altitude_to_unsigned(0.0), 0.0)
        self.assertEqual(CoordinateConverter.altitude_to_signed(0.0), 0.0)
        self.assertEqual(CoordinateConverter.altitude_to_unsigned(90.0), 90.0)
        self.assertEqual(CoordinateConverter.altitude_to_unsigned(-90.0), 270.0)
        self.assertEqual(CoordinateConverter.altitude_to_signed(270.0), -90.0)

        # Location edge cases
        self.assertEqual(CoordinateConverter.location_to_unsigned(0.0), 0.0)
        self.assertEqual(CoordinateConverter.location_to_signed(0.0), 0.0)
        self.assertEqual(CoordinateConverter.location_to_unsigned(180.0), 180.0)
        self.assertEqual(CoordinateConverter.location_to_unsigned(-180.0), 180.0)
        self.assertEqual(CoordinateConverter.location_to_signed(180.0), 180.0)

    def test_boundary_values(self):
        """Test boundary values for conversions"""
        # Test exactly at 180 degrees boundary
        self.assertEqual(CoordinateConverter.dec_to_signed(180.0), 180.0)
        self.assertEqual(CoordinateConverter.dec_to_signed(180.1), -179.9)
        self.assertEqual(CoordinateConverter.altitude_to_signed(180.0), 180.0)
        self.assertEqual(CoordinateConverter.altitude_to_signed(180.1), -179.9)
        self.assertEqual(CoordinateConverter.location_to_signed(180.0), 180.0)
        self.assertEqual(CoordinateConverter.location_to_signed(180.1), -179.9)


if __name__ == "__main__":
    unittest.main()

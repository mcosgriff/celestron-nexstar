"""
Unit tests for Celestron NexStar utilities module
Tests coordinate conversions and astronomical calculations.
"""

import unittest
import math
from datetime import datetime
from celestron_nexstar.utils import (
    ra_to_hours,
    ra_to_degrees,
    dec_to_degrees,
    hours_to_hms,
    degrees_to_dms,
    calculate_lst,
    calculate_julian_date,
    alt_az_to_ra_dec,
    ra_dec_to_alt_az,
    angular_separation,
    format_ra,
    format_dec,
    format_position,
)


class TestCoordinateConversions(unittest.TestCase):
    """Test suite for coordinate conversion functions"""

    def test_ra_to_hours_basic(self):
        """Test basic RA conversion"""
        result = ra_to_hours(12, 0, 0)
        self.assertEqual(result, 12.0)

    def test_ra_to_hours_with_minutes(self):
        """Test RA conversion with minutes"""
        result = ra_to_hours(12, 30, 0)
        self.assertAlmostEqual(result, 12.5, places=6)

    def test_ra_to_hours_with_seconds(self):
        """Test RA conversion with seconds"""
        result = ra_to_hours(12, 30, 45)
        self.assertAlmostEqual(result, 12.5125, places=6)

    def test_ra_to_hours_zero(self):
        """Test RA conversion with zero values"""
        result = ra_to_hours(0, 0, 0)
        self.assertEqual(result, 0.0)

    def test_ra_to_hours_maximum(self):
        """Test RA conversion with maximum values"""
        result = ra_to_hours(23, 59, 59)
        self.assertAlmostEqual(result, 23.9997222, places=6)

    def test_ra_to_degrees_basic(self):
        """Test RA to degrees conversion"""
        result = ra_to_degrees(12, 0, 0)
        self.assertAlmostEqual(result, 180.0, places=6)

    def test_ra_to_degrees_with_minutes(self):
        """Test RA to degrees with minutes"""
        result = ra_to_degrees(6, 30, 0)
        self.assertAlmostEqual(result, 97.5, places=6)

    def test_dec_to_degrees_positive(self):
        """Test declination conversion for positive values"""
        result = dec_to_degrees(45, 30, 0, "+")
        self.assertAlmostEqual(result, 45.5, places=6)

    def test_dec_to_degrees_negative(self):
        """Test declination conversion for negative values"""
        result = dec_to_degrees(45, 30, 0, "-")
        self.assertAlmostEqual(result, -45.5, places=6)

    def test_dec_to_degrees_with_seconds(self):
        """Test declination conversion with seconds"""
        result = dec_to_degrees(45, 30, 30, "+")
        self.assertAlmostEqual(result, 45.508333, places=6)

    def test_dec_to_degrees_zero(self):
        """Test declination conversion with zero"""
        result = dec_to_degrees(0, 0, 0, "+")
        self.assertEqual(result, 0.0)

    def test_hours_to_hms_basic(self):
        """Test hours to HMS conversion"""
        h, m, s = hours_to_hms(12.5125)
        self.assertEqual(h, 12)
        self.assertEqual(m, 30)
        self.assertAlmostEqual(s, 45.0, places=1)

    def test_hours_to_hms_zero(self):
        """Test hours to HMS conversion with zero"""
        h, m, s = hours_to_hms(0.0)
        self.assertEqual(h, 0)
        self.assertEqual(m, 0)
        self.assertAlmostEqual(s, 0.0, places=1)

    def test_hours_to_hms_integer(self):
        """Test hours to HMS conversion with integer hours"""
        h, m, s = hours_to_hms(15.0)
        self.assertEqual(h, 15)
        self.assertEqual(m, 0)
        self.assertAlmostEqual(s, 0.0, places=1)

    def test_degrees_to_dms_positive(self):
        """Test degrees to DMS conversion for positive values"""
        d, m, s, sign = degrees_to_dms(45.5)
        self.assertEqual(d, 45)
        self.assertEqual(m, 30)
        self.assertAlmostEqual(s, 0.0, places=1)
        self.assertEqual(sign, "+")

    def test_degrees_to_dms_negative(self):
        """Test degrees to DMS conversion for negative values"""
        d, m, s, sign = degrees_to_dms(-45.5)
        self.assertEqual(d, 45)
        self.assertEqual(m, 30)
        self.assertAlmostEqual(s, 0.0, places=1)
        self.assertEqual(sign, "-")

    def test_degrees_to_dms_with_seconds(self):
        """Test degrees to DMS conversion with seconds"""
        d, m, s, sign = degrees_to_dms(45.508333)
        self.assertEqual(d, 45)
        self.assertEqual(m, 30)
        self.assertAlmostEqual(s, 30.0, places=0)
        self.assertEqual(sign, "+")

    def test_degrees_to_dms_zero(self):
        """Test degrees to DMS conversion with zero"""
        d, m, s, sign = degrees_to_dms(0.0)
        self.assertEqual(d, 0)
        self.assertEqual(m, 0)
        self.assertAlmostEqual(s, 0.0, places=1)
        self.assertEqual(sign, "+")


class TestAstronomicalCalculations(unittest.TestCase):
    """Test suite for astronomical calculation functions"""

    def test_calculate_julian_date_j2000(self):
        """Test Julian Date calculation for J2000.0 epoch"""
        # J2000.0 = January 1, 2000, 12:00:00 UTC
        dt = datetime(2000, 1, 1, 12, 0, 0)
        jd = calculate_julian_date(dt)
        self.assertAlmostEqual(jd, 2451545.0, places=1)

    def test_calculate_julian_date_current_era(self):
        """Test Julian Date calculation for a known date"""
        # October 14, 2024, 00:00:00 UTC
        dt = datetime(2024, 10, 14, 0, 0, 0)
        jd = calculate_julian_date(dt)
        # Known JD for this date
        self.assertAlmostEqual(jd, 2460597.5, places=1)

    def test_calculate_lst_greenwich(self):
        """Test LST calculation for Greenwich (longitude = 0)"""
        dt = datetime(2024, 10, 14, 0, 0, 0)
        lst = calculate_lst(0.0, dt)

        # LST should be a value between 0 and 24
        self.assertGreaterEqual(lst, 0.0)
        self.assertLess(lst, 24.0)

    def test_calculate_lst_positive_longitude(self):
        """Test LST calculation for positive longitude"""
        dt = datetime(2024, 10, 14, 0, 0, 0)
        lst = calculate_lst(74.0, dt)  # New York approximate longitude

        self.assertGreaterEqual(lst, 0.0)
        self.assertLess(lst, 24.0)

    def test_calculate_lst_negative_longitude(self):
        """Test LST calculation for negative longitude"""
        dt = datetime(2024, 10, 14, 0, 0, 0)
        lst = calculate_lst(-74.0, dt)

        self.assertGreaterEqual(lst, 0.0)
        self.assertLess(lst, 24.0)

    def test_angular_separation_same_point(self):
        """Test angular separation between identical coordinates"""
        ra1, dec1 = 12.0, 45.0
        ra2, dec2 = 12.0, 45.0

        separation = angular_separation(ra1, dec1, ra2, dec2)
        self.assertAlmostEqual(separation, 0.0, places=2)

    def test_angular_separation_opposite_points(self):
        """Test angular separation between opposite points"""
        ra1, dec1 = 0.0, 0.0
        ra2, dec2 = 12.0, 0.0  # 180 degrees in RA

        separation = angular_separation(ra1, dec1, ra2, dec2)
        self.assertAlmostEqual(separation, 180.0, places=0)

    def test_angular_separation_90_degrees(self):
        """Test angular separation for ~90 degree separation"""
        ra1, dec1 = 0.0, 0.0
        ra2, dec2 = 6.0, 0.0  # 90 degrees in RA

        separation = angular_separation(ra1, dec1, ra2, dec2)
        self.assertAlmostEqual(separation, 90.0, places=0)

    def test_angular_separation_different_declinations(self):
        """Test angular separation with different declinations"""
        ra1, dec1 = 0.0, 0.0
        ra2, dec2 = 0.0, 45.0  # Same RA, different Dec

        separation = angular_separation(ra1, dec1, ra2, dec2)
        self.assertAlmostEqual(separation, 45.0, places=1)


class TestCoordinateTransforms(unittest.TestCase):
    """Test suite for coordinate transformation functions"""

    def test_alt_az_to_ra_dec_zenith(self):
        """Test Alt/Az to RA/Dec conversion for zenith"""
        # Zenith: alt=90, az=0
        # At latitude 40°N, longitude -74°W
        dt = datetime(2024, 10, 14, 0, 0, 0)
        ra, dec = alt_az_to_ra_dec(0.0, 90.0, 40.0, -74.0, dt)

        # At zenith, declination should equal latitude
        self.assertAlmostEqual(dec, 40.0, places=0)

        # RA should be a valid value
        self.assertGreaterEqual(ra, 0.0)
        self.assertLess(ra, 24.0)

    def test_alt_az_to_ra_dec_horizon(self):
        """Test Alt/Az to RA/Dec conversion for horizon"""
        dt = datetime(2024, 10, 14, 0, 0, 0)
        ra, dec = alt_az_to_ra_dec(180.0, 0.0, 40.0, -74.0, dt)

        # Values should be in valid ranges
        self.assertGreaterEqual(ra, 0.0)
        self.assertLess(ra, 24.0)
        self.assertGreaterEqual(dec, -90.0)
        self.assertLessEqual(dec, 90.0)

    def test_ra_dec_to_alt_az_basic(self):
        """Test RA/Dec to Alt/Az conversion"""
        dt = datetime(2024, 10, 14, 0, 0, 0)
        az, alt = ra_dec_to_alt_az(12.0, 45.0, 40.0, -74.0, dt)

        # Values should be in valid ranges
        self.assertGreaterEqual(az, 0.0)
        self.assertLess(az, 360.0)
        self.assertGreaterEqual(alt, -90.0)
        self.assertLessEqual(alt, 90.0)

    def test_coordinate_transform_round_trip(self):
        """Test round-trip coordinate transformation"""
        # Start with Alt/Az
        original_az, original_alt = 180.0, 45.0
        dt = datetime(2024, 10, 14, 0, 0, 0)
        lat, lon = 40.0, -74.0

        # Convert to RA/Dec
        ra, dec = alt_az_to_ra_dec(original_az, original_alt, lat, lon, dt)

        # Convert back to Alt/Az
        az, alt = ra_dec_to_alt_az(ra, dec, lat, lon, dt)

        # Should be close to original values
        self.assertAlmostEqual(az, original_az, places=1)
        self.assertAlmostEqual(alt, original_alt, places=1)


class TestFormatting(unittest.TestCase):
    """Test suite for formatting functions"""

    def test_format_ra_basic(self):
        """Test RA formatting"""
        result = format_ra(12.5, 2)
        self.assertIn("12h", result)
        self.assertIn("30m", result)
        self.assertIn("s", result)

    def test_format_ra_zero(self):
        """Test RA formatting with zero"""
        result = format_ra(0.0, 2)
        self.assertIn("00h", result)
        self.assertIn("00m", result)

    def test_format_ra_precision(self):
        """Test RA formatting precision"""
        result = format_ra(12.5125, 3)
        # Should have 3 decimal places for seconds
        self.assertRegex(result, r"\d{2}h \d{2}m \d{2}\.\d{3}s")

    def test_format_dec_positive(self):
        """Test Dec formatting for positive values"""
        result = format_dec(45.5, 1)
        self.assertIn("+", result)
        self.assertIn("45°", result)
        self.assertIn("30'", result)

    def test_format_dec_negative(self):
        """Test Dec formatting for negative values"""
        result = format_dec(-45.5, 1)
        self.assertIn("-", result)
        self.assertIn("45°", result)
        self.assertIn("30'", result)

    def test_format_dec_zero(self):
        """Test Dec formatting with zero"""
        result = format_dec(0.0, 1)
        self.assertIn("+00°", result)

    def test_format_position(self):
        """Test position formatting"""
        result = format_position(12.5, 45.5)
        self.assertIn("RA:", result)
        self.assertIn("Dec:", result)
        self.assertIn("12h", result)
        self.assertIn("45°", result)


class TestEdgeCases(unittest.TestCase):
    """Test suite for edge cases and boundary conditions"""

    def test_ra_hours_boundary_24(self):
        """Test RA conversion at 24-hour boundary"""
        result = ra_to_hours(24, 0, 0)
        self.assertEqual(result, 24.0)

    def test_dec_degrees_boundary_90(self):
        """Test Dec conversion at +90 degrees"""
        result = dec_to_degrees(90, 0, 0, "+")
        self.assertEqual(result, 90.0)

    def test_dec_degrees_boundary_neg_90(self):
        """Test Dec conversion at -90 degrees"""
        result = dec_to_degrees(90, 0, 0, "-")
        self.assertEqual(result, -90.0)

    def test_angular_separation_poles(self):
        """Test angular separation between north and south poles"""
        ra1, dec1 = 0.0, 90.0  # North pole
        ra2, dec2 = 12.0, -90.0  # South pole

        separation = angular_separation(ra1, dec1, ra2, dec2)
        self.assertAlmostEqual(separation, 180.0, places=0)

    def test_lst_wraps_correctly(self):
        """Test that LST wraps correctly at 24 hours"""
        dt = datetime(2024, 10, 14, 23, 59, 59)
        lst = calculate_lst(0.0, dt)

        # LST should always be in [0, 24) range
        self.assertGreaterEqual(lst, 0.0)
        self.assertLess(lst, 24.0)

    def test_alt_az_to_ra_dec_normalization(self):
        """Test that alt_az_to_ra_dec normalizes RA correctly"""
        # Use specific values that may cause RA to need normalization
        dt = datetime(2024, 10, 14, 0, 0, 0)

        # Test with various azimuth values that may result in RA < 0 or RA >= 24
        ra1, dec1 = alt_az_to_ra_dec(0.0, 45.0, 40.0, -74.0, dt)
        self.assertGreaterEqual(ra1, 0.0)
        self.assertLess(ra1, 24.0)

        ra2, dec2 = alt_az_to_ra_dec(270.0, 30.0, 40.0, 150.0, dt)
        self.assertGreaterEqual(ra2, 0.0)
        self.assertLess(ra2, 24.0)


if __name__ == "__main__":
    unittest.main()

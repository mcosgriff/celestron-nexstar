"""
Unit tests for utils module.

Tests coordinate conversion and astronomical calculation utilities.
"""

import unittest
from datetime import UTC, datetime

from celestron_nexstar.api.utils import (
    alt_az_to_ra_dec,
    angular_separation,
    calculate_julian_date,
    calculate_lst,
    dec_to_degrees,
    degrees_to_dms,
    format_dec,
    format_position,
    format_ra,
    hours_to_hms,
    ra_dec_to_alt_az,
    ra_to_degrees,
    ra_to_hours,
)


class TestRaToDegrees(unittest.TestCase):
    """Test suite for ra_to_degrees function"""

    def test_ra_to_degrees_hours_only(self):
        """Test RA conversion with hours only"""
        result = ra_to_degrees(12.0)
        self.assertAlmostEqual(result, 180.0, places=5)

        result = ra_to_degrees(0.0)
        self.assertAlmostEqual(result, 0.0, places=5)

        result = ra_to_degrees(24.0)
        self.assertAlmostEqual(result, 360.0, places=5)

    def test_ra_to_degrees_with_minutes(self):
        """Test RA conversion with hours and minutes"""
        result = ra_to_degrees(12, 30)
        self.assertAlmostEqual(result, 187.5, places=5)

        result = ra_to_degrees(6, 15)
        self.assertAlmostEqual(result, 93.75, places=5)

    def test_ra_to_degrees_with_seconds(self):
        """Test RA conversion with hours, minutes, and seconds"""
        result = ra_to_degrees(12, 30, 45)
        expected = 12 + 30 / 60.0 + 45 / 3600.0
        expected_degrees = expected * 15.0  # 15 degrees per hour
        self.assertAlmostEqual(result, expected_degrees, places=5)

    def test_ra_to_degrees_fractional(self):
        """Test RA conversion with fractional hours"""
        result = ra_to_degrees(12.5)
        self.assertAlmostEqual(result, 187.5, places=5)


class TestRaToHours(unittest.TestCase):
    """Test suite for ra_to_hours function"""

    def test_ra_to_hours_hours_only(self):
        """Test RA conversion to hours with hours only"""
        result = ra_to_hours(12.0)
        self.assertEqual(result, 12.0)

        result = ra_to_hours(0.0)
        self.assertEqual(result, 0.0)

    def test_ra_to_hours_with_minutes(self):
        """Test RA conversion to hours with hours and minutes"""
        result = ra_to_hours(12, 30)
        self.assertAlmostEqual(result, 12.5, places=10)

        result = ra_to_hours(6, 15)
        self.assertAlmostEqual(result, 6.25, places=10)

    def test_ra_to_hours_with_seconds(self):
        """Test RA conversion to hours with hours, minutes, and seconds"""
        result = ra_to_hours(12, 30, 45)
        expected = 12 + 30 / 60.0 + 45 / 3600.0
        self.assertAlmostEqual(result, expected, places=10)


class TestDecToDegrees(unittest.TestCase):
    """Test suite for dec_to_degrees function"""

    def test_dec_to_degrees_positive(self):
        """Test Dec conversion with positive sign"""
        result = dec_to_degrees(45.0, sign="+")
        self.assertAlmostEqual(result, 45.0, places=5)

        result = dec_to_degrees(45, 30, sign="+")
        self.assertAlmostEqual(result, 45.5, places=5)

    def test_dec_to_degrees_negative(self):
        """Test Dec conversion with negative sign"""
        result = dec_to_degrees(45.0, sign="-")
        self.assertAlmostEqual(result, -45.0, places=5)

        result = dec_to_degrees(30, 15, sign="-")
        self.assertAlmostEqual(result, -30.25, places=5)

    def test_dec_to_degrees_with_seconds(self):
        """Test Dec conversion with seconds"""
        result = dec_to_degrees(45, 30, 15, sign="+")
        expected = 45 + 30 / 60.0 + 15 / 3600.0
        self.assertAlmostEqual(result, expected, places=5)

    def test_dec_to_degrees_zero(self):
        """Test Dec conversion at zero"""
        result = dec_to_degrees(0.0, sign="+")
        self.assertAlmostEqual(result, 0.0, places=5)


class TestDegreesToDms(unittest.TestCase):
    """Test suite for degrees_to_dms function"""

    def test_degrees_to_dms_positive(self):
        """Test conversion of positive degrees to DMS"""
        degrees, minutes, seconds, sign = degrees_to_dms(45.5)
        self.assertEqual(degrees, 45)
        self.assertEqual(minutes, 30)
        self.assertAlmostEqual(seconds, 0.0, places=1)
        self.assertEqual(sign, "+")

    def test_degrees_to_dms_negative(self):
        """Test conversion of negative degrees to DMS"""
        degrees, minutes, seconds, sign = degrees_to_dms(-45.5)
        self.assertEqual(degrees, 45)
        self.assertEqual(minutes, 30)
        self.assertAlmostEqual(seconds, 0.0, places=1)
        self.assertEqual(sign, "-")

    def test_degrees_to_dms_zero(self):
        """Test conversion of zero degrees"""
        degrees, minutes, seconds, sign = degrees_to_dms(0.0)
        self.assertEqual(degrees, 0)
        self.assertEqual(minutes, 0)
        self.assertAlmostEqual(seconds, 0.0, places=1)
        self.assertEqual(sign, "+")

    def test_degrees_to_dms_large_value(self):
        """Test conversion of large degree values"""
        degrees, _minutes, _seconds, sign = degrees_to_dms(90.0)
        self.assertEqual(degrees, 90)
        self.assertEqual(sign, "+")

    def test_degrees_to_dms_roundtrip(self):
        """Test that degrees_to_dms and dec_to_degrees are approximately inverse"""
        original = 45.5125
        d, m, s, sign = degrees_to_dms(original)
        result = dec_to_degrees(d, m, s, sign)
        self.assertAlmostEqual(result, original, places=5)


class TestHoursToHms(unittest.TestCase):
    """Test suite for hours_to_hms function"""

    def test_hours_to_hms_integer(self):
        """Test conversion of integer hours"""
        hours, minutes, seconds = hours_to_hms(12.0)
        self.assertEqual(hours, 12)
        self.assertEqual(minutes, 0)
        self.assertAlmostEqual(seconds, 0.0, places=1)

    def test_hours_to_hms_fractional(self):
        """Test conversion of fractional hours"""
        hours, minutes, seconds = hours_to_hms(12.5)
        self.assertEqual(hours, 12)
        self.assertEqual(minutes, 30)
        self.assertAlmostEqual(seconds, 0.0, places=1)

    def test_hours_to_hms_with_seconds(self):
        """Test conversion with seconds component"""
        hours, minutes, seconds = hours_to_hms(12.5125)
        self.assertEqual(hours, 12)
        self.assertEqual(minutes, 30)
        self.assertGreater(seconds, 0.0)

    def test_hours_to_hms_zero(self):
        """Test conversion of zero hours"""
        hours, minutes, seconds = hours_to_hms(0.0)
        self.assertEqual(hours, 0)
        self.assertEqual(minutes, 0)
        self.assertAlmostEqual(seconds, 0.0, places=1)

    def test_hours_to_hms_roundtrip(self):
        """Test that hours_to_hms and ra_to_hours are approximately inverse"""
        original = 12.5125
        h, m, s = hours_to_hms(original)
        result = ra_to_hours(h, m, s)
        self.assertAlmostEqual(result, original, places=5)


class TestAltAzToRaDec(unittest.TestCase):
    """Test suite for alt_az_to_ra_dec function"""

    def test_alt_az_to_ra_dec_zenith(self):
        """Test conversion of zenith position"""
        # At zenith (alt=90), RA/Dec should match observer's location
        utc_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        ra, dec = alt_az_to_ra_dec(0.0, 90.0, 40.7128, -74.0060, utc_time)

        # RA/Dec should be valid
        self.assertGreaterEqual(ra, 0.0)
        self.assertLessEqual(ra, 24.0)
        self.assertGreaterEqual(dec, -90.0)
        self.assertLessEqual(dec, 90.0)

    def test_alt_az_to_ra_dec_horizon(self):
        """Test conversion of horizon position"""
        utc_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        ra, dec = alt_az_to_ra_dec(180.0, 0.0, 40.7128, -74.0060, utc_time)

        self.assertGreaterEqual(ra, 0.0)
        self.assertLessEqual(ra, 24.0)
        self.assertGreaterEqual(dec, -90.0)
        self.assertLessEqual(dec, 90.0)

    def test_alt_az_to_ra_dec_roundtrip(self):
        """Test that alt_az_to_ra_dec and ra_dec_to_alt_az are approximately inverse"""
        utc_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        original_az = 180.0
        original_alt = 45.0
        lat = 40.7128
        lon = -74.0060

        ra, dec = alt_az_to_ra_dec(original_az, original_alt, lat, lon, utc_time)
        az, alt = ra_dec_to_alt_az(ra, dec, lat, lon, utc_time)

        # Should be approximately equal (within 0.1 degrees due to coordinate system differences)
        self.assertAlmostEqual(az, original_az, delta=0.1)
        self.assertAlmostEqual(alt, original_alt, delta=0.1)


class TestRaDecToAltAz(unittest.TestCase):
    """Test suite for ra_dec_to_alt_az function"""

    def test_ra_dec_to_alt_az_basic(self):
        """Test basic RA/Dec to Alt/Az conversion"""
        utc_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        az, alt = ra_dec_to_alt_az(12.0, 45.0, 40.7128, -74.0060, utc_time)

        self.assertGreaterEqual(az, 0.0)
        self.assertLessEqual(az, 360.0)
        self.assertGreaterEqual(alt, -90.0)
        self.assertLessEqual(alt, 90.0)

    def test_ra_dec_to_alt_az_pole(self):
        """Test conversion of pole position"""
        utc_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        _az, alt = ra_dec_to_alt_az(0.0, 90.0, 40.7128, -74.0060, utc_time)

        # North celestial pole should be at high altitude for northern observer
        self.assertGreater(alt, 0.0)

    def test_ra_dec_to_alt_az_equator(self):
        """Test conversion of equatorial position"""
        utc_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        az, alt = ra_dec_to_alt_az(12.0, 0.0, 0.0, 0.0, utc_time)

        self.assertGreaterEqual(az, 0.0)
        self.assertLessEqual(az, 360.0)
        self.assertGreaterEqual(alt, -90.0)
        self.assertLessEqual(alt, 90.0)


class TestCalculateLst(unittest.TestCase):
    """Test suite for calculate_lst function"""

    def test_calculate_lst_basic(self):
        """Test basic LST calculation"""
        utc_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        lst = calculate_lst(0.0, utc_time)  # Prime meridian

        self.assertGreaterEqual(lst, 0.0)
        self.assertLessEqual(lst, 24.0)

    def test_calculate_lst_different_longitudes(self):
        """Test LST calculation for different longitudes"""
        utc_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

        lst_0 = calculate_lst(0.0, utc_time)
        lst_west = calculate_lst(-74.0060, utc_time)  # New York
        lst_east = calculate_lst(2.3522, utc_time)  # Paris

        # All should be valid
        self.assertGreaterEqual(lst_0, 0.0)
        self.assertLessEqual(lst_0, 24.0)
        self.assertGreaterEqual(lst_west, 0.0)
        self.assertLessEqual(lst_west, 24.0)
        self.assertGreaterEqual(lst_east, 0.0)
        self.assertLessEqual(lst_east, 24.0)

        # LST should differ based on longitude
        # West longitude should have earlier LST
        self.assertLess(lst_west, lst_0 + 0.1)  # Allow small tolerance

    def test_calculate_lst_different_times(self):
        """Test LST calculation for different times"""
        longitude = 0.0

        time1 = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        time2 = datetime(2024, 6, 15, 13, 0, 0, tzinfo=UTC)

        lst1 = calculate_lst(longitude, time1)
        lst2 = calculate_lst(longitude, time2)

        # LST should increase with time (approximately 1 hour per hour)
        self.assertGreater(lst2, lst1)


class TestCalculateJulianDate(unittest.TestCase):
    """Test suite for calculate_julian_date function"""

    def test_calculate_julian_date_basic(self):
        """Test basic Julian Date calculation"""
        dt = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        jd = calculate_julian_date(dt)

        # Julian Date for 2024-06-15 should be around 2460470
        self.assertGreater(jd, 2460000)
        self.assertLess(jd, 2470000)

    def test_calculate_julian_date_known_date(self):
        """Test Julian Date for a known date"""
        # January 1, 2000 12:00 UTC = JD 2451545.0
        dt = datetime(2000, 1, 1, 12, 0, 0, tzinfo=UTC)
        jd = calculate_julian_date(dt)

        self.assertAlmostEqual(jd, 2451545.0, places=1)

    def test_calculate_julian_date_ordering(self):
        """Test that later dates have larger Julian Dates"""
        dt1 = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        dt2 = datetime(2024, 6, 16, 12, 0, 0, tzinfo=UTC)

        jd1 = calculate_julian_date(dt1)
        jd2 = calculate_julian_date(dt2)

        self.assertGreater(jd2, jd1)
        self.assertAlmostEqual(jd2 - jd1, 1.0, places=2)


class TestAngularSeparation(unittest.TestCase):
    """Test suite for angular_separation function"""

    def test_angular_separation_same_point(self):
        """Test angular separation of same point"""
        result = angular_separation(12.0, 45.0, 12.0, 45.0)
        self.assertAlmostEqual(result, 0.0, places=5)

    def test_angular_separation_close_points(self):
        """Test angular separation of close points"""
        # Two points 1 degree apart in declination
        result = angular_separation(12.0, 45.0, 12.0, 46.0)
        self.assertAlmostEqual(result, 1.0, places=2)

    def test_angular_separation_opposite_points(self):
        """Test angular separation of opposite points"""
        # North pole and south pole
        result = angular_separation(0.0, 90.0, 0.0, -90.0)
        self.assertAlmostEqual(result, 180.0, places=2)

    def test_angular_separation_known_separation(self):
        """Test angular separation with known values"""
        # Points 90 degrees apart
        result = angular_separation(0.0, 0.0, 6.0, 0.0)  # 6 hours = 90 degrees
        self.assertAlmostEqual(result, 90.0, places=2)


class TestFormatRa(unittest.TestCase):
    """Test suite for format_ra function"""

    def test_format_ra_basic(self):
        """Test basic RA formatting"""
        result = format_ra(12.0)
        self.assertIn("12h", result)
        self.assertIn("m", result)
        self.assertIn("s", result)

    def test_format_ra_with_minutes(self):
        """Test RA formatting with minutes"""
        result = format_ra(12.5)
        self.assertIn("12h", result)
        self.assertIn("30m", result)

    def test_format_ra_precision(self):
        """Test RA formatting with different precision"""
        result1 = format_ra(12.5125, precision=1)
        result2 = format_ra(12.5125, precision=3)

        # Higher precision should have more decimal places
        self.assertIsInstance(result1, str)
        self.assertIsInstance(result2, str)


class TestFormatDec(unittest.TestCase):
    """Test suite for format_dec function"""

    def test_format_dec_positive(self):
        """Test Dec formatting for positive values"""
        result = format_dec(45.0)
        self.assertIn("+", result)
        self.assertIn("°", result)
        self.assertIn("'", result)
        self.assertIn('"', result)

    def test_format_dec_negative(self):
        """Test Dec formatting for negative values"""
        result = format_dec(-45.0)
        self.assertIn("-", result)
        self.assertIn("°", result)

    def test_format_dec_zero(self):
        """Test Dec formatting for zero"""
        result = format_dec(0.0)
        self.assertIn("+", result)
        self.assertIn("00°", result)

    def test_format_dec_precision(self):
        """Test Dec formatting with different precision"""
        result1 = format_dec(45.5125, precision=1)
        result2 = format_dec(45.5125, precision=3)

        self.assertIsInstance(result1, str)
        self.assertIsInstance(result2, str)


class TestFormatPosition(unittest.TestCase):
    """Test suite for format_position function"""

    def test_format_position_basic(self):
        """Test basic position formatting"""
        result = format_position(12.0, 45.0)
        self.assertIn("RA:", result)
        self.assertIn("Dec:", result)
        self.assertIn("12h", result)

    def test_format_position_negative_dec(self):
        """Test position formatting with negative declination"""
        result = format_position(12.0, -45.0)
        self.assertIn("RA:", result)
        self.assertIn("Dec:", result)
        self.assertIn("-", result)


if __name__ == "__main__":
    unittest.main()

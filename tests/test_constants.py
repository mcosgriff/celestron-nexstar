"""
Unit tests for constants module.

Tests all physical and astronomical constants used throughout the API.
"""

import unittest

from celestron_nexstar.api.core.constants import (
    ARCSEC_PER_ARCMIN,
    ARCSEC_PER_DEGREE,
    DEGREES_PER_HOUR_ANGLE,
    HUMAN_EYE_PUPIL_MM,
    MM_PER_INCH,
)


class TestConstants(unittest.TestCase):
    """Test suite for constants module"""

    def test_mm_per_inch(self):
        """Test millimeters per inch conversion factor"""
        self.assertEqual(MM_PER_INCH, 25.4)
        self.assertIsInstance(MM_PER_INCH, float)

    def test_arcsec_per_degree(self):
        """Test arcseconds per degree conversion factor"""
        self.assertEqual(ARCSEC_PER_DEGREE, 3600.0)
        self.assertIsInstance(ARCSEC_PER_DEGREE, float)
        # Verify: 1 degree = 60 arcminutes = 3600 arcseconds
        self.assertEqual(ARCSEC_PER_DEGREE, 60.0 * 60.0)

    def test_arcsec_per_arcmin(self):
        """Test arcseconds per arcminute conversion factor"""
        self.assertEqual(ARCSEC_PER_ARCMIN, 60.0)
        self.assertIsInstance(ARCSEC_PER_ARCMIN, float)
        # Verify relationship with ARCSEC_PER_DEGREE
        self.assertEqual(ARCSEC_PER_DEGREE, ARCSEC_PER_ARCMIN * 60.0)

    def test_degrees_per_hour_angle(self):
        """Test degrees per hour angle (RA conversion)"""
        self.assertEqual(DEGREES_PER_HOUR_ANGLE, 15.0)
        self.assertIsInstance(DEGREES_PER_HOUR_ANGLE, float)
        # Verify: 24 hours = 360 degrees, so 1 hour = 15 degrees
        self.assertEqual(DEGREES_PER_HOUR_ANGLE, 360.0 / 24.0)

    def test_human_eye_pupil_mm(self):
        """Test average dark-adapted human eye pupil diameter"""
        self.assertEqual(HUMAN_EYE_PUPIL_MM, 7.0)
        self.assertIsInstance(HUMAN_EYE_PUPIL_MM, float)
        # Verify it's a reasonable value (typically 5-8mm for dark-adapted eye)
        self.assertGreaterEqual(HUMAN_EYE_PUPIL_MM, 5.0)
        self.assertLessEqual(HUMAN_EYE_PUPIL_MM, 8.0)

    def test_constants_are_final(self):
        """Test that constants are properly typed as Final"""
        # This is more of a type-checking test, but we can verify values don't change
        original_values = {
            "MM_PER_INCH": MM_PER_INCH,
            "ARCSEC_PER_DEGREE": ARCSEC_PER_DEGREE,
            "ARCSEC_PER_ARCMIN": ARCSEC_PER_ARCMIN,
            "DEGREES_PER_HOUR_ANGLE": DEGREES_PER_HOUR_ANGLE,
            "HUMAN_EYE_PUPIL_MM": HUMAN_EYE_PUPIL_MM,
        }
        # Re-import to ensure values are consistent
        import celestron_nexstar.api.core.constants as constants_module

        self.assertEqual(constants_module.MM_PER_INCH, original_values["MM_PER_INCH"])
        self.assertEqual(constants_module.ARCSEC_PER_DEGREE, original_values["ARCSEC_PER_DEGREE"])
        self.assertEqual(constants_module.ARCSEC_PER_ARCMIN, original_values["ARCSEC_PER_ARCMIN"])
        self.assertEqual(constants_module.DEGREES_PER_HOUR_ANGLE, original_values["DEGREES_PER_HOUR_ANGLE"])
        self.assertEqual(constants_module.HUMAN_EYE_PUPIL_MM, original_values["HUMAN_EYE_PUPIL_MM"])


if __name__ == "__main__":
    unittest.main()

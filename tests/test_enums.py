"""
Unit tests for enums module.

Tests all enumeration classes used throughout the API.
"""

import unittest

from celestron_nexstar.api.enums import (
    Axis,
    CelestialObjectType,
    Direction,
    EphemerisSet,
    MoonPhase,
    OutputFormat,
    SkyBrightness,
    TrackingMode,
)


class TestSkyBrightness(unittest.TestCase):
    """Test suite for SkyBrightness enum"""

    def test_enum_values(self):
        """Test all SkyBrightness enum values"""
        self.assertEqual(SkyBrightness.EXCELLENT, "excellent")
        self.assertEqual(SkyBrightness.GOOD, "good")
        self.assertEqual(SkyBrightness.FAIR, "fair")
        self.assertEqual(SkyBrightness.POOR, "poor")
        self.assertEqual(SkyBrightness.URBAN, "urban")

    def test_enum_membership(self):
        """Test enum membership"""
        self.assertIn("excellent", SkyBrightness)
        self.assertIn("good", SkyBrightness)
        self.assertIn("fair", SkyBrightness)
        self.assertIn("poor", SkyBrightness)
        self.assertIn("urban", SkyBrightness)

    def test_enum_string_representation(self):
        """Test string representation of enum values"""
        self.assertEqual(str(SkyBrightness.EXCELLENT), "excellent")
        self.assertEqual(str(SkyBrightness.GOOD), "good")


class TestCelestialObjectType(unittest.TestCase):
    """Test suite for CelestialObjectType enum"""

    def test_enum_values(self):
        """Test all CelestialObjectType enum values"""
        self.assertEqual(CelestialObjectType.STAR, "star")
        self.assertEqual(CelestialObjectType.PLANET, "planet")
        self.assertEqual(CelestialObjectType.GALAXY, "galaxy")
        self.assertEqual(CelestialObjectType.NEBULA, "nebula")
        self.assertEqual(CelestialObjectType.CLUSTER, "cluster")
        self.assertEqual(CelestialObjectType.DOUBLE_STAR, "double_star")
        self.assertEqual(CelestialObjectType.ASTERISM, "asterism")
        self.assertEqual(CelestialObjectType.CONSTELLATION, "constellation")
        self.assertEqual(CelestialObjectType.MOON, "moon")

    def test_enum_membership(self):
        """Test enum membership"""
        self.assertIn("star", CelestialObjectType)
        self.assertIn("planet", CelestialObjectType)
        self.assertIn("galaxy", CelestialObjectType)
        self.assertIn("nebula", CelestialObjectType)
        self.assertIn("cluster", CelestialObjectType)
        self.assertIn("double_star", CelestialObjectType)
        self.assertIn("asterism", CelestialObjectType)
        self.assertIn("constellation", CelestialObjectType)
        self.assertIn("moon", CelestialObjectType)


class TestEphemerisSet(unittest.TestCase):
    """Test suite for EphemerisSet enum"""

    def test_enum_values(self):
        """Test all EphemerisSet enum values"""
        self.assertEqual(EphemerisSet.MINIMAL, "minimal")
        self.assertEqual(EphemerisSet.STANDARD, "standard")
        self.assertEqual(EphemerisSet.COMPLETE, "complete")
        self.assertEqual(EphemerisSet.FULL, "full")

    def test_enum_membership(self):
        """Test enum membership"""
        self.assertIn("minimal", EphemerisSet)
        self.assertIn("standard", EphemerisSet)
        self.assertIn("complete", EphemerisSet)
        self.assertIn("full", EphemerisSet)


class TestDirection(unittest.TestCase):
    """Test suite for Direction enum"""

    def test_enum_values(self):
        """Test all Direction enum values"""
        self.assertEqual(Direction.UP, "up")
        self.assertEqual(Direction.DOWN, "down")
        self.assertEqual(Direction.LEFT, "left")
        self.assertEqual(Direction.RIGHT, "right")

    def test_enum_membership(self):
        """Test enum membership"""
        self.assertIn("up", Direction)
        self.assertIn("down", Direction)
        self.assertIn("left", Direction)
        self.assertIn("right", Direction)


class TestAxis(unittest.TestCase):
    """Test suite for Axis enum"""

    def test_enum_values(self):
        """Test all Axis enum values"""
        self.assertEqual(Axis.AZ, "az")
        self.assertEqual(Axis.ALT, "alt")
        self.assertEqual(Axis.BOTH, "both")

    def test_enum_membership(self):
        """Test enum membership"""
        self.assertIn("az", Axis)
        self.assertIn("alt", Axis)
        self.assertIn("both", Axis)


class TestTrackingMode(unittest.TestCase):
    """Test suite for TrackingMode enum"""

    def test_enum_values(self):
        """Test all TrackingMode enum values"""
        self.assertEqual(TrackingMode.ALT_AZ, "alt-az")
        self.assertEqual(TrackingMode.EQ_NORTH, "eq-north")
        self.assertEqual(TrackingMode.EQ_SOUTH, "eq-south")

    def test_enum_membership(self):
        """Test enum membership"""
        self.assertIn("alt-az", TrackingMode)
        self.assertIn("eq-north", TrackingMode)
        self.assertIn("eq-south", TrackingMode)


class TestOutputFormat(unittest.TestCase):
    """Test suite for OutputFormat enum"""

    def test_enum_values(self):
        """Test all OutputFormat enum values"""
        self.assertEqual(OutputFormat.PRETTY, "pretty")
        self.assertEqual(OutputFormat.JSON, "json")
        self.assertEqual(OutputFormat.CSV, "csv")
        self.assertEqual(OutputFormat.DMS, "dms")
        self.assertEqual(OutputFormat.HMS, "hms")

    def test_enum_membership(self):
        """Test enum membership"""
        self.assertIn("pretty", OutputFormat)
        self.assertIn("json", OutputFormat)
        self.assertIn("csv", OutputFormat)
        self.assertIn("dms", OutputFormat)
        self.assertIn("hms", OutputFormat)


class TestMoonPhase(unittest.TestCase):
    """Test suite for MoonPhase enum"""

    def test_enum_values(self):
        """Test all MoonPhase enum values"""
        self.assertEqual(MoonPhase.NEW_MOON, "New Moon")
        self.assertEqual(MoonPhase.WAXING_CRESCENT, "Waxing Crescent")
        self.assertEqual(MoonPhase.FIRST_QUARTER, "First Quarter")
        self.assertEqual(MoonPhase.WAXING_GIBBOUS, "Waxing Gibbous")
        self.assertEqual(MoonPhase.FULL_MOON, "Full Moon")
        self.assertEqual(MoonPhase.WANING_GIBBOUS, "Waning Gibbous")
        self.assertEqual(MoonPhase.LAST_QUARTER, "Last Quarter")
        self.assertEqual(MoonPhase.WANING_CRESCENT, "Waning Crescent")

    def test_enum_membership(self):
        """Test enum membership"""
        self.assertIn("New Moon", MoonPhase)
        self.assertIn("Waxing Crescent", MoonPhase)
        self.assertIn("First Quarter", MoonPhase)
        self.assertIn("Waxing Gibbous", MoonPhase)
        self.assertIn("Full Moon", MoonPhase)
        self.assertIn("Waning Gibbous", MoonPhase)
        self.assertIn("Last Quarter", MoonPhase)
        self.assertIn("Waning Crescent", MoonPhase)

    def test_enum_string_representation(self):
        """Test string representation of moon phases"""
        self.assertEqual(str(MoonPhase.NEW_MOON), "New Moon")
        self.assertEqual(str(MoonPhase.FULL_MOON), "Full Moon")


class TestEnumInheritance(unittest.TestCase):
    """Test that all enums inherit from StrEnum"""

    def test_sky_brightness_is_str_enum(self):
        """Test SkyBrightness is a StrEnum"""
        self.assertIsInstance(SkyBrightness.EXCELLENT, str)
        from enum import StrEnum

        self.assertTrue(issubclass(SkyBrightness, StrEnum))

    def test_celestial_object_type_is_str_enum(self):
        """Test CelestialObjectType is a StrEnum"""
        self.assertIsInstance(CelestialObjectType.STAR, str)
        from enum import StrEnum

        self.assertTrue(issubclass(CelestialObjectType, StrEnum))

    def test_all_enums_are_strings(self):
        """Test that all enum values are strings"""
        from enum import StrEnum

        self.assertIsInstance(SkyBrightness.EXCELLENT, str)
        self.assertIsInstance(CelestialObjectType.STAR, str)
        self.assertIsInstance(EphemerisSet.MINIMAL, str)
        self.assertIsInstance(Direction.UP, str)
        self.assertIsInstance(Axis.AZ, str)
        self.assertIsInstance(TrackingMode.ALT_AZ, str)
        self.assertIsInstance(OutputFormat.PRETTY, str)
        self.assertIsInstance(MoonPhase.NEW_MOON, str)

        # Verify all enums inherit from StrEnum
        self.assertTrue(issubclass(SkyBrightness, StrEnum))
        self.assertTrue(issubclass(CelestialObjectType, StrEnum))
        self.assertTrue(issubclass(EphemerisSet, StrEnum))
        self.assertTrue(issubclass(Direction, StrEnum))
        self.assertTrue(issubclass(Axis, StrEnum))
        self.assertTrue(issubclass(TrackingMode, StrEnum))
        self.assertTrue(issubclass(OutputFormat, StrEnum))
        self.assertTrue(issubclass(MoonPhase, StrEnum))


if __name__ == "__main__":
    unittest.main()

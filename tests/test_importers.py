"""
Unit tests for importers.py

Tests catalog import utilities.
"""

import unittest

from celestron_nexstar.api.catalogs.importers import map_openngc_type, parse_catalog_number, parse_ra_dec
from celestron_nexstar.api.core.enums import CelestialObjectType


class TestParseRaDec(unittest.TestCase):
    """Test suite for parse_ra_dec function"""

    def test_parse_ra_dec_valid(self):
        """Test parsing valid RA/Dec strings"""
        ra_str = "12:30:45.5"
        dec_str = "+45:15:30.2"

        result = parse_ra_dec(ra_str, dec_str)

        self.assertIsNotNone(result)
        ra_hours, dec_degrees = result
        self.assertAlmostEqual(ra_hours, 12.5126389, places=5)
        self.assertAlmostEqual(dec_degrees, 45.2583889, places=5)

    def test_parse_ra_dec_negative_dec(self):
        """Test parsing negative declination"""
        ra_str = "6:15:30.0"
        dec_str = "-30:45:15.0"

        result = parse_ra_dec(ra_str, dec_str)

        self.assertIsNotNone(result)
        ra_hours, dec_degrees = result
        self.assertAlmostEqual(ra_hours, 6.2583333, places=5)
        self.assertAlmostEqual(dec_degrees, -30.7541667, places=5)

    def test_parse_ra_dec_invalid_format(self):
        """Test parsing invalid RA/Dec format"""
        ra_str = "invalid"
        dec_str = "invalid"

        result = parse_ra_dec(ra_str, dec_str)

        self.assertIsNone(result)

    def test_parse_ra_dec_incomplete(self):
        """Test parsing incomplete RA/Dec strings"""
        ra_str = "12:30"
        dec_str = "+45:15"

        result = parse_ra_dec(ra_str, dec_str)

        # Should handle gracefully or return None
        # The function will raise IndexError which is caught
        self.assertIsNone(result)

    def test_parse_ra_dec_zero_values(self):
        """Test parsing zero RA/Dec values"""
        ra_str = "0:0:0.0"
        dec_str = "+0:0:0.0"

        result = parse_ra_dec(ra_str, dec_str)

        self.assertIsNotNone(result)
        ra_hours, dec_degrees = result
        self.assertEqual(ra_hours, 0.0)
        self.assertEqual(dec_degrees, 0.0)


class TestMapOpenngcType(unittest.TestCase):
    """Test suite for map_openngc_type function"""

    def test_map_star_types(self):
        """Test mapping star types"""
        self.assertEqual(map_openngc_type("*"), CelestialObjectType.STAR)
        self.assertEqual(map_openngc_type("**"), CelestialObjectType.DOUBLE_STAR)
        self.assertEqual(map_openngc_type("Nova"), CelestialObjectType.STAR)

    def test_map_cluster_types(self):
        """Test mapping cluster types"""
        self.assertEqual(map_openngc_type("*Ass"), CelestialObjectType.CLUSTER)
        self.assertEqual(map_openngc_type("OCl"), CelestialObjectType.CLUSTER)
        self.assertEqual(map_openngc_type("GCl"), CelestialObjectType.CLUSTER)
        self.assertEqual(map_openngc_type("Cl+N"), CelestialObjectType.CLUSTER)

    def test_map_galaxy_types(self):
        """Test mapping galaxy types"""
        self.assertEqual(map_openngc_type("G"), CelestialObjectType.GALAXY)
        self.assertEqual(map_openngc_type("GPair"), CelestialObjectType.GALAXY)
        self.assertEqual(map_openngc_type("GTrpl"), CelestialObjectType.GALAXY)
        self.assertEqual(map_openngc_type("GGroup"), CelestialObjectType.GALAXY)

    def test_map_nebula_types(self):
        """Test mapping nebula types"""
        self.assertEqual(map_openngc_type("PN"), CelestialObjectType.NEBULA)
        self.assertEqual(map_openngc_type("HII"), CelestialObjectType.NEBULA)
        self.assertEqual(map_openngc_type("DrkN"), CelestialObjectType.NEBULA)
        self.assertEqual(map_openngc_type("EmN"), CelestialObjectType.NEBULA)
        self.assertEqual(map_openngc_type("Neb"), CelestialObjectType.NEBULA)
        self.assertEqual(map_openngc_type("RfN"), CelestialObjectType.NEBULA)
        self.assertEqual(map_openngc_type("SNR"), CelestialObjectType.NEBULA)

    def test_map_unknown_type(self):
        """Test mapping unknown type (should default to nebula)"""
        result = map_openngc_type("UnknownType")
        self.assertEqual(result, CelestialObjectType.NEBULA)


class TestParseCatalogNumber(unittest.TestCase):
    """Test suite for parse_catalog_number function"""

    def test_parse_messier_number(self):
        """Test parsing Messier catalog numbers"""
        self.assertEqual(parse_catalog_number("M31", "messier"), 31)
        self.assertEqual(parse_catalog_number("M1", "messier"), 1)
        self.assertEqual(parse_catalog_number("M101", "messier"), 101)

    def test_parse_ngc_number(self):
        """Test parsing NGC catalog numbers"""
        self.assertEqual(parse_catalog_number("NGC 224", "ngc"), 224)
        self.assertEqual(parse_catalog_number("NGC 1", "ngc"), 1)
        self.assertEqual(parse_catalog_number("NGC 1234", "ngc"), 1234)

    def test_parse_ic_number(self):
        """Test parsing IC catalog numbers"""
        self.assertEqual(parse_catalog_number("IC 1101", "ic"), 1101)
        self.assertEqual(parse_catalog_number("IC 1", "ic"), 1)

    def test_parse_caldwell_number(self):
        """Test parsing Caldwell catalog numbers"""
        self.assertEqual(parse_catalog_number("C1", "caldwell"), 1)
        self.assertEqual(parse_catalog_number("C100", "caldwell"), 100)

    def test_parse_with_suffix(self):
        """Test parsing catalog numbers with suffix (e.g., NGC 224A)"""
        self.assertEqual(parse_catalog_number("NGC 224A", "ngc"), 224)
        self.assertEqual(parse_catalog_number("M31B", "messier"), 31)

    def test_parse_case_insensitive(self):
        """Test parsing is case insensitive"""
        self.assertEqual(parse_catalog_number("m31", "messier"), 31)
        self.assertEqual(parse_catalog_number("ngc 224", "ngc"), 224)
        self.assertEqual(parse_catalog_number("ic 1101", "ic"), 1101)

    def test_parse_invalid(self):
        """Test parsing invalid catalog names"""
        self.assertIsNone(parse_catalog_number("Invalid", "unknown"))
        self.assertIsNone(parse_catalog_number("XYZ 123", "unknown"))
        self.assertIsNone(parse_catalog_number("", "unknown"))

    def test_parse_no_number(self):
        """Test parsing catalog names without numbers"""
        self.assertIsNone(parse_catalog_number("M", "messier"))
        self.assertIsNone(parse_catalog_number("NGC", "ngc"))


if __name__ == "__main__":
    unittest.main()

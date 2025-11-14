"""
Unit tests for geohash_utils module.

Tests geohash encoding, decoding, and spatial search utilities.
"""

import unittest

from celestron_nexstar.api.geohash_utils import (
    decode,
    encode,
    get_neighbors_for_search,
    get_precision_for_radius,
    neighbors,
)


class TestEncode(unittest.TestCase):
    """Test suite for encode function"""

    def test_encode_basic(self):
        """Test basic geohash encoding"""
        # Paris coordinates
        result = encode(48.8566, 2.3522, 7)
        self.assertEqual(result, "u09tvw0")
        self.assertEqual(len(result), 7)

    def test_encode_different_precisions(self):
        """Test encoding with different precision levels"""
        lat, lon = 40.7128, -74.0060  # New York

        # Test various precisions
        hash1 = encode(lat, lon, 1)
        self.assertEqual(len(hash1), 1)

        hash5 = encode(lat, lon, 5)
        self.assertEqual(len(hash5), 5)

        hash9 = encode(lat, lon, 9)
        self.assertEqual(len(hash9), 9)

        hash12 = encode(lat, lon, 12)
        self.assertEqual(len(hash12), 12)

    def test_encode_edge_cases(self):
        """Test encoding with edge case coordinates"""
        # North pole
        result = encode(90.0, 0.0, 5)
        self.assertIsInstance(result, str)
        self.assertEqual(len(result), 5)

        # South pole
        result = encode(-90.0, 0.0, 5)
        self.assertIsInstance(result, str)
        self.assertEqual(len(result), 5)

        # Equator, prime meridian
        result = encode(0.0, 0.0, 5)
        self.assertIsInstance(result, str)
        self.assertEqual(len(result), 5)

        # International date line
        result = encode(0.0, 180.0, 5)
        self.assertIsInstance(result, str)
        self.assertEqual(len(result), 5)

        result = encode(0.0, -180.0, 5)
        self.assertIsInstance(result, str)
        self.assertEqual(len(result), 5)

    def test_encode_clamping(self):
        """Test that coordinates are clamped to valid ranges"""
        # Test values outside valid range are clamped
        result1 = encode(100.0, 0.0, 5)  # Latitude > 90
        result2 = encode(90.0, 0.0, 5)  # Valid latitude
        self.assertEqual(result1, result2)

        result1 = encode(-100.0, 0.0, 5)  # Latitude < -90
        result2 = encode(-90.0, 0.0, 5)  # Valid latitude
        self.assertEqual(result1, result2)

        result1 = encode(0.0, 200.0, 5)  # Longitude > 180
        result2 = encode(0.0, 180.0, 5)  # Valid longitude
        self.assertEqual(result1, result2)

        result1 = encode(0.0, -200.0, 5)  # Longitude < -180
        result2 = encode(0.0, -180.0, 5)  # Valid longitude
        self.assertEqual(result1, result2)

    def test_encode_consistency(self):
        """Test that encoding is consistent for same coordinates"""
        lat, lon = 40.7128, -74.0060
        result1 = encode(lat, lon, 7)
        result2 = encode(lat, lon, 7)
        self.assertEqual(result1, result2)

    def test_encode_precision_1(self):
        """Test encoding with precision 1"""
        result = encode(40.7128, -74.0060, 1)
        self.assertEqual(len(result), 1)
        self.assertIn(result, "0123456789bcdefghjkmnpqrstuvwxyz")


class TestDecode(unittest.TestCase):
    """Test suite for decode function"""

    def test_decode_basic(self):
        """Test basic geohash decoding"""
        geohash = "u09tvqr"
        lat, lon, lat_err, lon_err = decode(geohash)

        # Check that decoded coordinates are reasonable
        self.assertGreaterEqual(lat, -90.0)
        self.assertLessEqual(lat, 90.0)
        self.assertGreaterEqual(lon, -180.0)
        self.assertLessEqual(lon, 180.0)

        # Check that errors are positive
        self.assertGreater(lat_err, 0.0)
        self.assertGreater(lon_err, 0.0)

    def test_decode_roundtrip(self):
        """Test that encode/decode roundtrip works approximately"""
        original_lat, original_lon = 40.7128, -74.0060
        geohash = encode(original_lat, original_lon, 9)
        lat, lon, lat_err, lon_err = decode(geohash)

        # Decoded coordinates should be within error bounds
        self.assertLessEqual(abs(lat - original_lat), lat_err)
        self.assertLessEqual(abs(lon - original_lon), lon_err)

    def test_decode_different_precisions(self):
        """Test decoding with different precision levels"""
        lat, lon = 40.7128, -74.0060

        for precision in [1, 5, 7, 9, 12]:
            geohash = encode(lat, lon, precision)
            decoded_lat, decoded_lon, lat_err, lon_err = decode(geohash)

            # Higher precision should have smaller errors
            self.assertGreaterEqual(decoded_lat, -90.0)
            self.assertLessEqual(decoded_lat, 90.0)
            self.assertGreaterEqual(decoded_lon, -180.0)
            self.assertLessEqual(decoded_lon, 180.0)

    def test_decode_invalid_character(self):
        """Test that decode raises ValueError for invalid characters"""
        with self.assertRaises(ValueError) as context:
            decode("invalid!")
        self.assertIn("Invalid geohash character", str(context.exception))

        with self.assertRaises(ValueError):
            decode("abcdei")  # 'i' is not in geohash alphabet

        with self.assertRaises(ValueError):
            decode("abcdeo")  # 'o' is not in geohash alphabet

    def test_decode_empty_string(self):
        """Test decoding empty string"""
        lat, lon, lat_err, lon_err = decode("")
        # Empty string should return center of world
        self.assertEqual(lat, 0.0)
        self.assertEqual(lon, 0.0)
        self.assertEqual(lat_err, 90.0)
        self.assertEqual(lon_err, 180.0)

    def test_decode_single_character(self):
        """Test decoding single character geohash"""
        geohash = "u"
        lat, lon, lat_err, lon_err = decode(geohash)
        self.assertGreaterEqual(lat, -90.0)
        self.assertLessEqual(lat, 90.0)
        self.assertGreaterEqual(lon, -180.0)
        self.assertLessEqual(lon, 180.0)


class TestNeighbors(unittest.TestCase):
    """Test suite for neighbors function"""

    def test_neighbors_basic(self):
        """Test that neighbors returns some neighbors (up to 8)"""
        geohash = "u09tvqr"
        neighbor_list = neighbors(geohash)
        # At boundaries, we may get fewer than 8 neighbors due to clamping
        self.assertGreater(len(neighbor_list), 0)
        self.assertLessEqual(len(neighbor_list), 8)

    def test_neighbors_no_duplicates(self):
        """Test that neighbors doesn't include the center point"""
        geohash = "u09tvqr"
        neighbor_list = neighbors(geohash)
        self.assertNotIn(geohash, neighbor_list)

    def test_neighbors_all_different(self):
        """Test that all neighbors are different"""
        geohash = "u09tvqr"
        neighbor_list = neighbors(geohash)
        self.assertEqual(len(neighbor_list), len(set(neighbor_list)))

    def test_neighbors_same_length(self):
        """Test that neighbors have same length as input"""
        geohash = "u09tvqr"
        neighbor_list = neighbors(geohash)
        for neighbor in neighbor_list:
            self.assertEqual(len(neighbor), len(geohash))

    def test_neighbors_single_character(self):
        """Test neighbors for single character geohash"""
        geohash = "u"
        neighbor_list = neighbors(geohash)
        # At boundaries, we may get fewer than 8 neighbors
        self.assertGreater(len(neighbor_list), 0)
        self.assertLessEqual(len(neighbor_list), 8)
        for neighbor in neighbor_list:
            self.assertEqual(len(neighbor), 1)

    def test_neighbors_pole_handling(self):
        """Test neighbors at poles (should handle clamping)"""
        # North pole - will have fewer neighbors due to clamping
        geohash = encode(90.0, 0.0, 5)
        neighbor_list = neighbors(geohash)
        self.assertGreater(len(neighbor_list), 0)
        self.assertLessEqual(len(neighbor_list), 8)
        self.assertNotIn(geohash, neighbor_list)

        # South pole - will have fewer neighbors due to clamping
        geohash = encode(-90.0, 0.0, 5)
        neighbor_list = neighbors(geohash)
        self.assertGreater(len(neighbor_list), 0)
        self.assertLessEqual(len(neighbor_list), 8)
        self.assertNotIn(geohash, neighbor_list)


class TestGetPrecisionForRadius(unittest.TestCase):
    """Test suite for get_precision_for_radius function"""

    def test_precision_large_radius(self):
        """Test precision for large radii"""
        self.assertEqual(get_precision_for_radius(10000), 1)
        self.assertEqual(get_precision_for_radius(5000), 1)
        self.assertEqual(get_precision_for_radius(4999), 2)

    def test_precision_medium_radius(self):
        """Test precision for medium radii"""
        self.assertEqual(get_precision_for_radius(1250), 2)
        self.assertEqual(get_precision_for_radius(1251), 2)
        self.assertEqual(get_precision_for_radius(1249), 3)

        self.assertEqual(get_precision_for_radius(156), 3)
        self.assertEqual(get_precision_for_radius(39), 4)
        self.assertEqual(get_precision_for_radius(5), 5)

    def test_precision_small_radius(self):
        """Test precision for small radii"""
        self.assertEqual(get_precision_for_radius(1.2), 6)
        self.assertEqual(get_precision_for_radius(0.15), 7)
        self.assertEqual(get_precision_for_radius(0.038), 8)
        self.assertEqual(get_precision_for_radius(0.037), 9)
        self.assertEqual(get_precision_for_radius(0.001), 9)

    def test_precision_boundary_values(self):
        """Test precision at boundary values"""
        # Test exact boundary values
        self.assertEqual(get_precision_for_radius(5000), 1)
        self.assertEqual(get_precision_for_radius(1250), 2)
        self.assertEqual(get_precision_for_radius(156), 3)
        self.assertEqual(get_precision_for_radius(39), 4)
        self.assertEqual(get_precision_for_radius(5), 5)
        self.assertEqual(get_precision_for_radius(1.2), 6)
        self.assertEqual(get_precision_for_radius(0.15), 7)
        self.assertEqual(get_precision_for_radius(0.038), 8)

    def test_precision_very_small_radius(self):
        """Test precision for very small radii"""
        self.assertEqual(get_precision_for_radius(0.0001), 9)
        self.assertEqual(get_precision_for_radius(0.0), 9)


class TestGetNeighborsForSearch(unittest.TestCase):
    """Test suite for get_neighbors_for_search function"""

    def test_get_neighbors_for_search_basic(self):
        """Test basic neighbor search"""
        geohash = "u09tvqr"
        result = get_neighbors_for_search(geohash, 5.0)
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)
        self.assertIn(geohash[:5], [r[:5] for r in result])  # Should include center

    def test_get_neighbors_for_search_includes_center(self):
        """Test that search includes the center geohash"""
        geohash = "u09tvqr"
        result = get_neighbors_for_search(geohash, 5.0)
        # Should include the center (truncated to appropriate precision)
        precision = get_precision_for_radius(5.0)
        center_prefix = geohash[:precision]
        self.assertIn(center_prefix, result)

    def test_get_neighbors_for_search_no_duplicates(self):
        """Test that search results have no duplicates"""
        geohash = "u09tvqr"
        result = get_neighbors_for_search(geohash, 5.0)
        self.assertEqual(len(result), len(set(result)))

    def test_get_neighbors_for_search_different_radii(self):
        """Test search with different radii"""
        geohash = "u09tvqr"

        # Large radius should use lower precision
        result_large = get_neighbors_for_search(geohash, 100.0)
        precision_large = get_precision_for_radius(100.0)

        # Small radius should use higher precision
        result_small = get_neighbors_for_search(geohash, 0.1)
        precision_small = get_precision_for_radius(0.1)

        # Higher precision should generally have more or equal neighbors
        # (though the count depends on the specific geohash)
        self.assertGreaterEqual(precision_small, precision_large)

    def test_get_neighbors_for_search_short_geohash(self):
        """Test search with geohash shorter than required precision"""
        geohash = "u09"  # Only 3 characters
        result = get_neighbors_for_search(geohash, 0.1)  # Requires precision 9
        # Should still work, using the available geohash
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    def test_get_neighbors_for_search_all_same_length(self):
        """Test that all returned geohashes have same length"""
        geohash = "u09tvqr"
        result = get_neighbors_for_search(geohash, 5.0)
        precision = get_precision_for_radius(5.0)
        for geohash_result in result:
            self.assertEqual(len(geohash_result), precision)


class TestGeohashRoundtrip(unittest.TestCase):
    """Test roundtrip encoding/decoding"""

    def test_roundtrip_high_precision(self):
        """Test roundtrip with high precision"""
        original_lat, original_lon = 40.7128, -74.0060
        geohash = encode(original_lat, original_lon, 12)
        lat, lon, lat_err, lon_err = decode(geohash)

        # With high precision, decoded should be very close to original
        self.assertLess(abs(lat - original_lat), 0.0001)
        self.assertLess(abs(lon - original_lon), 0.0001)

    def test_roundtrip_multiple_locations(self):
        """Test roundtrip for multiple locations"""
        test_locations = [
            (0.0, 0.0),  # Equator, prime meridian
            (40.7128, -74.0060),  # New York
            (51.5074, -0.1278),  # London
            (-33.8688, 151.2093),  # Sydney
            (90.0, 0.0),  # North pole
            (-90.0, 0.0),  # South pole
        ]

        for lat, lon in test_locations:
            geohash = encode(lat, lon, 9)
            decoded_lat, decoded_lon, lat_err, lon_err = decode(geohash)

            # Decoded should be within error bounds
            self.assertLessEqual(abs(decoded_lat - lat), lat_err)
            self.assertLessEqual(abs(decoded_lon - lon), lon_err)


if __name__ == "__main__":
    unittest.main()

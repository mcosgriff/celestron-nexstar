"""
Unit tests for sun_moon.py

Tests sun and moon time calculations.
"""

import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from celestron_nexstar.api.astronomy.sun_moon import calculate_sun_times


class TestCalculateSunTimes(unittest.TestCase):
    """Test suite for calculate_sun_times function"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_lat = 40.0
        self.test_lon = -100.0
        self.test_dt = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)

    @patch("celestron_nexstar.api.astronomy.sun_moon.get_sun_info")
    def test_calculate_sun_times_success(self, mock_get_sun_info):
        """Test successful sun times calculation"""
        # Mock sun_info object
        mock_sun_info = MagicMock()
        mock_sun_info.sunset_time = datetime(2024, 6, 15, 20, 30, tzinfo=UTC)
        mock_sun_info.sunrise_time = datetime(2024, 6, 15, 5, 45, tzinfo=UTC)
        mock_get_sun_info.return_value = mock_sun_info

        result = calculate_sun_times(self.test_lat, self.test_lon, self.test_dt)

        self.assertIsInstance(result, dict)
        self.assertIn("sunset", result)
        self.assertIn("sunrise", result)
        self.assertEqual(result["sunset"], mock_sun_info.sunset_time)
        self.assertEqual(result["sunrise"], mock_sun_info.sunrise_time)
        mock_get_sun_info.assert_called_once_with(self.test_lat, self.test_lon, self.test_dt)

    @patch("celestron_nexstar.api.astronomy.sun_moon.get_sun_info")
    def test_calculate_sun_times_with_default_datetime(self, mock_get_sun_info):
        """Test calculate_sun_times with default datetime (None)"""
        mock_sun_info = MagicMock()
        mock_sun_info.sunset_time = datetime(2024, 6, 15, 20, 30, tzinfo=UTC)
        mock_sun_info.sunrise_time = datetime(2024, 6, 15, 5, 45, tzinfo=UTC)
        mock_get_sun_info.return_value = mock_sun_info

        result = calculate_sun_times(self.test_lat, self.test_lon)

        self.assertIsInstance(result, dict)
        self.assertIn("sunset", result)
        self.assertIn("sunrise", result)
        mock_get_sun_info.assert_called_once_with(self.test_lat, self.test_lon, None)

    @patch("celestron_nexstar.api.astronomy.sun_moon.get_sun_info")
    def test_calculate_sun_times_failure(self, mock_get_sun_info):
        """Test calculate_sun_times when get_sun_info returns None"""
        mock_get_sun_info.return_value = None

        result = calculate_sun_times(self.test_lat, self.test_lon, self.test_dt)

        self.assertIsInstance(result, dict)
        self.assertIn("sunset", result)
        self.assertIn("sunrise", result)
        self.assertIsNone(result["sunset"])
        self.assertIsNone(result["sunrise"])


if __name__ == "__main__":
    unittest.main()

"""
Unit tests for observation/clear_sky.py

Tests Clear Sky Chart calculation functions.
"""

import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from celestron_nexstar.api.location.light_pollution import BortleClass, LightPollutionData
from celestron_nexstar.api.observation.clear_sky import (
    calculate_chart_data_point,
    calculate_darkness,
    calculate_transparency,
)


class TestCalculateTransparency(unittest.TestCase):
    """Test suite for calculate_transparency function"""

    def test_too_cloudy(self):
        """Test that high cloud cover returns too_cloudy"""
        result = calculate_transparency(cloud_cover_percent=50.0, humidity_percent=30.0)
        self.assertEqual(result, "too_cloudy")

    def test_transparent_low_humidity(self):
        """Test that low humidity returns transparent"""
        result = calculate_transparency(cloud_cover_percent=10.0, humidity_percent=25.0)
        self.assertEqual(result, "transparent")

    def test_above_average_humidity(self):
        """Test above average humidity range"""
        result = calculate_transparency(cloud_cover_percent=10.0, humidity_percent=40.0)
        self.assertEqual(result, "above_average")

    def test_average_humidity(self):
        """Test average humidity range"""
        result = calculate_transparency(cloud_cover_percent=10.0, humidity_percent=60.0)
        self.assertEqual(result, "average")

    def test_below_average_humidity(self):
        """Test below average humidity range"""
        result = calculate_transparency(cloud_cover_percent=10.0, humidity_percent=80.0)
        self.assertEqual(result, "below_average")

    def test_poor_humidity(self):
        """Test poor humidity range"""
        result = calculate_transparency(cloud_cover_percent=10.0, humidity_percent=90.0)
        self.assertEqual(result, "poor")

    def test_none_humidity_returns_average(self):
        """Test that None humidity returns average"""
        result = calculate_transparency(cloud_cover_percent=10.0, humidity_percent=None)
        self.assertEqual(result, "average")

    def test_none_cloud_cover(self):
        """Test with None cloud cover"""
        result = calculate_transparency(cloud_cover_percent=None, humidity_percent=40.0)
        self.assertEqual(result, "above_average")


class TestCalculateDarkness(unittest.TestCase):
    """Test suite for calculate_darkness function"""

    def test_daytime_returns_zero(self):
        """Test that daytime (sun above horizon) returns 0.0"""
        result = calculate_darkness(
            sun_altitude_deg=10.0, moon_illumination=0.5, moon_altitude_deg=45.0, base_limiting_magnitude=6.5
        )
        self.assertEqual(result, 0.0)

    def test_civil_twilight(self):
        """Test civil twilight (sun between 0 and -6 degrees)"""
        result = calculate_darkness(
            sun_altitude_deg=-3.0, moon_illumination=None, moon_altitude_deg=None, base_limiting_magnitude=6.5
        )
        self.assertEqual(result, 2.0)

    def test_nautical_twilight(self):
        """Test nautical twilight (sun between -6 and -12 degrees)"""
        result = calculate_darkness(
            sun_altitude_deg=-9.0, moon_illumination=None, moon_altitude_deg=None, base_limiting_magnitude=6.5
        )
        self.assertEqual(result, 3.0)

    def test_astronomical_twilight_no_moon(self):
        """Test astronomical twilight without moon"""
        result = calculate_darkness(
            sun_altitude_deg=-15.0, moon_illumination=None, moon_altitude_deg=None, base_limiting_magnitude=6.5
        )
        self.assertAlmostEqual(result, 6.0, places=1)  # 6.5 - 0.5

    def test_astronomical_twilight_with_moon(self):
        """Test astronomical twilight with moon"""
        result = calculate_darkness(
            sun_altitude_deg=-15.0, moon_illumination=0.5, moon_altitude_deg=45.0, base_limiting_magnitude=6.5
        )
        self.assertAlmostEqual(result, 5.5, places=1)  # 6.5 - 1.0

    def test_dark_sky_no_moon(self):
        """Test dark sky (sun < -18 degrees) without moon"""
        result = calculate_darkness(
            sun_altitude_deg=-20.0, moon_illumination=None, moon_altitude_deg=None, base_limiting_magnitude=6.5
        )
        self.assertEqual(result, 6.5)

    def test_dark_sky_full_moon_high(self):
        """Test dark sky with full moon at high altitude"""
        result = calculate_darkness(
            sun_altitude_deg=-20.0, moon_illumination=1.0, moon_altitude_deg=90.0, base_limiting_magnitude=6.5
        )
        # Full moon at zenith: 6.5 - (1.0 * 3.5 * 1.0) = 3.0
        self.assertAlmostEqual(result, 3.0, places=1)

    def test_dark_sky_new_moon(self):
        """Test dark sky with new moon (no reduction)"""
        result = calculate_darkness(
            sun_altitude_deg=-20.0, moon_illumination=0.0, moon_altitude_deg=45.0, base_limiting_magnitude=6.5
        )
        self.assertEqual(result, 6.5)

    def test_dark_sky_moon_below_horizon(self):
        """Test dark sky with moon below horizon (no reduction)"""
        result = calculate_darkness(
            sun_altitude_deg=-20.0, moon_illumination=1.0, moon_altitude_deg=-10.0, base_limiting_magnitude=6.5
        )
        self.assertEqual(result, 6.5)

    def test_none_sun_altitude(self):
        """Test with None sun altitude"""
        result = calculate_darkness(
            sun_altitude_deg=None, moon_illumination=0.5, moon_altitude_deg=45.0, base_limiting_magnitude=6.5
        )
        self.assertIsNone(result)


class TestCalculateChartDataPoint(unittest.TestCase):
    """Test suite for calculate_chart_data_point function"""

    def setUp(self):
        """Set up test fixtures"""
        self.lp_data = LightPollutionData(
            bortle_class=BortleClass.CLASS_3,
            sqm_value=21.5,
            naked_eye_limiting_magnitude=6.5,
            milky_way_visible=True,
            airglow_visible=True,
            zodiacal_light_visible=True,
            description="Good",
            recommendations=("Good for observing",),
        )

    @patch("celestron_nexstar.api.observation.clear_sky.get_sun_info")
    @patch("celestron_nexstar.api.observation.clear_sky.get_moon_info")
    def test_basic_calculation(self, mock_moon_info, mock_sun_info):
        """Test basic chart data point calculation"""
        # Mock sun and moon info
        mock_sun = MagicMock()
        mock_sun.altitude_deg = -20.0
        mock_sun_info.return_value = mock_sun

        mock_moon = MagicMock()
        mock_moon.illumination = 0.1
        mock_moon.altitude_deg = 30.0
        mock_moon_info.return_value = mock_moon

        result = calculate_chart_data_point(
            forecast_timestamp=datetime.now(UTC),
            cloud_cover_percent=10.0,
            humidity_percent=40.0,
            wind_speed_mph=5.0,
            temperature_f=70.0,
            seeing_score=80.0,
            observer_lat=40.0,
            observer_lon=-100.0,
            light_pollution_data=self.lp_data,
        )

        self.assertIn("timestamp", result)
        self.assertEqual(result["cloud_cover"], 10.0)
        self.assertEqual(result["transparency"], "above_average")
        self.assertEqual(result["seeing"], 80.0)
        self.assertIsNotNone(result["darkness"])
        self.assertEqual(result["wind"], 5.0)
        self.assertEqual(result["humidity"], 40.0)
        self.assertEqual(result["temperature"], 70.0)

    @patch("celestron_nexstar.api.observation.clear_sky.get_sun_info")
    @patch("celestron_nexstar.api.observation.clear_sky.get_moon_info")
    def test_too_cloudy_seeing_none(self, mock_moon_info, mock_sun_info):
        """Test that seeing is None when cloud cover > 80%"""
        mock_sun = MagicMock()
        mock_sun.altitude_deg = -20.0
        mock_sun_info.return_value = mock_sun

        mock_moon = MagicMock()
        mock_moon.illumination = 0.1
        mock_moon.altitude_deg = 30.0
        mock_moon_info.return_value = mock_moon

        result = calculate_chart_data_point(
            forecast_timestamp=datetime.now(UTC),
            cloud_cover_percent=85.0,
            humidity_percent=40.0,
            wind_speed_mph=5.0,
            temperature_f=70.0,
            seeing_score=80.0,
            observer_lat=40.0,
            observer_lon=-100.0,
            light_pollution_data=self.lp_data,
        )

        self.assertIsNone(result["seeing"])

    @patch("celestron_nexstar.api.observation.clear_sky.get_sun_info")
    @patch("celestron_nexstar.api.observation.clear_sky.get_moon_info")
    def test_none_cloud_cover_defaults_to_100(self, mock_moon_info, mock_sun_info):
        """Test that None cloud cover defaults to 100.0"""
        mock_sun = MagicMock()
        mock_sun.altitude_deg = -20.0
        mock_sun_info.return_value = mock_sun

        mock_moon = MagicMock()
        mock_moon.illumination = 0.1
        mock_moon.altitude_deg = 30.0
        mock_moon_info.return_value = mock_moon

        result = calculate_chart_data_point(
            forecast_timestamp=datetime.now(UTC),
            cloud_cover_percent=None,
            humidity_percent=40.0,
            wind_speed_mph=5.0,
            temperature_f=70.0,
            seeing_score=80.0,
            observer_lat=40.0,
            observer_lon=-100.0,
            light_pollution_data=self.lp_data,
        )

        self.assertEqual(result["cloud_cover"], 100.0)

    def test_timezone_handling(self):
        """Test that timezone is properly handled"""
        # Test with timezone-naive datetime
        naive_dt = datetime(2024, 1, 1, 12, 0, 0)

        with (
            patch("celestron_nexstar.api.observation.clear_sky.get_sun_info") as mock_sun_info,
            patch("celestron_nexstar.api.observation.clear_sky.get_moon_info") as mock_moon_info,
        ):
            mock_sun = MagicMock()
            mock_sun.altitude_deg = -20.0
            mock_sun_info.return_value = mock_sun

            mock_moon = MagicMock()
            mock_moon.illumination = 0.1
            mock_moon.altitude_deg = 30.0
            mock_moon_info.return_value = mock_moon

            result = calculate_chart_data_point(
                forecast_timestamp=naive_dt,
                cloud_cover_percent=10.0,
                humidity_percent=40.0,
                wind_speed_mph=5.0,
                temperature_f=70.0,
                seeing_score=80.0,
                observer_lat=40.0,
                observer_lon=-100.0,
                light_pollution_data=self.lp_data,
            )

            # Timestamp should be timezone-aware (UTC)
            self.assertIsNotNone(result["timestamp"].tzinfo)


if __name__ == "__main__":
    unittest.main()

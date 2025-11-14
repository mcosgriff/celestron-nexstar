"""
Unit tests for weather.py

Tests weather data fetching, seeing conditions calculations, and observing condition assessments.
"""

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from celestron_nexstar.api.models import WeatherForecastModel
from celestron_nexstar.api.observer import ObserverLocation
from celestron_nexstar.api import weather
from celestron_nexstar.api.weather import (
    HourlySeeingForecast,
    WeatherData,
    assess_observing_conditions,
    calculate_dew_point_fahrenheit,
    calculate_seeing_conditions,
    fetch_weather,
    fetch_weather_batch,
    get_weather_api_key,
)


class TestCalculateDewPointFahrenheit(unittest.TestCase):
    """Test suite for calculate_dew_point_fahrenheit function"""

    def test_calculate_dew_point_typical_conditions(self):
        """Test dew point calculation for typical conditions"""
        # 70°F, 50% humidity
        dew_point = calculate_dew_point_fahrenheit(70.0, 50.0)
        self.assertGreater(dew_point, 50.0)
        self.assertLess(dew_point, 70.0)

    def test_calculate_dew_point_high_humidity(self):
        """Test dew point calculation for high humidity"""
        # 70°F, 90% humidity - dew point should be close to temperature
        dew_point = calculate_dew_point_fahrenheit(70.0, 90.0)
        self.assertGreater(dew_point, 65.0)
        self.assertLess(dew_point, 70.0)

    def test_calculate_dew_point_low_humidity(self):
        """Test dew point calculation for low humidity"""
        # 70°F, 20% humidity - dew point should be much lower
        dew_point = calculate_dew_point_fahrenheit(70.0, 20.0)
        self.assertLess(dew_point, 50.0)

    def test_calculate_dew_point_saturated(self):
        """Test dew point at 100% humidity (should equal temperature)"""
        dew_point = calculate_dew_point_fahrenheit(70.0, 100.0)
        self.assertAlmostEqual(dew_point, 70.0, places=1)

    def test_calculate_dew_point_freezing(self):
        """Test dew point calculation at freezing temperature"""
        dew_point = calculate_dew_point_fahrenheit(32.0, 50.0)
        self.assertLess(dew_point, 32.0)

    def test_calculate_dew_point_consistency(self):
        """Test that dew point is always less than or equal to temperature"""
        test_cases = [
            (32.0, 50.0),
            (50.0, 60.0),
            (70.0, 80.0),
            (90.0, 30.0),
        ]
        for temp, humidity in test_cases:
            dew_point = calculate_dew_point_fahrenheit(temp, humidity)
            self.assertLessEqual(dew_point, temp, msg=f"Temp: {temp}, Humidity: {humidity}")


class TestGetWeatherApiKey(unittest.TestCase):
    """Test suite for get_weather_api_key function"""

    @patch.dict("os.environ", {"OPENWEATHER_API_KEY": "test_key_1"})
    def test_get_weather_api_key_from_openweather(self):
        """Test getting API key from OPENWEATHER_API_KEY"""
        key = get_weather_api_key()
        self.assertEqual(key, "test_key_1")

    @patch.dict("os.environ", {"OWM_API_KEY": "test_key_2"}, clear=True)
    def test_get_weather_api_key_from_owm(self):
        """Test getting API key from OWM_API_KEY"""
        key = get_weather_api_key()
        self.assertEqual(key, "test_key_2")

    @patch.dict("os.environ", {}, clear=True)
    def test_get_weather_api_key_not_set(self):
        """Test getting API key when not set"""
        key = get_weather_api_key()
        self.assertIsNone(key)

    @patch.dict("os.environ", {"OPENWEATHER_API_KEY": "key1", "OWM_API_KEY": "key2"})
    def test_get_weather_api_key_prefers_openweather(self):
        """Test that OPENWEATHER_API_KEY takes precedence"""
        key = get_weather_api_key()
        self.assertEqual(key, "key1")


class TestAssessObservingConditions(unittest.TestCase):
    """Test suite for assess_observing_conditions function"""

    def test_assess_conditions_excellent_clear(self):
        """Test assessment for excellent conditions (clear skies)"""
        weather = WeatherData(
            cloud_cover_percent=5.0,
            humidity_percent=40.0,
            visibility_km=20.0,
            wind_speed_ms=8.0,  # mph
        )
        status, warning = assess_observing_conditions(weather)
        self.assertEqual(status, "excellent")
        self.assertIn("Good observing conditions", warning)

    def test_assess_conditions_poor_cloudy(self):
        """Test assessment for poor conditions (very cloudy)"""
        weather = WeatherData(cloud_cover_percent=90.0)
        status, warning = assess_observing_conditions(weather)
        self.assertEqual(status, "poor")
        self.assertIn("Very cloudy", warning)

    def test_assess_conditions_fair_partly_cloudy(self):
        """Test assessment for fair conditions (partly cloudy)"""
        weather = WeatherData(cloud_cover_percent=60.0)
        status, warning = assess_observing_conditions(weather)
        self.assertEqual(status, "fair")
        self.assertIn("Partly cloudy", warning)

    def test_assess_conditions_high_humidity(self):
        """Test assessment with high humidity"""
        weather = WeatherData(
            cloud_cover_percent=10.0,
            humidity_percent=95.0,
        )
        status, warning = assess_observing_conditions(weather)
        self.assertIn(status, ["good", "fair"])
        self.assertIn("High humidity", warning)

    def test_assess_conditions_poor_visibility(self):
        """Test assessment with poor visibility"""
        weather = WeatherData(
            cloud_cover_percent=10.0,
            visibility_km=3.0,
        )
        status, warning = assess_observing_conditions(weather)
        self.assertEqual(status, "fair")
        self.assertIn("Poor visibility", warning)

    def test_assess_conditions_strong_wind(self):
        """Test assessment with strong wind"""
        weather = WeatherData(
            cloud_cover_percent=10.0,
            wind_speed_ms=30.0,  # mph
        )
        status, warning = assess_observing_conditions(weather)
        self.assertEqual(status, "fair")
        self.assertIn("Strong wind", warning)

    def test_assess_conditions_precipitation(self):
        """Test assessment with precipitation"""
        weather = WeatherData(
            cloud_cover_percent=50.0,
            condition="Rain",
        )
        status, warning = assess_observing_conditions(weather)
        self.assertEqual(status, "poor")
        self.assertIn("Precipitation", warning)

    def test_assess_conditions_error(self):
        """Test assessment with error"""
        weather = WeatherData(error="API error")
        status, warning = assess_observing_conditions(weather)
        self.assertEqual(status, "unavailable")
        self.assertEqual(warning, "API error")

    def test_assess_conditions_no_cloud_data(self):
        """Test assessment when cloud data is unavailable"""
        weather = WeatherData(cloud_cover_percent=None)
        status, warning = assess_observing_conditions(weather)
        self.assertEqual(status, "unavailable")
        self.assertIn("Cloud data unavailable", warning)

    def test_assess_conditions_good_cloud_cover(self):
        """Test assessment for good conditions (20-50% cloud cover)"""
        weather = WeatherData(cloud_cover_percent=35.0)
        status, warning = assess_observing_conditions(weather)
        self.assertEqual(status, "good")
        self.assertIn("Some clouds", warning)

    def test_assess_conditions_high_humidity_downgrades_excellent(self):
        """Test that high humidity downgrades excellent to good"""
        weather = WeatherData(
            cloud_cover_percent=5.0,  # Excellent
            humidity_percent=95.0,  # High humidity
        )
        status, warning = assess_observing_conditions(weather)
        self.assertEqual(status, "good")  # Downgraded from excellent
        self.assertIn("High humidity", warning)

    def test_assess_conditions_high_humidity_downgrades_good(self):
        """Test that high humidity downgrades good to fair"""
        weather = WeatherData(
            cloud_cover_percent=30.0,  # Good
            humidity_percent=95.0,  # High humidity
        )
        status, warning = assess_observing_conditions(weather)
        self.assertEqual(status, "fair")  # Downgraded from good
        self.assertIn("High humidity", warning)

    def test_assess_conditions_moderate_humidity_downgrades_excellent(self):
        """Test that moderate humidity downgrades excellent to good"""
        weather = WeatherData(
            cloud_cover_percent=5.0,  # Excellent
            humidity_percent=85.0,  # Moderate humidity
        )
        status, warning = assess_observing_conditions(weather)
        self.assertEqual(status, "good")  # Downgraded from excellent
        self.assertIn("Moderate humidity", warning)

    def test_assess_conditions_reduced_visibility(self):
        """Test assessment with reduced visibility (5-10 km)"""
        weather = WeatherData(
            cloud_cover_percent=10.0,
            visibility_km=7.0,  # Reduced visibility
        )
        status, warning = assess_observing_conditions(weather)
        self.assertEqual(status, "good")  # Downgraded from excellent
        self.assertIn("Reduced visibility", warning)

    def test_assess_conditions_moderate_wind(self):
        """Test assessment with moderate wind (15-25 mph)"""
        weather = WeatherData(
            cloud_cover_percent=10.0,
            wind_speed_ms=20.0,  # mph - moderate
        )
        status, warning = assess_observing_conditions(weather)
        self.assertEqual(status, "good")  # Downgraded from excellent
        self.assertIn("Moderate wind", warning)

    def test_assess_conditions_fog(self):
        """Test assessment with fog conditions"""
        weather = WeatherData(
            cloud_cover_percent=10.0,
            condition="Fog",
        )
        status, warning = assess_observing_conditions(weather)
        self.assertEqual(status, "fair")  # Downgraded from excellent/good
        self.assertIn("Reduced visibility", warning)

    def test_assess_conditions_mist(self):
        """Test assessment with mist conditions"""
        weather = WeatherData(
            cloud_cover_percent=10.0,
            condition="Mist",
        )
        status, warning = assess_observing_conditions(weather)
        self.assertEqual(status, "fair")  # Downgraded from excellent/good
        self.assertIn("Reduced visibility", warning)


class TestCalculateSeeingConditions(unittest.TestCase):
    """Test suite for calculate_seeing_conditions function"""

    def test_calculate_seeing_optimal_conditions(self):
        """Test seeing calculation for optimal conditions"""
        weather = WeatherData(
            temperature_c=70.0,
            dew_point_f=50.0,  # 20°F spread
            wind_speed_ms=7.0,  # mph - optimal range
            humidity_percent=30.0,
            cloud_cover_percent=10.0,
        )
        score = calculate_seeing_conditions(weather, temperature_change_per_hour=0.5)
        self.assertGreater(score, 80.0)
        self.assertLessEqual(score, 100.0)

    def test_calculate_seeing_high_clouds(self):
        """Test seeing calculation with high cloud cover (blocks measurement)"""
        weather = WeatherData(
            temperature_c=70.0,
            cloud_cover_percent=85.0,  # > 80% blocks seeing measurement
        )
        score = calculate_seeing_conditions(weather)
        self.assertEqual(score, 0.0)

    def test_calculate_seeing_error(self):
        """Test seeing calculation with error (returns default)"""
        weather = WeatherData(error="API error")
        score = calculate_seeing_conditions(weather)
        self.assertEqual(score, 50.0)

    def test_calculate_seeing_no_temperature(self):
        """Test seeing calculation without temperature (returns default)"""
        weather = WeatherData(temperature_c=None)
        score = calculate_seeing_conditions(weather)
        self.assertEqual(score, 50.0)

    def test_calculate_seeing_low_wind(self):
        """Test seeing calculation with low wind (insufficient mixing)"""
        weather = WeatherData(
            temperature_c=70.0,
            wind_speed_ms=2.0,  # mph - too low
        )
        score = calculate_seeing_conditions(weather)
        # Should be reduced due to low wind
        self.assertLess(score, 100.0)

    def test_calculate_seeing_high_wind(self):
        """Test seeing calculation with high wind (turbulence)"""
        weather = WeatherData(
            temperature_c=70.0,
            wind_speed_ms=25.0,  # mph - too high
        )
        score = calculate_seeing_conditions(weather)
        # Should be reduced due to high wind
        self.assertLess(score, 50.0)

    def test_calculate_seeing_high_humidity(self):
        """Test seeing calculation with high humidity"""
        weather = WeatherData(
            temperature_c=70.0,
            humidity_percent=90.0,
        )
        score = calculate_seeing_conditions(weather)
        # Should be reduced due to high humidity
        self.assertLess(score, 100.0)

    def test_calculate_seeing_temperature_stability(self):
        """Test seeing calculation with temperature stability"""
        weather = WeatherData(temperature_c=70.0)
        # Very stable
        score_stable = calculate_seeing_conditions(weather, temperature_change_per_hour=0.3)
        # Unstable
        score_unstable = calculate_seeing_conditions(weather, temperature_change_per_hour=6.0)
        self.assertGreater(score_stable, score_unstable)

    def test_calculate_seeing_score_range(self):
        """Test that seeing score is always between 0 and 100"""
        test_cases = [
            WeatherData(temperature_c=70.0, wind_speed_ms=100.0),  # Extreme wind
            WeatherData(temperature_c=70.0, humidity_percent=100.0),  # Saturated
            WeatherData(temperature_c=70.0, dew_point_f=69.0),  # Very close to dew point
        ]
        for weather in test_cases:
            score = calculate_seeing_conditions(weather)
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 100.0)

    def test_calculate_seeing_temp_spread_10_to_15(self):
        """Test seeing calculation with temp spread 10-15°F"""
        weather = WeatherData(
            temperature_c=70.0,
            dew_point_f=60.0,  # 10°F spread
        )
        score = calculate_seeing_conditions(weather)
        self.assertGreater(score, 0.0)

    def test_calculate_seeing_temp_spread_5_to_10(self):
        """Test seeing calculation with temp spread 5-10°F"""
        weather = WeatherData(
            temperature_c=70.0,
            dew_point_f=65.0,  # 5°F spread
        )
        score = calculate_seeing_conditions(weather)
        self.assertGreater(score, 0.0)

    def test_calculate_seeing_temp_spread_30_plus(self):
        """Test seeing calculation with temp spread >=30°F"""
        weather = WeatherData(
            temperature_c=70.0,
            dew_point_f=35.0,  # 35°F spread
        )
        score = calculate_seeing_conditions(weather)
        self.assertGreater(score, 0.0)

    def test_calculate_seeing_wind_10_to_15_mph(self):
        """Test seeing calculation with wind 10-15 mph"""
        weather = WeatherData(
            temperature_c=70.0,
            wind_speed_ms=12.0,  # mph
        )
        score = calculate_seeing_conditions(weather)
        self.assertGreater(score, 0.0)
        # Should be less than optimal (30 points for wind), but other factors contribute
        self.assertLess(score, 100.0)

    def test_calculate_seeing_wind_15_to_20_mph(self):
        """Test seeing calculation with wind 15-20 mph"""
        weather = WeatherData(
            temperature_c=70.0,
            wind_speed_ms=18.0,  # mph
        )
        score = calculate_seeing_conditions(weather)
        self.assertGreater(score, 0.0)
        # Wind score should be reduced, but other factors (temp spread, humidity, stability) contribute
        self.assertLess(score, 100.0)

    def test_calculate_seeing_humidity_30_to_60(self):
        """Test seeing calculation with humidity 30-60%"""
        weather = WeatherData(
            temperature_c=70.0,
            humidity_percent=45.0,
        )
        score = calculate_seeing_conditions(weather)
        self.assertGreater(score, 0.0)

    def test_calculate_seeing_humidity_60_to_80(self):
        """Test seeing calculation with humidity 60-80%"""
        weather = WeatherData(
            temperature_c=70.0,
            humidity_percent=70.0,
        )
        score = calculate_seeing_conditions(weather)
        self.assertGreater(score, 0.0)

    def test_calculate_seeing_stability_0_5_to_1_0(self):
        """Test seeing calculation with stability 0.5-1.0°F/hour"""
        weather = WeatherData(temperature_c=70.0)
        score = calculate_seeing_conditions(weather, temperature_change_per_hour=0.8)
        self.assertGreater(score, 0.0)

    def test_calculate_seeing_stability_1_0_to_2_0(self):
        """Test seeing calculation with stability 1.0-2.0°F/hour"""
        weather = WeatherData(temperature_c=70.0)
        score = calculate_seeing_conditions(weather, temperature_change_per_hour=1.5)
        self.assertGreater(score, 0.0)

    def test_calculate_seeing_stability_2_0_to_3_0(self):
        """Test seeing calculation with stability 2.0-3.0°F/hour"""
        weather = WeatherData(temperature_c=70.0)
        score = calculate_seeing_conditions(weather, temperature_change_per_hour=2.5)
        self.assertGreater(score, 0.0)

    def test_calculate_seeing_stability_3_0_to_5_0(self):
        """Test seeing calculation with stability 3.0-5.0°F/hour"""
        weather = WeatherData(temperature_c=70.0)
        score = calculate_seeing_conditions(weather, temperature_change_per_hour=4.0)
        self.assertGreater(score, 0.0)

    def test_calculate_seeing_stability_over_5_0(self):
        """Test seeing calculation with stability >5.0°F/hour"""
        weather = WeatherData(temperature_c=70.0)
        score = calculate_seeing_conditions(weather, temperature_change_per_hour=6.0)
        self.assertGreaterEqual(score, 0.0)


class TestIsForecastStale(unittest.TestCase):
    """Test suite for _is_forecast_stale function"""

    def test_forecast_stale_past_time(self):
        """Test that forecast for past time is stale"""
        now = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
        past_time = datetime(2024, 6, 15, 10, 0, tzinfo=UTC)

        forecast = WeatherForecastModel(
            latitude=40.0,
            longitude=-100.0,
            forecast_timestamp=past_time,
            fetched_at=datetime(2024, 6, 15, 9, 0, tzinfo=UTC),
            temperature_f=70.0,
            humidity_percent=50.0,
            cloud_cover_percent=10.0,
            wind_speed_mph=5.0,
        )

        self.assertTrue(weather._is_forecast_stale(forecast, now))

    def test_forecast_stale_near_term_old(self):
        """Test that near-term forecast (>2 hours old) is stale"""
        now = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
        future_time = datetime(2024, 6, 15, 13, 0, tzinfo=UTC)  # 1 hour ahead
        old_fetch = datetime(2024, 6, 15, 9, 0, tzinfo=UTC)  # 3 hours ago

        forecast = WeatherForecastModel(
            latitude=40.0,
            longitude=-100.0,
            forecast_timestamp=future_time,
            fetched_at=old_fetch,
            temperature_f=70.0,
            humidity_percent=50.0,
            cloud_cover_percent=10.0,
            wind_speed_mph=5.0,
        )

        self.assertTrue(weather._is_forecast_stale(forecast, now))

    def test_forecast_fresh_near_term(self):
        """Test that near-term forecast (<2 hours old) is fresh"""
        now = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
        future_time = datetime(2024, 6, 15, 13, 0, tzinfo=UTC)  # 1 hour ahead
        recent_fetch = datetime(2024, 6, 15, 11, 30, tzinfo=UTC)  # 30 minutes ago

        forecast = WeatherForecastModel(
            latitude=40.0,
            longitude=-100.0,
            forecast_timestamp=future_time,
            fetched_at=recent_fetch,
            temperature_f=70.0,
            humidity_percent=50.0,
            cloud_cover_percent=10.0,
            wind_speed_mph=5.0,
        )

        self.assertFalse(weather._is_forecast_stale(forecast, now))

    def test_forecast_stale_medium_term_old(self):
        """Test that medium-term forecast (>6 hours old) is stale"""
        now = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
        future_time = datetime(2024, 6, 15, 20, 0, tzinfo=UTC)  # 8 hours ahead
        old_fetch = datetime(2024, 6, 15, 5, 0, tzinfo=UTC)  # 7 hours ago

        forecast = WeatherForecastModel(
            latitude=40.0,
            longitude=-100.0,
            forecast_timestamp=future_time,
            fetched_at=old_fetch,
            temperature_f=70.0,
            humidity_percent=50.0,
            cloud_cover_percent=10.0,
            wind_speed_mph=5.0,
        )

        self.assertTrue(weather._is_forecast_stale(forecast, now))

    def test_forecast_stale_long_term_old(self):
        """Test that long-term forecast (>12 hours old) is stale"""
        now = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
        future_time = datetime(2024, 6, 16, 12, 0, tzinfo=UTC)  # 24 hours ahead
        old_fetch = datetime(2024, 6, 14, 23, 0, tzinfo=UTC)  # 13 hours ago

        forecast = WeatherForecastModel(
            latitude=40.0,
            longitude=-100.0,
            forecast_timestamp=future_time,
            fetched_at=old_fetch,
            temperature_f=70.0,
            humidity_percent=50.0,
            cloud_cover_percent=10.0,
            wind_speed_mph=5.0,
        )

        self.assertTrue(weather._is_forecast_stale(forecast, now))

    def test_forecast_timezone_naive(self):
        """Test that timezone-naive timestamps are handled"""
        now = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
        future_time = datetime(2024, 6, 15, 13, 0)  # Naive
        recent_fetch = datetime(2024, 6, 15, 11, 30)  # Naive

        forecast = WeatherForecastModel(
            latitude=40.0,
            longitude=-100.0,
            forecast_timestamp=future_time,
            fetched_at=recent_fetch,
            temperature_f=70.0,
            humidity_percent=50.0,
            cloud_cover_percent=10.0,
            wind_speed_mph=5.0,
        )

        # Should not raise exception
        result = weather._is_forecast_stale(forecast, now)
        self.assertIsInstance(result, bool)

    def test_forecast_timezone_different(self):
        """Test that different timezone timestamps are converted to UTC"""
        from datetime import timezone, timedelta

        now = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
        # Create timestamps in a different timezone (e.g., EST = UTC-5)
        est = timezone(timedelta(hours=-5))
        future_time = datetime(2024, 6, 15, 8, 0, tzinfo=est)  # 13:00 UTC
        recent_fetch = datetime(2024, 6, 15, 6, 30, tzinfo=est)  # 11:30 UTC

        forecast = WeatherForecastModel(
            latitude=40.0,
            longitude=-100.0,
            forecast_timestamp=future_time,
            fetched_at=recent_fetch,
            temperature_f=70.0,
            humidity_percent=50.0,
            cloud_cover_percent=10.0,
            wind_speed_mph=5.0,
        )

        # Should not raise exception and should handle timezone conversion
        result = weather._is_forecast_stale(forecast, now)
        self.assertIsInstance(result, bool)

    def test_forecast_stale_long_term_fresh(self):
        """Test that long-term forecast (<12 hours old) is fresh"""
        now = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
        future_time = datetime(2024, 6, 16, 13, 0, tzinfo=UTC)  # 25 hours ahead (>24, so long-term)
        recent_fetch = datetime(2024, 6, 15, 2, 0, tzinfo=UTC)  # 10 hours ago (fresh, <12)

        forecast = WeatherForecastModel(
            latitude=40.0,
            longitude=-100.0,
            forecast_timestamp=future_time,
            fetched_at=recent_fetch,
            temperature_f=70.0,
            humidity_percent=50.0,
            cloud_cover_percent=10.0,
            wind_speed_mph=5.0,
        )

        self.assertFalse(weather._is_forecast_stale(forecast, now))


class TestFetchWeather(unittest.TestCase):
    """Test suite for fetch_weather function"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_location = ObserverLocation(latitude=40.0, longitude=-100.0, name="Test Location")

    @patch("celestron_nexstar.api.weather.aiohttp.ClientSession")
    async def test_fetch_weather_success(self, mock_session_class):
        """Test successful weather fetch"""
        # Mock response
        mock_response = AsyncMock()
        mock_response.json = AsyncMock(
            return_value={
                "current": {
                    "temperature_2m": 70.0,
                    "relative_humidity_2m": 50.0,
                    "cloud_cover": 10.0,
                    "wind_speed_10m": 5.0,
                    "visibility": 20.0,
                    "weather_code": 0,  # Clear
                },
                "current_units": {
                    "temperature_2m": "°F",
                    "wind_speed_10m": "mph",
                },
            }
        )
        mock_response.status = 200

        # Mock session
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session

        weather = await fetch_weather(self.test_location)

        self.assertIsInstance(weather, WeatherData)
        self.assertIsNone(weather.error)

    @patch("celestron_nexstar.api.weather.aiohttp.ClientSession")
    async def test_fetch_weather_api_error(self, mock_session_class):
        """Test weather fetch with API error"""
        # Mock response with error
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal Server Error")

        # Mock session
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session

        weather = await fetch_weather(self.test_location)

        self.assertIsInstance(weather, WeatherData)
        self.assertIsNotNone(weather.error)

    @patch("celestron_nexstar.api.weather.aiohttp.ClientSession")
    async def test_fetch_weather_network_error(self, mock_session_class):
        """Test weather fetch with network error"""
        # Mock session that raises exception
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(side_effect=aiohttp.ClientError("Network error"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session

        weather = await fetch_weather(self.test_location)

        self.assertIsInstance(weather, WeatherData)
        self.assertIsNotNone(weather.error)


if __name__ == "__main__":
    unittest.main()

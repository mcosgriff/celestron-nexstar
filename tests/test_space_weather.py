"""
Unit tests for space_weather.py

Tests space weather data fetching and NOAA scale calculations.
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from celestron_nexstar.api.events.space_weather import (
    NOAAScale,
    SpaceWeatherConditions,
    get_goes_xray_data,
    get_kp_ap_data,
    get_solar_wind_data,
    get_space_weather_conditions,
)


class TestNOAAScale(unittest.TestCase):
    """Test suite for NOAAScale dataclass"""

    def test_creation(self):
        """Test creating a NOAAScale"""
        scale = NOAAScale(level=3, scale_type="G", description="Strong geomagnetic storm")
        self.assertEqual(scale.level, 3)
        self.assertEqual(scale.scale_type, "G")
        self.assertEqual(scale.description, "Strong geomagnetic storm")

    def test_display_name_r_scale(self):
        """Test display names for R scale"""
        self.assertEqual(NOAAScale(level=0, scale_type="R").display_name, "None")
        self.assertEqual(NOAAScale(level=1, scale_type="R").display_name, "Minor")
        self.assertEqual(NOAAScale(level=2, scale_type="R").display_name, "Moderate")
        self.assertEqual(NOAAScale(level=3, scale_type="R").display_name, "Strong")
        self.assertEqual(NOAAScale(level=4, scale_type="R").display_name, "Severe")
        self.assertEqual(NOAAScale(level=5, scale_type="R").display_name, "Extreme")

    def test_display_name_g_scale(self):
        """Test display names for G scale"""
        self.assertEqual(NOAAScale(level=0, scale_type="G").display_name, "None")
        self.assertEqual(NOAAScale(level=1, scale_type="G").display_name, "Minor")
        self.assertEqual(NOAAScale(level=5, scale_type="G").display_name, "Extreme")

    def test_display_name_s_scale(self):
        """Test display names for S scale"""
        self.assertEqual(NOAAScale(level=0, scale_type="S").display_name, "None")
        self.assertEqual(NOAAScale(level=1, scale_type="S").display_name, "Minor")
        self.assertEqual(NOAAScale(level=5, scale_type="S").display_name, "Extreme")

    def test_display_name_unknown_scale(self):
        """Test display name for unknown scale type"""
        scale = NOAAScale(level=3, scale_type="X")
        self.assertEqual(scale.display_name, "Level 3")

    def test_color_code(self):
        """Test color codes"""
        self.assertEqual(NOAAScale(level=0, scale_type="G").color_code, "green")
        self.assertEqual(NOAAScale(level=1, scale_type="G").color_code, "yellow")
        self.assertEqual(NOAAScale(level=2, scale_type="G").color_code, "yellow")
        self.assertEqual(NOAAScale(level=3, scale_type="G").color_code, "red")
        self.assertEqual(NOAAScale(level=4, scale_type="G").color_code, "bold red")
        self.assertEqual(NOAAScale(level=5, scale_type="G").color_code, "bold red")


class TestSpaceWeatherConditions(unittest.TestCase):
    """Test suite for SpaceWeatherConditions dataclass"""

    def test_creation(self):
        """Test creating SpaceWeatherConditions"""
        conditions = SpaceWeatherConditions()
        self.assertIsNone(conditions.r_scale)
        self.assertIsNone(conditions.s_scale)
        self.assertIsNone(conditions.g_scale)
        self.assertIsNotNone(conditions.alerts)
        self.assertEqual(conditions.alerts, [])

    def test_alerts_initialization(self):
        """Test that alerts list is initialized"""
        conditions = SpaceWeatherConditions()
        self.assertIsNotNone(conditions.alerts)
        self.assertIsInstance(conditions.alerts, list)

    def test_with_scales(self):
        """Test SpaceWeatherConditions with NOAA scales"""
        r_scale = NOAAScale(level=2, scale_type="R")
        g_scale = NOAAScale(level=3, scale_type="G")
        conditions = SpaceWeatherConditions(r_scale=r_scale, g_scale=g_scale)
        self.assertEqual(conditions.r_scale, r_scale)
        self.assertEqual(conditions.g_scale, g_scale)


class TestGetSolarWindData(unittest.TestCase):
    """Test suite for get_solar_wind_data function"""

    @patch("celestron_nexstar.api.events.space_weather._get_from_cache")
    @patch("celestron_nexstar.api.events.space_weather.aiohttp.ClientSession")
    def test_get_solar_wind_data_success(self, mock_session_class, mock_get_cache):
        """Test successful solar wind data fetch"""
        # Mock cache to return None (no cached data)
        mock_get_cache.return_value = None

        # Mock async context manager for session
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session

        # Mock plasma data response (used as async context manager)
        mock_plasma_response = AsyncMock()
        mock_plasma_response.__aenter__ = AsyncMock(return_value=mock_plasma_response)
        mock_plasma_response.__aexit__ = AsyncMock(return_value=None)
        mock_plasma_response.status = 200
        mock_plasma_response.json = AsyncMock(return_value=[
            ["time_tag", "density", "speed", "temperature"],
            ["2024-06-15T12:00:00Z", "5.0", "400.0", "100000.0"],
        ])
        mock_plasma_response.raise_for_status = MagicMock()

        # Mock magnetic field data response (used as async context manager)
        mock_mag_response = AsyncMock()
        mock_mag_response.__aenter__ = AsyncMock(return_value=mock_mag_response)
        mock_mag_response.__aexit__ = AsyncMock(return_value=None)
        mock_mag_response.status = 200
        mock_mag_response.json = AsyncMock(return_value=[
            ["time_tag", "bt", "bz", "phi", "theta"],
            ["2024-06-15T12:00:00Z", "8.5", "-3.2", "45.0", "10.0"],
        ])
        mock_mag_response.raise_for_status = MagicMock()

        # session.get() returns coroutines that resolve to async context managers
        # The coroutines resolve to the response objects which are used as context managers
        async def mock_get_plasma(*args, **kwargs):
            return mock_plasma_response

        async def mock_get_mag(*args, **kwargs):
            return mock_mag_response

        mock_session.get = MagicMock(side_effect=[mock_get_plasma(), mock_get_mag()])

        result = asyncio.run(get_solar_wind_data())

        self.assertIsInstance(result, dict)
        self.assertIn("solar_wind_speed", result)
        self.assertIn("solar_wind_bt", result)
        self.assertIn("solar_wind_bz", result)
        self.assertIn("solar_wind_density", result)
        self.assertEqual(result["solar_wind_speed"], 400.0)
        self.assertEqual(result["solar_wind_density"], 5.0)
        self.assertEqual(result["solar_wind_bt"], 8.5)
        self.assertEqual(result["solar_wind_bz"], -3.2)

    @patch("celestron_nexstar.api.events.space_weather._get_from_cache")
    @patch("celestron_nexstar.api.events.space_weather.aiohttp.ClientSession")
    def test_get_solar_wind_data_empty_response(self, mock_session_class, mock_get_cache):
        """Test solar wind data fetch with empty response"""
        # Mock cache to return None (no cached data)
        mock_get_cache.return_value = None

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session

        # For empty response, we need to mock both plasma and mag responses
        mock_plasma_response = AsyncMock()
        mock_plasma_response.__aenter__ = AsyncMock(return_value=mock_plasma_response)
        mock_plasma_response.__aexit__ = AsyncMock(return_value=None)
        mock_plasma_response.status = 200
        mock_plasma_response.json = AsyncMock(return_value=[])
        mock_plasma_response.raise_for_status = MagicMock()

        mock_mag_response = AsyncMock()
        mock_mag_response.__aenter__ = AsyncMock(return_value=mock_mag_response)
        mock_mag_response.__aexit__ = AsyncMock(return_value=None)
        mock_mag_response.status = 200
        mock_mag_response.json = AsyncMock(return_value=[])

        # session.get() returns coroutines that resolve to async context managers
        async def mock_get_plasma(*args, **kwargs):
            return mock_plasma_response

        async def mock_get_mag(*args, **kwargs):
            return mock_mag_response

        mock_session.get = MagicMock(side_effect=[mock_get_plasma(), mock_get_mag()])

        result = asyncio.run(get_solar_wind_data())

        self.assertIsInstance(result, dict)
        # When data is empty, function returns dict with None values, not empty dict
        self.assertEqual(result, {
            "solar_wind_speed": None,
            "solar_wind_bt": None,
            "solar_wind_bz": None,
            "solar_wind_density": None,
        })

    @patch("celestron_nexstar.api.events.space_weather._get_from_cache")
    @patch("celestron_nexstar.api.events.space_weather.aiohttp.ClientSession")
    def test_get_solar_wind_data_error(self, mock_session_class, mock_get_cache):
        """Test solar wind data fetch with error"""
        # Mock cache to return None (no cached data)
        mock_get_cache.return_value = None

        import aiohttp

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session

        # session.get() returns coroutines, so we need to make them raise errors
        async def mock_get_error(*args, **kwargs):
            raise aiohttp.ClientError("Network error")

        mock_session.get = MagicMock(side_effect=[mock_get_error(), mock_get_error()])

        result = asyncio.run(get_solar_wind_data())

        self.assertIsInstance(result, dict)
        self.assertEqual(result, {})


class TestGetGoesXrayData(unittest.TestCase):
    """Test suite for get_goes_xray_data function"""

    @patch("celestron_nexstar.api.events.space_weather.aiohttp.ClientSession")
    def test_get_goes_xray_data_success(self, mock_session_class):
        """Test successful GOES X-ray data fetch"""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session

        # In aiohttp, session.get() returns an async context manager directly
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=[
            {"time_tag": "2024-06-15T12:00:00Z", "flux": "1.5e-6", "class": "M2.5"},
            {"time_tag": "2024-06-15T11:00:00Z", "flux": "1.0e-6", "class": "C5.0"},
        ])
        mock_response.raise_for_status = MagicMock()

        mock_get_context = AsyncMock()
        mock_get_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_get_context.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_get_context)

        result = asyncio.run(get_goes_xray_data())

        self.assertIsInstance(result, dict)
        self.assertIn("xray_flux", result)
        self.assertIn("xray_class", result)
        self.assertEqual(result["xray_flux"], 1.5e-6)
        self.assertEqual(result["xray_class"], "M2.5")

    @patch("celestron_nexstar.api.events.space_weather.aiohttp.ClientSession")
    def test_get_goes_xray_data_empty(self, mock_session_class):
        """Test GOES X-ray data fetch with empty response"""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session

        mock_response = AsyncMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=[])
        mock_response.raise_for_status = MagicMock()

        async def mock_get(*args, **kwargs):
            return mock_response
        mock_session.get = mock_get

        result = asyncio.run(get_goes_xray_data())

        self.assertIsInstance(result, dict)
        self.assertEqual(result, {})

    @patch("celestron_nexstar.api.events.space_weather.aiohttp.ClientSession")
    def test_get_goes_xray_data_error(self, mock_session_class):
        """Test GOES X-ray data fetch with error"""
        import aiohttp

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session
        mock_session.get = AsyncMock(side_effect=aiohttp.ClientError("Network error"))

        result = asyncio.run(get_goes_xray_data())

        self.assertIsInstance(result, dict)
        self.assertEqual(result, {})


class TestGetKpApData(unittest.TestCase):
    """Test suite for get_kp_ap_data function"""

    @patch("celestron_nexstar.api.events.space_weather._get_from_cache")
    @patch("celestron_nexstar.api.events.space_weather.aiohttp.ClientSession")
    def test_get_kp_ap_data_success(self, mock_session_class, mock_get_cache):
        """Test successful Kp/Ap data fetch"""
        # Mock cache to return None (no cached data)
        mock_get_cache.return_value = None

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session

        # In aiohttp, session.get() returns an async context manager directly
        # When used in "async with session.get(...) as response:", it enters the context
        mock_response = AsyncMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=[
            ["time_tag", "kp", "observed"],
            ["2024-06-15 12:00:00", "3.0", "observed"],
            ["2024-06-15 11:00:00", "2.5", "observed"],
        ])
        mock_response.raise_for_status = MagicMock()

        # session.get() returns an async context manager that yields the response
        mock_session.get = MagicMock(return_value=mock_response)

        result = asyncio.run(get_kp_ap_data())

        self.assertIsInstance(result, dict)
        self.assertIn("kp_index", result)
        self.assertEqual(result["kp_index"], 3.0)

    @patch("celestron_nexstar.api.events.space_weather._get_from_cache")
    @patch("celestron_nexstar.api.events.space_weather.aiohttp.ClientSession")
    def test_get_kp_ap_data_error(self, mock_session_class, mock_get_cache):
        """Test Kp/Ap data fetch with error"""
        # Mock cache to return None (no cached data)
        mock_get_cache.return_value = None

        import aiohttp

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session
        # session.get() should raise an error when called
        # Since session.get() is used in "async with", we need to make it raise when entered
        mock_error_context = AsyncMock()
        mock_error_context.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("Network error"))
        mock_error_context.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_error_context)

        result = asyncio.run(get_kp_ap_data())

        self.assertIsInstance(result, dict)
        self.assertEqual(result, {})


class TestGetSpaceWeatherConditions(unittest.TestCase):
    """Test suite for get_space_weather_conditions function"""

    @patch("celestron_nexstar.api.events.space_weather.get_kp_ap_data")
    @patch("celestron_nexstar.api.events.space_weather.get_goes_xray_data")
    @patch("celestron_nexstar.api.events.space_weather.get_solar_wind_data")
    def test_get_space_weather_conditions_complete(self, mock_solar_wind, mock_xray, mock_kp):
        """Test getting complete space weather conditions"""
        mock_solar_wind.return_value = {
            "solar_wind_speed": 450.0,
            "solar_wind_bt": 7.5,
            "solar_wind_bz": -2.0,
            "solar_wind_density": 4.5,
        }
        mock_xray.return_value = {"xray_flux": 1.2e-6, "xray_class": "M1.5"}
        mock_kp.return_value = {"kp_index": 4.0}

        result = asyncio.run(get_space_weather_conditions())

        self.assertIsInstance(result, SpaceWeatherConditions)
        self.assertEqual(result.solar_wind_speed, 450.0)
        self.assertEqual(result.solar_wind_bt, 7.5)
        self.assertEqual(result.solar_wind_bz, -2.0)
        self.assertEqual(result.solar_wind_density, 4.5)
        self.assertEqual(result.xray_flux, 1.2e-6)
        self.assertEqual(result.xray_class, "M1.5")
        self.assertEqual(result.kp_index, 4.0)
        self.assertIsNotNone(result.last_updated)

    @patch("celestron_nexstar.api.events.space_weather.get_kp_ap_data", new_callable=AsyncMock)
    @patch("celestron_nexstar.api.events.space_weather.get_goes_xray_data", new_callable=AsyncMock)
    @patch("celestron_nexstar.api.events.space_weather.get_solar_wind_data", new_callable=AsyncMock)
    @patch("celestron_nexstar.api.events.space_weather.get_radio_flux_107", new_callable=AsyncMock)
    @patch("celestron_nexstar.api.events.space_weather.get_proton_flux_data", new_callable=AsyncMock)
    def test_get_space_weather_conditions_g_scale(self, mock_proton, mock_radio, mock_solar_wind, mock_xray, mock_kp):
        """Test G-scale calculation from Kp index"""
        mock_solar_wind.return_value = {}
        mock_xray.return_value = {}
        mock_kp.return_value = {"kp_index": 7.5}  # Should be G3
        mock_radio.return_value = None
        mock_proton.return_value = {}

        result = asyncio.run(get_space_weather_conditions())

        self.assertIsNotNone(result.g_scale)
        self.assertEqual(result.g_scale.level, 3)
        self.assertEqual(result.g_scale.scale_type, "G")

    @patch("celestron_nexstar.api.events.space_weather.get_kp_ap_data", new_callable=AsyncMock)
    @patch("celestron_nexstar.api.events.space_weather.get_goes_xray_data", new_callable=AsyncMock)
    @patch("celestron_nexstar.api.events.space_weather.get_solar_wind_data", new_callable=AsyncMock)
    @patch("celestron_nexstar.api.events.space_weather.get_radio_flux_107", new_callable=AsyncMock)
    @patch("celestron_nexstar.api.events.space_weather.get_proton_flux_data", new_callable=AsyncMock)
    def test_get_space_weather_conditions_r_scale(self, mock_proton, mock_radio, mock_solar_wind, mock_xray, mock_kp):
        """Test R-scale calculation from X-ray class"""
        mock_solar_wind.return_value = {}
        mock_xray.return_value = {"xray_class": "X15.0"}  # Should be R4 (>= 10)
        mock_kp.return_value = {}
        mock_radio.return_value = None
        mock_proton.return_value = {}

        result = asyncio.run(get_space_weather_conditions())

        self.assertIsNotNone(result.r_scale)
        self.assertEqual(result.r_scale.level, 4)
        self.assertEqual(result.r_scale.scale_type, "R")

    @patch("celestron_nexstar.api.events.space_weather.get_kp_ap_data", new_callable=AsyncMock)
    @patch("celestron_nexstar.api.events.space_weather.get_goes_xray_data", new_callable=AsyncMock)
    @patch("celestron_nexstar.api.events.space_weather.get_solar_wind_data", new_callable=AsyncMock)
    @patch("celestron_nexstar.api.events.space_weather.get_radio_flux_107", new_callable=AsyncMock)
    @patch("celestron_nexstar.api.events.space_weather.get_proton_flux_data", new_callable=AsyncMock)
    def test_get_space_weather_conditions_alerts(self, mock_proton, mock_radio, mock_solar_wind, mock_xray, mock_kp):
        """Test alert generation"""
        mock_solar_wind.return_value = {"solar_wind_speed": 650.0}  # High speed
        mock_xray.return_value = {"xray_class": "X2.0"}  # R3
        mock_kp.return_value = {"kp_index": 7.0}  # G3
        mock_radio.return_value = None
        mock_proton.return_value = {}

        result = asyncio.run(get_space_weather_conditions())

        self.assertIsNotNone(result.alerts)
        self.assertGreater(len(result.alerts), 0)
        # Should have alerts for G3 and R3 storms, and high solar wind
        self.assertTrue(any("G3" in alert for alert in result.alerts))
        self.assertTrue(any("R3" in alert for alert in result.alerts))
        self.assertTrue(any("High solar wind" in alert for alert in result.alerts))


if __name__ == "__main__":
    unittest.main()

"""
Unit tests for observer.py

Tests observer location management, geocoding, and auto-detection.
"""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from celestron_nexstar.api.location.observer import (
    DEFAULT_LOCATION,
    ObserverLocation,
    clear_observer_location,
    detect_location_automatically,
    geocode_location,
    geocode_location_batch,
    get_config_path,
    get_observer_location,
    load_location,
    save_location,
    set_observer_location,
)


class TestObserverLocation(unittest.TestCase):
    """Test suite for ObserverLocation dataclass"""

    def test_creation(self):
        """Test creating ObserverLocation"""
        location = ObserverLocation(latitude=40.0, longitude=-100.0, elevation=100.0, name="Test Location")
        self.assertEqual(location.latitude, 40.0)
        self.assertEqual(location.longitude, -100.0)
        self.assertEqual(location.elevation, 100.0)
        self.assertEqual(location.name, "Test Location")

    def test_default_values(self):
        """Test ObserverLocation with default values"""
        location = ObserverLocation(latitude=40.0, longitude=-100.0)
        self.assertEqual(location.elevation, 0.0)
        self.assertIsNone(location.name)

    def test_frozen(self):
        """Test that ObserverLocation is frozen (immutable)"""
        location = ObserverLocation(latitude=40.0, longitude=-100.0)
        with self.assertRaises(Exception):  # dataclass frozen raises FrozenInstanceError
            location.latitude = 50.0


class TestDefaultLocation(unittest.TestCase):
    """Test suite for DEFAULT_LOCATION"""

    def test_default_location(self):
        """Test default location values"""
        self.assertEqual(DEFAULT_LOCATION.latitude, 51.4769)
        self.assertEqual(DEFAULT_LOCATION.longitude, -0.0005)
        self.assertIn("Greenwich", DEFAULT_LOCATION.name or "")


class TestGetConfigPath(unittest.TestCase):
    """Test suite for get_config_path function"""

    def test_get_config_path(self):
        """Test getting config path"""
        path = get_config_path()
        self.assertIsInstance(path, Path)
        self.assertTrue(path.name.endswith(".json"))
        self.assertIn(".config", str(path))


class TestSaveLocation(unittest.TestCase):
    """Test suite for save_location function"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_config_file = Path(self.temp_dir) / "observer_location.json"

    def tearDown(self):
        """Clean up test fixtures"""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("celestron_nexstar.api.location.observer.get_config_path")
    def test_save_location(self, mock_get_path):
        """Test saving location to file"""
        mock_get_path.return_value = self.temp_config_file
        location = ObserverLocation(latitude=40.0, longitude=-100.0, name="Test")

        save_location(location)

        self.assertTrue(self.temp_config_file.exists())
        with self.temp_config_file.open() as f:
            data = json.load(f)
            self.assertEqual(data["latitude"], 40.0)
            self.assertEqual(data["longitude"], -100.0)
            self.assertEqual(data["name"], "Test")

    @patch("celestron_nexstar.api.location.observer.get_config_path")
    def test_save_location_with_elevation(self, mock_get_path):
        """Test saving location with elevation"""
        mock_get_path.return_value = self.temp_config_file
        location = ObserverLocation(latitude=40.0, longitude=-100.0, elevation=500.0, name="Mountain")

        save_location(location)

        with self.temp_config_file.open() as f:
            data = json.load(f)
            self.assertEqual(data["elevation"], 500.0)


class TestLoadLocation(unittest.TestCase):
    """Test suite for load_location function"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_config_file = Path(self.temp_dir) / "observer_location.json"

    def tearDown(self):
        """Clean up test fixtures"""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("celestron_nexstar.api.location.observer.get_config_path")
    def test_load_location_success(self, mock_get_path):
        """Test loading location from file"""
        mock_get_path.return_value = self.temp_config_file
        data = {"latitude": 40.0, "longitude": -100.0, "elevation": 100.0, "name": "Test"}
        with self.temp_config_file.open("w") as f:
            json.dump(data, f)

        location = load_location()

        self.assertEqual(location.latitude, 40.0)
        self.assertEqual(location.longitude, -100.0)
        self.assertEqual(location.elevation, 100.0)
        self.assertEqual(location.name, "Test")

    @patch("celestron_nexstar.api.location.observer.get_config_path")
    def test_load_location_not_exists(self, mock_get_path):
        """Test loading when file doesn't exist"""
        mock_get_path.return_value = self.temp_config_file

        location = load_location(ask_for_auto_detect=False)

        self.assertEqual(location, DEFAULT_LOCATION)

    @patch("celestron_nexstar.api.location.observer.get_config_path")
    def test_load_location_invalid_json(self, mock_get_path):
        """Test loading with invalid JSON"""
        mock_get_path.return_value = self.temp_config_file
        self.temp_config_file.write_text("invalid json{")

        location = load_location()

        self.assertEqual(location, DEFAULT_LOCATION)

    @patch("celestron_nexstar.api.location.observer.get_config_path")
    def test_load_location_missing_fields(self, mock_get_path):
        """Test loading with missing required fields"""
        mock_get_path.return_value = self.temp_config_file
        data = {"name": "Test"}  # Missing latitude/longitude
        with self.temp_config_file.open("w") as f:
            json.dump(data, f)

            location = load_location()

        self.assertEqual(location, DEFAULT_LOCATION)

    @patch("celestron_nexstar.api.location.observer.get_config_path")
    def test_load_location_invalid_latitude(self, mock_get_path):
        """Test loading with invalid latitude"""
        mock_get_path.return_value = self.temp_config_file
        data = {"latitude": 100.0, "longitude": -100.0}  # Invalid latitude
        with self.temp_config_file.open("w") as f:
            json.dump(data, f)

            location = load_location()

        self.assertEqual(location, DEFAULT_LOCATION)

    @patch("celestron_nexstar.api.location.observer.get_config_path")
    def test_load_location_invalid_longitude(self, mock_get_path):
        """Test loading with invalid longitude"""
        mock_get_path.return_value = self.temp_config_file
        data = {"latitude": 40.0, "longitude": 200.0}  # Invalid longitude
        with self.temp_config_file.open("w") as f:
            json.dump(data, f)

            location = load_location()

        self.assertEqual(location, DEFAULT_LOCATION)

    @patch("celestron_nexstar.api.location.observer.get_config_path")
    def test_load_location_negative_elevation(self, mock_get_path):
        """Test loading with negative elevation (should be clamped to 0)"""
        mock_get_path.return_value = self.temp_config_file
        data = {"latitude": 40.0, "longitude": -100.0, "elevation": -100.0}
        with self.temp_config_file.open("w") as f:
            json.dump(data, f)

            location = load_location()

        self.assertEqual(location.elevation, 0.0)


class TestGetObserverLocation(unittest.TestCase):
    """Test suite for get_observer_location function"""

    def setUp(self):
        """Set up test fixtures"""
        clear_observer_location()

    def tearDown(self):
        """Clean up test fixtures"""
        clear_observer_location()

    @patch("celestron_nexstar.api.location.observer.load_location")
    def test_get_observer_location_cached(self, mock_load):
        """Test getting cached observer location"""
        location = ObserverLocation(latitude=40.0, longitude=-100.0, name="Test")
        set_observer_location(location, save=False)

        result = get_observer_location()

        self.assertEqual(result, location)
        mock_load.assert_not_called()

    @patch("celestron_nexstar.api.location.observer.load_location")
    def test_get_observer_location_not_cached(self, mock_load):
        """Test getting observer location when not cached"""
        location = ObserverLocation(latitude=40.0, longitude=-100.0, name="Test")
        mock_load.return_value = location

        result = get_observer_location()

        self.assertEqual(result, location)
        mock_load.assert_called_once()


class TestSetObserverLocation(unittest.TestCase):
    """Test suite for set_observer_location function"""

    def setUp(self):
        """Set up test fixtures"""
        clear_observer_location()

    def tearDown(self):
        """Clean up test fixtures"""
        clear_observer_location()

    @patch("celestron_nexstar.api.location.observer.save_location")
    def test_set_observer_location_with_save(self, mock_save):
        """Test setting observer location with save"""
        location = ObserverLocation(latitude=40.0, longitude=-100.0, name="Test")

        set_observer_location(location, save=True)

        mock_save.assert_called_once_with(location)
        self.assertEqual(get_observer_location(), location)

    @patch("celestron_nexstar.api.location.observer.save_location")
    def test_set_observer_location_without_save(self, mock_save):
        """Test setting observer location without save"""
        location = ObserverLocation(latitude=40.0, longitude=-100.0, name="Test")

        set_observer_location(location, save=False)

        mock_save.assert_not_called()
        self.assertEqual(get_observer_location(), location)


class TestClearObserverLocation(unittest.TestCase):
    """Test suite for clear_observer_location function"""

    def setUp(self):
        """Set up test fixtures"""
        clear_observer_location()

    def tearDown(self):
        """Clean up test fixtures"""
        clear_observer_location()

    @patch("celestron_nexstar.api.location.observer.load_location")
    def test_clear_observer_location(self, mock_load):
        """Test clearing observer location"""
        location = ObserverLocation(latitude=40.0, longitude=-100.0, name="Test")
        set_observer_location(location, save=False)

        clear_observer_location()

        mock_load.return_value = DEFAULT_LOCATION
        result = get_observer_location()
        self.assertEqual(result, DEFAULT_LOCATION)


class TestGeocodeLocation(unittest.TestCase):
    """Test suite for geocode_location function"""

    @patch("aiohttp.ClientSession")
    def test_geocode_location_success(self, mock_session_class):
        """Test successful geocoding"""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value=[
                {
                    "lat": "40.7128",
                    "lon": "-74.0060",
                    "display_name": "New York, NY, USA",
                }
            ]
        )

        # Create async context manager for response
        mock_response_context = AsyncMock()
        mock_response_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_response_context)
        mock_session_class.return_value = mock_session

        result = asyncio.run(geocode_location("New York, NY"))

        self.assertIsInstance(result, ObserverLocation)
        self.assertAlmostEqual(result.latitude, 40.7128, places=4)
        self.assertAlmostEqual(result.longitude, -74.0060, places=4)
        self.assertIn("New York", result.name or "")

    @patch("aiohttp.ClientSession")
    def test_geocode_location_not_found(self, mock_session_class):
        """Test geocoding when location not found"""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=[])

        mock_response_context = AsyncMock()
        mock_response_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_response_context)
        mock_session_class.return_value = mock_session

        with self.assertRaises(ValueError) as context:
            asyncio.run(geocode_location("NonexistentPlace12345"))

        self.assertIn("Could not find location", str(context.exception))

    @patch("aiohttp.ClientSession")
    def test_geocode_location_api_error(self, mock_session_class):
        """Test geocoding when API returns error"""
        mock_response = AsyncMock()
        mock_response.status = 500

        mock_response_context = AsyncMock()
        mock_response_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_response_context)
        mock_session_class.return_value = mock_session

        with self.assertRaises(ValueError) as context:
            asyncio.run(geocode_location("New York"))

        self.assertIn("Geocoding API returned", str(context.exception))

    @patch("aiohttp.ClientSession")
    def test_geocode_location_exception(self, mock_session_class):
        """Test geocoding when exception occurs"""
        mock_session_class.side_effect = Exception("Connection error")

        with self.assertRaises(ValueError) as context:
            asyncio.run(geocode_location("New York"))

        self.assertIn("Failed to geocode", str(context.exception))


class TestGeocodeLocationBatch(unittest.TestCase):
    """Test suite for geocode_location_batch function"""

    @patch("celestron_nexstar.api.location.observer.geocode_location")
    def test_geocode_location_batch_success(self, mock_geocode):
        """Test successful batch geocoding"""
        location1 = ObserverLocation(latitude=40.7128, longitude=-74.0060, name="New York")
        location2 = ObserverLocation(latitude=34.0522, longitude=-118.2437, name="Los Angeles")
        mock_geocode.side_effect = [location1, location2]

        queries = ["New York", "Los Angeles"]
        result = asyncio.run(geocode_location_batch(queries))

        self.assertEqual(len(result), 2)
        self.assertIn("New York", result)
        self.assertIn("Los Angeles", result)

    @patch("celestron_nexstar.api.location.observer.geocode_location")
    def test_geocode_location_batch_with_errors(self, mock_geocode):
        """Test batch geocoding with some errors"""
        location1 = ObserverLocation(latitude=40.7128, longitude=-74.0060, name="New York")
        mock_geocode.side_effect = [location1, ValueError("Not found")]

        queries = ["New York", "Nonexistent"]
        result = asyncio.run(geocode_location_batch(queries))

        self.assertEqual(len(result), 1)
        self.assertIn("New York", result)
        self.assertNotIn("Nonexistent", result)


class TestDetectLocationAutomatically(unittest.TestCase):
    """Test suite for detect_location_automatically function"""

    @patch("celestron_nexstar.api.location.observer._get_location_from_system")
    @patch("celestron_nexstar.api.location.observer._get_location_from_ip")
    def test_detect_location_from_system(self, mock_ip, mock_system):
        """Test detection from system location services"""
        location = ObserverLocation(latitude=40.0, longitude=-100.0, name="System location")
        mock_system.return_value = location
        mock_ip.return_value = None

        result = asyncio.run(detect_location_automatically())

        self.assertEqual(result, location)
        mock_ip.assert_not_called()

    @patch("celestron_nexstar.api.location.observer._get_location_from_system")
    @patch("celestron_nexstar.api.location.observer._get_location_from_ip")
    def test_detect_location_from_ip(self, mock_ip, mock_system):
        """Test detection from IP when system fails"""
        mock_system.return_value = None
        location = ObserverLocation(latitude=40.0, longitude=-100.0, name="IP location")
        mock_ip.return_value = location

        result = asyncio.run(detect_location_automatically())

        self.assertEqual(result, location)

    @patch("celestron_nexstar.api.location.observer._get_location_from_system")
    @patch("celestron_nexstar.api.location.observer._get_location_from_ip")
    def test_detect_location_failure(self, mock_ip, mock_system):
        """Test detection failure"""
        mock_system.return_value = None
        mock_ip.return_value = None

        with self.assertRaises(ValueError) as context:
            asyncio.run(detect_location_automatically())

        self.assertIn("Could not automatically detect", str(context.exception))


class TestGetLocationFromIp(unittest.TestCase):
    """Test suite for _get_location_from_ip function"""

    @patch("aiohttp.ClientSession")
    def test_get_location_from_ip_success(self, mock_session_class):
        """Test successful IP geolocation"""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "latitude": 40.7128,
                "longitude": -74.0060,
                "city": "New York",
                "region": "New York",
                "country_name": "United States",
            }
        )

        mock_response_context = AsyncMock()
        mock_response_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_response_context)
        mock_session_class.return_value = mock_session

        from celestron_nexstar.api.location.observer import _get_location_from_ip

        result = asyncio.run(_get_location_from_ip())

        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.latitude, 40.7128, places=4)
        self.assertAlmostEqual(result.longitude, -74.0060, places=4)
        self.assertIn("New York", result.name or "")

    @patch("aiohttp.ClientSession")
    def test_get_location_from_ip_api_error(self, mock_session_class):
        """Test IP geolocation when API returns error"""
        mock_response = AsyncMock()
        mock_response.status = 500

        mock_response_context = AsyncMock()
        mock_response_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_response_context)
        mock_session_class.return_value = mock_session

        from celestron_nexstar.api.location.observer import _get_location_from_ip

        result = asyncio.run(_get_location_from_ip())

        self.assertIsNone(result)

    @patch("aiohttp.ClientSession")
    def test_get_location_from_ip_missing_coordinates(self, mock_session_class):
        """Test IP geolocation when response missing coordinates"""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"city": "New York"})  # Missing lat/lon

        mock_response_context = AsyncMock()
        mock_response_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_response_context)
        mock_session_class.return_value = mock_session

        from celestron_nexstar.api.location.observer import _get_location_from_ip

        result = asyncio.run(_get_location_from_ip())

        self.assertIsNone(result)


class TestGetLocationFromSystem(unittest.TestCase):
    """Test suite for _get_location_from_system function"""

    @patch("platform.system")
    def test_get_location_from_system_linux(self, mock_platform):
        """Test system location on Linux"""
        mock_platform.return_value = "Linux"
        from celestron_nexstar.api.location.observer import _get_location_from_system

        # Should return None if dbus not available or permission denied
        result = asyncio.run(_get_location_from_system())
        # Result may be None if dbus not available, which is expected
        self.assertIsNone(result)  # dbus likely not available in test environment

    @patch("platform.system")
    def test_get_location_from_system_darwin(self, mock_platform):
        """Test system location on macOS"""
        mock_platform.return_value = "Darwin"
        from celestron_nexstar.api.location.observer import _get_location_from_system

        # Should return None if PyObjC not available
        result = asyncio.run(_get_location_from_system())
        # Result may be None if PyObjC not available, which is expected
        self.assertIsNone(result)  # PyObjC likely not available in test environment

    @patch("platform.system")
    def test_get_location_from_system_windows(self, mock_platform):
        """Test system location on Windows"""
        mock_platform.return_value = "Windows"
        from celestron_nexstar.api.location.observer import _get_location_from_system

        # Should return None if winrt not available
        result = asyncio.run(_get_location_from_system())
        # Result may be None if winrt not available, which is expected
        self.assertIsNone(result)  # winrt likely not available in test environment

    @patch("platform.system")
    def test_get_location_from_system_unknown(self, mock_platform):
        """Test system location on unknown platform"""
        mock_platform.return_value = "UnknownOS"
        from celestron_nexstar.api.location.observer import _get_location_from_system

        result = asyncio.run(_get_location_from_system())
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()

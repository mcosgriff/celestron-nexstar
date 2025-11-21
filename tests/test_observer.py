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

from celestron_nexstar.api.core.exceptions import (
    GeocodingError,
    LocationNotFoundError,
    LocationNotSetError,
)
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

        with self.assertRaises(LocationNotFoundError) as context:
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

        with self.assertRaises(GeocodingError) as context:
            asyncio.run(geocode_location("New York"))

        self.assertIn("Geocoding API returned", str(context.exception))

    @patch("aiohttp.ClientSession")
    def test_geocode_location_exception(self, mock_session_class):
        """Test geocoding when exception occurs"""
        mock_session_class.side_effect = Exception("Connection error")

        with self.assertRaises(GeocodingError) as context:
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

        with self.assertRaises(LocationNotSetError) as context:
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


class TestLoadLocationEdgeCases(unittest.TestCase):
    """Test suite for edge cases in load_location function"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_config_file = Path(self.temp_dir) / "observer_location.json"

    def tearDown(self):
        """Clean up test fixtures"""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("celestron_nexstar.api.location.observer.get_config_path")
    def test_load_location_with_type_error(self, mock_get_path):
        """Test loading with TypeError (invalid data type)"""
        mock_get_path.return_value = self.temp_config_file
        # Write invalid data that causes TypeError
        self.temp_config_file.write_text('{"latitude": "not a number", "longitude": -100.0}')

        location = load_location()
        self.assertEqual(location, DEFAULT_LOCATION)

    @patch("celestron_nexstar.api.location.observer.get_config_path")
    def test_load_location_with_zero_elevation(self, mock_get_path):
        """Test loading with zero elevation"""
        mock_get_path.return_value = self.temp_config_file
        data = {"latitude": 40.0, "longitude": -100.0, "elevation": 0.0}
        with self.temp_config_file.open("w") as f:
            json.dump(data, f)

        location = load_location()
        self.assertEqual(location.elevation, 0.0)

    @patch("celestron_nexstar.api.location.observer.get_config_path")
    def test_load_location_with_high_elevation(self, mock_get_path):
        """Test loading with high elevation"""
        mock_get_path.return_value = self.temp_config_file
        data = {"latitude": 40.0, "longitude": -100.0, "elevation": 8848.0}  # Mount Everest
        with self.temp_config_file.open("w") as f:
            json.dump(data, f)

        location = load_location()
        self.assertEqual(location.elevation, 8848.0)

    @patch("celestron_nexstar.api.location.observer.get_config_path")
    def test_load_location_without_name(self, mock_get_path):
        """Test loading location without name field"""
        mock_get_path.return_value = self.temp_config_file
        data = {"latitude": 40.0, "longitude": -100.0}  # No name
        with self.temp_config_file.open("w") as f:
            json.dump(data, f)

        location = load_location()
        self.assertIsNone(location.name)

    @patch("celestron_nexstar.api.location.observer.get_config_path")
    def test_load_location_with_empty_name(self, mock_get_path):
        """Test loading location with empty name"""
        mock_get_path.return_value = self.temp_config_file
        data = {"latitude": 40.0, "longitude": -100.0, "name": ""}
        with self.temp_config_file.open("w") as f:
            json.dump(data, f)

        location = load_location()
        self.assertEqual(location.name, "")


class TestGeocodeLocationEdgeCases(unittest.TestCase):
    """Test suite for edge cases in geocode_location function"""

    @patch("aiohttp.ClientSession")
    def test_geocode_location_with_empty_response(self, mock_session_class):
        """Test geocoding with empty response"""
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

        with self.assertRaises(LocationNotFoundError):
            asyncio.run(geocode_location("Test Location"))

    @patch("aiohttp.ClientSession")
    def test_geocode_location_with_missing_coordinates(self, mock_session_class):
        """Test geocoding with response missing lat/lon"""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=[{"display_name": "Test"}])  # Missing lat/lon

        mock_response_context = AsyncMock()
        mock_response_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_response_context)
        mock_session_class.return_value = mock_session

        with self.assertRaises(GeocodingError):
            asyncio.run(geocode_location("Test Location"))

    @patch("aiohttp.ClientSession")
    def test_geocode_location_with_invalid_coordinates(self, mock_session_class):
        """Test geocoding with invalid coordinate values"""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=[{"lat": "invalid", "lon": "invalid", "display_name": "Test"}])

        mock_response_context = AsyncMock()
        mock_response_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_response_context)
        mock_session_class.return_value = mock_session

        with self.assertRaises(GeocodingError):
            asyncio.run(geocode_location("Test Location"))


class TestGetObserverLocationEdgeCases(unittest.TestCase):
    """Test suite for edge cases in get_observer_location function"""

    def setUp(self):
        """Set up test fixtures"""
        clear_observer_location()

    def tearDown(self):
        """Clean up test fixtures"""
        clear_observer_location()

    @patch("celestron_nexstar.api.location.observer.load_location")
    def test_get_observer_location_ask_for_auto_detect(self, mock_load):
        """Test get_observer_location with ask_for_auto_detect=True"""
        location = ObserverLocation(latitude=40.0, longitude=-100.0, name="Test")
        mock_load.return_value = location

        result = get_observer_location(ask_for_auto_detect=True)

        self.assertEqual(result, location)
        mock_load.assert_called_once_with(ask_for_auto_detect=True)


class TestSetObserverLocationEdgeCases(unittest.TestCase):
    """Test suite for edge cases in set_observer_location function"""

    def setUp(self):
        """Set up test fixtures"""
        clear_observer_location()

    def tearDown(self):
        """Clean up test fixtures"""
        clear_observer_location()

    @patch("celestron_nexstar.api.location.observer.save_location")
    def test_set_observer_location_without_save(self, mock_save):
        """Test setting location without saving"""
        location = ObserverLocation(latitude=40.0, longitude=-100.0, name="Test")

        set_observer_location(location, save=False)

        self.assertEqual(get_observer_location(), location)
        mock_save.assert_not_called()

    def test_set_observer_location_extreme_coordinates(self):
        """Test setting location with extreme but valid coordinates"""
        # North pole
        location_north = ObserverLocation(latitude=90.0, longitude=0.0, name="North Pole")
        set_observer_location(location_north, save=False)
        self.assertEqual(get_observer_location().latitude, 90.0)

        # South pole
        location_south = ObserverLocation(latitude=-90.0, longitude=0.0, name="South Pole")
        set_observer_location(location_south, save=False)
        self.assertEqual(get_observer_location().latitude, -90.0)

        # International Date Line
        location_idl = ObserverLocation(latitude=0.0, longitude=180.0, name="IDL")
        set_observer_location(location_idl, save=False)
        self.assertEqual(get_observer_location().longitude, 180.0)

        # Prime Meridian
        location_pm = ObserverLocation(latitude=0.0, longitude=0.0, name="Prime Meridian")
        set_observer_location(location_pm, save=False)
        self.assertEqual(get_observer_location().longitude, 0.0)


class TestLoadLocationAutoDetect(unittest.TestCase):
    """Test suite for load_location auto-detect functionality"""

    @patch("celestron_nexstar.api.location.observer.get_config_path")
    @patch("sys.stdin.isatty")
    @patch("celestron_nexstar.api.location.observer.detect_location_automatically")
    def test_load_location_auto_detect_yes(self, mock_detect, mock_isatty, mock_get_path):
        """Test load_location with auto-detect when user says yes"""
        import tempfile
        from pathlib import Path

        temp_dir = tempfile.mkdtemp()
        temp_config_file = Path(temp_dir) / "observer_location.json"
        mock_get_path.return_value = temp_config_file
        mock_isatty.return_value = True
        mock_detect.return_value = ObserverLocation(latitude=40.0, longitude=-100.0, name="Detected")

        with patch("rich.console.Console") as mock_console_class, \
             patch("rich.prompt.Confirm") as mock_confirm_class, \
             patch("celestron_nexstar.api.location.observer.save_location") as mock_save:
            mock_console = MagicMock()
            mock_console_class.return_value = mock_console
            # Confirm.ask is called as a class method with console parameter
            mock_confirm_class.ask = MagicMock(side_effect=[True, True])  # Yes to detect, yes to use

            from celestron_nexstar.api.location.observer import load_location
            result = load_location(ask_for_auto_detect=True)

            # Should return detected location
            self.assertEqual(result.latitude, 40.0)
            self.assertEqual(result.longitude, -100.0)

        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    @patch("celestron_nexstar.api.location.observer.get_config_path")
    @patch("sys.stdin.isatty")
    def test_load_location_auto_detect_no_tty(self, mock_isatty, mock_get_path):
        """Test load_location when not in TTY (no auto-detect prompt)"""
        import tempfile
        from pathlib import Path

        temp_dir = tempfile.mkdtemp()
        temp_config_file = Path(temp_dir) / "observer_location.json"
        mock_get_path.return_value = temp_config_file
        mock_isatty.return_value = False  # Not a TTY

        from celestron_nexstar.api.location.observer import load_location
        result = load_location(ask_for_auto_detect=True)

        # Should return default location
        from celestron_nexstar.api.location.observer import DEFAULT_LOCATION
        self.assertEqual(result, DEFAULT_LOCATION)

        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    @patch("celestron_nexstar.api.location.observer.get_config_path")
    @patch("sys.stdin.isatty")
    @patch("celestron_nexstar.api.location.observer.detect_location_automatically")
    def test_load_location_auto_detect_user_says_no(self, mock_detect, mock_isatty, mock_get_path):
        """Test load_location with auto-detect when user says no"""
        import tempfile
        from pathlib import Path

        temp_dir = tempfile.mkdtemp()
        temp_config_file = Path(temp_dir) / "observer_location.json"
        mock_get_path.return_value = temp_config_file
        mock_isatty.return_value = True

        with patch("rich.console.Console") as mock_console_class, \
             patch("rich.prompt.Confirm") as mock_confirm_class:
            mock_console = MagicMock()
            mock_console_class.return_value = mock_console
            # Confirm.ask is called as a class method with console parameter
            # First ask is for "Detect location automatically?" - user says no
            mock_confirm_class.ask = MagicMock(return_value=False)  # User says no to detection

            from celestron_nexstar.api.location.observer import load_location
            result = load_location(ask_for_auto_detect=True)

            # Should return default location
            from celestron_nexstar.api.location.observer import DEFAULT_LOCATION
            self.assertEqual(result, DEFAULT_LOCATION)
            # detect_location_automatically should not be called if user says no
            mock_detect.assert_not_called()

        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    @patch("celestron_nexstar.api.location.observer.get_config_path")
    @patch("sys.stdin.isatty")
    @patch("celestron_nexstar.api.location.observer.detect_location_automatically")
    def test_load_location_auto_detect_user_rejects_location(self, mock_detect, mock_isatty, mock_get_path):
        """Test load_location when user rejects detected location"""
        import tempfile
        from pathlib import Path

        temp_dir = tempfile.mkdtemp()
        temp_config_file = Path(temp_dir) / "observer_location.json"
        mock_get_path.return_value = temp_config_file
        mock_isatty.return_value = True
        mock_detect.return_value = ObserverLocation(latitude=40.0, longitude=-100.0, name="Detected")

        with patch("rich.console.Console") as mock_console_class, \
             patch("rich.prompt.Confirm") as mock_confirm_class:
            mock_console = MagicMock()
            mock_console_class.return_value = mock_console
            # Confirm.ask is called as a class method with console parameter
            mock_confirm_class.ask = MagicMock(side_effect=[True, False])  # Yes to detect, no to use

            from celestron_nexstar.api.location.observer import load_location
            result = load_location(ask_for_auto_detect=True)

            # Should return default location
            from celestron_nexstar.api.location.observer import DEFAULT_LOCATION
            self.assertEqual(result, DEFAULT_LOCATION)

        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    @patch("celestron_nexstar.api.location.observer.get_config_path")
    @patch("sys.stdin.isatty")
    @patch("celestron_nexstar.api.location.observer.detect_location_automatically")
    def test_load_location_auto_detect_exception(self, mock_detect, mock_isatty, mock_get_path):
        """Test load_location when auto-detect raises exception"""
        import tempfile
        from pathlib import Path

        temp_dir = tempfile.mkdtemp()
        temp_config_file = Path(temp_dir) / "observer_location.json"
        mock_get_path.return_value = temp_config_file
        mock_isatty.return_value = True
        mock_detect.side_effect = Exception("Detection failed")

        with patch("rich.console.Console") as mock_console_class, \
             patch("rich.prompt.Confirm") as mock_confirm_class:
            mock_console = MagicMock()
            mock_console_class.return_value = mock_console
            mock_confirm = MagicMock()
            mock_confirm.ask.return_value = True  # Yes to detect
            mock_confirm_class.return_value = mock_confirm

            from celestron_nexstar.api.location.observer import load_location
            result = load_location(ask_for_auto_detect=True)

            # Should return default location on error
            from celestron_nexstar.api.location.observer import DEFAULT_LOCATION
            self.assertEqual(result, DEFAULT_LOCATION)

        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    @patch("celestron_nexstar.api.location.observer.get_config_path")
    @patch("sys.stdin.isatty")
    @patch("celestron_nexstar.api.location.observer.detect_location_automatically")
    def test_load_location_auto_detect_value_error(self, mock_detect, mock_isatty, mock_get_path):
        """Test load_location when auto-detect raises ValueError"""
        import tempfile
        from pathlib import Path

        temp_dir = tempfile.mkdtemp()
        temp_config_file = Path(temp_dir) / "observer_location.json"
        mock_get_path.return_value = temp_config_file
        mock_isatty.return_value = True
        mock_detect.side_effect = ValueError("Location not found")

        with patch("rich.console.Console") as mock_console_class, \
             patch("rich.prompt.Confirm") as mock_confirm_class:
            mock_console = MagicMock()
            mock_console_class.return_value = mock_console
            mock_confirm = MagicMock()
            mock_confirm.ask.return_value = True  # Yes to detect
            mock_confirm_class.return_value = mock_confirm

            from celestron_nexstar.api.location.observer import load_location
            result = load_location(ask_for_auto_detect=True)

            # Should return default location on error
            from celestron_nexstar.api.location.observer import DEFAULT_LOCATION
            self.assertEqual(result, DEFAULT_LOCATION)

        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)





if __name__ == "__main__":
    unittest.main()

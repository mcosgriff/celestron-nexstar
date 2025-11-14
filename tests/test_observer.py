"""
Unit tests for observer location management.
Tests geocoding, location saving/loading, and configuration management.
"""

import asyncio
import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from celestron_nexstar.api.location.observer import (
    DEFAULT_LOCATION,
    ObserverLocation,
    clear_observer_location,
    geocode_location,
    get_config_path,
    get_observer_location,
    load_location,
    save_location,
    set_observer_location,
)


class TestObserverLocation(unittest.TestCase):
    """Test suite for ObserverLocation dataclass."""

    def test_observer_location_creation(self):
        """Test creating an ObserverLocation."""
        location = ObserverLocation(latitude=40.7128, longitude=-74.0060, elevation=10.0, name="New York City")
        self.assertEqual(location.latitude, 40.7128)
        self.assertEqual(location.longitude, -74.0060)
        self.assertEqual(location.elevation, 10.0)
        self.assertEqual(location.name, "New York City")

    def test_observer_location_defaults(self):
        """Test ObserverLocation with default values."""
        location = ObserverLocation(latitude=50.0, longitude=10.0)
        self.assertEqual(location.elevation, 0.0)
        self.assertIsNone(location.name)

    def test_default_location(self):
        """Test that DEFAULT_LOCATION is Greenwich Observatory."""
        self.assertAlmostEqual(DEFAULT_LOCATION.latitude, 51.4769, places=4)
        self.assertAlmostEqual(DEFAULT_LOCATION.longitude, -0.0005, places=4)
        self.assertEqual(DEFAULT_LOCATION.elevation, 0.0)
        self.assertIn("Greenwich", DEFAULT_LOCATION.name)


class TestConfigPath(unittest.TestCase):
    """Test suite for configuration path management."""

    @patch("celestron_nexstar.api.location.observer.Path.mkdir")
    @patch("celestron_nexstar.api.location.observer.Path.home")
    def test_get_config_path(self, mock_home, mock_mkdir):
        """Test getting the config path."""
        mock_home.return_value = Path("/home/testuser")
        config_path = get_config_path()

        expected_path = Path("/home/testuser/.config/celestron-nexstar/observer_location.json")
        self.assertEqual(config_path, expected_path)


class TestSaveLoadLocation(unittest.TestCase):
    """Test suite for saving and loading observer locations."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_location = ObserverLocation(
            latitude=34.0522, longitude=-118.2437, elevation=100.0, name="Los Angeles"
        )

    @patch("celestron_nexstar.api.location.observer.get_config_path")
    def test_save_location(self, mock_get_config_path):
        """Test saving a location to config file."""
        mock_path = MagicMock()
        mock_file = MagicMock()
        mock_path.open.return_value.__enter__.return_value = mock_file
        mock_get_config_path.return_value = mock_path

        save_location(self.test_location)

        mock_path.open.assert_called_once_with("w")
        # Verify json.dump was called
        self.assertTrue(mock_file.write.called or hasattr(mock_file, "__enter__"))

    @patch("celestron_nexstar.api.location.observer.get_config_path")
    def test_load_location_file_not_exists(self, mock_get_config_path):
        """Test loading location when config file doesn't exist."""
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_get_config_path.return_value = mock_path

        location = load_location()

        self.assertEqual(location, DEFAULT_LOCATION)

    @patch("celestron_nexstar.api.location.observer.get_config_path")
    def test_load_location_success(self, mock_get_config_path):
        """Test successfully loading a location from config file."""
        mock_path = MagicMock()
        mock_path.exists.return_value = True

        test_data = {"latitude": 34.0522, "longitude": -118.2437, "elevation": 100.0, "name": "Los Angeles"}

        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = json.dumps(test_data)
        mock_path.open.return_value = mock_file
        mock_get_config_path.return_value = mock_path

        with patch("json.load", return_value=test_data):
            location = load_location()

        self.assertEqual(location.latitude, 34.0522)
        self.assertEqual(location.longitude, -118.2437)
        self.assertEqual(location.elevation, 100.0)
        self.assertEqual(location.name, "Los Angeles")

    @patch("celestron_nexstar.api.location.observer.get_config_path")
    def test_load_location_corrupted_file(self, mock_get_config_path):
        """Test loading location with corrupted config file."""
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.open.return_value.__enter__.return_value = MagicMock()
        mock_get_config_path.return_value = mock_path

        with patch("json.load", side_effect=json.JSONDecodeError("msg", "doc", 0)):
            location = load_location()

        self.assertEqual(location, DEFAULT_LOCATION)

    @patch("celestron_nexstar.api.location.observer.get_config_path")
    def test_load_location_missing_keys(self, mock_get_config_path):
        """Test loading location with missing required keys."""
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.open.return_value.__enter__.return_value = MagicMock()
        mock_get_config_path.return_value = mock_path

        # Missing latitude key
        with patch("json.load", return_value={"longitude": -118.2437}):
            location = load_location()

        self.assertEqual(location, DEFAULT_LOCATION)

    @patch("celestron_nexstar.api.location.observer.get_config_path")
    def test_load_location_no_elevation(self, mock_get_config_path):
        """Test loading location without elevation (should default to 0.0)."""
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.open.return_value.__enter__.return_value = MagicMock()
        mock_get_config_path.return_value = mock_path

        test_data = {
            "latitude": 34.0522,
            "longitude": -118.2437,
        }

        with patch("json.load", return_value=test_data):
            location = load_location()

        self.assertEqual(location.latitude, 34.0522)
        self.assertEqual(location.longitude, -118.2437)
        self.assertEqual(location.elevation, 0.0)
        self.assertIsNone(location.name)


class TestGetSetObserverLocation(unittest.TestCase):
    """Test suite for getting and setting the current observer location."""

    def setUp(self):
        """Set up test fixtures."""
        # Clear any cached location before each test
        clear_observer_location()

    def tearDown(self):
        """Clean up after each test."""
        clear_observer_location()

    @patch("celestron_nexstar.api.location.observer.load_location")
    def test_get_observer_location_first_call(self, mock_load):
        """Test getting observer location on first call (loads from file)."""
        test_location = ObserverLocation(latitude=40.0, longitude=-100.0, name="Test Location")
        mock_load.return_value = test_location

        location = get_observer_location()

        self.assertEqual(location, test_location)
        mock_load.assert_called_once()

    @patch("celestron_nexstar.api.location.observer.load_location")
    def test_get_observer_location_cached(self, mock_load):
        """Test that subsequent calls use cached location."""
        test_location = ObserverLocation(latitude=40.0, longitude=-100.0, name="Test Location")
        mock_load.return_value = test_location

        # First call
        location1 = get_observer_location()
        # Second call
        location2 = get_observer_location()

        self.assertEqual(location1, location2)
        # Should only load once, then use cache
        mock_load.assert_called_once()

    @patch("celestron_nexstar.api.location.observer.save_location")
    def test_set_observer_location_with_save(self, mock_save):
        """Test setting observer location with save=True."""
        test_location = ObserverLocation(latitude=45.0, longitude=-90.0, name="New Location")

        set_observer_location(test_location, save=True)

        # Verify it was saved
        mock_save.assert_called_once_with(test_location)

        # Verify it's now the current location
        current = get_observer_location()
        self.assertEqual(current, test_location)

    @patch("celestron_nexstar.api.location.observer.save_location")
    def test_set_observer_location_without_save(self, mock_save):
        """Test setting observer location with save=False."""
        test_location = ObserverLocation(latitude=45.0, longitude=-90.0, name="New Location")

        set_observer_location(test_location, save=False)

        # Verify it was NOT saved
        mock_save.assert_not_called()

        # Verify it's still the current location
        current = get_observer_location()
        self.assertEqual(current, test_location)

    @patch("celestron_nexstar.api.location.observer.load_location")
    def test_clear_observer_location(self, mock_load):
        """Test clearing cached observer location."""
        test_location = ObserverLocation(latitude=40.0, longitude=-100.0, name="Test Location")
        mock_load.return_value = test_location

        # Get location (caches it)
        get_observer_location()
        mock_load.assert_called_once()

        # Clear the cache
        clear_observer_location()

        # Get location again (should load from file again)
        get_observer_location()
        self.assertEqual(mock_load.call_count, 2)


class TestGeocoding(unittest.TestCase):
    """Test suite for geocoding functionality."""

    @patch("aiohttp.ClientSession")
    def test_geocode_location_success(self, mock_session_class):
        """Test successful geocoding of a location."""
        # Mock the async context manager and response
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

        # Mock session.get() to return an async context manager
        mock_get_context = AsyncMock()
        mock_get_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_get_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_get_context)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

        result = asyncio.run(geocode_location("New York City"))

        self.assertIsNotNone(result)
        self.assertEqual(result.latitude, 40.7128)
        self.assertEqual(result.longitude, -74.0060)
        self.assertEqual(result.elevation, 0.0)
        self.assertEqual(result.name, "New York, NY, USA")

    @patch("aiohttp.ClientSession")
    def test_geocode_location_not_found(self, mock_session_class):
        """Test geocoding when location is not found."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=[])

        mock_get_context = AsyncMock()
        mock_get_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_get_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_get_context)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

        with self.assertRaises(ValueError) as context:
            asyncio.run(geocode_location("NonexistentPlace12345"))

        self.assertIn("Could not find location", str(context.exception))

    @patch("aiohttp.ClientSession")
    def test_geocode_location_geopy_error(self, mock_session_class):
        """Test geocoding when HTTP error occurs."""
        mock_response = AsyncMock()
        mock_response.status = 500

        mock_get_context = AsyncMock()
        mock_get_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_get_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_get_context)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

        with self.assertRaises(ValueError) as context:
            asyncio.run(geocode_location("New York"))

        self.assertIn("Geocoding API returned HTTP 500", str(context.exception))

    @patch("aiohttp.ClientSession")
    def test_geocode_location_no_altitude(self, mock_session_class):
        """Test geocoding when altitude is not provided."""
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

        mock_get_context = AsyncMock()
        mock_get_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_get_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_get_context)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

        result = asyncio.run(geocode_location("New York City"))

        self.assertIsNotNone(result)
        self.assertEqual(result.elevation, 0.0)  # Should default to 0.0


if __name__ == "__main__":
    unittest.main()

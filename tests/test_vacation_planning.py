"""
Unit tests for vacation_planning.py

Tests vacation planning functionality including dark sky site finding
and viewing information retrieval.
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from celestron_nexstar.api.light_pollution import BortleClass
from celestron_nexstar.api.observer import ObserverLocation
from celestron_nexstar.api.vacation_planning import (
    DarkSkySite,
    VacationViewingInfo,
    _haversine_distance,
    find_dark_sites_near,
    get_vacation_viewing_info,
    populate_dark_sky_sites_database,
)


class TestHaversineDistance(unittest.TestCase):
    """Test suite for _haversine_distance function"""

    def test_same_point(self):
        """Test distance between same point is zero"""
        distance = _haversine_distance(40.0, -100.0, 40.0, -100.0)
        self.assertAlmostEqual(distance, 0.0, places=2)

    def test_known_distance(self):
        """Test distance calculation for known coordinates"""
        # Distance between New York and Los Angeles is approximately 3944 km
        # New York: 40.7128, -74.0060
        # Los Angeles: 34.0522, -118.2437
        distance = _haversine_distance(40.7128, -74.0060, 34.0522, -118.2437)
        self.assertAlmostEqual(distance, 3944, delta=50)  # Allow 50km tolerance

    def test_short_distance(self):
        """Test distance calculation for nearby points"""
        # Two points about 1 degree apart (roughly 111 km at equator)
        distance = _haversine_distance(0.0, 0.0, 1.0, 0.0)
        self.assertAlmostEqual(distance, 111, delta=5)

    def test_negative_coordinates(self):
        """Test distance calculation with negative coordinates"""
        distance = _haversine_distance(-40.0, -100.0, -35.0, -95.0)
        self.assertGreater(distance, 0)
        self.assertLess(distance, 1000)


class TestDarkSkySite(unittest.TestCase):
    """Test suite for DarkSkySite dataclass"""

    def test_creation(self):
        """Test creating a DarkSkySite"""
        site = DarkSkySite(
            name="Test Site",
            latitude=40.0,
            longitude=-100.0,
            bortle_class=BortleClass.CLASS_2,
            sqm_value=21.5,
            distance_km=50.0,
            description="A test site",
            notes="Some notes",
        )
        self.assertEqual(site.name, "Test Site")
        self.assertEqual(site.latitude, 40.0)
        self.assertEqual(site.longitude, -100.0)
        self.assertEqual(site.bortle_class, BortleClass.CLASS_2)
        self.assertEqual(site.sqm_value, 21.5)
        self.assertEqual(site.distance_km, 50.0)
        self.assertEqual(site.description, "A test site")
        self.assertEqual(site.notes, "Some notes")

    def test_creation_without_notes(self):
        """Test creating a DarkSkySite without notes"""
        site = DarkSkySite(
            name="Test Site",
            latitude=40.0,
            longitude=-100.0,
            bortle_class=BortleClass.CLASS_3,
            sqm_value=21.0,
            distance_km=25.0,
            description="A test site",
        )
        self.assertIsNone(site.notes)


class TestVacationViewingInfo(unittest.TestCase):
    """Test suite for VacationViewingInfo dataclass"""

    def test_creation(self):
        """Test creating a VacationViewingInfo"""
        location = ObserverLocation(latitude=40.0, longitude=-100.0, name="Test Location")
        info = VacationViewingInfo(
            location=location,
            bortle_class=BortleClass.CLASS_4,
            sqm_value=20.5,
            naked_eye_limiting_magnitude=5.5,
            milky_way_visible=True,
            description="Good viewing",
            recommendations=("Bring telescope", "Check weather"),
        )
        self.assertEqual(info.location, location)
        self.assertEqual(info.bortle_class, BortleClass.CLASS_4)
        self.assertEqual(info.sqm_value, 20.5)
        self.assertEqual(info.naked_eye_limiting_magnitude, 5.5)
        self.assertTrue(info.milky_way_visible)
        self.assertEqual(info.description, "Good viewing")
        self.assertEqual(len(info.recommendations), 2)


class TestFindDarkSitesNear(unittest.TestCase):
    """Test suite for find_dark_sites_near function"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_location = ObserverLocation(latitude=40.0, longitude=-100.0, name="Test Location")

    @patch("celestron_nexstar.api.vacation_planning.asyncio.run")
    @patch("celestron_nexstar.api.vacation_planning.geocode_location")
    def test_find_dark_sites_near_with_string_location(self, mock_geocode, mock_asyncio_run):
        """Test find_dark_sites_near with string location"""
        mock_asyncio_run.return_value = self.test_location
        mock_geocode.return_value = self.test_location

        with patch("celestron_nexstar.api.vacation_planning.asyncio.run") as mock_run:
            # Mock the async _get_sites function
            mock_db_sites = []
            mock_run.side_effect = [
                self.test_location,  # First call for geocode
                mock_db_sites,  # Second call for _get_sites
            ]

            with patch("celestron_nexstar.api.database_seeder.load_seed_json") as mock_load:
                mock_load.return_value = []
                result = find_dark_sites_near("Test Location")

        self.assertIsInstance(result, list)

    def test_find_dark_sites_near_with_observer_location(self):
        """Test find_dark_sites_near with ObserverLocation"""
        with patch("celestron_nexstar.api.vacation_planning.asyncio.run") as mock_run:
            # Mock the async _get_sites function to return empty list
            mock_run.return_value = []

            with patch("celestron_nexstar.api.database_seeder.load_seed_json") as mock_load:
                mock_load.return_value = []
                result = find_dark_sites_near(self.test_location)

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)

    @patch("celestron_nexstar.api.models.get_db_session")
    def test_find_dark_sites_near_with_database_sites(self, mock_get_session):
        """Test find_dark_sites_near with database sites"""
        # Mock database site
        mock_db_site = MagicMock()
        mock_db_site.name = "Test Site"
        mock_db_site.latitude = 40.1
        mock_db_site.longitude = -100.1
        mock_db_site.bortle_class = 2
        mock_db_site.sqm_value = 21.5
        mock_db_site.description = "A test site"
        mock_db_site.notes = None

        # Mock async session
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_db_site]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session_context = MagicMock()
        mock_session_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_context.__aexit__ = AsyncMock(return_value=None)
        mock_get_session.return_value = mock_session_context

        with patch("celestron_nexstar.api.vacation_planning.asyncio.run") as mock_run:
            # Mock the async _get_sites function to return the mock sites
            async def _get_sites():
                return [mock_db_site]

            mock_run.return_value = [mock_db_site]

            result = find_dark_sites_near(self.test_location, max_distance_km=200.0)

        # Should return sites from database
        self.assertIsInstance(result, list)

    def test_find_dark_sites_near_with_json_fallback(self):
        """Test find_dark_sites_near with JSON fallback"""
        with patch("celestron_nexstar.api.vacation_planning.asyncio.run") as mock_run:
            # Mock database query to fail/return empty
            mock_run.side_effect = Exception("Database error")

            with patch("celestron_nexstar.api.database_seeder.load_seed_json") as mock_load:
                # Use a geohash that will match the search area
                # For location 40.0, -100.0, a nearby geohash would be similar
                with patch("celestron_nexstar.api.geohash_utils.get_neighbors_for_search") as mock_neighbors:
                    # Mock neighbors to include the site's geohash prefix
                    mock_neighbors.return_value = ["9yf0", "9yf1", "9yf2"]
                    mock_load.return_value = [
                        {
                            "name": "Test Site",
                            "latitude": 40.1,
                            "longitude": -100.1,
                            "bortle_class": 2,
                            "sqm_value": 21.5,
                            "description": "A test site",
                            "geohash": "9yf01234567",  # Full geohash
                        }
                    ]
                    result = find_dark_sites_near(self.test_location, max_distance_km=200.0)

        self.assertIsInstance(result, list)

    def test_find_dark_sites_near_filters_by_bortle_class(self):
        """Test find_dark_sites_near filters by minimum Bortle class"""
        with patch("celestron_nexstar.api.vacation_planning.asyncio.run") as mock_run:
            mock_run.side_effect = Exception("Database error")

            with patch("celestron_nexstar.api.database_seeder.load_seed_json") as mock_load:
                with patch("celestron_nexstar.api.geohash_utils.get_neighbors_for_search") as mock_neighbors:
                    mock_neighbors.return_value = ["9yf0", "9yf1"]
                    mock_load.return_value = [
                        {
                            "name": "Bright Site",
                            "latitude": 40.1,
                            "longitude": -100.1,
                            "bortle_class": 5,  # Too bright
                            "sqm_value": 19.0,
                            "description": "Bright site",
                            "geohash": "9yf01234567",
                        },
                        {
                            "name": "Dark Site",
                            "latitude": 40.2,
                            "longitude": -100.2,
                            "bortle_class": 2,  # Dark enough
                            "sqm_value": 21.5,
                            "description": "Dark site",
                            "geohash": "9yf11234567",
                        },
                    ]
                    result = find_dark_sites_near(self.test_location, min_bortle=BortleClass.CLASS_4)

        # Should only include sites with bortle <= 4
        self.assertIsInstance(result, list)
        for site in result:
            self.assertLessEqual(site.bortle_class, BortleClass.CLASS_4)

    def test_find_dark_sites_near_filters_by_distance(self):
        """Test find_dark_sites_near filters by maximum distance"""
        with patch("celestron_nexstar.api.vacation_planning.asyncio.run") as mock_run:
            mock_run.side_effect = Exception("Database error")

            with patch("celestron_nexstar.api.database_seeder.load_seed_json") as mock_load:
                with patch("celestron_nexstar.api.geohash_utils.get_neighbors_for_search") as mock_neighbors:
                    # Return geohashes that will match both sites
                    mock_neighbors.return_value = ["9yf0", "c2b2"]
                    mock_load.return_value = [
                        {
                            "name": "Near Site",
                            "latitude": 40.1,  # Close
                            "longitude": -100.1,
                            "bortle_class": 2,
                            "sqm_value": 21.5,
                            "description": "Near site",
                            "geohash": "9yf01234567",
                        },
                        {
                            "name": "Far Site",
                            "latitude": 50.0,  # Far away
                            "longitude": -110.0,
                            "bortle_class": 2,
                            "sqm_value": 21.5,
                            "description": "Far site",
                            "geohash": "c2b21234567",
                        },
                    ]
                result = find_dark_sites_near(self.test_location, max_distance_km=50.0)

        # Should only include sites within 50 km
        self.assertIsInstance(result, list)
        for site in result:
            self.assertLessEqual(site.distance_km, 50.0)

    def test_find_dark_sites_near_sorts_by_distance(self):
        """Test find_dark_sites_near sorts results by distance"""
        with patch("celestron_nexstar.api.vacation_planning.asyncio.run") as mock_run:
            mock_run.side_effect = Exception("Database error")

            with patch("celestron_nexstar.api.database_seeder.load_seed_json") as mock_load:
                with patch("celestron_nexstar.api.geohash_utils.get_neighbors_for_search") as mock_neighbors:
                    # Return geohashes that will match the site prefixes
                    # The code checks if item_prefix.startswith(search_prefix), so search_prefix should be shorter or equal
                    mock_neighbors.return_value = ["9yf012345", "9yf212345"]  # 9-char prefixes
                    mock_load.return_value = [
                        {
                            "name": "Far Site",
                            "latitude": 40.5,
                            "longitude": -100.5,
                            "bortle_class": 2,
                            "sqm_value": 21.5,
                            "description": "Far site",
                            "geohash": "9yf21234567",  # Starts with 9yf212345
                        },
                        {
                            "name": "Near Site",
                            "latitude": 40.1,
                            "longitude": -100.1,
                            "bortle_class": 2,
                            "sqm_value": 21.5,
                            "description": "Near site",
                            "geohash": "9yf01234567",  # Starts with 9yf012345
                        },
                    ]
                    result = find_dark_sites_near(self.test_location, max_distance_km=200.0)

        # Should be sorted by distance (nearest first)
        self.assertGreater(len(result), 1)
        for i in range(len(result) - 1):
            self.assertLessEqual(result[i].distance_km, result[i + 1].distance_km)


class TestGetVacationViewingInfo(unittest.TestCase):
    """Test suite for get_vacation_viewing_info function"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_location = ObserverLocation(latitude=40.0, longitude=-100.0, name="Test Location")

    @patch("celestron_nexstar.api.vacation_planning.asyncio.run")
    @patch("celestron_nexstar.api.vacation_planning.geocode_location")
    def test_get_vacation_viewing_info_with_string_location(self, mock_geocode, mock_asyncio_run):
        """Test get_vacation_viewing_info with string location"""
        mock_asyncio_run.return_value = self.test_location
        mock_geocode.return_value = self.test_location

        from celestron_nexstar.api.light_pollution import LightPollutionData

        mock_light_data = LightPollutionData(
            bortle_class=BortleClass.CLASS_4,
            sqm_value=20.5,
            naked_eye_limiting_magnitude=5.5,
            milky_way_visible=True,
            airglow_visible=False,
            zodiacal_light_visible=False,
            description="Good viewing",
            recommendations=("Bring telescope",),
        )

        with patch("celestron_nexstar.api.vacation_planning.asyncio.run") as mock_run:
            mock_run.side_effect = [
                self.test_location,  # First call for geocode
                mock_light_data,  # Second call for get_light_pollution_data
            ]

            result = get_vacation_viewing_info("Test Location")

        self.assertIsInstance(result, VacationViewingInfo)
        self.assertEqual(result.location, self.test_location)

    @patch("celestron_nexstar.api.vacation_planning.asyncio.run")
    @patch("celestron_nexstar.api.vacation_planning.get_light_pollution_data")
    def test_get_vacation_viewing_info_with_observer_location(self, mock_get_light, mock_asyncio_run):
        """Test get_vacation_viewing_info with ObserverLocation"""
        from celestron_nexstar.api.light_pollution import LightPollutionData

        mock_light_data = LightPollutionData(
            bortle_class=BortleClass.CLASS_3,
            sqm_value=21.0,
            naked_eye_limiting_magnitude=6.0,
            milky_way_visible=True,
            airglow_visible=False,
            zodiacal_light_visible=False,
            description="Excellent viewing",
            recommendations=("Bring telescope", "Check weather"),
        )

        mock_asyncio_run.return_value = mock_light_data
        mock_get_light.return_value = mock_light_data

        result = get_vacation_viewing_info(self.test_location)

        self.assertIsInstance(result, VacationViewingInfo)
        self.assertEqual(result.location, self.test_location)
        self.assertEqual(result.bortle_class, BortleClass.CLASS_3)
        self.assertEqual(result.sqm_value, 21.0)
        self.assertTrue(result.milky_way_visible)


class TestPopulateDarkSkySitesDatabase(unittest.TestCase):
    """Test suite for populate_dark_sky_sites_database function"""

    @patch("celestron_nexstar.api.vacation_planning.asyncio.run")
    @patch("celestron_nexstar.api.database_seeder.seed_dark_sky_sites")
    def test_populate_dark_sky_sites_database(self, mock_seed, mock_asyncio_run):
        """Test populate_dark_sky_sites_database"""
        mock_session = MagicMock()
        mock_asyncio_run.return_value = None

        populate_dark_sky_sites_database(mock_session)

        # Should call asyncio.run with the seed function
        mock_asyncio_run.assert_called_once()


if __name__ == "__main__":
    unittest.main()

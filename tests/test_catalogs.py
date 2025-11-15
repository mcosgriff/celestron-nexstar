"""
Unit tests for Celestial Object Catalog functions.

Tests catalog loading, searching, and object retrieval with comprehensive coverage.
"""

import asyncio
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


# Import directly from catalogs module to avoid import chain issues
# Add src to path if needed
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Import catalogs module directly (not through api.__init__)
from celestron_nexstar.api.catalogs.catalogs import (  # noqa: E402
    CelestialObject,
    get_all_catalogs_dict,
    get_all_objects,
    get_available_catalogs,
    get_catalog,
    get_object_by_name,
)
from celestron_nexstar.api.core.enums import CelestialObjectType  # noqa: E402
from celestron_nexstar.api.core.exceptions import CatalogNotFoundError  # noqa: E402
from celestron_nexstar.api.database.database import CatalogDatabase  # noqa: E402


# Import search_objects conditionally - it may trigger astropy import
try:
    from celestron_nexstar.api.catalogs.catalogs import search_objects
except Exception:
    # If import fails due to astropy/deal conflict, skip search_objects tests
    search_objects = None


class TestCelestialObject(unittest.TestCase):
    """Test suite for CelestialObject class"""

    def setUp(self):
        """Set up test fixtures"""
        self.star = CelestialObject(
            name="HR 5459",
            common_name="Vega",
            ra_hours=18.6156,
            dec_degrees=38.7836,
            magnitude=0.03,
            object_type=CelestialObjectType.STAR,
            catalog="bright_stars",
            description="Bright star in Lyra",
            constellation="Lyra",
        )

        self.planet = CelestialObject(
            name="jupiter",
            common_name="Jupiter",
            ra_hours=10.0,
            dec_degrees=20.0,
            magnitude=-2.0,
            object_type=CelestialObjectType.PLANET,
            catalog="planets",
            description="Gas giant planet",
        )

    def test_matches_search_by_name(self):
        """Test matches_search finds objects by name"""
        self.assertTrue(self.star.matches_search("Vega"))
        self.assertTrue(self.star.matches_search("vega"))  # Case insensitive
        self.assertTrue(self.star.matches_search("HR 5459"))
        self.assertFalse(self.star.matches_search("Mars"))

    def test_matches_search_by_common_name(self):
        """Test matches_search finds objects by common_name"""
        # matches_search checks name, common_name, and description
        self.assertTrue(self.star.matches_search("Vega"))  # Matches common_name
        self.assertTrue(self.star.matches_search("HR 5459"))  # Matches name
        # Create an object where only common_name matches (not name)
        obj_common_only = CelestialObject(
            name="HR 1234",
            common_name="Test Star",
            ra_hours=10.0,
            dec_degrees=20.0,
            magnitude=5.0,
            object_type=CelestialObjectType.STAR,
            catalog="test",
        )
        self.assertTrue(obj_common_only.matches_search("Test Star"))  # Matches by common_name
        self.assertTrue(obj_common_only.matches_search("Test"))  # Partial match in common_name
        # "HR 1234" should match because it's in the name field
        self.assertTrue(obj_common_only.matches_search("HR 1234"))  # Matches name
        self.assertFalse(obj_common_only.matches_search("Nonexistent"))  # No match

    def test_matches_search_by_description(self):
        """Test matches_search finds objects by description"""
        self.assertTrue(self.star.matches_search("Lyra"))
        self.assertTrue(self.star.matches_search("Bright"))
        self.assertFalse(self.star.matches_search("Galaxy"))

    def test_matches_search_partial_match(self):
        """Test matches_search with partial matches"""
        self.assertTrue(self.star.matches_search("Veg"))
        self.assertTrue(self.star.matches_search("ega"))

    def test_with_current_position_fixed_object(self):
        """Test with_current_position returns self for fixed objects"""
        result = self.star.with_current_position()
        self.assertIs(result, self.star)  # Should return same object
        self.assertEqual(result.ra_hours, 18.6156)
        self.assertEqual(result.dec_degrees, 38.7836)

    def test_with_current_position_dynamic_object(self):
        """Test with_current_position updates position for dynamic objects"""
        with patch("celestron_nexstar.api.catalogs.catalogs.get_planetary_position", return_value=(12.0, 30.0)):
            result = self.planet.with_current_position()
            self.assertIsNot(result, self.planet)  # Should return new object
            self.assertEqual(result.ra_hours, 12.0)
            self.assertEqual(result.dec_degrees, 30.0)

    def test_with_current_position_dynamic_object_failure(self):
        """Test with_current_position handles ephemeris calculation failure"""
        with patch("celestron_nexstar.api.catalogs.catalogs.get_planetary_position", side_effect=ValueError("Not found")):
            result = self.planet.with_current_position()
            # Should return original object on failure
            self.assertEqual(result.ra_hours, 10.0)
            self.assertEqual(result.dec_degrees, 20.0)

    def test_with_current_position_with_datetime(self):
        """Test with_current_position accepts datetime parameter"""
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        with patch("celestron_nexstar.api.catalogs.catalogs.get_planetary_position", return_value=(15.0, 40.0)) as mock_get:
            self.planet.with_current_position(dt=dt)
            mock_get.assert_called_once()
            # Check that dt was passed (via call args)
            call_args = mock_get.call_args
            self.assertEqual(call_args[1]["dt"], dt)


class TestGetObjectByName(unittest.TestCase):
    """Test suite for get_object_by_name function"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_db = MagicMock(spec=CatalogDatabase)
        # Mock async methods
        self.mock_db.get_by_name = AsyncMock()
        self.mock_db.search = AsyncMock()
        # Mock the async context manager for _AsyncSession
        self.mock_session_context = MagicMock()
        self.mock_session_context.__aenter__ = AsyncMock(return_value=self.mock_db)
        self.mock_session_context.__aexit__ = AsyncMock(return_value=None)
        self.mock_db._AsyncSession = MagicMock(return_value=self.mock_session_context)
        self.mock_obj = CelestialObject(
            name="Rigil Kentaurus",
            common_name="Alpha Centauri",
            ra_hours=14.6597,
            dec_degrees=-60.8358,
            magnitude=-0.27,
            object_type=CelestialObjectType.STAR,
            catalog="bright_stars",
        )

    @patch("celestron_nexstar.api.database.database.get_database")
    def test_get_object_by_name_exact_match(self, mock_get_db):
        """Test get_object_by_name with exact match"""
        mock_get_db.return_value = self.mock_db
        self.mock_db.get_by_name.return_value = self.mock_obj

        result = asyncio.run(get_object_by_name("Rigil Kentaurus"))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "Rigil Kentaurus")
        self.mock_db.get_by_name.assert_called_once_with("Rigil Kentaurus")

    @patch("celestron_nexstar.api.database.database.get_database")
    def test_get_object_by_name_without_catalog_name(self, mock_get_db):
        """Test get_object_by_name without optional catalog_name parameter"""
        mock_get_db.return_value = self.mock_db
        self.mock_db.get_by_name.return_value = self.mock_obj

        # This should not raise an error about missing catalog_name
        result = asyncio.run(get_object_by_name("Rigil Kentaurus"))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "Rigil Kentaurus")

    @patch("celestron_nexstar.api.database.database.get_database")
    def test_get_object_by_name_with_catalog_name(self, mock_get_db):
        """Test get_object_by_name with catalog_name parameter"""
        mock_get_db.return_value = self.mock_db
        self.mock_db.get_by_name.return_value = self.mock_obj

        result = asyncio.run(get_object_by_name("Rigil Kentaurus", catalog_name="bright_stars"))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "Rigil Kentaurus")

    @patch("celestron_nexstar.api.database.database.get_database")
    def test_get_object_by_name_no_exact_match_uses_search(self, mock_get_db):
        """Test get_object_by_name falls back to FTS search when no exact match"""
        mock_get_db.return_value = self.mock_db
        self.mock_db.get_by_name.return_value = None
        self.mock_db.search.return_value = [self.mock_obj]

        result = asyncio.run(get_object_by_name("Rigil"))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "Rigil Kentaurus")
        self.mock_db.get_by_name.assert_called_once_with("Rigil")
        self.mock_db.search.assert_called_once_with("Rigil", limit=20)

    @patch("celestron_nexstar.api.database.database.get_database")
    def test_get_object_by_name_empty_string(self, mock_get_db):
        """Test get_object_by_name with empty string"""
        # Empty string is caught by deal contract, so expect PreContractError
        with self.assertRaises(Exception):  # noqa: B017  # deal.PreContractError
            asyncio.run(get_object_by_name(""))

        mock_get_db.assert_not_called()

    @patch("celestron_nexstar.api.database.database.get_database")
    def test_get_object_by_name_database_exception(self, mock_get_db):
        """Test get_object_by_name handles database exceptions gracefully"""
        mock_get_db.return_value = self.mock_db
        self.mock_db.get_by_name.side_effect = Exception("Database error")

        result = asyncio.run(get_object_by_name("Test"))

        # Should return empty list on exception
        self.assertEqual(result, [])

    @patch("celestron_nexstar.api.database.database.get_database")
    def test_get_object_by_name_filters_duplicates(self, mock_get_db):
        """Test get_object_by_name filters duplicate names from search results"""
        mock_get_db.return_value = self.mock_db
        self.mock_db.get_by_name.return_value = None
        # Create multiple objects with same name (shouldn't happen, but test it)
        obj1 = CelestialObject(
            name="Test Star",
            common_name=None,
            ra_hours=10.0,
            dec_degrees=20.0,
            magnitude=5.0,
            object_type=CelestialObjectType.STAR,
            catalog="test",
        )
        obj2 = CelestialObject(
            name="Test Star",
            common_name=None,
            ra_hours=11.0,
            dec_degrees=21.0,
            magnitude=5.1,
            object_type=CelestialObjectType.STAR,
            catalog="test",
        )
        self.mock_db.search.return_value = [obj1, obj2]

        result = asyncio.run(get_object_by_name("Test"))

        # Should only return one (first match)
        self.assertEqual(len(result), 1)

    @patch("celestron_nexstar.api.database.database.get_database")
    def test_get_object_by_name_filters_by_name_contains(self, mock_get_db):
        """Test get_object_by_name only includes objects where name contains query"""
        mock_get_db.return_value = self.mock_db
        self.mock_db.get_by_name.return_value = None
        # Object where common_name matches but name doesn't
        obj = CelestialObject(
            name="HR 1234",
            common_name="Test Star",
            ra_hours=10.0,
            dec_degrees=20.0,
            magnitude=5.0,
            object_type=CelestialObjectType.STAR,
            catalog="test",
        )
        self.mock_db.search.return_value = [obj]

        result = asyncio.run(get_object_by_name("Test"))

        # Should be empty because name doesn't contain "Test"
        self.assertEqual(result, [])


class TestSearchObjects(unittest.TestCase):
    """Test suite for search_objects function"""

    @unittest.skipIf(search_objects is None, "search_objects import failed (astropy/deal conflict)")
    def setUp(self):
        """Set up test fixtures"""
        self.mock_db = MagicMock(spec=CatalogDatabase)
        self.mock_db._model_to_object = MagicMock()
        # Mock async session context manager
        self.mock_session = AsyncMock()
        self.mock_session.execute = AsyncMock()
        self.mock_session_context = MagicMock()
        self.mock_session_context.__aenter__ = AsyncMock(return_value=self.mock_session)
        self.mock_session_context.__aexit__ = AsyncMock(return_value=None)
        self.mock_db._AsyncSession = MagicMock(return_value=self.mock_session_context)

        self.mock_obj = CelestialObject(
            name="M31",
            common_name="Andromeda Galaxy",
            ra_hours=0.7117,
            dec_degrees=41.2692,
            magnitude=3.4,
            object_type=CelestialObjectType.GALAXY,
            catalog="messier",
            description="Spiral galaxy",
        )

    @patch("celestron_nexstar.api.database.database.get_database")
    def test_search_objects_exact_match_name(self, mock_get_db):
        """Test search_objects finds exact match by name"""
        mock_get_db.return_value = self.mock_db
        from celestron_nexstar.api.database.models import CelestialObjectModel

        mock_model = MagicMock(spec=CelestialObjectModel)
        mock_model.name = "M31"
        mock_model.common_name = "Andromeda Galaxy"
        mock_model.ra_hours = 0.7117
        mock_model.dec_degrees = 41.2692
        mock_model.magnitude = 3.4
        mock_model.object_type = "galaxy"
        mock_model.catalog = "messier"
        mock_model.description = "Spiral galaxy"
        mock_model.is_dynamic = False
        mock_model.ephemeris_name = None
        mock_model.parent_planet = None
        mock_model.constellation = None

        self.mock_db._model_to_object.return_value = self.mock_obj
        # Mock the async execute result - search_objects uses result.scalars().all()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_model]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        self.mock_session.execute = AsyncMock(return_value=mock_result)

        result = asyncio.run(search_objects("M31"))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0].name, "M31")
        self.assertEqual(result[0][1], "exact")

    @patch("celestron_nexstar.api.database.database.get_database")
    def test_search_objects_without_catalog_name(self, mock_get_db):
        """Test search_objects without optional catalog_name parameter"""
        mock_get_db.return_value = self.mock_db
        from celestron_nexstar.api.database.models import CelestialObjectModel

        mock_model = MagicMock(spec=CelestialObjectModel)
        self.mock_db._model_to_object.return_value = self.mock_obj
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_model]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        self.mock_session.execute = AsyncMock(return_value=mock_result)

        # This should not raise an error about missing catalog_name
        result = asyncio.run(search_objects("M31"))

        self.assertIsInstance(result, list)

    @patch("celestron_nexstar.api.database.database.get_database")
    def test_search_objects_with_catalog_name(self, mock_get_db):
        """Test search_objects with catalog_name parameter"""
        mock_get_db.return_value = self.mock_db
        from celestron_nexstar.api.database.models import CelestialObjectModel

        mock_model = MagicMock(spec=CelestialObjectModel)
        self.mock_db._model_to_object.return_value = self.mock_obj
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_model]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        self.mock_session.execute = AsyncMock(return_value=mock_result)

        result = asyncio.run(search_objects("M31", catalog_name="messier"))

        self.assertIsInstance(result, list)

    @patch("celestron_nexstar.api.database.database.get_database")
    def test_search_objects_substring_match_name(self, mock_get_db):
        """Test search_objects finds substring matches in name"""
        mock_get_db.return_value = self.mock_db
        from celestron_nexstar.api.database.models import CelestialObjectModel

        mock_model = MagicMock(spec=CelestialObjectModel)
        mock_model.name = "M31"
        mock_model.common_name = None
        self.mock_db._model_to_object.return_value = self.mock_obj
        # First call returns empty (no exact match), second call returns substring match in name
        # The function makes: exact query, name query, common_name query, FTS query
        mock_scalars_empty = MagicMock()
        mock_scalars_empty.all.return_value = []
        mock_scalars_match = MagicMock()
        mock_scalars_match.all.return_value = [mock_model]
        mock_result_empty = MagicMock()
        mock_result_empty.scalars.return_value = mock_scalars_empty
        mock_result_match = MagicMock()
        mock_result_match.scalars.return_value = mock_scalars_match
        # search_objects does: exact query (empty), name query (match), common_name query (empty), FTS (empty)
        self.mock_session.execute = AsyncMock(
            side_effect=[mock_result_empty, mock_result_match, mock_result_empty, mock_result_empty]
        )

        result = asyncio.run(search_objects("M3"))

        self.assertGreater(len(result), 0)
        # Should find M31 when searching for "M3"

    @patch("celestron_nexstar.api.database.database.get_database")
    def test_search_objects_with_update_positions_false(self, mock_get_db):
        """Test search_objects with update_positions=False"""
        mock_get_db.return_value = self.mock_db
        from celestron_nexstar.api.database.models import CelestialObjectModel

        mock_model = MagicMock(spec=CelestialObjectModel)
        self.mock_db._model_to_object.return_value = self.mock_obj
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_model]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        self.mock_session.execute = AsyncMock(return_value=mock_result)

        result = asyncio.run(search_objects("M31", update_positions=False))

        # Should not call with_current_position
        self.assertIsInstance(result, list)

    @patch("celestron_nexstar.api.database.database.get_database")
    def test_search_objects_empty_query(self, mock_get_db):
        """Test search_objects with empty query"""
        # Empty query should be caught by deal.pre, but test the function handles it
        mock_get_db.return_value = self.mock_db

        # This should be caught by deal contract, so expect PreContractError
        with self.assertRaises(Exception):  # noqa: B017  # deal.PreContractError
            asyncio.run(search_objects(""))

    @patch("celestron_nexstar.api.database.database.get_database")
    def test_search_objects_database_exception(self, mock_get_db):
        """Test search_objects handles database exceptions gracefully"""
        mock_get_db.return_value = self.mock_db
        self.mock_db._AsyncSession.side_effect = Exception("Database error")

        result = asyncio.run(search_objects("M31"))

        # Should return empty list on exception
        self.assertEqual(result, [])

    @patch("celestron_nexstar.api.database.database.get_database")
    def test_search_objects_fts_search(self, mock_get_db):
        """Test search_objects uses FTS5 for description search"""
        mock_get_db.return_value = self.mock_db
        from celestron_nexstar.api.database.models import CelestialObjectModel

        mock_model = MagicMock(spec=CelestialObjectModel)
        mock_model.id = 1
        mock_model.name = "M31"
        self.mock_db._model_to_object.return_value = self.mock_obj
        self.mock_db.ensure_fts_table.return_value = None

        # No exact or name match
        self.mock_session.execute.return_value.scalar_one_or_none.return_value = None
        self.mock_session.execute.return_value.scalars.return_value.all.return_value = []

        # FTS search returns a result - need to mock multiple execute calls
        # First: exact match (empty), second: name match (empty), third: FTS
        mock_scalars_empty = MagicMock()
        mock_scalars_empty.all.return_value = []
        mock_result_empty = MagicMock()
        mock_result_empty.scalars.return_value = mock_scalars_empty
        # FTS returns rows with id
        mock_result_fts = MagicMock()
        mock_result_fts.fetchall.return_value = [(1,)]
        self.mock_session.execute = AsyncMock(side_effect=[mock_result_empty, mock_result_empty, mock_result_fts])
        self.mock_session.get = AsyncMock(return_value=mock_model)

        result = asyncio.run(search_objects("spiral"))

        # Should find objects matching in description
        self.assertIsInstance(result, list)


class TestCatalogLoading(unittest.TestCase):
    """Test suite for catalog loading functions"""

    def setUp(self):
        """Clear cache before each test"""
        from celestron_nexstar.api.catalogs.catalogs import _catalog_cache

        _catalog_cache.clear()

    @patch("pathlib.Path.open", create=True)
    @patch("celestron_nexstar.api.catalogs.catalogs._get_catalogs_path")
    @patch("celestron_nexstar.api.catalogs.catalogs.yaml.safe_load")
    def test_get_catalog_success(self, mock_yaml_load, mock_get_path, mock_open):
        """Test get_catalog loads catalog from YAML"""
        mock_get_path.return_value = Path("/test/catalogs.yaml")
        mock_open.return_value.__enter__.return_value = MagicMock()
        mock_yaml_load.return_value = {
            "bright_stars": [
                {
                    "name": "HR 5459",
                    "common_name": "Vega",
                    "ra_hours": 18.6156,
                    "dec_degrees": 38.7836,
                    "magnitude": 0.03,
                    "type": "star",
                    "description": "Bright star",
                }
            ]
        }

        result = get_catalog("bright_stars")

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "HR 5459")
        self.assertEqual(result[0].common_name, "Vega")

    @patch("pathlib.Path.open", create=True)
    @patch("celestron_nexstar.api.catalogs.catalogs._get_catalogs_path")
    @patch("celestron_nexstar.api.catalogs.catalogs.yaml.safe_load")
    def test_get_catalog_not_found(self, mock_yaml_load, mock_get_path, mock_open):
        """Test get_catalog raises ValueError for unknown catalog"""
        mock_get_path.return_value = Path("/test/catalogs.yaml")
        mock_open.return_value.__enter__.return_value = MagicMock()
        mock_yaml_load.return_value = {"other_catalog": []}

        with self.assertRaises(CatalogNotFoundError):
            get_catalog("nonexistent")

    @patch("pathlib.Path.open", create=True)
    @patch("celestron_nexstar.api.catalogs.catalogs._get_catalogs_path")
    @patch("celestron_nexstar.api.catalogs.catalogs.yaml.safe_load")
    def test_get_all_catalogs_dict(self, mock_yaml_load, mock_get_path, mock_open):
        """Test get_all_catalogs_dict loads all catalogs"""
        mock_get_path.return_value = Path("/test/catalogs.yaml")
        mock_open.return_value.__enter__.return_value = MagicMock()
        mock_yaml_load.return_value = {
            "bright_stars": [
                {
                    "name": "HR 5459",
                    "ra_hours": 18.6156,
                    "dec_degrees": 38.7836,
                    "magnitude": 0.03,
                    "type": "star",
                }
            ],
            "messier": [
                {
                    "name": "M31",
                    "ra_hours": 0.7117,
                    "dec_degrees": 41.2692,
                    "magnitude": 3.4,
                    "type": "galaxy",
                }
            ],
        }

        result = get_all_catalogs_dict()

        self.assertIsInstance(result, dict)
        self.assertIn("bright_stars", result)
        self.assertIn("messier", result)
        self.assertEqual(len(result["bright_stars"]), 1)
        self.assertEqual(len(result["messier"]), 1)

    @patch("pathlib.Path.open", create=True)
    @patch("celestron_nexstar.api.catalogs.catalogs._get_catalogs_path")
    @patch("celestron_nexstar.api.catalogs.catalogs.yaml.safe_load")
    def test_get_all_objects(self, mock_yaml_load, mock_get_path, mock_open):
        """Test get_all_objects returns all objects from all catalogs"""
        mock_get_path.return_value = Path("/test/catalogs.yaml")
        mock_open.return_value.__enter__.return_value = MagicMock()
        mock_yaml_load.return_value = {
            "bright_stars": [
                {
                    "name": "HR 5459",
                    "ra_hours": 18.6156,
                    "dec_degrees": 38.7836,
                    "magnitude": 0.03,
                    "type": "star",
                }
            ],
            "messier": [
                {
                    "name": "M31",
                    "ra_hours": 0.7117,
                    "dec_degrees": 41.2692,
                    "magnitude": 3.4,
                    "type": "galaxy",
                }
            ],
        }

        result = get_all_objects()

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)  # One from each catalog

    @patch("pathlib.Path.open", create=True)
    @patch("celestron_nexstar.api.catalogs.catalogs._get_catalogs_path")
    @patch("celestron_nexstar.api.catalogs.catalogs.yaml.safe_load")
    def test_get_available_catalogs(self, mock_yaml_load, mock_get_path, mock_open):
        """Test get_available_catalogs returns list of catalog names"""
        mock_get_path.return_value = Path("/test/catalogs.yaml")
        mock_open.return_value.__enter__.return_value = MagicMock()
        mock_yaml_load.return_value = {
            "bright_stars": [],
            "messier": [],
            "planets": [],
        }

        result = get_available_catalogs()

        self.assertIsInstance(result, list)
        self.assertIn("bright_stars", result)
        self.assertIn("messier", result)
        self.assertIn("planets", result)
        self.assertEqual(len(result), 3)

    @patch("pathlib.Path.open", create=True)
    @patch("celestron_nexstar.api.catalogs.catalogs._get_catalogs_path")
    @patch("celestron_nexstar.api.catalogs.catalogs.yaml.safe_load")
    def test_get_catalog_with_optional_fields(self, mock_yaml_load, mock_get_path, mock_open):
        """Test get_catalog handles optional fields (common_name, description, etc.)"""
        mock_get_path.return_value = Path("/test/catalogs.yaml")
        mock_open.return_value.__enter__.return_value = MagicMock()
        mock_yaml_load.return_value = {
            "test_catalog": [
                {
                    "name": "Test Object",
                    "ra_hours": 10.0,
                    "dec_degrees": 20.0,
                    "magnitude": 5.0,
                    "type": "star",
                    # Optional fields missing
                }
            ]
        }

        result = get_catalog("test_catalog")

        self.assertEqual(len(result), 1)
        self.assertIsNone(result[0].common_name)
        self.assertIsNone(result[0].description)

    @patch("pathlib.Path.open", create=True)
    @patch("celestron_nexstar.api.catalogs.catalogs._get_catalogs_path")
    @patch("celestron_nexstar.api.catalogs.catalogs.yaml.safe_load")
    def test_get_catalog_with_all_fields(self, mock_yaml_load, mock_get_path, mock_open):
        """Test get_catalog handles all optional fields"""
        mock_get_path.return_value = Path("/test/catalogs.yaml")
        mock_open.return_value.__enter__.return_value = MagicMock()
        mock_yaml_load.return_value = {
            "test_catalog": [
                {
                    "name": "Test Object",
                    "common_name": "Test",
                    "ra_hours": 10.0,
                    "dec_degrees": 20.0,
                    "magnitude": 5.0,
                    "type": "star",
                    "description": "A test object",
                    "parent_planet": None,
                    "constellation": "Test",
                }
            ]
        }

        result = get_catalog("test_catalog")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].common_name, "Test")
        self.assertEqual(result[0].description, "A test object")
        self.assertEqual(result[0].constellation, "Test")


if __name__ == "__main__":
    unittest.main()

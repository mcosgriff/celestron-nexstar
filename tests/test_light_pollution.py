"""
Unit tests for light_pollution.py

Tests light pollution data fetching, Bortle scale conversion, and caching.
"""

import asyncio
import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from celestron_nexstar.api.core.exceptions import DatabaseError
from celestron_nexstar.api.location.light_pollution import (
    BortleClass,
    LightPollutionData,
    _create_light_pollution_data,
    _ensure_cache_dir,
    _fetch_sqm,
    _get_bortle_characteristics,
    _get_cache_key,
    _is_cache_stale,
    _is_cache_too_old,
    _load_cache,
    _save_cache,
    get_light_pollution_data,
    get_light_pollution_data_batch,
    sqm_to_bortle,
)


class TestBortleClass(unittest.TestCase):
    """Test suite for BortleClass enum"""

    def test_bortle_class_values(self):
        """Test BortleClass enum values"""
        self.assertEqual(BortleClass.CLASS_1, 1)
        self.assertEqual(BortleClass.CLASS_2, 2)
        self.assertEqual(BortleClass.CLASS_3, 3)
        self.assertEqual(BortleClass.CLASS_9, 9)


class TestLightPollutionData(unittest.TestCase):
    """Test suite for LightPollutionData dataclass"""

    def test_creation(self):
        """Test creating LightPollutionData"""
        data = LightPollutionData(
            bortle_class=BortleClass.CLASS_3,
            sqm_value=21.5,
            naked_eye_limiting_magnitude=6.5,
            milky_way_visible=True,
            airglow_visible=True,
            zodiacal_light_visible=True,
            description="Good",
            recommendations=("Good for observing",),
            source="database",
            cached=False,
        )
        self.assertEqual(data.bortle_class, BortleClass.CLASS_3)
        self.assertEqual(data.sqm_value, 21.5)
        self.assertTrue(data.milky_way_visible)
        self.assertFalse(data.cached)


class TestSqmToBortle(unittest.TestCase):
    """Test suite for sqm_to_bortle function"""

    def test_class_1(self):
        """Test Class 1 (excellent dark sky)"""
        self.assertEqual(sqm_to_bortle(22.0), BortleClass.CLASS_1)
        self.assertEqual(sqm_to_bortle(21.99), BortleClass.CLASS_1)

    def test_class_2(self):
        """Test Class 2 (typical dark site)"""
        self.assertEqual(sqm_to_bortle(21.95), BortleClass.CLASS_2)
        self.assertEqual(sqm_to_bortle(21.89), BortleClass.CLASS_2)

    def test_class_3(self):
        """Test Class 3 (rural sky)"""
        self.assertEqual(sqm_to_bortle(21.80), BortleClass.CLASS_3)
        self.assertEqual(sqm_to_bortle(21.69), BortleClass.CLASS_3)

    def test_class_4(self):
        """Test Class 4 (rural/suburban)"""
        self.assertEqual(sqm_to_bortle(21.0), BortleClass.CLASS_4)
        self.assertEqual(sqm_to_bortle(20.49), BortleClass.CLASS_4)

    def test_class_5(self):
        """Test Class 5 (suburban)"""
        self.assertEqual(sqm_to_bortle(20.0), BortleClass.CLASS_5)
        self.assertEqual(sqm_to_bortle(19.50), BortleClass.CLASS_5)

    def test_class_6(self):
        """Test Class 6 (bright suburban)"""
        self.assertEqual(sqm_to_bortle(19.0), BortleClass.CLASS_6)
        self.assertEqual(sqm_to_bortle(18.94), BortleClass.CLASS_6)

    def test_class_7(self):
        """Test Class 7 (suburban/urban)"""
        self.assertEqual(sqm_to_bortle(18.5), BortleClass.CLASS_7)
        self.assertEqual(sqm_to_bortle(18.38), BortleClass.CLASS_7)

    def test_class_8(self):
        """Test Class 8 (city)"""
        self.assertEqual(sqm_to_bortle(18.0), BortleClass.CLASS_8)
        self.assertEqual(sqm_to_bortle(17.5), BortleClass.CLASS_8)

    def test_class_9(self):
        """Test Class 9 (inner-city)"""
        self.assertEqual(sqm_to_bortle(17.0), BortleClass.CLASS_9)
        self.assertEqual(sqm_to_bortle(15.0), BortleClass.CLASS_9)


class TestGetBortleCharacteristics(unittest.TestCase):
    """Test suite for _get_bortle_characteristics function"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_session = AsyncMock()

    def test_get_bortle_characteristics_success(self):
        """Test successful retrieval of Bortle characteristics"""
        mock_model = MagicMock()
        mock_model.sqm_min = 21.69
        mock_model.sqm_max = 21.89
        mock_model.naked_eye_mag = 6.5
        mock_model.milky_way = True
        mock_model.airglow = True
        mock_model.zodiacal_light = True
        mock_model.description = "Rural sky"
        mock_model.recommendations = '["Good for observing"]'

        self.mock_session.scalar = AsyncMock(return_value=mock_model)

        result = asyncio.run(_get_bortle_characteristics(self.mock_session, BortleClass.CLASS_3))

        self.assertIsInstance(result, dict)
        self.assertEqual(result["sqm_range"], (21.69, 21.89))
        self.assertEqual(result["naked_eye_mag"], 6.5)
        self.assertTrue(result["milky_way"])

    def test_get_bortle_characteristics_not_found(self):
        """Test error when Bortle characteristics not found"""
        self.mock_session.scalar = AsyncMock(return_value=None)

        with self.assertRaises(DatabaseError) as context:
            asyncio.run(_get_bortle_characteristics(self.mock_session, BortleClass.CLASS_3))

        self.assertIn("Bortle class", str(context.exception))


class TestCreateLightPollutionData(unittest.TestCase):
    """Test suite for _create_light_pollution_data function"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_session = AsyncMock()

    @patch("celestron_nexstar.api.location.light_pollution._get_bortle_characteristics")
    def test_create_light_pollution_data(self, mock_get_chars):
        """Test creating LightPollutionData from SQM"""
        # SQM 21.5 maps to CLASS_4 (20.49-21.69 range)
        mock_get_chars.return_value = {
            "sqm_range": (20.49, 21.69),
            "naked_eye_mag": 6.0,
            "milky_way": True,
            "airglow": True,
            "zodiacal_light": True,
            "description": "Rural/suburban sky",
            "recommendations": ["Good for observing"],
        }

        result = asyncio.run(_create_light_pollution_data(self.mock_session, 21.5, source="database", cached=False))

        self.assertIsInstance(result, LightPollutionData)
        self.assertEqual(result.bortle_class, BortleClass.CLASS_4)
        self.assertEqual(result.sqm_value, 21.5)
        self.assertEqual(result.source, "database")
        self.assertFalse(result.cached)


class TestCacheFunctions(unittest.TestCase):
    """Test suite for cache-related functions"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cache_dir = None

    def tearDown(self):
        """Clean up test fixtures"""
        import shutil

        if self.original_cache_dir is not None:
            # Restore original cache dir
            from celestron_nexstar.api.location.light_pollution import CACHE_DIR

            CACHE_DIR = self.original_cache_dir
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_cache_key(self):
        """Test cache key generation"""
        key = _get_cache_key(40.123456, -100.987654)
        self.assertEqual(key, "40.12,-100.99")

    def test_ensure_cache_dir(self):
        """Test cache directory creation"""
        with patch("celestron_nexstar.api.location.light_pollution.CACHE_DIR", Path(self.temp_dir) / "cache"):
            _ensure_cache_dir()
            self.assertTrue((Path(self.temp_dir) / "cache").exists())

    def test_save_and_load_cache(self):
        """Test saving and loading cache"""
        cache_file = Path(self.temp_dir) / "test_cache.json"
        with patch("celestron_nexstar.api.location.light_pollution.CACHE_FILE", cache_file):
            test_data = {"data": {"40.0,-100.0": {"sqm": 21.5}}, "timestamp": datetime.now(UTC).isoformat()}
            _save_cache(test_data)

            loaded = _load_cache()
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["data"]["40.0,-100.0"]["sqm"], 21.5)

    def test_load_cache_not_exists(self):
        """Test loading cache when file doesn't exist"""
        with patch("celestron_nexstar.api.location.light_pollution.CACHE_FILE", Path(self.temp_dir) / "nonexistent.json"):
            result = _load_cache()
            self.assertIsNone(result)

    def test_load_cache_invalid_json(self):
        """Test loading cache with invalid JSON"""
        cache_file = Path(self.temp_dir) / "invalid_cache.json"
        cache_file.write_text("invalid json{")
        with patch("celestron_nexstar.api.location.light_pollution.CACHE_FILE", cache_file):
            result = _load_cache()
            self.assertIsNone(result)

    def test_is_cache_stale_fresh(self):
        """Test cache staleness check with fresh cache"""
        cache_data = {"timestamp": datetime.now(UTC).isoformat()}
        self.assertFalse(_is_cache_stale(cache_data))

    def test_is_cache_stale_old(self):
        """Test cache staleness check with old cache"""
        old_time = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
        cache_data = {"timestamp": old_time}
        self.assertTrue(_is_cache_stale(cache_data))

    def test_is_cache_stale_no_timestamp(self):
        """Test cache staleness check without timestamp"""
        cache_data = {}
        self.assertTrue(_is_cache_stale(cache_data))

    def test_is_cache_too_old_fresh(self):
        """Test cache age check with fresh cache"""
        cache_data = {"timestamp": datetime.now(UTC).isoformat()}
        self.assertFalse(_is_cache_too_old(cache_data))

    def test_is_cache_too_old_very_old(self):
        """Test cache age check with very old cache"""
        old_time = (datetime.now(UTC) - timedelta(days=8)).isoformat()
        cache_data = {"timestamp": old_time}
        self.assertTrue(_is_cache_too_old(cache_data))

    def test_is_cache_too_old_no_timestamp(self):
        """Test cache age check without timestamp"""
        cache_data = {}
        self.assertTrue(_is_cache_too_old(cache_data))


class TestFetchSqm(unittest.TestCase):
    """Test suite for _fetch_sqm function"""

    @patch("celestron_nexstar.api.database.database.get_database")
    @patch("celestron_nexstar.api.database.light_pollution_db.get_sqm_from_database")
    def test_fetch_sqm_success(self, mock_get_sqm, mock_get_db):
        """Test successful SQM fetch from database"""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_get_sqm.return_value = 21.5

        result = asyncio.run(_fetch_sqm(40.0, -100.0))

        self.assertEqual(result, 21.5)

    @patch("celestron_nexstar.api.database.database.get_database")
    @patch("celestron_nexstar.api.database.light_pollution_db.get_sqm_from_database")
    def test_fetch_sqm_not_found(self, mock_get_sqm, mock_get_db):
        """Test SQM fetch when not in database"""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_get_sqm.return_value = None

        result = asyncio.run(_fetch_sqm(40.0, -100.0))

        self.assertIsNone(result)

    @patch("celestron_nexstar.api.database.database.get_database")
    def test_fetch_sqm_exception(self, mock_get_db):
        """Test SQM fetch when exception occurs"""
        mock_get_db.side_effect = Exception("Database error")

        result = asyncio.run(_fetch_sqm(40.0, -100.0))

        self.assertIsNone(result)


class TestGetLightPollutionData(unittest.TestCase):
    """Test suite for get_light_pollution_data function"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_session = AsyncMock()

    @patch("celestron_nexstar.api.location.light_pollution._fetch_sqm")
    @patch("celestron_nexstar.api.location.light_pollution._create_light_pollution_data")
    @patch("celestron_nexstar.api.location.light_pollution._load_cache")
    @patch("celestron_nexstar.api.location.light_pollution._save_cache")
    def test_get_light_pollution_data_success(self, mock_save, mock_load, mock_create, mock_fetch):
        """Test successful light pollution data retrieval"""
        mock_load.return_value = None  # No cache
        mock_fetch.return_value = 21.5

        mock_data = LightPollutionData(
            bortle_class=BortleClass.CLASS_3,
            sqm_value=21.5,
            naked_eye_limiting_magnitude=6.5,
            milky_way_visible=True,
            airglow_visible=True,
            zodiacal_light_visible=True,
            description="Good",
            recommendations=("Good for observing",),
        )
        mock_create.return_value = mock_data

        result = asyncio.run(get_light_pollution_data(self.mock_session, 40.0, -100.0))

        self.assertIsInstance(result, LightPollutionData)
        mock_fetch.assert_called_once_with(40.0, -100.0)

    @patch("celestron_nexstar.api.location.light_pollution._fetch_sqm")
    @patch("celestron_nexstar.api.location.light_pollution._load_cache")
    def test_get_light_pollution_data_from_cache(self, mock_load, mock_fetch):
        """Test using cached light pollution data"""
        now = datetime.now(UTC)
        cache_data = {
            "data": {
                "40.0,-100.0": {
                    "sqm": 21.5,
                    "source": "database",
                    "timestamp": now.isoformat(),
                }
            },
            "timestamp": now.isoformat(),
        }
        mock_load.return_value = cache_data

        mock_data = LightPollutionData(
            bortle_class=BortleClass.CLASS_3,
            sqm_value=21.5,
            naked_eye_limiting_magnitude=6.5,
            milky_way_visible=True,
            airglow_visible=True,
            zodiacal_light_visible=True,
            description="Good",
            recommendations=("Good for observing",),
            cached=True,
        )

        with patch("celestron_nexstar.api.location.light_pollution._create_light_pollution_data") as mock_create:
            mock_create.return_value = mock_data

            result = asyncio.run(get_light_pollution_data(self.mock_session, 40.0, -100.0))

            self.assertTrue(result.cached)
            mock_fetch.assert_not_called()

    @patch("celestron_nexstar.api.location.light_pollution._fetch_sqm")
    @patch("celestron_nexstar.api.location.light_pollution._load_cache")
    def test_get_light_pollution_data_not_found(self, mock_load, mock_fetch):
        """Test error when no light pollution data found"""
        mock_load.return_value = None
        mock_fetch.return_value = None

        with self.assertRaises(DatabaseError) as context:
            asyncio.run(get_light_pollution_data(self.mock_session, 40.0, -100.0))

        self.assertIn("No light pollution data found", str(context.exception))

    @patch("celestron_nexstar.api.location.light_pollution._fetch_sqm")
    @patch("celestron_nexstar.api.location.light_pollution._load_cache")
    @patch("celestron_nexstar.api.location.light_pollution._create_light_pollution_data")
    @patch("celestron_nexstar.api.location.light_pollution._save_cache")
    def test_get_light_pollution_data_force_refresh(self, mock_save, mock_create, mock_load, mock_fetch):
        """Test forcing refresh of light pollution data"""
        mock_load.return_value = {"data": {"40.0,-100.0": {"sqm": 21.5}}}
        mock_fetch.return_value = 21.8

        mock_data = LightPollutionData(
            bortle_class=BortleClass.CLASS_3,
            sqm_value=21.8,
            naked_eye_limiting_magnitude=6.5,
            milky_way_visible=True,
            airglow_visible=True,
            zodiacal_light_visible=True,
            description="Good",
            recommendations=("Good for observing",),
        )
        mock_create.return_value = mock_data

        result = asyncio.run(get_light_pollution_data(self.mock_session, 40.0, -100.0, force_refresh=True))

        mock_fetch.assert_called_once()
        self.assertFalse(result.cached)


class TestGetLightPollutionDataBatch(unittest.TestCase):
    """Test suite for get_light_pollution_data_batch function"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_session = AsyncMock()

    @patch("celestron_nexstar.api.location.light_pollution.get_light_pollution_data")
    def test_get_light_pollution_data_batch_success(self, mock_get_data):
        """Test successful batch retrieval"""
        locations = [(40.0, -100.0), (41.0, -101.0)]
        mock_data1 = LightPollutionData(
            bortle_class=BortleClass.CLASS_3,
            sqm_value=21.5,
            naked_eye_limiting_magnitude=6.5,
            milky_way_visible=True,
            airglow_visible=True,
            zodiacal_light_visible=True,
            description="Good",
            recommendations=("Good",),
        )
        mock_data2 = LightPollutionData(
            bortle_class=BortleClass.CLASS_4,
            sqm_value=20.5,
            naked_eye_limiting_magnitude=6.0,
            milky_way_visible=False,
            airglow_visible=True,
            zodiacal_light_visible=True,
            description="Fair",
            recommendations=("Fair",),
        )
        mock_get_data.side_effect = [mock_data1, mock_data2]

        result = asyncio.run(get_light_pollution_data_batch(self.mock_session, locations))

        self.assertEqual(len(result), 2)
        self.assertIn((40.0, -100.0), result)
        self.assertIn((41.0, -101.0), result)

    @patch("celestron_nexstar.api.location.light_pollution.get_light_pollution_data")
    def test_get_light_pollution_data_batch_with_errors(self, mock_get_data):
        """Test batch retrieval with some errors"""
        locations = [(40.0, -100.0), (41.0, -101.0)]
        mock_data1 = LightPollutionData(
            bortle_class=BortleClass.CLASS_3,
            sqm_value=21.5,
            naked_eye_limiting_magnitude=6.5,
            milky_way_visible=True,
            airglow_visible=True,
            zodiacal_light_visible=True,
            description="Good",
            recommendations=("Good",),
        )
        mock_get_data.side_effect = [mock_data1, DatabaseError("No data")]

        result = asyncio.run(get_light_pollution_data_batch(self.mock_session, locations))

        self.assertEqual(len(result), 1)
        self.assertIn((40.0, -100.0), result)
        self.assertNotIn((41.0, -101.0), result)


if __name__ == "__main__":
    unittest.main()

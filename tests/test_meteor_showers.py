"""
Unit tests for meteor_showers.py

Tests meteor shower calendar and active shower calculations.
"""

import asyncio
import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from celestron_nexstar.api.astronomy.meteor_showers import (
    MeteorShower,
    _is_date_in_range,
    get_active_showers,
    get_all_meteor_showers,
    get_peak_showers,
    get_radiant_position,
)
from celestron_nexstar.api.core.exceptions import DatabaseError


class TestMeteorShower(unittest.TestCase):
    """Test suite for MeteorShower dataclass"""

    def test_creation(self):
        """Test creating a MeteorShower"""
        shower = MeteorShower(
            name="Perseids",
            activity_start_month=7,
            activity_start_day=17,
            activity_end_month=8,
            activity_end_day=24,
            peak_month=8,
            peak_day=12,
            peak_end_month=8,
            peak_end_day=13,
            zhr_peak=100,
            velocity_km_s=59,
            radiant_ra_hours=3.2,
            radiant_dec_degrees=58.0,
            parent_comet="109P/Swift-Tuttle",
            description="One of the best annual meteor showers",
        )
        self.assertEqual(shower.name, "Perseids")
        self.assertEqual(shower.peak_month, 8)
        self.assertEqual(shower.peak_day, 12)
        self.assertEqual(shower.zhr_peak, 100)
        self.assertEqual(shower.parent_comet, "109P/Swift-Tuttle")


class TestIsDateInRange(unittest.TestCase):
    """Test suite for _is_date_in_range function"""

    def test_normal_range(self):
        """Test date in normal range (no year wraparound)"""
        # April 14 to April 30
        self.assertTrue(_is_date_in_range(4, 20, 4, 14, 4, 30))
        self.assertTrue(_is_date_in_range(4, 14, 4, 14, 4, 30))
        self.assertTrue(_is_date_in_range(4, 30, 4, 14, 4, 30))
        self.assertFalse(_is_date_in_range(4, 10, 4, 14, 4, 30))
        self.assertFalse(_is_date_in_range(5, 1, 4, 14, 4, 30))

    def test_wraparound_range(self):
        """Test date in wraparound range (crosses year boundary)"""
        # Dec 28 to Jan 12
        self.assertTrue(_is_date_in_range(12, 30, 12, 28, 1, 12))
        self.assertTrue(_is_date_in_range(1, 5, 12, 28, 1, 12))
        self.assertTrue(_is_date_in_range(12, 28, 12, 28, 1, 12))
        self.assertTrue(_is_date_in_range(1, 12, 12, 28, 1, 12))
        self.assertFalse(_is_date_in_range(12, 20, 12, 28, 1, 12))
        self.assertFalse(_is_date_in_range(1, 15, 12, 28, 1, 12))


class TestGetAllMeteorShowers(unittest.TestCase):
    """Test suite for get_all_meteor_showers function"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_session = AsyncMock()

    def test_get_all_meteor_showers_success(self):
        """Test successful retrieval of meteor showers"""
        # Mock count query
        self.mock_session.scalar = AsyncMock(return_value=2)

        # Mock meteor shower models
        mock_model1 = MagicMock()
        mock_shower1 = MeteorShower(
            name="Perseids",
            activity_start_month=7,
            activity_start_day=17,
            activity_end_month=8,
            activity_end_day=24,
            peak_month=8,
            peak_day=12,
            peak_end_month=8,
            peak_end_day=13,
            zhr_peak=100,
            velocity_km_s=59,
            radiant_ra_hours=3.2,
            radiant_dec_degrees=58.0,
            parent_comet="109P/Swift-Tuttle",
            description="Best annual shower",
        )
        mock_model1.to_meteor_shower.return_value = mock_shower1

        mock_model2 = MagicMock()
        mock_shower2 = MeteorShower(
            name="Geminids",
            activity_start_month=12,
            activity_start_day=4,
            activity_end_month=12,
            activity_end_day=17,
            peak_month=12,
            peak_day=14,
            peak_end_month=12,
            peak_end_day=15,
            zhr_peak=120,
            velocity_km_s=35,
            radiant_ra_hours=7.5,
            radiant_dec_degrees=32.0,
            parent_comet="3200 Phaethon",
            description="Rich meteor shower",
        )
        mock_model2.to_meteor_shower.return_value = mock_shower2

        # Mock execute query
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_model1, mock_model2]
        self.mock_session.execute = AsyncMock(return_value=mock_result)

        result = asyncio.run(get_all_meteor_showers(self.mock_session))

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].name, "Perseids")
        self.assertEqual(result[1].name, "Geminids")

    def test_get_all_meteor_showers_empty_database(self):
        """Test error when database is empty"""
        self.mock_session.scalar = AsyncMock(return_value=0)

        with self.assertRaises(DatabaseError) as context:
            asyncio.run(get_all_meteor_showers(self.mock_session))

        self.assertIn("No meteor showers found", str(context.exception))


class TestGetActiveShowers(unittest.TestCase):
    """Test suite for get_active_showers function"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_session = AsyncMock()

    @patch("celestron_nexstar.api.astronomy.meteor_showers.get_all_meteor_showers")
    def test_get_active_showers_success(self, mock_get_all):
        """Test successful retrieval of active showers"""
        # Create a shower active in August
        shower = MeteorShower(
            name="Perseids",
            activity_start_month=7,
            activity_start_day=17,
            activity_end_month=8,
            activity_end_day=24,
            peak_month=8,
            peak_day=12,
            peak_end_month=8,
            peak_end_day=13,
            zhr_peak=100,
            velocity_km_s=59,
            radiant_ra_hours=3.2,
            radiant_dec_degrees=58.0,
            parent_comet="109P/Swift-Tuttle",
            description="Best annual shower",
        )
        mock_get_all.return_value = [shower]

        # Check on August 12 (during activity period)
        check_date = datetime(2024, 8, 12, tzinfo=UTC)
        result = asyncio.run(get_active_showers(self.mock_session, check_date))

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "Perseids")

    @patch("celestron_nexstar.api.astronomy.meteor_showers.get_all_meteor_showers")
    def test_get_active_showers_not_active(self, mock_get_all):
        """Test filtering showers not active on date"""
        shower = MeteorShower(
            name="Perseids",
            activity_start_month=7,
            activity_start_day=17,
            activity_end_month=8,
            activity_end_day=24,
            peak_month=8,
            peak_day=12,
            peak_end_month=8,
            peak_end_day=13,
            zhr_peak=100,
            velocity_km_s=59,
            radiant_ra_hours=3.2,
            radiant_dec_degrees=58.0,
            parent_comet="109P/Swift-Tuttle",
            description="Best annual shower",
        )
        mock_get_all.return_value = [shower]

        # Check on September 1 (outside activity period)
        check_date = datetime(2024, 9, 1, tzinfo=UTC)
        result = asyncio.run(get_active_showers(self.mock_session, check_date))

        self.assertEqual(len(result), 0)

    @patch("celestron_nexstar.api.astronomy.meteor_showers.get_all_meteor_showers")
    def test_get_active_showers_default_date(self, mock_get_all):
        """Test get_active_showers with default date (now)"""
        mock_get_all.return_value = []

        result = asyncio.run(get_active_showers(self.mock_session))

        self.assertIsInstance(result, list)


class TestGetPeakShowers(unittest.TestCase):
    """Test suite for get_peak_showers function"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_session = AsyncMock()

    @patch("celestron_nexstar.api.astronomy.meteor_showers.get_all_meteor_showers")
    def test_get_peak_showers_success(self, mock_get_all):
        """Test successful retrieval of peak showers"""
        shower = MeteorShower(
            name="Perseids",
            activity_start_month=7,
            activity_start_day=17,
            activity_end_month=8,
            activity_end_day=24,
            peak_month=8,
            peak_day=12,
            peak_end_month=8,
            peak_end_day=13,
            zhr_peak=100,
            velocity_km_s=59,
            radiant_ra_hours=3.2,
            radiant_dec_degrees=58.0,
            parent_comet="109P/Swift-Tuttle",
            description="Best annual shower",
        )
        mock_get_all.return_value = [shower]

        # Check on August 12 (peak day)
        check_date = datetime(2024, 8, 12, tzinfo=UTC)
        result = asyncio.run(get_peak_showers(self.mock_session, check_date))

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "Perseids")


class TestGetRadiantPosition(unittest.TestCase):
    """Test suite for get_radiant_position function"""

    @patch("celestron_nexstar.api.astronomy.meteor_showers.ra_dec_to_alt_az")
    def test_get_radiant_position(self, mock_ra_dec_to_alt_az):
        """Test getting radiant position"""
        shower = MeteorShower(
            name="Perseids",
            activity_start_month=7,
            activity_start_day=17,
            activity_end_month=8,
            activity_end_day=24,
            peak_month=8,
            peak_day=12,
            peak_end_month=8,
            peak_end_day=13,
            zhr_peak=100,
            velocity_km_s=59,
            radiant_ra_hours=3.2,
            radiant_dec_degrees=58.0,
            parent_comet="109P/Swift-Tuttle",
            description="Best annual shower",
        )

        mock_ra_dec_to_alt_az.return_value = (45.0, 180.0)  # altitude, azimuth

        result = get_radiant_position(shower, 40.0, -100.0, datetime(2024, 8, 12, tzinfo=UTC))

        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], 45.0)  # altitude
        self.assertEqual(result[1], 180.0)  # azimuth


if __name__ == "__main__":
    unittest.main()

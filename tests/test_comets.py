"""
Unit tests for comets.py

Tests comet tracking and visibility calculations.
"""

import asyncio
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from celestron_nexstar.api.astronomy.comets import (
    Comet,
    CometVisibility,
    _estimate_comet_magnitude,
    get_known_comets,
    get_upcoming_comets,
    get_visible_comets,
)
from celestron_nexstar.api.core.exceptions import DatabaseError
from celestron_nexstar.api.location.observer import ObserverLocation


class TestComet(unittest.TestCase):
    """Test suite for Comet dataclass"""

    def test_creation(self):
        """Test creating a Comet"""
        comet = Comet(
            name="Halley's Comet",
            designation="1P/Halley",
            perihelion_date=datetime(2061, 7, 28, tzinfo=UTC),
            perihelion_distance_au=0.586,
            peak_magnitude=2.0,
            peak_date=datetime(2061, 7, 28, tzinfo=UTC),
            is_periodic=True,
            period_years=75.3,
            notes="Famous periodic comet",
        )
        self.assertEqual(comet.name, "Halley's Comet")
        self.assertEqual(comet.designation, "1P/Halley")
        self.assertTrue(comet.is_periodic)
        self.assertEqual(comet.period_years, 75.3)


class TestCometVisibility(unittest.TestCase):
    """Test suite for CometVisibility dataclass"""

    def test_creation(self):
        """Test creating a CometVisibility"""
        comet = Comet(
            name="Test Comet",
            designation="C/2024 A1",
            perihelion_date=datetime(2024, 6, 15, tzinfo=UTC),
            perihelion_distance_au=1.0,
            peak_magnitude=5.0,
            peak_date=datetime(2024, 6, 15, tzinfo=UTC),
            is_periodic=False,
            period_years=None,
            notes="Test",
        )
        visibility = CometVisibility(
            comet=comet,
            date=datetime(2024, 6, 15, tzinfo=UTC),
            magnitude=5.0,
            altitude=45.0,
            is_visible=True,
            best_viewing_time=datetime(2024, 6, 15, 2, 0, tzinfo=UTC),
            notes="Visible",
        )
        self.assertEqual(visibility.comet, comet)
        self.assertEqual(visibility.magnitude, 5.0)
        self.assertEqual(visibility.altitude, 45.0)
        self.assertTrue(visibility.is_visible)


class TestEstimateCometMagnitude(unittest.TestCase):
    """Test suite for _estimate_comet_magnitude function"""

    def setUp(self):
        """Set up test fixtures"""
        self.comet = Comet(
            name="Test Comet",
            designation="C/2024 A1",
            perihelion_date=datetime(2024, 6, 15, tzinfo=UTC),
            perihelion_distance_au=1.0,
            peak_magnitude=5.0,
            peak_date=datetime(2024, 6, 15, tzinfo=UTC),
            is_periodic=False,
            period_years=None,
            notes="Test",
        )

    def test_near_perihelion(self):
        """Test magnitude estimation near perihelion"""
        date = datetime(2024, 6, 20, tzinfo=UTC)  # 5 days after perihelion
        magnitude = _estimate_comet_magnitude(self.comet, date)
        self.assertEqual(magnitude, 5.0)  # Should use peak magnitude

    def test_far_from_perihelion(self):
        """Test magnitude estimation far from perihelion"""
        date = datetime(2024, 8, 15, tzinfo=UTC)  # 61 days after perihelion
        magnitude = _estimate_comet_magnitude(self.comet, date)
        # Should be dimmer: 5.0 + (61/10 * 0.1) = 5.0 + 0.61 = 5.61
        self.assertAlmostEqual(magnitude, 5.61, places=2)

    def test_before_perihelion(self):
        """Test magnitude estimation before perihelion"""
        date = datetime(2024, 5, 15, tzinfo=UTC)  # 31 days before perihelion
        magnitude = _estimate_comet_magnitude(self.comet, date)
        # Should be dimmer: 5.0 + (31/10 * 0.1) = 5.0 + 0.31 = 5.31
        self.assertAlmostEqual(magnitude, 5.31, places=2)


class TestGetKnownComets(unittest.TestCase):
    """Test suite for get_known_comets function"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_session = AsyncMock()

    def test_get_known_comets_success(self):
        """Test successful retrieval of comets"""
        # Mock count query
        self.mock_session.scalar = AsyncMock(return_value=2)

        # Mock comet models
        mock_model1 = MagicMock()
        mock_comet1 = Comet(
            name="Comet 1",
            designation="C/2024 A1",
            perihelion_date=datetime(2024, 6, 15, tzinfo=UTC),
            perihelion_distance_au=1.0,
            peak_magnitude=5.0,
            peak_date=datetime(2024, 6, 15, tzinfo=UTC),
            is_periodic=False,
            period_years=None,
            notes="Test 1",
        )
        mock_model1.to_comet.return_value = mock_comet1

        mock_model2 = MagicMock()
        mock_comet2 = Comet(
            name="Comet 2",
            designation="C/2024 B2",
            perihelion_date=datetime(2024, 7, 15, tzinfo=UTC),
            perihelion_distance_au=1.2,
            peak_magnitude=6.0,
            peak_date=datetime(2024, 7, 15, tzinfo=UTC),
            is_periodic=False,
            period_years=None,
            notes="Test 2",
        )
        mock_model2.to_comet.return_value = mock_comet2

        # Mock execute query
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_model1, mock_model2]
        self.mock_session.execute = AsyncMock(return_value=mock_result)

        result = asyncio.run(get_known_comets(self.mock_session))

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].name, "Comet 1")
        self.assertEqual(result[1].name, "Comet 2")

    def test_get_known_comets_empty_database(self):
        """Test error when database is empty"""
        self.mock_session.scalar = AsyncMock(return_value=0)

        with self.assertRaises(DatabaseError) as context:
            asyncio.run(get_known_comets(self.mock_session))

        self.assertIn("No comets found", str(context.exception))


class TestGetVisibleComets(unittest.TestCase):
    """Test suite for get_visible_comets function"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_session = AsyncMock()
        self.test_location = ObserverLocation(latitude=40.0, longitude=-100.0, name="Test Location")

    @patch("celestron_nexstar.api.astronomy.comets.get_known_comets")
    def test_get_visible_comets_success(self, mock_get_known):
        """Test successful retrieval of visible comets"""
        # Create a comet that's active in the time window
        now = datetime.now(UTC)
        comet = Comet(
            name="Test Comet",
            designation="C/2024 A1",
            perihelion_date=now + timedelta(days=30),
            perihelion_distance_au=1.0,
            peak_magnitude=5.0,
            peak_date=now + timedelta(days=30),
            is_periodic=False,
            period_years=None,
            notes="Test",
        )
        mock_get_known.return_value = [comet]

        result = asyncio.run(
            get_visible_comets(self.mock_session, self.test_location, months_ahead=12, max_magnitude=8.0)
        )

        self.assertIsInstance(result, list)
        # Should have visibility entries for the comet

    @patch("celestron_nexstar.api.astronomy.comets.get_known_comets")
    def test_get_visible_comets_outside_window(self, mock_get_known):
        """Test filtering comets outside time window"""
        # Create a comet that's not active in the time window
        now = datetime.now(UTC)
        comet = Comet(
            name="Old Comet",
            designation="C/2020 A1",
            perihelion_date=now - timedelta(days=200),  # Too old
            perihelion_distance_au=1.0,
            peak_magnitude=5.0,
            peak_date=now - timedelta(days=200),
            is_periodic=False,
            period_years=None,
            notes="Old",
        )
        mock_get_known.return_value = [comet]

        result = asyncio.run(
            get_visible_comets(self.mock_session, self.test_location, months_ahead=12, max_magnitude=8.0)
        )

        # Should be empty since comet is outside activity window
        self.assertEqual(len(result), 0)

    @patch("celestron_nexstar.api.astronomy.comets.get_known_comets")
    def test_get_visible_comets_magnitude_filter(self, mock_get_known):
        """Test filtering by magnitude"""
        now = datetime.now(UTC)
        comet = Comet(
            name="Dim Comet",
            designation="C/2024 A1",
            perihelion_date=now + timedelta(days=30),
            perihelion_distance_au=1.0,
            peak_magnitude=10.0,  # Too dim
            peak_date=now + timedelta(days=30),
            is_periodic=False,
            period_years=None,
            notes="Dim",
        )
        mock_get_known.return_value = [comet]

        result = asyncio.run(
            get_visible_comets(self.mock_session, self.test_location, months_ahead=12, max_magnitude=8.0)
        )

        # Should be empty since comet is too dim
        self.assertEqual(len(result), 0)


class TestGetUpcomingComets(unittest.TestCase):
    """Test suite for get_upcoming_comets function"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_session = AsyncMock()
        self.test_location = ObserverLocation(latitude=40.0, longitude=-100.0, name="Test Location")

    @patch("celestron_nexstar.api.astronomy.comets.get_visible_comets")
    def test_get_upcoming_comets(self, mock_get_visible):
        """Test get_upcoming_comets calls get_visible_comets with correct parameters"""
        mock_visibility = CometVisibility(
            comet=Comet(
                name="Test",
                designation="C/2024 A1",
                perihelion_date=datetime.now(UTC),
                perihelion_distance_au=1.0,
                peak_magnitude=5.0,
                peak_date=datetime.now(UTC),
                is_periodic=False,
                period_years=None,
                notes="Test",
            ),
            date=datetime.now(UTC),
            magnitude=5.0,
            altitude=30.0,
            is_visible=True,
            best_viewing_time=None,
            notes="Test",
        )
        mock_get_visible.return_value = [mock_visibility]

        result = asyncio.run(get_upcoming_comets(self.mock_session, self.test_location, months_ahead=24))

        mock_get_visible.assert_called_once_with(
            self.mock_session, self.test_location, months_ahead=24, max_magnitude=10.0
        )
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()

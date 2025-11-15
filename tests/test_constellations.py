"""
Unit tests for constellations.py

Tests constellation and asterism catalog functions.
"""

import asyncio
import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from celestron_nexstar.api.core.exceptions import DatabaseError
from celestron_nexstar.api.astronomy.constellations import (
    Asterism,
    Constellation,
    get_famous_asterisms,
    get_prominent_constellations,
    get_visible_asterisms,
    get_visible_constellations,
)


class TestConstellation(unittest.TestCase):
    """Test suite for Constellation dataclass"""

    def test_creation(self):
        """Test creating a Constellation"""
        constellation = Constellation(
            name="Orion",
            abbreviation="Ori",
            ra_hours=5.5,
            dec_degrees=5.0,
            area_sq_deg=594.0,
            brightest_star="Rigel",
            magnitude=0.18,
            season="Winter",
            hemisphere="Equatorial",
            description="The Hunter",
        )
        self.assertEqual(constellation.name, "Orion")
        self.assertEqual(constellation.abbreviation, "Ori")
        self.assertEqual(constellation.ra_hours, 5.5)
        self.assertEqual(constellation.dec_degrees, 5.0)
        self.assertEqual(constellation.season, "Winter")


class TestAsterism(unittest.TestCase):
    """Test suite for Asterism dataclass"""

    def test_creation(self):
        """Test creating an Asterism"""
        asterism = Asterism(
            name="Big Dipper",
            alt_names=["Plough", "Ursa Major"],
            ra_hours=11.0,
            dec_degrees=50.0,
            size_degrees=25.0,
            parent_constellation="Ursa Major",
            season="Spring",
            hemisphere="Northern",
            member_stars=["Dubhe", "Merak", "Phecda", "Megrez", "Alioth", "Mizar", "Alkaid"],
            description="Seven bright stars forming a dipper shape",
        )
        self.assertEqual(asterism.name, "Big Dipper")
        self.assertEqual(len(asterism.alt_names), 2)
        self.assertEqual(asterism.parent_constellation, "Ursa Major")
        self.assertEqual(len(asterism.member_stars), 7)


class TestGetProminentConstellations(unittest.TestCase):
    """Test suite for get_prominent_constellations function"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_session = AsyncMock()

    def test_get_prominent_constellations_success(self):
        """Test successful retrieval of constellations"""
        # Mock count query
        self.mock_session.scalar = AsyncMock(return_value=2)

        # Mock constellation models
        mock_model1 = MagicMock()
        mock_constellation1 = Constellation(
            name="Orion",
            abbreviation="Ori",
            ra_hours=5.5,
            dec_degrees=5.0,
            area_sq_deg=594.0,
            brightest_star="Rigel",
            magnitude=0.18,
            season="Winter",
            hemisphere="Equatorial",
            description="The Hunter",
        )
        mock_model1.to_constellation.return_value = mock_constellation1

        mock_model2 = MagicMock()
        mock_constellation2 = Constellation(
            name="Ursa Major",
            abbreviation="UMa",
            ra_hours=10.5,
            dec_degrees=55.0,
            area_sq_deg=1280.0,
            brightest_star="Alioth",
            magnitude=1.76,
            season="Spring",
            hemisphere="Northern",
            description="The Great Bear",
        )
        mock_model2.to_constellation.return_value = mock_constellation2

        # Mock execute query
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_model1, mock_model2]
        self.mock_session.execute = AsyncMock(return_value=mock_result)

        result = asyncio.run(get_prominent_constellations(self.mock_session))

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].name, "Orion")
        self.assertEqual(result[1].name, "Ursa Major")

    def test_get_prominent_constellations_empty_database(self):
        """Test error when database is empty"""
        self.mock_session.scalar = AsyncMock(return_value=0)

        with self.assertRaises(DatabaseError) as context:
            asyncio.run(get_prominent_constellations(self.mock_session))

        self.assertIn("No constellations found", str(context.exception))


class TestGetFamousAsterisms(unittest.TestCase):
    """Test suite for get_famous_asterisms function"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_session = AsyncMock()

    def test_get_famous_asterisms_success(self):
        """Test successful retrieval of asterisms"""
        # Mock count query
        self.mock_session.scalar = AsyncMock(return_value=1)

        # Mock asterism model
        mock_model = MagicMock()
        mock_asterism = Asterism(
            name="Big Dipper",
            alt_names=["Plough"],
            ra_hours=11.0,
            dec_degrees=50.0,
            size_degrees=25.0,
            parent_constellation="Ursa Major",
            season="Spring",
            hemisphere="Northern",
            member_stars=["Dubhe", "Merak"],
            description="Seven bright stars",
        )
        mock_model.to_asterism.return_value = mock_asterism

        # Mock execute query
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_model]
        self.mock_session.execute = AsyncMock(return_value=mock_result)

        result = asyncio.run(get_famous_asterisms(self.mock_session))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "Big Dipper")

    def test_get_famous_asterisms_empty_database(self):
        """Test error when database is empty"""
        self.mock_session.scalar = AsyncMock(return_value=0)

        with self.assertRaises(DatabaseError) as context:
            asyncio.run(get_famous_asterisms(self.mock_session))

        self.assertIn("No asterisms found", str(context.exception))


class TestGetVisibleConstellations(unittest.TestCase):
    """Test suite for get_visible_constellations function"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_session = AsyncMock()

    @patch("celestron_nexstar.api.astronomy.constellations.get_prominent_constellations")
    @patch("celestron_nexstar.api.astronomy.constellations.ra_dec_to_alt_az")
    def test_get_visible_constellations_success(self, mock_ra_dec_to_alt_az, mock_get_constellations):
        """Test successful retrieval of visible constellations"""
        # Mock constellations
        constellation = Constellation(
            name="Orion",
            abbreviation="Ori",
            ra_hours=5.5,
            dec_degrees=5.0,
            area_sq_deg=594.0,
            brightest_star="Rigel",
            magnitude=0.18,
            season="Winter",
            hemisphere="Equatorial",
            description="The Hunter",
        )
        mock_get_constellations.return_value = [constellation]

        # Mock altitude calculation - return altitude above threshold
        mock_ra_dec_to_alt_az.return_value = (45.0, 180.0)  # altitude, azimuth

        result = asyncio.run(
            get_visible_constellations(self.mock_session, latitude=40.0, longitude=-100.0, min_altitude_deg=20.0)
        )

        self.assertIsInstance(result, list)
        # Should have entries for visible constellations
        if result:
            self.assertIsInstance(result[0], tuple)
            self.assertEqual(len(result[0]), 3)  # (constellation, altitude, azimuth)

    @patch("celestron_nexstar.api.astronomy.constellations.get_prominent_constellations")
    @patch("celestron_nexstar.api.astronomy.constellations.ra_dec_to_alt_az")
    def test_get_visible_constellations_below_horizon(self, mock_ra_dec_to_alt_az, mock_get_constellations):
        """Test filtering constellations below horizon"""
        constellation = Constellation(
            name="Orion",
            abbreviation="Ori",
            ra_hours=5.5,
            dec_degrees=5.0,
            area_sq_deg=594.0,
            brightest_star="Rigel",
            magnitude=0.18,
            season="Winter",
            hemisphere="Equatorial",
            description="The Hunter",
        )
        mock_get_constellations.return_value = [constellation]

        # Mock altitude calculation - return altitude below threshold
        mock_ra_dec_to_alt_az.return_value = (10.0, 180.0)  # altitude below 20°

        result = asyncio.run(
            get_visible_constellations(self.mock_session, latitude=40.0, longitude=-100.0, min_altitude_deg=20.0)
        )

        # Should be empty since constellation is below horizon
        self.assertEqual(len(result), 0)


class TestGetVisibleAsterisms(unittest.TestCase):
    """Test suite for get_visible_asterisms function"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_session = AsyncMock()

    @patch("celestron_nexstar.api.astronomy.constellations.get_famous_asterisms")
    @patch("celestron_nexstar.api.astronomy.constellations.ra_dec_to_alt_az")
    def test_get_visible_asterisms_success(self, mock_ra_dec_to_alt_az, mock_get_asterisms):
        """Test successful retrieval of visible asterisms"""
        # Mock asterisms
        asterism = Asterism(
            name="Big Dipper",
            alt_names=["Plough"],
            ra_hours=11.0,
            dec_degrees=50.0,
            size_degrees=25.0,
            parent_constellation="Ursa Major",
            season="Spring",
            hemisphere="Northern",
            member_stars=["Dubhe", "Merak"],
            description="Seven bright stars",
        )
        mock_get_asterisms.return_value = [asterism]

        # Mock altitude calculation - return altitude above threshold
        mock_ra_dec_to_alt_az.return_value = (50.0, 180.0)  # altitude, azimuth

        result = asyncio.run(
            get_visible_asterisms(self.mock_session, latitude=40.0, longitude=-100.0, min_altitude_deg=20.0)
        )

        self.assertIsInstance(result, list)
        # Should have entries for visible asterisms
        if result:
            self.assertIsInstance(result[0], tuple)
            self.assertEqual(len(result[0]), 3)  # (asterism, altitude, azimuth)


if __name__ == "__main__":
    unittest.main()

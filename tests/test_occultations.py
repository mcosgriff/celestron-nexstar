"""
Unit tests for occultations.py

Tests asteroid occultation calculations.
"""

import unittest
from datetime import UTC, datetime

from celestron_nexstar.api.astronomy.occultations import Occultation, get_upcoming_occultations
from celestron_nexstar.api.location.observer import ObserverLocation


class TestOccultation(unittest.TestCase):
    """Test suite for Occultation dataclass"""

    def test_creation(self):
        """Test creating an Occultation"""
        occultation = Occultation(
            date=datetime(2024, 6, 15, 20, 0, tzinfo=UTC),
            asteroid_name="Asteroid 123",
            star_name="Alpha Star",
            star_magnitude=5.5,
            duration_seconds=10.5,
            magnitude_drop=2.0,
            is_visible=True,
            notes="Test occultation",
        )
        self.assertEqual(occultation.asteroid_name, "Asteroid 123")
        self.assertEqual(occultation.star_name, "Alpha Star")
        self.assertEqual(occultation.star_magnitude, 5.5)
        self.assertEqual(occultation.duration_seconds, 10.5)
        self.assertEqual(occultation.magnitude_drop, 2.0)
        self.assertTrue(occultation.is_visible)
        self.assertEqual(occultation.notes, "Test occultation")


class TestGetUpcomingOccultations(unittest.TestCase):
    """Test suite for get_upcoming_occultations function"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_location = ObserverLocation(latitude=40.0, longitude=-100.0, name="Test Location")

    def test_get_upcoming_occultations_default(self):
        """Test get_upcoming_occultations with default parameters"""
        result = get_upcoming_occultations(self.test_location)

        self.assertIsInstance(result, list)
        # Currently returns empty list (not yet fully implemented)
        self.assertEqual(len(result), 0)

    def test_get_upcoming_occultations_custom_months(self):
        """Test get_upcoming_occultations with custom months_ahead"""
        result = get_upcoming_occultations(self.test_location, months_ahead=6)

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)

    def test_get_upcoming_occultations_custom_magnitude(self):
        """Test get_upcoming_occultations with custom min_magnitude"""
        result = get_upcoming_occultations(self.test_location, min_magnitude=10.0)

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)


if __name__ == "__main__":
    unittest.main()

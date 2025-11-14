"""
Unit tests for variable_stars.py

Tests variable star event calculations and data structures.
"""

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from celestron_nexstar.api.location.observer import ObserverLocation
from celestron_nexstar.api.astronomy.variable_stars import (
    KNOWN_VARIABLE_STARS,
    VariableStar,
    VariableStarEvent,
    _calculate_next_event,
    get_variable_star_events,
)


class TestVariableStar(unittest.TestCase):
    """Test suite for VariableStar dataclass"""

    def test_creation(self):
        """Test creating a VariableStar"""
        star = VariableStar(
            name="Test Star",
            designation="α Test",
            variable_type="cepheid",
            period_days=5.5,
            magnitude_min=3.0,
            magnitude_max=4.0,
            ra_hours=12.0,
            dec_degrees=45.0,
            notes="A test star",
        )
        self.assertEqual(star.name, "Test Star")
        self.assertEqual(star.designation, "α Test")
        self.assertEqual(star.variable_type, "cepheid")
        self.assertEqual(star.period_days, 5.5)
        self.assertEqual(star.magnitude_min, 3.0)
        self.assertEqual(star.magnitude_max, 4.0)
        self.assertEqual(star.ra_hours, 12.0)
        self.assertEqual(star.dec_degrees, 45.0)
        self.assertEqual(star.notes, "A test star")


class TestVariableStarEvent(unittest.TestCase):
    """Test suite for VariableStarEvent dataclass"""

    def test_creation(self):
        """Test creating a VariableStarEvent"""
        star = VariableStar(
            name="Test Star",
            designation="α Test",
            variable_type="cepheid",
            period_days=5.5,
            magnitude_min=3.0,
            magnitude_max=4.0,
            ra_hours=12.0,
            dec_degrees=45.0,
            notes="A test star",
        )
        event_date = datetime(2024, 6, 15, 20, 0, tzinfo=UTC)
        event = VariableStarEvent(
            star=star,
            event_type="minimum",
            date=event_date,
            magnitude=3.0,
            is_visible=True,
            notes="At minimum",
        )
        self.assertEqual(event.star, star)
        self.assertEqual(event.event_type, "minimum")
        self.assertEqual(event.date, event_date)
        self.assertEqual(event.magnitude, 3.0)
        self.assertTrue(event.is_visible)
        self.assertEqual(event.notes, "At minimum")


class TestKnownVariableStars(unittest.TestCase):
    """Test suite for KNOWN_VARIABLE_STARS constant"""

    def test_known_stars_not_empty(self):
        """Test that KNOWN_VARIABLE_STARS is not empty"""
        self.assertGreater(len(KNOWN_VARIABLE_STARS), 0)

    def test_known_stars_are_variable_stars(self):
        """Test that all known stars are VariableStar instances"""
        for star in KNOWN_VARIABLE_STARS:
            self.assertIsInstance(star, VariableStar)

    def test_algol_in_known_stars(self):
        """Test that Algol is in the known stars list"""
        algol = next((s for s in KNOWN_VARIABLE_STARS if s.name == "Algol"), None)
        self.assertIsNotNone(algol)
        self.assertEqual(algol.variable_type, "eclipsing_binary")
        self.assertAlmostEqual(algol.period_days, 2.867, places=2)

    def test_all_stars_have_required_fields(self):
        """Test that all known stars have all required fields"""
        for star in KNOWN_VARIABLE_STARS:
            self.assertIsInstance(star.name, str)
            self.assertIsInstance(star.designation, str)
            self.assertIsInstance(star.variable_type, str)
            self.assertIsInstance(star.period_days, float)
            self.assertGreater(star.period_days, 0)
            self.assertIsInstance(star.magnitude_min, float)
            self.assertIsInstance(star.magnitude_max, float)
            self.assertLessEqual(star.magnitude_min, star.magnitude_max)  # min should be brighter (lower number)
            self.assertIsInstance(star.ra_hours, float)
            self.assertGreaterEqual(star.ra_hours, 0)
            self.assertLess(star.ra_hours, 24)
            self.assertIsInstance(star.dec_degrees, float)
            self.assertGreaterEqual(star.dec_degrees, -90)
            self.assertLessEqual(star.dec_degrees, 90)
            self.assertIsInstance(star.notes, str)


class TestCalculateNextEvent(unittest.TestCase):
    """Test suite for _calculate_next_event function"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_star = VariableStar(
            name="Test Star",
            designation="α Test",
            variable_type="cepheid",
            period_days=5.0,
            magnitude_min=3.0,
            magnitude_max=4.0,
            ra_hours=12.0,
            dec_degrees=45.0,
            notes="Test",
        )

    def test_calculate_next_event_minimum(self):
        """Test calculating next minimum event"""
        start_date = datetime(2024, 6, 1, tzinfo=UTC)
        event_date = _calculate_next_event(self.test_star, start_date, "minimum")
        self.assertIsNotNone(event_date)
        self.assertIsInstance(event_date, datetime)
        self.assertGreater(event_date, start_date)

    def test_calculate_next_event_maximum(self):
        """Test calculating next maximum event"""
        start_date = datetime(2024, 6, 1, tzinfo=UTC)
        event_date = _calculate_next_event(self.test_star, start_date, "maximum")
        self.assertIsNotNone(event_date)
        self.assertIsInstance(event_date, datetime)
        self.assertGreater(event_date, start_date)

    def test_calculate_next_event_future_date(self):
        """Test calculating next event from a future date"""
        start_date = datetime(2025, 1, 1, tzinfo=UTC)
        event_date = _calculate_next_event(self.test_star, start_date, "minimum")
        self.assertIsNotNone(event_date)
        self.assertGreater(event_date, start_date)

    def test_calculate_next_event_short_period(self):
        """Test calculating next event for short period star"""
        short_period_star = VariableStar(
            name="Short Period",
            designation="SP",
            variable_type="eclipsing_binary",
            period_days=1.0,
            magnitude_min=3.0,
            magnitude_max=4.0,
            ra_hours=12.0,
            dec_degrees=45.0,
            notes="Test",
        )
        start_date = datetime(2024, 6, 1, tzinfo=UTC)
        event_date = _calculate_next_event(short_period_star, start_date, "minimum")
        self.assertIsNotNone(event_date)
        # Should be within a few days for a 1-day period
        days_diff = (event_date - start_date).days
        self.assertLess(days_diff, 2)


class TestGetVariableStarEvents(unittest.TestCase):
    """Test suite for get_variable_star_events function"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_location = ObserverLocation(latitude=40.0, longitude=-100.0, name="Test Location")

    @patch("celestron_nexstar.api.astronomy.variable_stars.datetime")
    def test_get_variable_star_events_default(self, mock_datetime):
        """Test get_variable_star_events with default parameters"""
        # Mock current time
        mock_now = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        events = get_variable_star_events(self.test_location)

        self.assertIsInstance(events, list)
        # Should have events for all known stars
        self.assertGreater(len(events), 0)

    @patch("celestron_nexstar.api.astronomy.variable_stars.datetime")
    def test_get_variable_star_events_filtered_by_type(self, mock_datetime):
        """Test get_variable_star_events filtered by event type"""
        mock_now = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        events = get_variable_star_events(self.test_location, event_type="minimum")

        self.assertIsInstance(events, list)
        # All events should be minimum type
        for event in events:
            self.assertEqual(event.event_type, "minimum")

    @patch("celestron_nexstar.api.astronomy.variable_stars.datetime")
    def test_get_variable_star_events_months_ahead(self, mock_datetime):
        """Test get_variable_star_events with custom months_ahead"""
        mock_now = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        events = get_variable_star_events(self.test_location, months_ahead=1)

        self.assertIsInstance(events, list)
        # All events should be within 1 month
        end_date = mock_now + timedelta(days=30)
        for event in events:
            self.assertLessEqual(event.date, end_date)

    @patch("celestron_nexstar.api.astronomy.variable_stars.datetime")
    def test_get_variable_star_events_sorted_by_date(self, mock_datetime):
        """Test that events are sorted by date"""
        mock_now = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        events = get_variable_star_events(self.test_location)

        # Should be sorted by date
        if len(events) > 1:
            for i in range(len(events) - 1):
                self.assertLessEqual(events[i].date, events[i + 1].date)

    @patch("celestron_nexstar.api.astronomy.variable_stars.datetime")
    def test_get_variable_star_events_contains_star_info(self, mock_datetime):
        """Test that events contain star information"""
        mock_now = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        events = get_variable_star_events(self.test_location)

        self.assertGreater(len(events), 0)
        for event in events:
            self.assertIsInstance(event.star, VariableStar)
            self.assertIsInstance(event.event_type, str)
            self.assertIn(event.event_type, ["minimum", "maximum"])
            self.assertIsInstance(event.magnitude, float)
            self.assertIsInstance(event.is_visible, bool)
            self.assertIsInstance(event.notes, str)

    @patch("celestron_nexstar.api.astronomy.variable_stars.datetime")
    def test_get_variable_star_events_magnitude_correct(self, mock_datetime):
        """Test that event magnitude matches star magnitude for event type"""
        mock_now = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        events = get_variable_star_events(self.test_location)

        for event in events:
            if event.event_type == "minimum":
                self.assertEqual(event.magnitude, event.star.magnitude_min)
            elif event.event_type == "maximum":
                self.assertEqual(event.magnitude, event.star.magnitude_max)


if __name__ == "__main__":
    unittest.main()

"""
Unit tests for space_events.py

Tests space event calendar and viewing location calculations.
"""

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from celestron_nexstar.api.events.space_events import (
    SpaceEvent,
    SpaceEventType,
    ViewingRequirement,
    find_best_viewing_location,
    get_upcoming_events,
    is_event_visible_from_location,
    populate_space_events_database,
)
from celestron_nexstar.api.location.observer import ObserverLocation


class TestSpaceEventType(unittest.TestCase):
    """Test suite for SpaceEventType enum"""

    def test_enum_values(self):
        """Test SpaceEventType enum values"""
        self.assertEqual(SpaceEventType.METEOR_SHOWER, "meteor_shower")
        self.assertEqual(SpaceEventType.PLANETARY_OPPOSITION, "planetary_opposition")
        self.assertEqual(SpaceEventType.SOLAR_ECLIPSE, "solar_eclipse")
        self.assertEqual(SpaceEventType.LUNAR_ECLIPSE, "lunar_eclipse")


class TestViewingRequirement(unittest.TestCase):
    """Test suite for ViewingRequirement dataclass"""

    def test_creation(self):
        """Test creating a ViewingRequirement"""
        req = ViewingRequirement(
            min_latitude=-90.0,
            max_latitude=90.0,
            dark_sky_required=True,
            min_bortle_class=3,
            equipment_needed="naked_eye",
            notes="Test requirement",
        )
        self.assertEqual(req.min_latitude, -90.0)
        self.assertEqual(req.max_latitude, 90.0)
        self.assertTrue(req.dark_sky_required)
        self.assertEqual(req.min_bortle_class, 3)
        self.assertEqual(req.equipment_needed, "naked_eye")
        self.assertEqual(req.notes, "Test requirement")


class TestSpaceEvent(unittest.TestCase):
    """Test suite for SpaceEvent dataclass"""

    def test_creation(self):
        """Test creating a SpaceEvent"""
        req = ViewingRequirement(dark_sky_required=True)
        event = SpaceEvent(
            name="Test Event",
            event_type=SpaceEventType.METEOR_SHOWER,
            date=datetime(2024, 6, 15, 20, 0, tzinfo=UTC),
            description="A test event",
            viewing_requirements=req,
            source="Test Source",
            url="https://example.com",
        )
        self.assertEqual(event.name, "Test Event")
        self.assertEqual(event.event_type, SpaceEventType.METEOR_SHOWER)
        self.assertEqual(event.description, "A test event")
        self.assertEqual(event.viewing_requirements, req)
        self.assertEqual(event.source, "Test Source")
        self.assertEqual(event.url, "https://example.com")


class TestIsEventVisibleFromLocation(unittest.TestCase):
    """Test suite for is_event_visible_from_location function"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_location = ObserverLocation(latitude=40.0, longitude=-100.0, name="Test Location")

    def test_visible_no_restrictions(self):
        """Test event visible when no restrictions"""
        req = ViewingRequirement()
        event = SpaceEvent(
            name="Test",
            event_type=SpaceEventType.METEOR_SHOWER,
            date=datetime.now(UTC),
            description="Test",
            viewing_requirements=req,
        )

        result = is_event_visible_from_location(event, self.test_location)
        self.assertTrue(result)

    def test_visible_within_latitude_bounds(self):
        """Test event visible when within latitude bounds"""
        req = ViewingRequirement(min_latitude=30.0, max_latitude=50.0)
        event = SpaceEvent(
            name="Test",
            event_type=SpaceEventType.METEOR_SHOWER,
            date=datetime.now(UTC),
            description="Test",
            viewing_requirements=req,
        )

        result = is_event_visible_from_location(event, self.test_location)
        self.assertTrue(result)

    def test_not_visible_below_min_latitude(self):
        """Test event not visible when below min latitude"""
        req = ViewingRequirement(min_latitude=50.0)
        event = SpaceEvent(
            name="Test",
            event_type=SpaceEventType.METEOR_SHOWER,
            date=datetime.now(UTC),
            description="Test",
            viewing_requirements=req,
        )

        result = is_event_visible_from_location(event, self.test_location)
        self.assertFalse(result)

    def test_not_visible_above_max_latitude(self):
        """Test event not visible when above max latitude"""
        req = ViewingRequirement(max_latitude=30.0)
        event = SpaceEvent(
            name="Test",
            event_type=SpaceEventType.METEOR_SHOWER,
            date=datetime.now(UTC),
            description="Test",
            viewing_requirements=req,
        )

        result = is_event_visible_from_location(event, self.test_location)
        self.assertFalse(result)

    def test_visible_within_longitude_bounds(self):
        """Test event visible when within longitude bounds"""
        req = ViewingRequirement(min_longitude=-110.0, max_longitude=-90.0)
        event = SpaceEvent(
            name="Test",
            event_type=SpaceEventType.METEOR_SHOWER,
            date=datetime.now(UTC),
            description="Test",
            viewing_requirements=req,
        )

        result = is_event_visible_from_location(event, self.test_location)
        self.assertTrue(result)

    def test_not_visible_outside_longitude_bounds(self):
        """Test event not visible when outside longitude bounds"""
        req = ViewingRequirement(min_longitude=-90.0, max_longitude=-80.0)
        event = SpaceEvent(
            name="Test",
            event_type=SpaceEventType.METEOR_SHOWER,
            date=datetime.now(UTC),
            description="Test",
            viewing_requirements=req,
        )

        result = is_event_visible_from_location(event, self.test_location)
        self.assertFalse(result)


class TestGetUpcomingEvents(unittest.TestCase):
    """Test suite for get_upcoming_events function"""

    def setUp(self):
        """Set up test fixtures"""
        self.start_date = datetime(2024, 6, 1, tzinfo=UTC)
        self.end_date = datetime(2024, 12, 31, tzinfo=UTC)

    @patch("celestron_nexstar.api.events.space_events.asyncio.run")
    def test_get_upcoming_events_with_database(self, mock_asyncio_run):
        """Test get_upcoming_events with database data"""
        # Mock database event
        mock_event_model = MagicMock()
        mock_event_model.name = "Test Event"
        mock_event_model.event_type = "meteor_shower"
        mock_event_model.date = datetime(2024, 7, 15, tzinfo=UTC)
        mock_event_model.description = "Test description"
        mock_event_model.min_latitude = None
        mock_event_model.max_latitude = None
        mock_event_model.min_longitude = None
        mock_event_model.max_longitude = None
        mock_event_model.dark_sky_required = False
        mock_event_model.min_bortle_class = None
        mock_event_model.equipment_needed = None
        mock_event_model.viewing_notes = None
        mock_event_model.source = "Test Source"
        mock_event_model.url = None

        mock_asyncio_run.return_value = [mock_event_model]

        result = get_upcoming_events(self.start_date, self.end_date)

        self.assertIsInstance(result, list)
        if result:  # If database has data
            self.assertIsInstance(result[0], SpaceEvent)
            self.assertEqual(result[0].name, "Test Event")

    @patch("celestron_nexstar.api.events.space_events.asyncio.run")
    def test_get_upcoming_events_filtered_by_type(self, mock_asyncio_run):
        """Test get_upcoming_events filtered by event type"""
        mock_event_model = MagicMock()
        mock_event_model.name = "Meteor Shower"
        mock_event_model.event_type = "meteor_shower"
        mock_event_model.date = datetime(2024, 7, 15, tzinfo=UTC)
        mock_event_model.description = "Test"
        mock_event_model.min_latitude = None
        mock_event_model.max_latitude = None
        mock_event_model.min_longitude = None
        mock_event_model.max_longitude = None
        mock_event_model.dark_sky_required = False
        mock_event_model.min_bortle_class = None
        mock_event_model.equipment_needed = None
        mock_event_model.viewing_notes = None
        mock_event_model.source = "Test"
        mock_event_model.url = None

        mock_asyncio_run.return_value = [mock_event_model]

        result = get_upcoming_events(
            self.start_date, self.end_date, event_types=[SpaceEventType.METEOR_SHOWER]
        )

        self.assertIsInstance(result, list)
        if result:
            for event in result:
                self.assertEqual(event.event_type, SpaceEventType.METEOR_SHOWER)


class TestFindBestViewingLocation(unittest.TestCase):
    """Test suite for find_best_viewing_location function"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_location = ObserverLocation(latitude=40.0, longitude=-100.0, name="Test Location")

    def test_not_visible_from_location(self):
        """Test when event is not visible from current location"""
        req = ViewingRequirement(min_latitude=50.0)  # Above current location
        event = SpaceEvent(
            name="Test",
            event_type=SpaceEventType.METEOR_SHOWER,
            date=datetime.now(UTC),
            description="Test",
            viewing_requirements=req,
        )

        location, message = find_best_viewing_location(event, self.test_location)

        self.assertIsNone(location)
        self.assertIn("not visible", message.lower())

    def test_good_location_no_dark_sky_required(self):
        """Test when current location is good and no dark sky required"""
        req = ViewingRequirement(dark_sky_required=False)
        event = SpaceEvent(
            name="Test",
            event_type=SpaceEventType.METEOR_SHOWER,
            date=datetime.now(UTC),
            description="Test",
            viewing_requirements=req,
        )

        location, message = find_best_viewing_location(event, self.test_location)

        self.assertIsNone(location)
        self.assertIn("good viewing", message.lower())

    @patch("celestron_nexstar.api.events.space_events.asyncio.run")
    def test_dark_sky_required_meets_requirements(self, mock_asyncio_run):
        """Test when dark sky is required and current location meets requirements"""
        from celestron_nexstar.api.location.light_pollution import BortleClass, LightPollutionData

        req = ViewingRequirement(dark_sky_required=True, min_bortle_class=4)
        event = SpaceEvent(
            name="Test",
            event_type=SpaceEventType.METEOR_SHOWER,
            date=datetime.now(UTC),
            description="Test",
            viewing_requirements=req,
        )

        # Mock light pollution data - current location is Bortle 3 (better than required 4)
        # Since 3 <= 4, it should return "good viewing"
        mock_light_data = LightPollutionData(
            bortle_class=BortleClass.CLASS_3,
            sqm_value=21.5,
            naked_eye_limiting_magnitude=6.5,
            milky_way_visible=True,
            airglow_visible=True,
            zodiacal_light_visible=True,
            description="Good",
            recommendations="Good for observing",
        )
        mock_asyncio_run.return_value = mock_light_data

        location, message = find_best_viewing_location(event, self.test_location)

        self.assertIsNone(location)
        self.assertIn("good viewing", message.lower())


class TestPopulateSpaceEventsDatabase(unittest.TestCase):
    """Test suite for populate_space_events_database function"""

    @patch("celestron_nexstar.api.events.space_events.asyncio.run")
    def test_populate_space_events_database(self, mock_asyncio_run):
        """Test populate_space_events_database"""
        mock_session = MagicMock()
        mock_asyncio_run.return_value = None

        populate_space_events_database(mock_session)

        # Should call asyncio.run with the seed function
        mock_asyncio_run.assert_called_once()


if __name__ == "__main__":
    unittest.main()

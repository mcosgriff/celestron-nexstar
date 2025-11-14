"""
Unit tests for zodiacal_light.py

Tests zodiacal light and gegenschein viewing window calculations.
"""

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from celestron_nexstar.api.astronomy.zodiacal_light import (
    ZodiacalLightWindow,
    get_gegenschein_windows,
    get_zodiacal_light_windows,
)
from celestron_nexstar.api.location.observer import ObserverLocation


class TestZodiacalLightWindow(unittest.TestCase):
    """Test suite for ZodiacalLightWindow dataclass"""

    def test_creation(self):
        """Test creating a ZodiacalLightWindow"""
        window_date = datetime(2024, 6, 15, tzinfo=UTC)
        start_time = datetime(2024, 6, 15, 20, 0, tzinfo=UTC)
        end_time = datetime(2024, 6, 15, 21, 0, tzinfo=UTC)
        window = ZodiacalLightWindow(
            date=window_date,
            window_type="evening",
            start_time=start_time,
            end_time=end_time,
            sun_altitude_start=-12.0,
            sun_altitude_end=-18.0,
            viewing_quality="excellent",
            notes="Test window",
        )
        self.assertEqual(window.date, window_date)
        self.assertEqual(window.window_type, "evening")
        self.assertEqual(window.start_time, start_time)
        self.assertEqual(window.end_time, end_time)
        self.assertEqual(window.sun_altitude_start, -12.0)
        self.assertEqual(window.sun_altitude_end, -18.0)
        self.assertEqual(window.viewing_quality, "excellent")
        self.assertEqual(window.notes, "Test window")


class TestGetZodiacalLightWindows(unittest.TestCase):
    """Test suite for get_zodiacal_light_windows function"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_location = ObserverLocation(latitude=40.0, longitude=-100.0, name="Test Location")

    @patch("celestron_nexstar.api.astronomy.zodiacal_light.get_sun_info")
    @patch("celestron_nexstar.api.astronomy.zodiacal_light.datetime")
    def test_get_zodiacal_light_windows_default(self, mock_datetime, mock_get_sun_info):
        """Test get_zodiacal_light_windows with default parameters"""
        # Mock current time
        mock_now = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        # Mock sun info
        mock_sun_info = MagicMock()
        mock_sun_info.sunset_time = datetime(2024, 6, 1, 20, 0, tzinfo=UTC)
        mock_sun_info.sunrise_time = datetime(2024, 6, 2, 6, 0, tzinfo=UTC)
        mock_get_sun_info.return_value = mock_sun_info

        windows = get_zodiacal_light_windows(self.test_location)

        self.assertIsInstance(windows, list)

    @patch("celestron_nexstar.api.astronomy.zodiacal_light.get_sun_info")
    @patch("celestron_nexstar.api.astronomy.zodiacal_light.datetime")
    def test_get_zodiacal_light_windows_spring_evening(self, mock_datetime, mock_get_sun_info):
        """Test zodiacal light windows for spring evening (optimal)"""
        mock_now = datetime(2024, 4, 1, 12, 0, tzinfo=UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        mock_sun_info = MagicMock()
        mock_sun_info.sunset_time = datetime(2024, 4, 1, 19, 0, tzinfo=UTC)
        mock_sun_info.sunrise_time = datetime(2024, 4, 2, 6, 30, tzinfo=UTC)
        mock_get_sun_info.return_value = mock_sun_info

        windows = get_zodiacal_light_windows(self.test_location, months_ahead=1)

        # Should have evening windows with excellent quality in spring
        evening_windows = [w for w in windows if w.window_type == "evening"]
        if evening_windows:
            for window in evening_windows:
                if 3 <= window.date.month <= 5:
                    self.assertEqual(window.viewing_quality, "excellent")

    @patch("celestron_nexstar.api.astronomy.zodiacal_light.get_sun_info")
    @patch("celestron_nexstar.api.astronomy.zodiacal_light.datetime")
    def test_get_zodiacal_light_windows_autumn_morning(self, mock_datetime, mock_get_sun_info):
        """Test zodiacal light windows for autumn morning (optimal)"""
        mock_now = datetime(2024, 10, 1, 12, 0, tzinfo=UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        mock_sun_info = MagicMock()
        mock_sun_info.sunset_time = datetime(2024, 10, 1, 18, 0, tzinfo=UTC)
        mock_sun_info.sunrise_time = datetime(2024, 10, 2, 7, 0, tzinfo=UTC)
        mock_get_sun_info.return_value = mock_sun_info

        windows = get_zodiacal_light_windows(self.test_location, months_ahead=1)

        # Should have morning windows with excellent quality in autumn
        morning_windows = [w for w in windows if w.window_type == "morning"]
        if morning_windows:
            for window in morning_windows:
                if 9 <= window.date.month <= 11:
                    self.assertEqual(window.viewing_quality, "excellent")

    @patch("celestron_nexstar.api.astronomy.zodiacal_light.get_sun_info")
    @patch("celestron_nexstar.api.astronomy.zodiacal_light.datetime")
    def test_get_zodiacal_light_windows_sorted(self, mock_datetime, mock_get_sun_info):
        """Test that windows are sorted by start time"""
        mock_now = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        mock_sun_info = MagicMock()
        mock_sun_info.sunset_time = datetime(2024, 6, 1, 20, 0, tzinfo=UTC)
        mock_sun_info.sunrise_time = datetime(2024, 6, 2, 6, 0, tzinfo=UTC)
        mock_get_sun_info.return_value = mock_sun_info

        windows = get_zodiacal_light_windows(self.test_location, months_ahead=1)

        # Should be sorted by start_time
        if len(windows) > 1:
            for i in range(len(windows) - 1):
                self.assertLessEqual(windows[i].start_time, windows[i + 1].start_time)

    @patch("celestron_nexstar.api.astronomy.zodiacal_light.get_sun_info")
    @patch("celestron_nexstar.api.astronomy.zodiacal_light.datetime")
    def test_get_zodiacal_light_windows_window_times(self, mock_datetime, mock_get_sun_info):
        """Test that window times are calculated correctly"""
        mock_now = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        sunset = datetime(2024, 6, 1, 20, 0, tzinfo=UTC)
        sunrise = datetime(2024, 6, 2, 6, 0, tzinfo=UTC)

        mock_sun_info = MagicMock()
        mock_sun_info.sunset_time = sunset
        mock_sun_info.sunrise_time = sunrise
        mock_get_sun_info.return_value = mock_sun_info

        windows = get_zodiacal_light_windows(self.test_location, months_ahead=1)

        # Check evening windows
        evening_windows = [w for w in windows if w.window_type == "evening"]
        for window in evening_windows:
            # Evening window should be 60-90 minutes after sunset
            expected_start = sunset + timedelta(minutes=60)
            expected_end = sunset + timedelta(minutes=90)
            self.assertEqual(window.start_time, expected_start)
            self.assertEqual(window.end_time, expected_end)

        # Check morning windows
        morning_windows = [w for w in windows if w.window_type == "morning"]
        for window in morning_windows:
            # Morning window should be 60-90 minutes before sunrise
            expected_start = sunrise - timedelta(minutes=90)
            expected_end = sunrise - timedelta(minutes=60)
            self.assertEqual(window.start_time, expected_start)
            self.assertEqual(window.end_time, expected_end)


class TestGetGegenscheinWindows(unittest.TestCase):
    """Test suite for get_gegenschein_windows function"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_location = ObserverLocation(latitude=40.0, longitude=-100.0, name="Test Location")

    @patch("celestron_nexstar.api.astronomy.zodiacal_light.datetime")
    def test_get_gegenschein_windows_default(self, mock_datetime):
        """Test get_gegenschein_windows with default parameters"""
        mock_now = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        windows = get_gegenschein_windows(self.test_location)

        self.assertIsInstance(windows, list)

    @patch("celestron_nexstar.api.astronomy.zodiacal_light.datetime")
    def test_get_gegenschein_windows_autumn_winter(self, mock_datetime):
        """Test gegenschein windows for autumn/winter (optimal)"""
        mock_now = datetime(2024, 10, 1, 12, 0, tzinfo=UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        windows = get_gegenschein_windows(self.test_location, months_ahead=3)

        # Should have windows with excellent quality in autumn/winter
        for window in windows:
            month = window.date.month
            if 9 <= month <= 11 or month >= 12 or month <= 2:
                self.assertEqual(window.viewing_quality, "excellent")

    @patch("celestron_nexstar.api.astronomy.zodiacal_light.datetime")
    def test_get_gegenschein_windows_sorted(self, mock_datetime):
        """Test that windows are sorted by start time"""
        mock_now = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        windows = get_gegenschein_windows(self.test_location, months_ahead=1)

        # Should be sorted by start_time
        if len(windows) > 1:
            for i in range(len(windows) - 1):
                self.assertLessEqual(windows[i].start_time, windows[i + 1].start_time)

    @patch("celestron_nexstar.api.astronomy.zodiacal_light.datetime")
    def test_get_gegenschein_windows_midnight_type(self, mock_datetime):
        """Test that gegenschein windows have midnight type"""
        mock_now = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        windows = get_gegenschein_windows(self.test_location, months_ahead=1)

        for window in windows:
            self.assertEqual(window.window_type, "midnight")

    @patch("celestron_nexstar.api.astronomy.zodiacal_light.datetime")
    def test_get_gegenschein_windows_time_range(self, mock_datetime):
        """Test that gegenschein windows are around midnight ± 2 hours"""
        mock_now = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        windows = get_gegenschein_windows(self.test_location, months_ahead=1)

        for window in windows:
            # Window should be around midnight
            midnight = window.date.replace(hour=0, minute=0, second=0, microsecond=0)
            expected_start = midnight - timedelta(hours=2)
            expected_end = midnight + timedelta(hours=2)
            self.assertEqual(window.start_time, expected_start)
            self.assertEqual(window.end_time, expected_end)

    @patch("celestron_nexstar.api.astronomy.zodiacal_light.datetime")
    def test_get_gegenschein_windows_sun_altitude(self, mock_datetime):
        """Test that gegenschein windows have correct sun altitude"""
        mock_now = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        windows = get_gegenschein_windows(self.test_location, months_ahead=1)

        for window in windows:
            # Gegenschein is at anti-sun point
            self.assertEqual(window.sun_altitude_start, -90.0)
            self.assertEqual(window.sun_altitude_end, -90.0)


if __name__ == "__main__":
    unittest.main()

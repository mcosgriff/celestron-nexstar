"""
Unit tests for tracking.py

Tests PositionTracker for background telescope position tracking.
"""

import time
import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from celestron_nexstar.api.telescope.tracking import PositionTracker


class TestPositionTracker(unittest.TestCase):
    """Test suite for PositionTracker class"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_get_port = MagicMock(return_value="/dev/ttyUSB0")
        self.tracker = PositionTracker(self.mock_get_port)

    def test_initialization(self):
        """Test tracker initialization"""
        self.assertFalse(self.tracker.enabled)
        self.assertFalse(self.tracker.running)
        self.assertIsNone(self.tracker.thread)
        self.assertEqual(self.tracker.update_interval, 2.0)
        self.assertEqual(self.tracker.last_position, {})
        self.assertIsNone(self.tracker.last_update)
        self.assertEqual(self.tracker.error_count, 0)
        self.assertTrue(self.tracker.history_enabled)
        self.assertFalse(self.tracker.is_slewing)
        self.assertEqual(self.tracker.alert_threshold, 5.0)
        self.assertFalse(self.tracker.expected_slew)
        self.assertFalse(self.tracker.show_chart)

    def test_set_interval_valid(self):
        """Test setting valid update interval"""
        result = self.tracker.set_interval(5.0)
        self.assertTrue(result)
        self.assertEqual(self.tracker.get_interval(), 5.0)

    def test_set_interval_invalid_too_low(self):
        """Test setting interval too low"""
        result = self.tracker.set_interval(0.1)
        self.assertFalse(result)
        self.assertEqual(self.tracker.get_interval(), 2.0)  # Should remain default

    def test_set_interval_invalid_too_high(self):
        """Test setting interval too high"""
        result = self.tracker.set_interval(50.0)
        self.assertFalse(result)
        self.assertEqual(self.tracker.get_interval(), 2.0)  # Should remain default

    def test_get_interval(self):
        """Test getting update interval"""
        self.tracker.update_interval = 3.0
        self.assertEqual(self.tracker.get_interval(), 3.0)

    def test_get_history_empty(self):
        """Test getting history when empty"""
        history = self.tracker.get_history()
        self.assertIsInstance(history, list)
        self.assertEqual(len(history), 0)

    def test_get_history_with_entries(self):
        """Test getting history with entries"""
        # Add some mock history
        with self.tracker.lock:
            self.tracker.history.append(
                {
                    "timestamp": datetime.now(UTC),
                    "ra_hours": 12.0,
                    "dec_degrees": 45.0,
                    "alt_degrees": 30.0,
                    "az_degrees": 180.0,
                }
            )

        history = self.tracker.get_history()
        self.assertEqual(len(history), 1)

    def test_get_history_last_n(self):
        """Test getting last N history entries"""
        # Add multiple entries
        with self.tracker.lock:
            for i in range(5):
                self.tracker.history.append(
                    {
                        "timestamp": datetime.now(UTC),
                        "ra_hours": 12.0 + i,
                        "dec_degrees": 45.0,
                        "alt_degrees": 30.0,
                        "az_degrees": 180.0,
                    }
                )

        history = self.tracker.get_history(last=3)
        self.assertEqual(len(history), 3)

    def test_get_history_since(self):
        """Test getting history since a timestamp"""
        now = datetime.now(UTC)
        with self.tracker.lock:
            # Add old entry
            self.tracker.history.append(
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "ra_hours": 12.0,
                    "dec_degrees": 45.0,
                    "alt_degrees": 30.0,
                    "az_degrees": 180.0,
                }
            )
            # Add recent entry
            self.tracker.history.append(
                {
                    "timestamp": now,
                    "ra_hours": 13.0,
                    "dec_degrees": 45.0,
                    "alt_degrees": 30.0,
                    "az_degrees": 180.0,
                }
            )

        history = self.tracker.get_history(since=datetime(2024, 6, 1, tzinfo=UTC))
        self.assertEqual(len(history), 1)

    def test_clear_history(self):
        """Test clearing history"""
        with self.tracker.lock:
            self.tracker.history.append({"timestamp": datetime.now(UTC), "ra_hours": 12.0, "dec_degrees": 45.0, "alt_degrees": 30.0, "az_degrees": 180.0})

        self.tracker.clear_history()
        self.assertEqual(len(self.tracker.get_history()), 0)

    def test_get_history_stats_empty(self):
        """Test getting stats with empty history"""
        stats = self.tracker.get_history_stats()
        self.assertEqual(stats["count"], 0)
        self.assertEqual(stats["duration_seconds"], 0)

    def test_get_history_stats_with_entries(self):
        """Test getting stats with history entries"""
        now = datetime.now(UTC)
        with self.tracker.lock:
            self.tracker.history.append(
                {
                    "timestamp": now,
                    "ra_hours": 12.0,
                    "dec_degrees": 45.0,
                    "alt_degrees": 30.0,
                    "az_degrees": 180.0,
                }
            )
            self.tracker.history.append(
                {
                    "timestamp": now,
                    "ra_hours": 12.1,
                    "dec_degrees": 45.1,
                    "alt_degrees": 30.1,
                    "az_degrees": 180.1,
                }
            )

        stats = self.tracker.get_history_stats()
        self.assertEqual(stats["count"], 2)
        self.assertIn("duration_seconds", stats)
        self.assertIn("total_ra_drift_arcsec", stats)
        self.assertIn("total_dec_drift_arcsec", stats)

    def test_calculate_velocity(self):
        """Test velocity calculation"""
        prev_pos = {"ra_hours": 12.0, "dec_degrees": 45.0, "alt_degrees": 30.0, "az_degrees": 180.0}
        curr_pos = {"ra_hours": 12.1, "dec_degrees": 45.1, "alt_degrees": 30.1, "az_degrees": 180.1}
        time_delta = 1.0  # 1 second

        velocity = self.tracker._calculate_velocity(prev_pos, curr_pos, time_delta)

        self.assertIn("ra", velocity)
        self.assertIn("dec", velocity)
        self.assertIn("alt", velocity)
        self.assertIn("az", velocity)
        self.assertIn("total", velocity)

    def test_calculate_velocity_zero_time(self):
        """Test velocity calculation with zero time delta"""
        prev_pos = {"ra_hours": 12.0, "dec_degrees": 45.0, "alt_degrees": 30.0, "az_degrees": 180.0}
        curr_pos = {"ra_hours": 12.1, "dec_degrees": 45.1, "alt_degrees": 30.1, "az_degrees": 180.1}

        velocity = self.tracker._calculate_velocity(prev_pos, curr_pos, 0.0)

        self.assertEqual(velocity["ra"], 0.0)
        self.assertEqual(velocity["dec"], 0.0)
        self.assertEqual(velocity["total"], 0.0)

    def test_get_velocity(self):
        """Test getting current velocity"""
        with self.tracker.lock:
            self.tracker.last_velocity = {"ra": 0.1, "dec": 0.05, "total": 0.15}

        velocity = self.tracker.get_velocity()
        self.assertIsInstance(velocity, dict)
        self.assertIn("ra", velocity)

    def test_get_velocity_empty(self):
        """Test getting velocity when none available"""
        velocity = self.tracker.get_velocity()
        self.assertIsInstance(velocity, dict)

    def test_set_alert_threshold_valid(self):
        """Test setting valid alert threshold"""
        result = self.tracker.set_alert_threshold(10.0)
        self.assertTrue(result)
        self.assertEqual(self.tracker.get_alert_threshold(), 10.0)

    def test_set_alert_threshold_invalid_too_low(self):
        """Test setting threshold too low"""
        result = self.tracker.set_alert_threshold(0.05)
        self.assertFalse(result)

    def test_set_alert_threshold_invalid_too_high(self):
        """Test setting threshold too high"""
        result = self.tracker.set_alert_threshold(25.0)
        self.assertFalse(result)

    def test_get_alert_threshold(self):
        """Test getting alert threshold"""
        self.tracker.alert_threshold = 7.5
        self.assertEqual(self.tracker.get_alert_threshold(), 7.5)

    def test_set_expected_slew(self):
        """Test setting expected slew flag"""
        self.tracker.set_expected_slew(True)
        self.assertTrue(self.tracker.expected_slew)
        self.tracker.set_expected_slew(False)
        self.assertFalse(self.tracker.expected_slew)

    def test_set_chart_enabled(self):
        """Test enabling/disabling chart"""
        self.tracker.set_chart_enabled(True)
        self.assertTrue(self.tracker.show_chart)
        self.tracker.set_chart_enabled(False)
        self.assertFalse(self.tracker.show_chart)

    def test_get_compass_indicator(self):
        """Test compass indicator generation"""
        self.assertEqual(self.tracker._get_compass_indicator(0), "N")
        self.assertEqual(self.tracker._get_compass_indicator(90), "E")
        self.assertEqual(self.tracker._get_compass_indicator(180), "S")
        self.assertEqual(self.tracker._get_compass_indicator(270), "W")
        self.assertEqual(self.tracker._get_compass_indicator(45), "NE")

    def test_get_altitude_bar(self):
        """Test altitude bar generation"""
        bar = self.tracker._get_altitude_bar(0)
        self.assertIsInstance(bar, str)
        self.assertEqual(len(bar), 3)

        bar = self.tracker._get_altitude_bar(90)
        self.assertIsInstance(bar, str)
        self.assertEqual(len(bar), 3)

        bar = self.tracker._get_altitude_bar(45)
        self.assertIsInstance(bar, str)
        self.assertEqual(len(bar), 3)

    def test_get_altitude_bar_clamped(self):
        """Test altitude bar with clamped values"""
        bar_negative = self.tracker._get_altitude_bar(-10)
        bar_zero = self.tracker._get_altitude_bar(0)
        self.assertEqual(bar_negative, bar_zero)  # Should be clamped to 0

        bar_high = self.tracker._get_altitude_bar(100)
        bar_max = self.tracker._get_altitude_bar(90)
        self.assertEqual(bar_high, bar_max)  # Should be clamped to 90

    def test_export_history_csv(self):
        """Test exporting history as CSV"""
        # Add some history
        with self.tracker.lock:
            self.tracker.history.append(
                {
                    "timestamp": datetime.now(UTC),
                    "ra_hours": 12.0,
                    "dec_degrees": 45.0,
                    "alt_degrees": 30.0,
                    "az_degrees": 180.0,
                }
            )

        import tempfile
        import os

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            temp_path = f.name

        try:
            success, message = self.tracker.export_history(temp_path, format="csv")
            self.assertTrue(success)
            self.assertIn("Exported", message)
            # Verify file exists
            self.assertTrue(os.path.exists(temp_path))
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_export_history_json(self):
        """Test exporting history as JSON"""
        # Add some history
        with self.tracker.lock:
            self.tracker.history.append(
                {
                    "timestamp": datetime.now(UTC),
                    "ra_hours": 12.0,
                    "dec_degrees": 45.0,
                    "alt_degrees": 30.0,
                    "az_degrees": 180.0,
                }
            )

        import tempfile
        import os

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            success, message = self.tracker.export_history(temp_path, format="json")
            self.assertTrue(success)
            self.assertIn("Exported", message)
            # Verify file exists
            self.assertTrue(os.path.exists(temp_path))
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_export_history_empty(self):
        """Test exporting empty history"""
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            temp_path = f.name

        try:
            success, message = self.tracker.export_history(temp_path, format="csv")
            self.assertFalse(success)
            self.assertIn("No history", message)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_export_history_invalid_format(self):
        """Test exporting with invalid format"""
        import tempfile
        import os

        with self.tracker.lock:
            self.tracker.history.append(
                {
                    "timestamp": datetime.now(UTC),
                    "ra_hours": 12.0,
                    "dec_degrees": 45.0,
                    "alt_degrees": 30.0,
                    "az_degrees": 180.0,
                }
            )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            temp_path = f.name

        try:
            success, message = self.tracker.export_history(temp_path, format="invalid")
            self.assertFalse(success)
            self.assertIn("Unknown format", message)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_get_status_text_no_data(self):
        """Test getting status text with no data"""
        text = self.tracker.get_status_text()
        self.assertEqual(text, "")

    @patch("celestron_nexstar.api.telescope.tracking.datetime")
    def test_get_status_text_with_data(self, mock_datetime):
        """Test getting status text with position data"""
        now = datetime.now(UTC)
        mock_datetime.now.return_value = now

        with self.tracker.lock:
            self.tracker.enabled = True
            self.tracker.last_position = {
                "ra_hours": 12.5,
                "dec_degrees": 45.0,
                "alt_degrees": 30.0,
                "az_degrees": 180.0,
            }
            self.tracker.last_update = now

        text = self.tracker.get_status_text()
        self.assertIsInstance(text, str)
        self.assertIn("RA:", text)
        self.assertIn("Dec:", text)
        self.assertIn("Alt:", text)
        self.assertIn("Az:", text)

    @patch("celestron_nexstar.api.telescope.tracking.datetime")
    def test_get_status_text_with_slew(self, mock_datetime):
        """Test getting status text with slewing"""
        now = datetime.now(UTC)
        mock_datetime.now.return_value = now

        with self.tracker.lock:
            self.tracker.enabled = True
            self.tracker.last_position = {
                "ra_hours": 12.5,
                "dec_degrees": 45.0,
                "alt_degrees": 30.0,
                "az_degrees": 180.0,
            }
            self.tracker.last_update = now
            self.tracker.is_slewing = True
            self.tracker.last_velocity = {"total": 2.5}

        text = self.tracker.get_status_text()
        self.assertIn("Slewing", text)

    @patch("celestron_nexstar.api.telescope.tracking.datetime")
    def test_get_status_text_with_chart(self, mock_datetime):
        """Test getting status text with chart enabled"""
        now = datetime.now(UTC)
        mock_datetime.now.return_value = now

        with self.tracker.lock:
            self.tracker.enabled = True
            self.tracker.last_position = {
                "ra_hours": 12.5,
                "dec_degrees": 45.0,
                "alt_degrees": 30.0,
                "az_degrees": 180.0,
            }
            self.tracker.last_update = now
            self.tracker.show_chart = True

        text = self.tracker.get_status_text()
        self.assertIsInstance(text, str)

    def test_start_stop(self):
        """Test starting and stopping tracker"""
        self.tracker.start()
        # Give thread a moment to start
        time.sleep(0.1)
        self.assertTrue(self.tracker.running)
        self.assertTrue(self.tracker.enabled)

        self.tracker.stop()
        # Give thread a moment to stop
        time.sleep(0.1)
        self.assertFalse(self.tracker.enabled)
        # Note: running may still be True briefly while thread exits

    def test_start_already_running(self):
        """Test starting when already running"""
        self.tracker.running = True
        self.tracker.start()  # Should not start again
        # Should not raise exception


if __name__ == "__main__":
    unittest.main()

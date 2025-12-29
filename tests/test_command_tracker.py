"""
Unit tests for CommandTracker module.

Tests command tracking, history management, filtering, and export functionality.
"""

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from celestron_nexstar.api.telescope.command_tracker import CommandRecord, CommandTracker


class TestCommandRecord(unittest.TestCase):
    """Test suite for CommandRecord dataclass."""

    def test_command_record_creation(self):
        """Test creating a command record."""
        record = CommandRecord(
            timestamp="2025-12-27T10:30:15.234",
            command="E",
            response="12345678,87654321",
            duration_ms=45.23,
            success=True,
            decoded="RA: 12h 34m 56s, Dec: +45° 12' 34\"",
        )

        self.assertEqual(record.command, "E")
        self.assertEqual(record.response, "12345678,87654321")
        self.assertAlmostEqual(record.duration_ms, 45.23)
        self.assertTrue(record.success)
        self.assertIsNone(record.error)

    def test_command_record_to_dict(self):
        """Test converting record to dictionary."""
        record = CommandRecord(
            timestamp="2025-12-27T10:30:15.234",
            command="E",
            response="12345678,87654321",
            duration_ms=45.23,
            success=True,
        )

        data = record.to_dict()

        self.assertIsInstance(data, dict)
        self.assertEqual(data["command"], "E")
        self.assertEqual(data["success"], True)

    def test_command_record_from_dict(self):
        """Test creating record from dictionary."""
        data = {
            "timestamp": "2025-12-27T10:30:15.234",
            "command": "E",
            "response": "12345678,87654321",
            "duration_ms": 45.23,
            "success": True,
            "error": None,
            "decoded": None,
        }

        record = CommandRecord.from_dict(data)

        self.assertEqual(record.command, "E")
        self.assertEqual(record.response, "12345678,87654321")
        self.assertAlmostEqual(record.duration_ms, 45.23)
        self.assertTrue(record.success)


class TestCommandTracker(unittest.TestCase):
    """Test suite for CommandTracker class."""

    def setUp(self):
        """Set up test fixtures."""
        self.tracker = CommandTracker(max_history=10)

    def test_initialization(self):
        """Test tracker initialization."""
        self.assertEqual(self.tracker.max_history, 10)
        self.assertEqual(len(self.tracker.history), 0)

    def test_start_command(self):
        """Test starting command tracking."""
        self.tracker.start_command("E")
        self.assertIn("E", self.tracker._pending_commands)

    def test_record_successful_command(self):
        """Test recording a successful command."""
        # Start tracking
        self.tracker.start_command("E")

        # Record completion
        self.tracker.record_command(
            command="E", response="12345678,87654321", success=True
        )

        # Verify
        self.assertEqual(len(self.tracker.history), 1)
        record = self.tracker.history[0]
        self.assertEqual(record.command, "E")
        self.assertEqual(record.response, "12345678,87654321")
        self.assertTrue(record.success)
        self.assertIsNotNone(record.duration_ms)

    def test_record_failed_command(self):
        """Test recording a failed command."""
        # Start tracking
        self.tracker.start_command("E")

        # Record failure
        self.tracker.record_command(
            command="E",
            response=None,
            success=False,
            error="Timeout waiting for response",
        )

        # Verify
        self.assertEqual(len(self.tracker.history), 1)
        record = self.tracker.history[0]
        self.assertEqual(record.command, "E")
        self.assertIsNone(record.response)
        self.assertFalse(record.success)
        self.assertEqual(record.error, "Timeout waiting for response")

    def test_circular_buffer_overflow(self):
        """Test that history maintains max_history limit."""
        # Add more commands than max_history
        for i in range(15):
            self.tracker.start_command(f"CMD{i}")
            self.tracker.record_command(
                command=f"CMD{i}", response=f"RESP{i}", success=True
            )

        # Verify only last 10 are kept
        self.assertEqual(len(self.tracker.history), 10)

        # Verify oldest commands were dropped
        commands = [r.command for r in self.tracker.history]
        self.assertIn("CMD14", commands)  # Most recent
        self.assertNotIn("CMD0", commands)  # Oldest, should be dropped

    def test_get_history_all(self):
        """Test getting all history."""
        # Add some commands
        for i in range(5):
            self.tracker.start_command(f"CMD{i}")
            self.tracker.record_command(
                command=f"CMD{i}", response=f"RESP{i}", success=True
            )

        # Get all history (most recent first)
        history = self.tracker.get_history()

        self.assertEqual(len(history), 5)
        # Should be in reverse order (most recent first)
        self.assertEqual(history[0].command, "CMD4")
        self.assertEqual(history[4].command, "CMD0")

    def test_get_history_filter_success(self):
        """Test filtering history by success."""
        # Add mix of successful and failed commands
        self.tracker.record_command(command="CMD1", response="RESP1", success=True)
        self.tracker.record_command(
            command="CMD2", response=None, success=False, error="Timeout"
        )
        self.tracker.record_command(command="CMD3", response="RESP3", success=True)

        # Get only successful
        history = self.tracker.get_history(filter_type="success")

        self.assertEqual(len(history), 2)
        self.assertTrue(all(r.success for r in history))

    def test_get_history_filter_failed(self):
        """Test filtering history by failure."""
        # Add mix of successful and failed commands
        self.tracker.record_command(command="CMD1", response="RESP1", success=True)
        self.tracker.record_command(
            command="CMD2", response=None, success=False, error="Timeout"
        )
        self.tracker.record_command(command="CMD3", response="RESP3", success=True)

        # Get only failed
        history = self.tracker.get_history(filter_type="failed")

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].command, "CMD2")
        self.assertFalse(history[0].success)

    def test_get_history_filter_by_command(self):
        """Test filtering history by specific command."""
        # Add various commands
        self.tracker.record_command(command="E", response="12345678,87654321", success=True)
        self.tracker.record_command(command="J", response="1", success=True)
        self.tracker.record_command(command="E", response="11111111,22222222", success=True)

        # Get only 'E' commands
        history = self.tracker.get_history(filter_type="command:E")

        self.assertEqual(len(history), 2)
        self.assertTrue(all(r.command == "E" for r in history))

    def test_get_history_with_limit(self):
        """Test limiting history results."""
        # Add 10 commands
        for i in range(10):
            self.tracker.record_command(
                command=f"CMD{i}", response=f"RESP{i}", success=True
            )

        # Get only 3 most recent
        history = self.tracker.get_history(limit=3)

        self.assertEqual(len(history), 3)
        # Should be most recent
        self.assertEqual(history[0].command, "CMD9")
        self.assertEqual(history[2].command, "CMD7")

    def test_get_statistics_empty(self):
        """Test statistics with empty history."""
        stats = self.tracker.get_statistics()

        self.assertEqual(stats["total_commands"], 0)
        self.assertEqual(stats["successful_commands"], 0)
        self.assertEqual(stats["failed_commands"], 0)
        self.assertEqual(stats["success_rate"], 0.0)
        self.assertEqual(stats["average_duration_ms"], 0.0)

    def test_get_statistics_with_data(self):
        """Test statistics calculation."""
        # Add successful commands with durations
        self.tracker.start_command("CMD1")
        self.tracker.record_command(command="CMD1", response="RESP1", success=True)

        self.tracker.start_command("CMD2")
        self.tracker.record_command(command="CMD2", response="RESP2", success=True)

        # Add failed command
        self.tracker.record_command(
            command="CMD3", response=None, success=False, error="Timeout"
        )

        stats = self.tracker.get_statistics()

        self.assertEqual(stats["total_commands"], 3)
        self.assertEqual(stats["successful_commands"], 2)
        self.assertEqual(stats["failed_commands"], 1)
        self.assertAlmostEqual(stats["success_rate"], 66.67, places=1)
        # Average duration should be >= 0 (may be 0 if test runs very fast)
        self.assertGreaterEqual(stats["average_duration_ms"], 0)

    def test_export_to_json(self):
        """Test exporting history to JSON file."""
        # Add some commands
        self.tracker.record_command(command="E", response="12345678,87654321", success=True)
        self.tracker.record_command(command="J", response="1", success=True)

        # Export to temp file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            filepath = Path(f.name)

        try:
            self.tracker.export_to_json(filepath)

            # Verify file exists and is valid JSON
            self.assertTrue(filepath.exists())

            with filepath.open("r") as f:
                data = json.load(f)

            # Verify structure
            self.assertIn("exported_at", data)
            self.assertIn("total_commands", data)
            self.assertIn("statistics", data)
            self.assertIn("commands", data)

            # Verify data
            self.assertEqual(data["total_commands"], 2)
            self.assertEqual(len(data["commands"]), 2)

        finally:
            # Cleanup
            if filepath.exists():
                filepath.unlink()

    def test_import_from_json(self):
        """Test importing history from JSON file."""
        # Create export data
        export_data = {
            "exported_at": datetime.now(UTC).isoformat(),
            "total_commands": 2,
            "statistics": {},
            "commands": [
                {
                    "timestamp": "2025-12-27T10:30:15.234",
                    "command": "E",
                    "response": "12345678,87654321",
                    "duration_ms": 45.23,
                    "success": True,
                    "error": None,
                    "decoded": None,
                },
                {
                    "timestamp": "2025-12-27T10:30:16.234",
                    "command": "J",
                    "response": "1",
                    "duration_ms": 30.5,
                    "success": True,
                    "error": None,
                    "decoded": None,
                },
            ],
        }

        # Write to temp file
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".json"
        ) as f:
            json.dump(export_data, f)
            filepath = Path(f.name)

        try:
            # Import
            imported_count = self.tracker.import_from_json(filepath)

            # Verify
            self.assertEqual(imported_count, 2)
            self.assertEqual(len(self.tracker.history), 2)

            # Check data
            history = list(self.tracker.history)
            self.assertEqual(history[0].command, "E")
            self.assertEqual(history[1].command, "J")

        finally:
            # Cleanup
            if filepath.exists():
                filepath.unlink()

    def test_clear_history(self):
        """Test clearing all history."""
        # Add some commands
        for i in range(5):
            self.tracker.record_command(
                command=f"CMD{i}", response=f"RESP{i}", success=True
            )

        # Clear
        self.tracker.clear_history()

        # Verify
        self.assertEqual(len(self.tracker.history), 0)
        self.assertEqual(len(self.tracker._pending_commands), 0)

    def test_get_recent_commands(self):
        """Test getting recent unique commands."""
        # Add commands (some duplicates)
        self.tracker.record_command(command="E", response="RESP1", success=True)
        self.tracker.record_command(command="J", response="RESP2", success=True)
        self.tracker.record_command(command="E", response="RESP3", success=True)
        self.tracker.record_command(command="K", response="RESP4", success=True)
        self.tracker.record_command(command="J", response="RESP5", success=True)

        # Get recent unique (count=3)
        recent = self.tracker.get_recent_commands(count=3)

        # Verify
        self.assertEqual(len(recent), 3)
        # Should be unique
        self.assertEqual(len(set(recent)), 3)
        # Should be most recent
        self.assertEqual(recent[0], "J")  # Most recent
        self.assertEqual(recent[1], "K")  # Second most recent unique
        self.assertEqual(recent[2], "E")  # Third most recent unique


if __name__ == "__main__":
    unittest.main()

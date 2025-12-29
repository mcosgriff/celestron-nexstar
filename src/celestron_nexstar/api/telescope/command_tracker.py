"""
Command Tracker for Telescope Protocol

Tracks all telescope commands for debugging, analysis, and replay functionality.
Thread-safe implementation using Qt signals for UI updates.
"""

from __future__ import annotations

import json
import logging
from collections import deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


@dataclass
class CommandRecord:
    """Record of a single telescope command and response."""

    timestamp: str  # ISO format timestamp
    command: str  # Command sent (without terminator)
    response: str | None  # Response received (without terminator), None if pending/failed
    duration_ms: float | None  # Duration in milliseconds, None if pending/failed
    success: bool  # True if command completed successfully
    error: str | None = None  # Error message if command failed
    decoded: str | None = None  # Human-readable decoded response (optional)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CommandRecord:
        """Create from dictionary."""
        return cls(**data)


class CommandTracker:
    """
    Tracks telescope commands for history and debugging.

    Thread-safe using deque (thread-safe for append/pop operations).
    Maintains a circular buffer of recent commands.
    """

    def __init__(self, max_history: int = 100) -> None:
        """
        Initialize command tracker.

        Args:
            max_history: Maximum number of commands to keep in history (circular buffer)
        """
        self.max_history = max_history
        self.history: deque[CommandRecord] = deque(maxlen=max_history)
        self._pending_commands: dict[str, datetime] = {}  # command -> start_time

    def start_command(self, command: str) -> None:
        """
        Record when a command is sent.

        Args:
            command: Command string (without terminator)
        """
        # Store start time for duration calculation
        self._pending_commands[command] = datetime.now(UTC)
        logger.debug(f"CommandTracker: Started tracking command: {command!r}")

    def record_command(
        self,
        command: str,
        response: str | None = None,
        success: bool = True,
        error: str | None = None,
        decoded: str | None = None,
    ) -> None:
        """
        Record command completion.

        Args:
            command: Command string (without terminator)
            response: Response received (without terminator), None if failed
            success: True if command completed successfully
            error: Error message if command failed
            decoded: Human-readable decoded response (optional)
        """
        # Calculate duration
        duration_ms = None
        if command in self._pending_commands:
            start_time = self._pending_commands.pop(command)
            duration = (datetime.now(UTC) - start_time).total_seconds() * 1000
            duration_ms = round(duration, 2)

        # Create record
        record = CommandRecord(
            timestamp=datetime.now(UTC).isoformat(),
            command=command,
            response=response,
            duration_ms=duration_ms,
            success=success,
            error=error,
            decoded=decoded,
        )

        # Add to history (thread-safe append)
        self.history.append(record)

        logger.debug(f"CommandTracker: Recorded command: {command!r}, success={success}, duration={duration_ms}ms")

    def get_history(
        self,
        filter_type: str | None = None,
        limit: int | None = None,
    ) -> list[CommandRecord]:
        """
        Retrieve command history with optional filtering.

        Args:
            filter_type: Filter type - 'success', 'failed', 'command:<cmd>', or None for all
            limit: Maximum number of records to return (most recent first)

        Returns:
            List of command records (most recent first)
        """
        # Convert deque to list (most recent last) and reverse
        records = list(self.history)
        records.reverse()  # Most recent first

        # Apply filters
        if filter_type == "success":
            records = [r for r in records if r.success]
        elif filter_type == "failed":
            records = [r for r in records if not r.success]
        elif filter_type and filter_type.startswith("command:"):
            cmd_filter = filter_type.split(":", 1)[1]
            records = [r for r in records if r.command == cmd_filter]

        # Apply limit
        if limit is not None:
            records = records[:limit]

        return records

    def get_statistics(self) -> dict[str, Any]:
        """
        Get statistics about command history.

        Returns:
            Dictionary with statistics
        """
        if not self.history:
            return {
                "total_commands": 0,
                "successful_commands": 0,
                "failed_commands": 0,
                "success_rate": 0.0,
                "average_duration_ms": 0.0,
            }

        records = list(self.history)
        successful = [r for r in records if r.success]
        failed = [r for r in records if not r.success]

        # Calculate average duration (only for successful commands with duration)
        durations = [r.duration_ms for r in successful if r.duration_ms is not None]
        avg_duration = sum(durations) / len(durations) if durations else 0.0

        return {
            "total_commands": len(records),
            "successful_commands": len(successful),
            "failed_commands": len(failed),
            "success_rate": len(successful) / len(records) * 100 if records else 0.0,
            "average_duration_ms": round(avg_duration, 2),
        }

    def export_to_json(self, filepath: Path | str) -> None:
        """
        Export command history to JSON file.

        Args:
            filepath: Path to output JSON file

        Raises:
            IOError: If file cannot be written
        """
        filepath = Path(filepath)

        # Get all records (most recent first)
        records = self.get_history()

        # Build export data
        export_data = {
            "exported_at": datetime.now(UTC).isoformat(),
            "total_commands": len(records),
            "statistics": self.get_statistics(),
            "commands": [r.to_dict() for r in records],
        }

        # Write to file
        try:
            with filepath.open("w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2)
            logger.info(f"CommandTracker: Exported {len(records)} commands to {filepath}")
        except Exception as e:
            logger.error(f"CommandTracker: Failed to export to {filepath}: {e}")
            raise

    def import_from_json(self, filepath: Path | str) -> int:
        """
        Import command history from JSON file.

        Args:
            filepath: Path to input JSON file

        Returns:
            Number of commands imported

        Raises:
            IOError: If file cannot be read
            ValueError: If file format is invalid
        """
        filepath = Path(filepath)

        try:
            with filepath.open("r", encoding="utf-8") as f:
                data = json.load(f)

            # Validate format
            if "commands" not in data:
                raise ValueError("Invalid export format: missing 'commands' key")

            # Import commands
            imported = 0
            for cmd_dict in data["commands"]:
                try:
                    record = CommandRecord.from_dict(cmd_dict)
                    self.history.append(record)
                    imported += 1
                except Exception as e:
                    logger.warning(f"CommandTracker: Failed to import record: {e}")
                    continue

            logger.info(f"CommandTracker: Imported {imported} commands from {filepath}")
            return imported

        except Exception as e:
            logger.error(f"CommandTracker: Failed to import from {filepath}: {e}")
            raise

    def clear_history(self) -> None:
        """Clear all command history."""
        self.history.clear()
        self._pending_commands.clear()
        logger.info("CommandTracker: Cleared command history")

    def get_recent_commands(self, count: int = 10) -> list[str]:
        """
        Get list of recent unique commands (for autocomplete/suggestions).

        Args:
            count: Maximum number of unique commands to return

        Returns:
            List of unique command strings (most recent first)
        """
        seen = set()
        recent = []

        # Iterate in reverse (most recent first)
        for record in reversed(self.history):
            if record.command not in seen:
                seen.add(record.command)
                recent.append(record.command)
                if len(recent) >= count:
                    break

        return recent

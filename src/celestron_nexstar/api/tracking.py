"""
Position Tracker for Background Telescope Tracking

This module provides the PositionTracker class for monitoring telescope position
in a background thread with features including:
- Configurable update intervals
- Position history logging
- Slew speed tracking
- Collision detection alerts
- Position export (CSV/JSON)
- ASCII star chart visualization
"""

from __future__ import annotations

import csv
import json
import threading
import time
from collections import deque
from collections.abc import Callable
from datetime import datetime
from typing import Any


class PositionTracker:
    """Background thread for tracking telescope position."""

    def __init__(self, get_port_func: Callable[[], str | None]) -> None:
        """Initialize the position tracker.

        Args:
            get_port_func: Function to get the telescope port (returns str | None)
        """
        self.get_port = get_port_func
        self.enabled = False
        self.running = False
        self.thread: threading.Thread | None = None
        self.lock = threading.Lock()
        self.update_interval = 2.0  # seconds
        self.last_position: dict[str, Any] = {}
        self.last_update: datetime | None = None
        self.error_count = 0
        # Position history using circular buffer
        self.history: deque[dict[str, Any]] = deque(maxlen=1000)
        self.history_enabled = True
        # Slew speed tracking
        self.last_velocity: dict[str, float] = {}  # degrees/sec for alt, az; hours/sec for RA
        self.is_slewing = False
        # Collision detection
        self.alert_threshold = 5.0  # degrees/sec - unexpected movement threshold
        self.expected_slew = False  # Flag to indicate an expected slew is in progress
        self.last_alert: datetime | None = None  # Prevent alert spam
        # ASCII chart visualization
        self.show_chart = False  # Toggle for ASCII star chart in status bar

    def start(self) -> None:
        """Start background position tracking."""
        with self.lock:
            if self.running:
                return

            self.enabled = True
            self.running = True
            self.error_count = 0
            self.thread = threading.Thread(target=self._track_loop, daemon=True)
            self.thread.start()

    def stop(self) -> None:
        """Stop background position tracking."""
        with self.lock:
            self.enabled = False
            if self.thread:
                # Thread will exit on next iteration
                self.running = False

    def set_interval(self, seconds: float) -> bool:
        """Set the tracking update interval.

        Args:
            seconds: Update interval in seconds (0.5 to 30.0)

        Returns:
            True if interval was set, False if invalid
        """
        if not (0.5 <= seconds <= 30.0):
            return False

        with self.lock:
            self.update_interval = seconds
        return True

    def get_interval(self) -> float:
        """Get the current update interval."""
        with self.lock:
            return self.update_interval

    def get_history(self, last: int | None = None, since: datetime | None = None) -> list[dict[str, Any]]:
        """Get position history with optional filtering.

        Args:
            last: Return only the last N entries
            since: Return only entries since this timestamp

        Returns:
            List of position history entries
        """
        with self.lock:
            history_list = list(self.history)

        # Filter by timestamp if requested
        if since:
            history_list = [entry for entry in history_list if entry["timestamp"] >= since]

        # Limit to last N if requested
        if last:
            history_list = history_list[-last:]

        return history_list

    def clear_history(self) -> None:
        """Clear all position history."""
        with self.lock:
            self.history.clear()

    def get_history_stats(self) -> dict[str, Any]:
        """Get statistics about the position history.

        Returns:
            Dictionary with stats: count, duration, drift, etc.
        """
        with self.lock:
            history_list = list(self.history)

        if len(history_list) < 2:
            return {
                "count": len(history_list),
                "duration_seconds": 0,
                "total_ra_drift_arcsec": 0,
                "total_dec_drift_arcsec": 0,
            }

        first = history_list[0]
        last = history_list[-1]
        duration = (last["timestamp"] - first["timestamp"]).total_seconds()

        # Calculate drift in arcseconds
        ra_drift = abs(last["ra_hours"] - first["ra_hours"]) * 15 * 3600  # hours to arcsec
        dec_drift = abs(last["dec_degrees"] - first["dec_degrees"]) * 3600  # degrees to arcsec

        return {
            "count": len(history_list),
            "duration_seconds": duration,
            "first_timestamp": first["timestamp"],
            "last_timestamp": last["timestamp"],
            "total_ra_drift_arcsec": ra_drift,
            "total_dec_drift_arcsec": dec_drift,
        }

    def _calculate_velocity(
        self, prev_pos: dict[str, Any], curr_pos: dict[str, Any], time_delta: float
    ) -> dict[str, float]:
        """Calculate velocity between two positions.

        Args:
            prev_pos: Previous position dict
            curr_pos: Current position dict
            time_delta: Time elapsed in seconds

        Returns:
            Dictionary with velocity components in degrees/sec
        """
        if time_delta <= 0:
            return {"ra": 0.0, "dec": 0.0, "alt": 0.0, "az": 0.0, "total": 0.0}

        # Calculate rate of change
        ra_rate = (curr_pos["ra_hours"] - prev_pos["ra_hours"]) / time_delta  # hours/sec
        dec_rate = (curr_pos["dec_degrees"] - prev_pos["dec_degrees"]) / time_delta  # deg/sec
        alt_rate = (curr_pos["alt_degrees"] - prev_pos["alt_degrees"]) / time_delta  # deg/sec
        az_rate = (curr_pos["az_degrees"] - prev_pos["az_degrees"]) / time_delta  # deg/sec

        # Calculate total angular velocity using spherical geometry (approximate)
        # Convert RA to degrees for this calculation
        ra_deg_rate = ra_rate * 15  # Convert hours/sec to deg/sec
        total_rate = (ra_deg_rate**2 + dec_rate**2) ** 0.5  # degrees/sec

        return {
            "ra": ra_rate,  # hours/sec
            "dec": dec_rate,  # deg/sec
            "alt": alt_rate,  # deg/sec
            "az": az_rate,  # deg/sec
            "total": total_rate,  # deg/sec
        }

    def get_velocity(self) -> dict[str, float]:
        """Get current velocity (slew speed).

        Returns:
            Dictionary with velocity components
        """
        with self.lock:
            return self.last_velocity.copy() if self.last_velocity else {}

    def set_alert_threshold(self, threshold: float) -> bool:
        """Set the collision alert threshold.

        Args:
            threshold: Velocity threshold in degrees/sec (0.1 to 20.0)

        Returns:
            True if threshold was set, False if invalid
        """
        if not (0.1 <= threshold <= 20.0):
            return False

        with self.lock:
            self.alert_threshold = threshold
        return True

    def get_alert_threshold(self) -> float:
        """Get the current alert threshold."""
        with self.lock:
            return self.alert_threshold

    def set_expected_slew(self, expected: bool) -> None:
        """Set whether a slew is expected (to suppress collision alerts)."""
        with self.lock:
            self.expected_slew = expected

    def set_chart_enabled(self, enabled: bool) -> None:
        """Enable or disable ASCII star chart visualization."""
        with self.lock:
            self.show_chart = enabled

    def _get_compass_indicator(self, azimuth: float) -> str:
        """Get compass rose indicator for azimuth.

        Args:
            azimuth: Azimuth in degrees (0-360)

        Returns:
            Compass indicator string
        """
        # 16-point compass rose
        directions = [
            "N",
            "NNE",
            "NE",
            "ENE",
            "E",
            "ESE",
            "SE",
            "SSE",
            "S",
            "SSW",
            "SW",
            "WSW",
            "W",
            "WNW",
            "NW",
            "NNW",
        ]

        # Calculate index (0-15)
        index = int((azimuth + 11.25) / 22.5) % 16
        return directions[index]

    def _get_altitude_bar(self, altitude: float) -> str:
        """Get altitude bar graph.

        Args:
            altitude: Altitude in degrees (0-90)

        Returns:
            Bar graph string using block characters
        """
        # Clamp altitude to 0-90
        alt = max(0, min(90, altitude))

        # Use 8 levels of blocks
        blocks = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
        level = int((alt / 90) * 7)  # 0-7
        return blocks[level] * 3

    def export_history(self, filename: str, format: str = "csv") -> tuple[bool, str]:
        """Export position history to a file.

        Args:
            filename: Output file path
            format: Export format ('csv' or 'json')

        Returns:
            Tuple of (success, message)
        """
        with self.lock:
            history_list = list(self.history)

        if not history_list:
            return False, "No history to export"

        try:
            if format.lower() == "csv":
                with open(filename, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["timestamp", "ra_hours", "dec_degrees", "alt_degrees", "az_degrees"])
                    for entry in history_list:
                        writer.writerow(
                            [
                                entry["timestamp"].isoformat(),
                                entry["ra_hours"],
                                entry["dec_degrees"],
                                entry["alt_degrees"],
                                entry["az_degrees"],
                            ]
                        )
                return True, f"Exported {len(history_list)} entries to {filename}"

            elif format.lower() == "json":
                # Convert datetime objects to ISO format for JSON
                json_data = []
                for entry in history_list:
                    json_entry = entry.copy()
                    json_entry["timestamp"] = entry["timestamp"].isoformat()
                    json_data.append(json_entry)

                with open(filename, "w") as f:
                    json.dump(
                        {"export_time": datetime.now().isoformat(), "count": len(json_data), "positions": json_data},
                        f,
                        indent=2,
                    )
                return True, f"Exported {len(history_list)} entries to {filename}"

            else:
                return False, f"Unknown format: {format}. Use 'csv' or 'json'"

        except Exception as e:
            return False, f"Export failed: {e}"

    def _track_loop(self) -> None:
        """Background tracking loop."""
        while self.enabled:
            try:
                # Import here to avoid circular dependencies
                from .telescope import NexStarTelescope

                # Check if we have a connection
                port = self.get_port()
                if not port:
                    time.sleep(self.update_interval)
                    continue

                # Get current position
                try:
                    with NexStarTelescope(str(port)) as telescope:
                        ra_hours, dec_degrees = telescope.get_position_ra_dec()
                        alt_degrees, az_degrees = telescope.get_position_alt_az()

                        with self.lock:
                            now = datetime.now()
                            prev_position = self.last_position.copy()
                            prev_time = self.last_update

                            curr_position = {
                                "ra_hours": ra_hours,
                                "dec_degrees": dec_degrees,
                                "alt_degrees": alt_degrees,
                                "az_degrees": az_degrees,
                            }

                            self.last_position = curr_position
                            self.last_update = now
                            self.error_count = 0

                            # Calculate velocity if we have a previous position
                            if prev_position and prev_time:
                                time_delta = (now - prev_time).total_seconds()
                                self.last_velocity = self._calculate_velocity(prev_position, curr_position, time_delta)

                                # Detect if slewing (velocity > 0.1 deg/sec)
                                self.is_slewing = self.last_velocity.get("total", 0) > 0.1

                                # Check for unexpected movement (collision detection)
                                total_speed = self.last_velocity.get("total", 0)
                                if not self.expected_slew and total_speed > self.alert_threshold:
                                    # Alert only once every 5 seconds to prevent spam
                                    should_alert = True
                                    if self.last_alert:
                                        seconds_since_alert = (now - self.last_alert).total_seconds()
                                        should_alert = seconds_since_alert >= 5

                                    if should_alert:
                                        self.last_alert = now
                                        # Log alert in history with special marker
                                        if self.history_enabled:
                                            self.history.append(
                                                {
                                                    "timestamp": now,
                                                    "ra_hours": ra_hours,
                                                    "dec_degrees": dec_degrees,
                                                    "alt_degrees": alt_degrees,
                                                    "az_degrees": az_degrees,
                                                    "alert": "UNEXPECTED_MOVEMENT",
                                                    "speed": total_speed,
                                                }
                                            )

                            # Add to history if enabled
                            if self.history_enabled:
                                self.history.append(
                                    {
                                        "timestamp": now,
                                        "ra_hours": ra_hours,
                                        "dec_degrees": dec_degrees,
                                        "alt_degrees": alt_degrees,
                                        "az_degrees": az_degrees,
                                    }
                                )

                except Exception:
                    with self.lock:
                        self.error_count += 1
                        # Stop tracking after 3 consecutive errors
                        if self.error_count >= 3:
                            self.enabled = False
                            self.running = False

                time.sleep(self.update_interval)

            except Exception:
                # Fatal error in tracking loop
                with self.lock:
                    self.enabled = False
                    self.running = False
                break

    def get_status_text(self) -> str:
        """Get formatted status text for display."""
        with self.lock:
            if not self.enabled or not self.last_position:
                return ""

            ra = self.last_position.get("ra_hours", 0)
            dec = self.last_position.get("dec_degrees", 0)
            alt = self.last_position.get("alt_degrees", 0)
            az = self.last_position.get("az_degrees", 0)

            # Format RA as hours:minutes:seconds
            ra_h = int(ra)
            ra_m = int((ra - ra_h) * 60)
            ra_s = int(((ra - ra_h) * 60 - ra_m) * 60)

            # Format Dec as degrees:arcminutes:arcseconds
            dec_sign = "+" if dec >= 0 else "-"
            dec_abs = abs(dec)
            dec_d = int(dec_abs)
            dec_m = int((dec_abs - dec_d) * 60)
            dec_s = int(((dec_abs - dec_d) * 60 - dec_m) * 60)

            age = ""
            if self.last_update:
                seconds_ago = (datetime.now() - self.last_update).total_seconds()
                age = " [live]" if seconds_ago < 5 else f" [{int(seconds_ago)}s ago]"

            # Add slew speed indicator if moving
            slew_info = ""
            if self.is_slewing and self.last_velocity:
                speed = self.last_velocity.get("total", 0)

                # Check if this is unexpected movement
                if not self.expected_slew and speed > self.alert_threshold:
                    slew_info = f"  [⚠ ALERT: {speed:.2f}°/s]"
                else:
                    slew_info = f"  [Slewing: {speed:.2f}°/s]"

            # Add ASCII chart visualization if enabled
            chart_info = ""
            if self.show_chart:
                compass = self._get_compass_indicator(az)
                alt_bar = self._get_altitude_bar(alt)
                chart_info = f"  [{compass} {alt_bar}]"

            return (
                f"RA: {ra_h:02d}h{ra_m:02d}m{ra_s:02d}s  "
                f"Dec: {dec_sign}{dec_d:02d}°{dec_m:02d}'{dec_s:02d}\"  "
                f"Alt: {alt:.1f}°  Az: {az:.1f}°{age}{chart_info}{slew_info}"
            )


"""
Tracking History Graph Dialog

Real-time graph of telescope position with tracking accuracy visualization and export.
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


try:
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas  # type: ignore[import-not-found]
    from matplotlib.figure import Figure  # type: ignore[import-not-found]

    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    FigureCanvas = None  # type: ignore[assignment,misc]
    Figure = None  # type: ignore[assignment,misc]

if TYPE_CHECKING:
    from celestron_nexstar import NexStarTelescope
    from celestron_nexstar.api.telescope.tracking import PositionTracker

logger = logging.getLogger(__name__)


class TrackingHistoryDialog(QDialog):
    """Dialog showing real-time tracking history graph."""

    def __init__(
        self,
        parent: QWidget | None = None,
        telescope: NexStarTelescope | None = None,
        position_tracker: PositionTracker | None = None,
    ) -> None:
        """Initialize the tracking history dialog."""
        super().__init__(parent)
        self.setWindowTitle("Tracking History Graph")
        self.setMinimumWidth(900)
        self.setMinimumHeight(600)

        if not MATPLOTLIB_AVAILABLE:
            QMessageBox.warning(
                parent,
                "Matplotlib Not Available",
                "Matplotlib is required for the tracking history graph. Please install it with: pip install matplotlib",
            )
            self.reject()
            return

        self.telescope = telescope
        self.position_tracker = position_tracker
        self._own_tracker = False  # Track if we created our own tracker

        # Create position tracker if not provided
        if not self.position_tracker and self.telescope:
            from celestron_nexstar.api.telescope.tracking import PositionTracker

            # Get port from telescope config if available
            def get_port() -> str | None:
                if self.telescope and hasattr(self.telescope, "config") and self.telescope.config:
                    return getattr(self.telescope.config, "port", None)
                return None

            self.position_tracker = PositionTracker(get_port)
            self._own_tracker = True
            # Start tracking if telescope is connected
            try:
                self.position_tracker.start()
            except Exception as e:
                logger.warning(f"Could not start position tracker: {e}")

        self.coordinate_system = "alt_az"  # "alt_az" or "ra_dec"
        self.update_interval_ms = 1000  # Update every second

        # Data storage
        self.time_data: list[datetime] = []
        self.ra_data: list[float] = []
        self.dec_data: list[float] = []
        self.alt_data: list[float] = []
        self.az_data: list[float] = []
        self.max_points = 1000  # Maximum points to display

        # Main layout
        main_layout = QVBoxLayout(self)

        # Controls toolbar
        controls_layout = QHBoxLayout()

        # Coordinate system selection
        controls_layout.addWidget(QLabel("Coordinate System:"))
        self.coord_combo = QComboBox()
        self.coord_combo.addItems(["Alt/Az (Horizontal)", "RA/Dec (Equatorial)"])
        self.coord_combo.currentIndexChanged.connect(self._on_coordinate_system_changed)
        controls_layout.addWidget(self.coord_combo)

        controls_layout.addSpacing(20)

        # Clear button
        self.clear_button = QPushButton("Clear History")
        self.clear_button.clicked.connect(self._on_clear_clicked)
        controls_layout.addWidget(self.clear_button)

        # Export button
        self.export_button = QPushButton("Export Data")
        self.export_button.clicked.connect(self._on_export_clicked)
        controls_layout.addWidget(self.export_button)

        controls_layout.addStretch()

        # Status label
        self.status_label = QLabel("Waiting for position data...")
        controls_layout.addWidget(self.status_label)

        main_layout.addLayout(controls_layout)

        # Create matplotlib figure
        self.figure = Figure(figsize=(10, 6))
        self.canvas = FigureCanvas(self.figure)
        main_layout.addWidget(self.canvas)

        # Create subplots
        if self.coordinate_system == "alt_az":
            self._create_alt_az_plots()
        else:
            self._create_ra_dec_plots()

        # Update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_graph)
        self.update_timer.start(self.update_interval_ms)

        # Initial update
        self._update_graph()

    def _create_alt_az_plots(self) -> None:
        """Create Alt/Az coordinate plots."""
        self.figure.clear()

        # Altitude plot
        self.ax_alt = self.figure.add_subplot(2, 1, 1)
        self.ax_alt.set_ylabel("Altitude (degrees)")
        self.ax_alt.set_title("Telescope Position Tracking - Altitude")
        self.ax_alt.grid(True, alpha=0.3)
        (self.line_alt,) = self.ax_alt.plot([], [], "b-", label="Altitude", linewidth=1.5)
        self.ax_alt.legend()
        self.ax_alt.set_ylim(-90, 90)

        # Azimuth plot
        self.ax_az = self.figure.add_subplot(2, 1, 2)
        self.ax_az.set_xlabel("Time")
        self.ax_az.set_ylabel("Azimuth (degrees)")
        self.ax_az.set_title("Telescope Position Tracking - Azimuth")
        self.ax_az.grid(True, alpha=0.3)
        (self.line_az,) = self.ax_az.plot([], [], "r-", label="Azimuth", linewidth=1.5)
        self.ax_az.legend()
        self.ax_az.set_ylim(0, 360)

        self.figure.tight_layout()
        self.canvas.draw()

    def _create_ra_dec_plots(self) -> None:
        """Create RA/Dec coordinate plots."""
        self.figure.clear()

        # RA plot
        self.ax_ra = self.figure.add_subplot(2, 1, 1)
        self.ax_ra.set_ylabel("RA (hours)")
        self.ax_ra.set_title("Telescope Position Tracking - Right Ascension")
        self.ax_ra.grid(True, alpha=0.3)
        (self.line_ra,) = self.ax_ra.plot([], [], "g-", label="RA", linewidth=1.5)
        self.ax_ra.legend()
        self.ax_ra.set_ylim(0, 24)

        # Dec plot
        self.ax_dec = self.figure.add_subplot(2, 1, 2)
        self.ax_dec.set_xlabel("Time")
        self.ax_dec.set_ylabel("Dec (degrees)")
        self.ax_dec.set_title("Telescope Position Tracking - Declination")
        self.ax_dec.grid(True, alpha=0.3)
        (self.line_dec,) = self.ax_dec.plot([], [], "m-", label="Dec", linewidth=1.5)
        self.ax_dec.legend()
        self.ax_dec.set_ylim(-90, 90)

        self.figure.tight_layout()
        self.canvas.draw()

    def _on_coordinate_system_changed(self, index: int) -> None:
        """Handle coordinate system change."""
        self.coordinate_system = "alt_az" if index == 0 else "ra_dec"
        if self.coordinate_system == "alt_az":
            self._create_alt_az_plots()
        else:
            self._create_ra_dec_plots()
        self._update_graph()

    def _update_graph(self) -> None:
        """Update the graph with latest position data."""
        if not self.position_tracker:
            self.status_label.setText("No position tracker available")
            return

        # Get position history
        try:
            history = self.position_tracker.get_history()
            if not history:
                self.status_label.setText("No position data available")
                return

            # Extract data
            time_data = []
            ra_data = []
            dec_data = []
            alt_data = []
            az_data = []

            for entry in history:
                timestamp = entry.get("timestamp")
                if isinstance(timestamp, str):
                    timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                elif not isinstance(timestamp, datetime):
                    continue

                time_data.append(timestamp)
                ra_data.append(entry.get("ra_hours", 0))
                dec_data.append(entry.get("dec_degrees", 0))
                alt_data.append(entry.get("alt_degrees", 0))
                az_data.append(entry.get("az_degrees", 0))

            # Limit to max_points
            if len(time_data) > self.max_points:
                time_data = time_data[-self.max_points :]
                ra_data = ra_data[-self.max_points :]
                dec_data = dec_data[-self.max_points :]
                alt_data = alt_data[-self.max_points :]
                az_data = az_data[-self.max_points :]

            # Update plots
            if self.coordinate_system == "alt_az":
                if time_data and alt_data and az_data:
                    self.line_alt.set_data(time_data, alt_data)
                    self.line_az.set_data(time_data, az_data)

                    # Update axis limits
                    self.ax_alt.relim()
                    self.ax_alt.autoscale_view()
                    self.ax_az.relim()
                    self.ax_az.autoscale_view()

                    # Format x-axis
                    from matplotlib import dates  # type: ignore[import-not-found]

                    self.ax_alt.xaxis.set_major_formatter(dates.DateFormatter("%H:%M:%S"))
                    self.ax_az.xaxis.set_major_formatter(dates.DateFormatter("%H:%M:%S"))

                    # Calculate tracking accuracy (drift)
                    if len(alt_data) > 1:
                        alt_drift = abs(alt_data[-1] - alt_data[0])
                        az_drift = abs(az_data[-1] - az_data[0])
                        self.status_label.setText(
                            f"Points: {len(time_data)} | Alt drift: {alt_drift:.3f}° | Az drift: {az_drift:.3f}°"
                        )
                    else:
                        self.status_label.setText(f"Points: {len(time_data)}")
            else:
                if time_data and ra_data and dec_data:
                    self.line_ra.set_data(time_data, ra_data)
                    self.line_dec.set_data(time_data, dec_data)

                    # Update axis limits
                    self.ax_ra.relim()
                    self.ax_ra.autoscale_view()
                    self.ax_dec.relim()
                    self.ax_dec.autoscale_view()

                    # Format x-axis
                    from matplotlib import dates  # type: ignore[import-not-found]

                    self.ax_ra.xaxis.set_major_formatter(dates.DateFormatter("%H:%M:%S"))
                    self.ax_dec.xaxis.set_major_formatter(dates.DateFormatter("%H:%M:%S"))

                    # Calculate tracking accuracy (drift)
                    if len(ra_data) > 1:
                        ra_drift = abs(ra_data[-1] - ra_data[0]) * 15  # Convert hours to degrees
                        dec_drift = abs(dec_data[-1] - dec_data[0])
                        self.status_label.setText(
                            f"Points: {len(time_data)} | RA drift: {ra_drift:.3f}° | Dec drift: {dec_drift:.3f}°"
                        )
                    else:
                        self.status_label.setText(f"Points: {len(time_data)}")

            # Redraw canvas
            self.canvas.draw()

        except Exception as e:
            logger.error(f"Error updating tracking graph: {e}", exc_info=True)
            self.status_label.setText(f"Error: {e}")

    def _on_clear_clicked(self) -> None:
        """Handle clear history button click."""
        if not self.position_tracker:
            return

        reply = QMessageBox.question(
            self,
            "Clear History",
            "Clear all tracking history?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.position_tracker.clear_history()
            self._update_graph()

    def _on_export_clicked(self) -> None:
        """Handle export button click."""
        if not self.position_tracker:
            QMessageBox.warning(self, "No Data", "No position tracker available.")
            return

        history = self.position_tracker.get_history()
        if not history:
            QMessageBox.warning(self, "No Data", "No tracking data to export.")
            return

        # Ask for file format
        filename, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Tracking Data",
            f"tracking_data_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.csv",
            "CSV Files (*.csv);;JSON Files (*.json);;All Files (*)",
        )

        if not filename:
            return

        try:
            if selected_filter.startswith("CSV") or filename.endswith(".csv"):
                self._export_csv(history, filename)
            else:
                self._export_json(history, filename)

            QMessageBox.information(self, "Export Complete", f"Tracking data exported to {filename}")
        except Exception as e:
            logger.error(f"Error exporting tracking data: {e}", exc_info=True)
            QMessageBox.critical(self, "Export Error", f"Failed to export data: {e}")

    def _export_csv(self, history: list[dict[str, Any]], filename: str) -> None:
        """Export tracking data to CSV."""
        with Path(filename).open("w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "timestamp",
                    "ra_hours",
                    "dec_degrees",
                    "alt_degrees",
                    "az_degrees",
                    "velocity_ra",
                    "velocity_dec",
                    "velocity_alt",
                    "velocity_az",
                ],
            )
            writer.writeheader()
            for entry in history:
                row = {
                    "timestamp": entry.get("timestamp", ""),
                    "ra_hours": entry.get("ra_hours", ""),
                    "dec_degrees": entry.get("dec_degrees", ""),
                    "alt_degrees": entry.get("alt_degrees", ""),
                    "az_degrees": entry.get("az_degrees", ""),
                    "velocity_ra": entry.get("velocity", {}).get("ra_hours_per_sec", ""),
                    "velocity_dec": entry.get("velocity", {}).get("dec_degrees_per_sec", ""),
                    "velocity_alt": entry.get("velocity", {}).get("alt_degrees_per_sec", ""),
                    "velocity_az": entry.get("velocity", {}).get("az_degrees_per_sec", ""),
                }
                writer.writerow(row)

    def _export_json(self, history: list[dict[str, Any]], filename: str) -> None:
        """Export tracking data to JSON."""
        export_data = {
            "export_time": datetime.now(UTC).isoformat(),
            "count": len(history),
            "positions": history,
        }
        with Path(filename).open("w") as f:
            json.dump(export_data, f, indent=2, default=str)

    def close_event(self, event: Any) -> None:
        """Handle dialog close event."""
        self.update_timer.stop()
        # Stop our own tracker if we created it
        if self._own_tracker and self.position_tracker:
            self.position_tracker.stop()
        super().closeEvent(event)

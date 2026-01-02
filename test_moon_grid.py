#!/usr/bin/env python3
"""
Test script for Moon Calendar Grid

Tests the calendar grid widget with sample data.
"""

import sys
from datetime import UTC, datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from PySide6.QtWidgets import QApplication, QHBoxLayout, QMainWindow, QSplitter, QWidget

from celestron_nexstar.api.location.observer import ObserverLocation
from celestron_nexstar.gui.widgets.moon_calendar_grid import (
    MoonCalendarGrid,
    PhaseTimelineWidget,
)
from celestron_nexstar.gui.workers.moon_workers import MoonDataWorker


class TestWindow(QMainWindow):
    """Test window for calendar grid."""

    def __init__(self):
        """Initialize test window."""
        super().__init__()

        self.setWindowTitle("Moon Calendar Grid Test")
        self.setGeometry(100, 100, 1200, 700)

        # Create central widget with splitter
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QHBoxLayout(central_widget)

        # Create splitter
        splitter = QSplitter()
        layout.addWidget(splitter)

        # Create calendar grid
        self.calendar_grid = MoonCalendarGrid()
        self.calendar_grid.cell_clicked.connect(self._on_cell_clicked)
        splitter.addWidget(self.calendar_grid)

        # Create phase timeline
        self.timeline = PhaseTimelineWidget()
        self.timeline.phase_clicked.connect(self._on_phase_clicked)
        self.timeline.load_more_requested.connect(self._on_load_more_requested)
        splitter.addWidget(self.timeline)

        # Set splitter sizes (40% calendar, 60% timeline)
        splitter.setSizes([400, 600])

        # Status bar
        self.statusBar().showMessage("Loading moon data...")

        # Load data
        self._load_data()

    def _load_data(self):
        """Load moon data for current month."""
        # Create sample observer location (Los Angeles)
        location = ObserverLocation(
            latitude=34.0522,
            longitude=-118.2437,
            elevation=285,
            name="Los Angeles",
        )

        # Current month
        now = datetime.now(UTC)
        year = now.year
        month = now.month

        print(f"Loading data for {year}-{month:02d}...")

        # Create worker
        self.worker = MoonDataWorker(year, month, location, months_ahead=6)
        self.worker.data_ready.connect(self._on_data_ready)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.start()

    def _on_data_ready(self, moon_data, phase_events):
        """Handle data ready."""
        print(f"Data loaded: {len(moon_data)} days, {len(phase_events)} events")

        # Get current month/year
        now = datetime.now(UTC)

        # Populate calendar grid
        self.calendar_grid.set_month_data(now.year, now.month, moon_data)

        # Populate timeline
        self.timeline.set_phase_events(phase_events)

        # Update status
        self.statusBar().showMessage(
            f"Loaded {len(moon_data)} days, {len(phase_events)} phase events"
        )

    def _on_error(self, error_msg):
        """Handle error."""
        print(f"Error: {error_msg}")
        self.statusBar().showMessage(f"Error: {error_msg}")

    def _on_cell_clicked(self, date):
        """Handle calendar cell click."""
        print(f"Cell clicked: {date.strftime('%Y-%m-%d')}")
        self.statusBar().showMessage(f"Selected: {date.strftime('%B %d, %Y')}")

    def _on_phase_clicked(self, date, phase):
        """Handle phase timeline click."""
        print(f"Phase clicked: {date.strftime('%Y-%m-%d')} - {phase}")
        self.statusBar().showMessage(f"Selected: {phase} on {date.strftime('%B %d, %Y')}")

    def _on_load_more_requested(self):
        """Handle load more request."""
        print("Load More button clicked - would load additional months")
        self.statusBar().showMessage("Load More feature - would extend timeline by 6 months")


def main():
    """Run test."""
    app = QApplication(sys.argv)

    window = TestWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

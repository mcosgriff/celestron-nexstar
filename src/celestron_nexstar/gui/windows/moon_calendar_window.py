"""
Moon Calendar Window

Non-modal window displaying monthly moon calendar with phase timeline.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from celestron_nexstar.api.core.utils import get_local_timezone
from celestron_nexstar.api.location.observer import get_observer_location
from celestron_nexstar.gui.widgets.moon_calendar_grid import (
    MoonCalendarGrid,
    PhaseTimelineWidget,
)
from celestron_nexstar.gui.workers.moon_workers import MoonDataWorker, MoonDayData, MoonPhaseEvent


if TYPE_CHECKING:
    from celestron_nexstar.api.location.observer import ObserverLocation


logger = logging.getLogger(__name__)


class MoonCalendarWindow(QMainWindow):
    """
    Non-modal window displaying moon calendar and phase timeline.

    Features:
    - Monthly calendar grid with moon phases
    - Phase timeline showing upcoming major phases
    - Traditional full moon names
    - Special event highlighting (supermoons, blue moons)
    - Month navigation
    - Integration with Moon Info Dialog
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the moon calendar window."""
        super().__init__(parent)

        # Window state
        self._moon_data_cache: dict[str, dict[str, MoonDayData]] = {}  # {year-month: {date: data}}
        self._phase_events_cache: dict[str, list[MoonPhaseEvent]] = {}  # {year-month: events}
        self._worker: MoonDataWorker | None = None
        self._progress_dialog: QProgressDialog | None = None
        self._location: ObserverLocation = get_observer_location()
        self._local_timezone = get_local_timezone(self._location.latitude, self._location.longitude)
        self._current_year = datetime.now(self._local_timezone).year
        self._current_month = datetime.now(self._local_timezone).month

        # Window setup
        self.setWindowTitle("Moon Calendar")
        self.setMinimumSize(1200, 700)
        self.resize(1200, 700)

        # Create UI
        self._create_ui()

        # Load current month
        self._load_month_data(self._current_year, self._current_month)

    def _create_ui(self) -> None:
        """Create the UI layout."""
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Top controls
        controls_layout = QHBoxLayout()

        # Navigation buttons
        self.prev_button = QPushButton("◀ Previous")
        self.prev_button.clicked.connect(self._on_previous_month)
        controls_layout.addWidget(self.prev_button)

        self.today_button = QPushButton("Today")
        self.today_button.clicked.connect(self._on_today)
        controls_layout.addWidget(self.today_button)

        self.next_button = QPushButton("Next ▶")
        self.next_button.clicked.connect(self._on_next_month)
        controls_layout.addWidget(self.next_button)

        controls_layout.addSpacing(20)

        # Month/Year label
        self.month_label = QLabel()
        font = self.month_label.font()
        font.setPointSize(14)
        font.setBold(True)
        self.month_label.setFont(font)
        controls_layout.addWidget(self.month_label)

        controls_layout.addSpacing(20)

        # Date picker
        date_label = QLabel("Jump to:")
        controls_layout.addWidget(date_label)

        self.date_picker = QDateEdit()
        self.date_picker.setCalendarPopup(True)
        self.date_picker.setDisplayFormat("MMMM yyyy")
        self.date_picker.setDate(datetime.now(self._local_timezone).date())
        self.date_picker.dateChanged.connect(self._on_date_picker_changed)
        controls_layout.addWidget(self.date_picker)

        controls_layout.addStretch()

        # Location label
        self.location_label = QLabel()
        self._update_location_label()
        controls_layout.addWidget(self.location_label)

        main_layout.addLayout(controls_layout)

        # Splitter with calendar and timeline
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Calendar grid (left pane)
        self.calendar_grid = MoonCalendarGrid()
        self.calendar_grid.cell_clicked.connect(self._on_cell_clicked)
        splitter.addWidget(self.calendar_grid)

        # Phase timeline (right pane)
        self.timeline = PhaseTimelineWidget()
        self.timeline.phase_clicked.connect(self._on_phase_clicked)
        self.timeline.load_more_requested.connect(self._on_load_more)
        splitter.addWidget(self.timeline)

        # Set splitter sizes (40% calendar, 60% timeline)
        splitter.setSizes([400, 600])

        main_layout.addWidget(splitter)

        # Update month label
        self._update_month_label()

        # Status bar
        self.statusBar().showMessage("Ready")

    def _update_location_label(self) -> None:
        """Update the location label."""
        if self._location.name:
            self.location_label.setText(f"📍 {self._location.name}")
        else:
            self.location_label.setText(
                f"📍 {abs(self._location.latitude):.2f}°{'N' if self._location.latitude >= 0 else 'S'}, "
                f"{abs(self._location.longitude):.2f}°{'E' if self._location.longitude >= 0 else 'W'}"
            )

    def _update_month_label(self) -> None:
        """Update the month/year label."""
        date = datetime(self._current_year, self._current_month, 1)
        self.month_label.setText(date.strftime("%B %Y"))

    @staticmethod
    def _get_cache_key(year: int, month: int) -> str:
        """Get cache key for year/month."""
        return f"{year}-{month:02d}"

    def _load_month_data(self, year: int, month: int) -> None:
        """
        Load moon data for a specified month.

        Args:
            year: Year to load
            month: Month to load (1-12)
        """
        cache_key = self._get_cache_key(year, month)

        # Check cache first
        if cache_key in self._moon_data_cache:
            logger.debug(f"Using cached data for {cache_key}")
            self._populate_ui(
                self._moon_data_cache[cache_key],
                self._phase_events_cache.get(cache_key, []),
            )
            self.statusBar().showMessage(f"Loaded {cache_key} from cache")
            return

        # Cancel existing worker
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait()

        # Create progress dialog
        self._progress_dialog = QProgressDialog(
            f"Loading moon data for {datetime(year, month, 1).strftime('%B %Y')}...",
            "Cancel",
            0,
            100,
            self,
        )
        self._progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress_dialog.setMinimumDuration(500)  # Show after 500ms
        self._progress_dialog.canceled.connect(self._on_loading_canceled)

        # Create and start worker
        self._worker = MoonDataWorker(year, month, self._location, months_ahead=6)
        self._worker.data_ready.connect(self._on_data_ready)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.progress_updated.connect(self._on_progress)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

        self.statusBar().showMessage(f"Loading {cache_key}...")

    def _populate_ui(self, moon_data: dict[str, MoonDayData], phase_events: list[MoonPhaseEvent]) -> None:
        """
        Populate UI with moon data.

        Args:
            moon_data: Dictionary of moon data by date
            phase_events: List of phase events
        """
        # Update calendar grid
        self.calendar_grid.set_month_data(self._current_year, self._current_month, moon_data, phase_events)

        # Update timeline (replace events)
        self.timeline.set_phase_events(phase_events, replace=True)

        # Update status
        self.statusBar().showMessage(f"Showing {len(moon_data)} days, {len(phase_events)} phase events")

    def _on_data_ready(self, moon_data: dict[str, MoonDayData], phase_events: list[MoonPhaseEvent]) -> None:
        """Handle worker data ready."""
        # Cache the data
        cache_key = self._get_cache_key(self._current_year, self._current_month)
        self._moon_data_cache[cache_key] = moon_data
        self._phase_events_cache[cache_key] = phase_events

        logger.debug(f"Cached {len(moon_data)} days, {len(phase_events)} events for {cache_key}")

        # Populate UI
        self._populate_ui(moon_data, phase_events)

        # Close progress dialog
        if self._progress_dialog:
            self._progress_dialog.close()
            self._progress_dialog = None

    def _on_error(self, error_msg: str) -> None:
        """Handle worker error."""
        logger.error(f"Error loading moon data: {error_msg}")

        # Close progress dialog
        if self._progress_dialog:
            self._progress_dialog.close()
            self._progress_dialog = None

        # Show error message
        QMessageBox.critical(self, "Error Loading Moon Data", f"Failed to load moon data:\n\n{error_msg}")

        self.statusBar().showMessage("Error loading data")

    def _on_progress(self, current: int, total: int) -> None:
        """Handle worker progress."""
        if self._progress_dialog:
            percent = int((current / total) * 100)
            self._progress_dialog.setValue(percent)

    def _on_worker_finished(self) -> None:
        """Handle worker finished."""
        if self._progress_dialog:
            self._progress_dialog.close()
            self._progress_dialog = None

    def _on_loading_canceled(self) -> None:
        """Handle loading canceled."""
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait()
        self.statusBar().showMessage("Loading canceled")

    def _on_previous_month(self) -> None:
        """Navigate to previous month."""
        if self._current_month == 1:
            self._current_year -= 1
            self._current_month = 12
        else:
            self._current_month -= 1

        self._update_month_label()
        self._load_month_data(self._current_year, self._current_month)

        # Update date picker without triggering signal
        self.date_picker.blockSignals(True)
        self.date_picker.setDate(datetime(self._current_year, self._current_month, 1).date())
        self.date_picker.blockSignals(False)

    def _on_next_month(self) -> None:
        """Navigate to next month."""
        if self._current_month == 12:
            self._current_year += 1
            self._current_month = 1
        else:
            self._current_month += 1

        self._update_month_label()
        self._load_month_data(self._current_year, self._current_month)

        # Update date picker without triggering signal
        self.date_picker.blockSignals(True)
        self.date_picker.setDate(
            datetime(self._current_year, self._current_month, 1, tzinfo=self._local_timezone).date()
        )
        self.date_picker.blockSignals(False)

    def _on_today(self) -> None:
        """Navigate to current month."""
        now = datetime.now(self._local_timezone)
        self._current_year = now.year
        self._current_month = now.month

        self._update_month_label()
        self._load_month_data(self._current_year, self._current_month)

        # Update date picker without triggering signal
        self.date_picker.blockSignals(True)
        self.date_picker.setDate(now.date())
        self.date_picker.blockSignals(False)

    def _on_date_picker_changed(self) -> None:
        """Handle date picker change."""
        date = self.date_picker.date()
        year = date.year()
        month = date.month()

        if year != self._current_year or month != self._current_month:
            self._current_year = year
            self._current_month = month

            self._update_month_label()
            self._load_month_data(self._current_year, self._current_month)

    def _on_cell_clicked(self, date: datetime) -> None:
        """
        Handle calendar cell click.

        Opens Moon Info Dialog for the selected date.

        Args:
            date: Date that was clicked
        """
        logger.debug(f"Cell clicked: {date.strftime('%Y-%m-%d')}")

        try:
            # Import here to avoid circular dependency
            from celestron_nexstar.gui.dialogs.moon_info_dialog import MoonInfoDialog

            # Open Moon Info Dialog with target date at noon (same as calendar calculations)
            date_at_noon = date.replace(hour=12, minute=0, second=0, microsecond=0)
            dialog = MoonInfoDialog(self, target_date=date_at_noon)
            dialog.exec()

        except Exception as e:
            logger.exception("Error opening Moon Info Dialog")
            QMessageBox.warning(
                self,
                "Error",
                f"Could not open Moon Info Dialog:\n\n{e}",
            )

    def _on_phase_clicked(self, date: datetime, phase_name: str) -> None:
        """
        Handle timeline phase click.

        Opens Moon Info Dialog for the selected date.

        Args:
            date: Date of the phase event
            phase_name: Name of the phase
        """
        logger.debug(f"Phase clicked: {date.strftime('%Y-%m-%d')} - {phase_name}")

        # Same as cell click - open Moon Info Dialog
        self._on_cell_clicked(date)

    def _on_load_more(self) -> None:
        """Handle load more request."""
        logger.debug("Load more requested - extending timeline")

        # Calculate next 6 months to load
        # This would ideally spawn a new worker to calculate additional months
        # For now, show a message
        self.statusBar().showMessage("Load More feature - would calculate additional 6 months of phase events")

        # TODO: Implement loading additional months
        # Would need to:
        # 1. Calculate end date of current timeline
        # 2. Spawn worker for next 6 months
        # 3. Append results to timeline (replace=False)

    def closeEvent(self, event) -> None:
        """Handle window close event."""
        # Cancel any running worker
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait()

        # Close progress dialog
        if self._progress_dialog:
            self._progress_dialog.close()

        super().closeEvent(event)

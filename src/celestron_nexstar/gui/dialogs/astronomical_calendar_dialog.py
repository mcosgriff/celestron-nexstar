"""
Astronomical Calendar Dialog

Shows a full month calendar with upcoming astronomical events including:
- Super Full Moons
- Meteor showers
- Eclipses (lunar and solar)
- Planetary events (oppositions, conjunctions, etc.)
- Moon phases
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QDate, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QMouseEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from celestron_nexstar.api.astronomy.solar_system import get_moon_info
from celestron_nexstar.api.core.enums import MoonPhase
from celestron_nexstar.api.location.observer import get_observer_location


if TYPE_CHECKING:
    from celestron_nexstar.api.location.observer import ObserverLocation


logger = logging.getLogger(__name__)


def _run_async_safe(coro: Coroutine[Any, Any, Any]) -> Any:
    """
    Run an async coroutine from a sync context, handling both cases:
    - If called from sync context: uses asyncio.run()
    - If called from async context: creates new event loop in thread

    Args:
        coro: The coroutine to run

    Returns:
        The result of the coroutine
    """
    try:
        # Check if we're in an async context
        asyncio.get_running_loop()
        # We're in an async context, need to use a thread with new event loop
        future: concurrent.futures.Future[Any] = concurrent.futures.Future()

        def run_in_thread() -> None:
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                result = new_loop.run_until_complete(coro)
                future.set_result(result)
                new_loop.close()
            except Exception as e:
                future.set_exception(e)

        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()
        return future.result()
    except RuntimeError:
        # No running loop, use asyncio.run()
        return asyncio.run(coro)


@dataclass
class CalendarEvent:
    """An astronomical event for the calendar."""

    date: datetime
    title: str
    description: str
    event_type: str  # "moon_phase", "meteor_shower", "eclipse", "planetary", "other"
    color: str  # Hex color for highlighting


class _ClickableDayCell(QWidget):
    """Clickable day cell widget for calendar."""

    def __init__(self, date: QDate, calendar_widget: CustomCalendarWidget) -> None:
        """Initialize clickable day cell."""
        super().__init__()
        self.date = date
        self.calendar_widget = calendar_widget

    def mouse_press_event(self, event: QMouseEvent) -> None:
        """Handle mouse press event."""
        self.calendar_widget._on_cell_clicked(event, self.date)

    def mouse_double_click_event(self, event: QMouseEvent) -> None:
        """Handle mouse double-click event."""
        self.calendar_widget._on_cell_double_clicked(event, self.date)


class CustomCalendarWidget(QWidget):
    """Custom calendar widget that displays events directly in day cells."""

    date_selected = Signal(QDate)  # Signal emitted when a date is clicked
    date_double_clicked = Signal(QDate, list)  # Signal emitted when a date is double-clicked (date, events)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the custom calendar widget."""
        super().__init__(parent)
        self.events_by_date: dict[str, list[CalendarEvent]] = {}
        self.current_date = QDate.currentDate()
        self.selected_date = QDate.currentDate()
        self._init_ui()

    def _is_dark_theme(self) -> bool:
        """Detect if the current theme is dark mode."""
        from PySide6.QtGui import QGuiApplication, QPalette

        app = QGuiApplication.instance()
        if app and isinstance(app, QGuiApplication):
            palette = app.palette()
            window_color = palette.color(QPalette.ColorRole.Window)
            brightness = window_color.lightness()
            return bool(brightness < 128)
        return False

    def _get_theme_colors(self) -> dict[str, str]:
        """Get theme-aware colors."""
        is_dark = self._is_dark_theme()
        if is_dark:
            return {
                "bg": "#1e1e1e",
                "bg_alt": "#2d2d2d",
                "text": "#ffffff",
                "text_dim": "#888888",
                "border": "#444444",
                "border_alt": "#555555",
                "selected_bg": "#1565C0",
                "selected_text": "#ffffff",
                "today": "#4CAF50",
            }
        else:
            return {
                "bg": "#ffffff",
                "bg_alt": "#f5f5f5",
                "text": "#000000",
                "text_dim": "#666666",
                "border": "#dddddd",
                "border_alt": "#cccccc",
                "selected_bg": "#2196F3",
                "selected_text": "#ffffff",
                "today": "#4CAF50",
            }

    def _init_ui(self) -> None:
        """Initialize the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Month/Year header with navigation
        header_layout = QGridLayout()
        header_layout.setColumnStretch(0, 1)
        header_layout.setColumnStretch(1, 3)
        header_layout.setColumnStretch(2, 1)

        # Previous month button
        prev_button = QPushButton("◀")
        prev_button.setMaximumWidth(40)
        prev_button.clicked.connect(self._previous_month)
        header_layout.addWidget(prev_button, 0, 0)

        # Month/Year label
        colors = self._get_theme_colors()
        self.month_label = QLabel()
        self.month_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPointSize(16)
        font.setBold(True)
        self.month_label.setFont(font)
        self.month_label.setStyleSheet(f"color: {colors['text']};")
        header_layout.addWidget(self.month_label, 0, 1)

        # Next month button
        next_button = QPushButton("▶")
        next_button.setMaximumWidth(40)
        next_button.clicked.connect(self._next_month)
        header_layout.addWidget(next_button, 0, 2)

        layout.addLayout(header_layout)

        # Calendar grid
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.calendar_widget = QWidget()
        self.calendar_layout = QGridLayout(self.calendar_widget)
        self.calendar_layout.setSpacing(2)
        scroll_area.setWidget(self.calendar_widget)

        layout.addWidget(scroll_area)

        self._update_calendar()

    def _previous_month(self) -> None:
        """Navigate to previous month."""
        self.current_date = self.current_date.addMonths(-1)
        self._update_calendar()

    def _next_month(self) -> None:
        """Navigate to next month."""
        self.current_date = self.current_date.addMonths(1)
        self._update_calendar()

    def set_selected_date(self, date: QDate) -> None:
        """Set the selected date and navigate to that month."""
        self.selected_date = date
        self.current_date = QDate(date.year(), date.month(), 1)
        self._update_calendar()

    def set_events(self, events_by_date: dict[str, list[CalendarEvent]]) -> None:
        """Set events to display in the calendar."""
        self.events_by_date = events_by_date
        self._update_calendar()

    def _update_calendar(self) -> None:
        """Update the calendar display."""
        # Clear existing widgets
        while self.calendar_layout.count():
            child = self.calendar_layout.takeAt(0)
            widget = child.widget()
            if widget:
                widget.deleteLater()

        # Update month/year label
        month_name = self.current_date.toString("MMMM yyyy")
        self.month_label.setText(month_name)

        # Day headers
        colors = self._get_theme_colors()
        day_headers = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        for col, day in enumerate(day_headers):
            header = QLabel(day)
            header.setAlignment(Qt.AlignmentFlag.AlignCenter)
            font = QFont()
            font.setBold(True)
            header.setFont(font)
            header.setStyleSheet(f"color: {colors['text']}; background-color: {colors['bg_alt']}; padding: 5px;")
            self.calendar_layout.addWidget(header, 0, col)

        # Get first day of month and number of days
        first_day = QDate(self.current_date.year(), self.current_date.month(), 1)
        days_in_month = first_day.daysInMonth()
        start_weekday = first_day.dayOfWeek()  # 1=Monday, 7=Sunday in Qt, but we want 0=Sunday

        # Convert to 0-based Sunday=0
        start_col = start_weekday % 7

        # Get previous month's last days for padding
        prev_month = first_day.addMonths(-1)
        days_in_prev_month = prev_month.daysInMonth()

        row = 1
        col = 0

        # Add days from previous month
        for i in range(start_col):
            day_num = days_in_prev_month - start_col + i + 1
            date = QDate(prev_month.year(), prev_month.month(), day_num)
            self._add_day_cell(date, row, col, is_current_month=False)
            col += 1

        # Add days from current month
        for day_num in range(1, days_in_month + 1):
            date = QDate(self.current_date.year(), self.current_date.month(), day_num)
            self._add_day_cell(date, row, col, is_current_month=True)
            col += 1
            if col >= 7:
                col = 0
                row += 1

        # Add days from next month to fill the grid
        next_month = first_day.addMonths(1)
        day_num = 1
        while row < 7:  # Fill up to 6 rows
            while col < 7:
                date = QDate(next_month.year(), next_month.month(), day_num)
                self._add_day_cell(date, row, col, is_current_month=False)
                col += 1
                day_num += 1
            col = 0
            row += 1

    def _add_day_cell(self, date: QDate, row: int, col: int, is_current_month: bool) -> None:
        """Add a day cell to the calendar."""
        date_key = date.toString("yyyy-MM-dd")
        events = self.events_by_date.get(date_key, [])

        # Get theme colors
        colors = self._get_theme_colors()

        # Create clickable day cell widget
        clickable_cell = _ClickableDayCell(date, self)
        cell_layout = QVBoxLayout(clickable_cell)
        cell_layout.setContentsMargins(6, 6, 6, 6)
        cell_layout.setSpacing(3)  # Increased spacing between events

        # Day number
        day_label = QLabel(str(date.day()))
        day_font = QFont()
        day_font.setBold(True)
        if date == self.selected_date:
            day_font.setPointSize(day_font.pointSize() + 2)
        day_label.setFont(day_font)

        # Style based on current month and selection
        if not is_current_month:
            day_label.setStyleSheet(f"color: {colors['text_dim']};")
        elif date == self.selected_date:
            day_label.setStyleSheet(
                f"color: {colors['selected_text']}; background-color: {colors['selected_bg']}; "
                f"border: 2px solid {colors['selected_bg']}; border-radius: 3px; padding: 2px;"
            )
        elif date == QDate.currentDate():
            day_label.setStyleSheet(f"color: {colors['today']}; font-weight: bold;")
        else:
            day_label.setStyleSheet(f"color: {colors['text']};")

        cell_layout.addWidget(day_label)

        # Add events (sorted by time)
        sorted_events = sorted(events, key=lambda e: e.date if e.date else datetime.min)
        for event in sorted_events[:5]:  # Limit to 5 events per day
            # Format event text: "Event Name HH:MM" (event name first, then time)
            event_text = event.title
            time_str = ""
            if event.date:
                # Use local time if available, otherwise UTC
                event_time = event.date
                if event_time.hour < 24:  # Has time info
                    time_str = event_time.strftime("%H:%M")
                    # Format: "Event Name HH:MM" (event name first, then time)
                    event_text = f"{event_text} {time_str}"
                else:
                    event_text = event.title
            else:
                event_text = event.title

            event_label = QLabel(event_text)
            event_label.setWordWrap(False)  # Don't wrap, keep on one line
            event_font = QFont()
            event_font.setPointSize(8)
            event_label.setFont(event_font)

            # Use theme-aware text color with better spacing
            event_label.setStyleSheet(f"color: {colors['text']}; padding: 1px 0px; margin: 0px; line-height: 1.3;")

            cell_layout.addWidget(event_label)

        if len(events) > 5:
            more_label = QLabel(f"... {len(events) - 5} more")
            more_label.setStyleSheet(f"color: {colors['text_dim']}; font-size: 7pt; padding: 2px 0px;")
            cell_layout.addWidget(more_label)

        # Set styling for clickable cell
        if is_current_month:
            clickable_cell.setStyleSheet(f"border: 1px solid {colors['border']}; background-color: {colors['bg']};")
        else:
            clickable_cell.setStyleSheet(
                f"border: 1px solid {colors['border_alt']}; background-color: {colors['bg_alt']};"
            )

        clickable_cell.setMinimumHeight(100)  # Ensure cells are tall enough for events

        self.calendar_layout.addWidget(clickable_cell, row, col)

    def _on_cell_clicked(self, event: Any, date: QDate) -> None:
        """Handle cell click."""
        self.selected_date = date
        self._update_calendar()
        self.date_selected.emit(date)

    def _on_cell_double_clicked(self, event: Any, date: QDate) -> None:
        """Handle cell double-click - open events modal."""
        date_key = date.toString("yyyy-MM-dd")
        events = self.events_by_date.get(date_key, [])

        # Only open modal if there are events
        if events:
            self.date_double_clicked.emit(date, events)


class AstronomicalCalendarDialog(QDialog):
    """Dialog showing astronomical calendar with events."""

    # Signal to trigger UI updates from background threads
    _update_formatting_signal = Signal()
    _close_progress_signal = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the astronomical calendar dialog."""
        super().__init__(parent)
        self.setWindowTitle("Astronomical Calendar")
        self.setMinimumWidth(900)
        self.setMinimumHeight(600)
        self.resize(1000, 700)

        # Store events by date
        self.events_by_date: dict[str, list[CalendarEvent]] = {}

        # Create layout
        layout = QVBoxLayout(self)

        # Calendar widget (full width)
        calendar_layout = QVBoxLayout()
        calendar_layout.setContentsMargins(0, 0, 0, 0)

        # Custom calendar widget
        self.calendar = CustomCalendarWidget()
        self.calendar.date_double_clicked.connect(self._on_date_double_clicked)
        calendar_layout.addWidget(self.calendar)

        # Today button
        today_button = QPushButton("Today")
        today_button.clicked.connect(self._on_today_clicked)
        calendar_layout.addWidget(today_button)

        layout.addLayout(calendar_layout)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Store progress dialog as instance variable
        self._progress_dialog: QProgressDialog | None = None

        # Connect signals for thread-safe UI updates
        self._update_formatting_signal.connect(self._update_calendar_formatting)
        self._close_progress_signal.connect(self._close_progress)

        # Load events
        self._load_events()

    def _load_events(self) -> None:
        """Load all astronomical events."""
        try:
            get_observer_location()
            now = datetime.now(UTC)

            # Show progress dialog
            self._progress_dialog = QProgressDialog("Loading astronomical events...", "Cancel", 0, 0, self)
            self._progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            self._progress_dialog.setCancelButton(None)  # Disable cancel button
            self._progress_dialog.show()

            # Process events to show the dialog immediately
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()

            # Load events in background thread, but update UI on main thread
            def _load_in_background() -> None:
                """Load events in background and update UI on main thread."""
                try:
                    # Load AstroPixels events first (primary source)
                    self._load_astropixels_events(now)

                    # Load other events
                    # self._load_space_events(now)

                    # Load meteor showers (async but fast)
                    # self._load_meteor_showers(now)

                    # Load eclipses (async but fast)
                    # self._load_eclipses(location, now)

                    # Load moon phases last (slower, but optimized)
                    # Skip this since AstroPixels already has moon phases
                    # self._load_moon_phases(location, now)

                    # Update calendar formatting on main thread using signal
                    # This ensures the call happens on the main Qt thread
                    self._update_formatting_signal.emit()
                except Exception as e:
                    logger.error(f"Error loading events: {e}", exc_info=True)
                finally:
                    # Always close progress dialog on main thread
                    self._close_progress_signal.emit()

            # Run in background thread
            thread = threading.Thread(target=_load_in_background, daemon=True)
            thread.start()

            # Set timeout to close progress dialog
            QTimer.singleShot(30000, self._close_progress)  # 30 second timeout

        except Exception as e:
            logger.error(f"Error initializing event loading: {e}", exc_info=True)
            if self._progress_dialog:
                self._progress_dialog.close()

    def _close_progress(self) -> None:
        """Close progress dialog (called from main thread)."""
        if self._progress_dialog:
            self._progress_dialog.close()
            self._progress_dialog = None

    def _load_astropixels_events(self, start_date: datetime) -> None:
        """Load AstroPixels events from cache or fetch if needed."""
        try:
            from celestron_nexstar.api.database.models import get_db_session
            from celestron_nexstar.api.events.astropixels_almanac import (
                TIMEZONE_OFFSETS,
                cache_astropixels_events,
                get_cached_astropixels_events,
            )
            from celestron_nexstar.api.location.observer import get_observer_location

            # Get location
            location = get_observer_location()

            async def _load() -> None:
                async with get_db_session() as session:
                    # Determine year and timezone
                    year = start_date.year
                    # Get user's timezone
                    try:
                        from celestron_nexstar.api.core.utils import get_local_timezone

                        tz = get_local_timezone(location.latitude, location.longitude)
                        # Map timezone to AstroPixels format
                        # Default to MST if we can't determine
                        if tz:
                            tz_name = str(tz)
                            timezone_map = {
                                "America/New_York": "EST",
                                "America/Chicago": "CST",
                                "America/Denver": "MST",
                                "America/Los_Angeles": "PST",
                                "America/Anchorage": "AKST",
                                "Pacific/Honolulu": "HST",
                            }
                            tz_str = timezone_map.get(tz_name, "MST")
                        else:
                            tz_str = "MST"
                    except Exception:
                        tz_str = "MST"  # Default to MST

                    # Check if events are cached, if not fetch and cache them
                    end_date = start_date + timedelta(days=365)

                    # Get timezone offset for reconstructing local_date from database events
                    tz_offset = TIMEZONE_OFFSETS.get(tz_str, -7)  # Default to MST
                    cached_events = await get_cached_astropixels_events(session, start_date, end_date, tz_offset)

                    # Always fetch and cache to ensure we have all events (force_refresh=False to use cache if available)
                    logger.info(f"Fetching AstroPixels almanac for {year} ({tz_str})")
                    await cache_astropixels_events(session, year, tz_str, force_refresh=False)
                    # Also cache next year if we're near the end of the year
                    if start_date.month >= 11:
                        await cache_astropixels_events(session, year + 1, tz_str, force_refresh=False)

                    # Get cached events with timezone offset
                    cached_events = await get_cached_astropixels_events(session, start_date, end_date, tz_offset)

                    # Add events to calendar
                    logger.info(f"Adding {len(cached_events)} AstroPixels events to calendar")
                    events_by_month: dict[int, int] = {}
                    december_events: list[str] = []
                    for event in cached_events:
                        # Determine color based on event type
                        color_map = {
                            "moon_phase": "#f39c12" if "Full" in event.event_name else "#3498db",
                            "meteor_shower": "#9b59b6",
                            "lunar_eclipse": "#e74c3c",
                            "solar_eclipse": "#c0392b",
                            "planetary_opposition": "#16a085",
                            "planetary_elongation": "#16a085",
                            "solstice": "#27ae60",
                            "equinox": "#27ae60",
                            "conjunction": "#16a085",
                            "moon_position": "#95a5a6",
                            "other": "#34495e",
                        }
                        color = color_map.get(event.event_type, "#34495e")

                        # Use local_date if available (for correct calendar date), otherwise use UTC date
                        # For AstroPixels events, local_date is set; for database events, it's None
                        if event.local_date:
                            # Use the local date (timezone-naive) for correct calendar date
                            event_date = event.local_date
                            month = event.local_date.month
                        else:
                            # For database events without local_date, reconstruct local date from UTC
                            # by adding back the timezone offset
                            # This is approximate but should work for most cases
                            event_date = event.date
                            month = event.date.month

                        # Debug logging for FULL MOON events
                        if "FULL MOON" in event.event_name.upper() or "full moon" in event.event_name.lower():
                            logger.debug(
                                f"Adding FULL MOON to calendar: {event.event_name}, "
                                f"event_date={event_date}, local_date={event.local_date}, "
                                f"utc_date={event.date}, type={event.event_type}"
                            )

                        # Track events by month for debugging
                        events_by_month[month] = events_by_month.get(month, 0) + 1

                        # Track December events specifically
                        if month == 12:
                            december_events.append(f"{event_date.day:02d} {event.event_name}")

                        self._add_event(
                            event_date,
                            event.event_name,
                            event.description,
                            event.event_type,
                            color,
                        )

                    logger.info(f"Events by month: {events_by_month}")
                    if december_events:
                        logger.info(f"December events ({len(december_events)}): {sorted(december_events)}")

                    # Update calendar formatting after loading events
                    # Use signal to ensure this runs on the main Qt thread
                    self._update_formatting_signal.emit()

            # Run async load - UI updates will be scheduled from the background thread
            _run_async_safe(_load())

        except Exception as e:
            logger.error(f"Error loading AstroPixels events: {e}", exc_info=True)

    def _load_moon_phases(self, location: ObserverLocation | Any, start_date: datetime) -> None:
        """Load moon phases for the next 12 months."""
        try:
            # Use a more efficient approach: calculate approximate moon phases
            # Moon cycle is ~29.5 days, so we can estimate phase dates
            # We'll sample every 3 days to find phase transitions, then check more precisely
            current_date = start_date.replace(hour=12, minute=0, second=0, microsecond=0)
            end_date = current_date + timedelta(days=365)

            last_phase: MoonPhase | None = None

            # Sample every 3 days to find phase changes (much faster)
            sample_interval = timedelta(days=3)

            # Limit to ~120 samples instead of 365
            max_samples = 120
            sample_count = 0

            while current_date < end_date and sample_count < max_samples:
                moon_info = get_moon_info(location.latitude, location.longitude, current_date)
                if moon_info:
                    phase = moon_info.phase_name
                    illumination = moon_info.illumination

                    # Only add events when phase changes to significant phases
                    if phase != last_phase:
                        if phase == MoonPhase.NEW_MOON:
                            self._add_event(
                                current_date,
                                "New Moon",
                                f"New Moon - {illumination:.1%} illuminated",
                                "moon_phase",
                                "#2c3e50",
                            )
                        elif phase == MoonPhase.FULL_MOON:
                            # Check if it's a supermoon (perigee)
                            # For simplicity, we'll mark all full moons, but could enhance this
                            if illumination > 0.99:
                                self._add_event(
                                    current_date,
                                    "Full Moon",
                                    f"Full Moon - {illumination:.1%} illuminated",
                                    "moon_phase",
                                    "#f39c12",
                                )
                            else:
                                self._add_event(
                                    current_date,
                                    "Full Moon",
                                    f"Full Moon - {illumination:.1%} illuminated",
                                    "moon_phase",
                                    "#e67e22",
                                )
                        elif phase == MoonPhase.FIRST_QUARTER:
                            self._add_event(
                                current_date,
                                "First Quarter Moon",
                                f"First Quarter - {illumination:.1%} illuminated",
                                "moon_phase",
                                "#3498db",
                            )
                        elif phase == MoonPhase.LAST_QUARTER:
                            self._add_event(
                                current_date,
                                "Last Quarter Moon",
                                f"Last Quarter - {illumination:.1%} illuminated",
                                "moon_phase",
                                "#3498db",
                            )

                        last_phase = phase

                # Move to next sample point
                current_date += sample_interval
                sample_count += 1

        except Exception as e:
            logger.error(f"Error loading moon phases: {e}", exc_info=True)

    def _load_meteor_showers(self, start_date: datetime) -> None:
        """Load meteor showers from database."""
        try:
            from celestron_nexstar.api.astronomy.meteor_showers import get_all_meteor_showers
            from celestron_nexstar.api.database.models import get_db_session

            async def _load() -> None:
                async with get_db_session() as session:
                    showers = await get_all_meteor_showers(session)
                    current_date = start_date
                    end_date = current_date + timedelta(days=365)

                    for shower in showers:
                        # Check if shower is active in the next year
                        shower_start = datetime(
                            current_date.year,
                            shower.activity_start_month,
                            shower.activity_start_day,
                            tzinfo=UTC,
                        )
                        shower_end = datetime(
                            current_date.year,
                            shower.activity_end_month,
                            shower.activity_end_day,
                            tzinfo=UTC,
                        )

                        # Handle year wrap-around
                        if shower_end < shower_start:
                            shower_end = datetime(
                                current_date.year + 1,
                                shower.activity_end_month,
                                shower.activity_end_day,
                                tzinfo=UTC,
                            )

                        # Check if we need to look at next year too
                        if shower_start < current_date:
                            shower_start = datetime(
                                current_date.year + 1,
                                shower.activity_start_month,
                                shower.activity_start_day,
                                tzinfo=UTC,
                            )
                            shower_end = datetime(
                                current_date.year + 1,
                                shower.activity_end_month,
                                shower.activity_end_day,
                                tzinfo=UTC,
                            )
                            if shower_end < shower_start:
                                shower_end = datetime(
                                    current_date.year + 2,
                                    shower.activity_end_month,
                                    shower.activity_end_day,
                                    tzinfo=UTC,
                                )

                        # Add peak date
                        peak_date = datetime(
                            shower_start.year,
                            shower.peak_month,
                            shower.peak_day,
                            tzinfo=UTC,
                        )

                        if current_date <= peak_date <= end_date:
                            self._add_event(
                                peak_date,
                                f"{shower.name} Peak",
                                f"Peak activity: {shower.zhr_peak} meteors/hour",
                                "meteor_shower",
                                "#9b59b6",
                            )

                        # Add start and end dates if in range
                        if current_date <= shower_start <= end_date:
                            self._add_event(
                                shower_start,
                                f"{shower.name} Begins",
                                "Shower activity begins",
                                "meteor_shower",
                                "#8e44ad",
                            )

                        if current_date <= shower_end <= end_date:
                            self._add_event(
                                shower_end,
                                f"{shower.name} Ends",
                                "Shower activity ends",
                                "meteor_shower",
                                "#8e44ad",
                            )

            _run_async_safe(_load())

        except Exception as e:
            logger.error(f"Error loading meteor showers: {e}", exc_info=True)

    def _load_eclipses(self, location: ObserverLocation | Any, start_date: datetime) -> None:
        """Load eclipses from database."""
        try:
            from celestron_nexstar.api.astronomy.eclipses import (
                get_next_lunar_eclipse,
                get_next_solar_eclipse,
            )
            from celestron_nexstar.api.database.models import get_db_session

            async def _load() -> None:
                async with get_db_session() as session:
                    # Load lunar eclipses
                    lunar_eclipses = await get_next_lunar_eclipse(session, location, years_ahead=1)
                    for eclipse in lunar_eclipses:
                        self._add_event(
                            eclipse.maximum_time,
                            "Lunar Eclipse",
                            f"{eclipse.eclipse_type.replace('_', ' ').title()}: {eclipse.notes}",
                            "eclipse",
                            "#e74c3c",  # Red for lunar
                        )

                    # Load solar eclipses
                    solar_eclipses = await get_next_solar_eclipse(session, location, years_ahead=1)
                    for eclipse in solar_eclipses:
                        self._add_event(
                            eclipse.maximum_time,
                            "Solar Eclipse",
                            f"{eclipse.eclipse_type.replace('_', ' ').title()}: {eclipse.notes}",
                            "eclipse",
                            "#c0392b",  # Dark red for solar
                        )

            _run_async_safe(_load())

        except Exception as e:
            logger.error(f"Error loading eclipses: {e}", exc_info=True)

    def _load_space_events(self, start_date: datetime) -> None:
        """Load space events from database."""
        try:
            from celestron_nexstar.api.events.space_events import get_upcoming_events

            end_date = start_date + timedelta(days=365)
            events = get_upcoming_events(start_date, end_date)

            for event in events:
                # Determine color based on event type
                if event.event_type.value == "meteor_shower":
                    color = "#9b59b6"
                elif event.event_type.value in ["lunar_eclipse", "solar_eclipse"]:
                    color = "#e74c3c"
                elif event.event_type.value in ["planetary_opposition", "planetary_elongation"]:
                    color = "#16a085"
                elif event.event_type.value in ["solstice", "equinox"]:
                    color = "#27ae60"
                else:
                    color = "#34495e"

                self._add_event(
                    event.date,
                    event.name,
                    event.description,
                    "space_event",
                    color,
                )

        except Exception as e:
            logger.error(f"Error loading space events: {e}", exc_info=True)

    def _add_event(self, date: datetime, title: str, description: str, event_type: str, color: str) -> None:
        """Add an event to the calendar."""
        # Use the date as-is for the date key (this should be the local date)
        # This ensures events appear on the correct calendar date
        if date.tzinfo is None:
            # Timezone-naive: use as-is for date key (this is the local date from AstroPixels)
            date_key = date.strftime("%Y-%m-%d")
            # Convert to UTC for storage
            date_utc = date.replace(tzinfo=UTC)
        else:
            # Timezone-aware: use the date components (year, month, day) for the key
            # This preserves the calendar date even if timezone conversion shifts the day
            date_key = f"{date.year}-{date.month:02d}-{date.day:02d}"
            # Ensure it's in UTC for storage
            date_utc = date.astimezone(UTC)

        if date_key not in self.events_by_date:
            self.events_by_date[date_key] = []

        event = CalendarEvent(
            date=date_utc,  # Store UTC datetime
            title=title,
            description=description,
            event_type=event_type,
            color=color,
        )

        self.events_by_date[date_key].append(event)

    def _update_calendar_formatting(self) -> None:
        """Update calendar to display events in day cells."""
        # Update the custom calendar widget with events
        self.calendar.set_events(self.events_by_date)
        logger.info(f"Updated calendar with {len(self.events_by_date)} dates with events")

    def _on_today_clicked(self) -> None:
        """Handle Today button click - navigate to today's date."""
        today = QDate.currentDate()
        self.calendar.set_selected_date(today)

    def _on_date_double_clicked(self, date: QDate, events: list[CalendarEvent]) -> None:
        """Handle date double-click - show events in modal."""
        if not events:
            return

        # Get theme colors
        is_dark = self._is_dark_theme()
        text_color = "#ffffff" if is_dark else "#000000"
        text_dim_color = "#aaaaaa" if is_dark else "#666666"
        bg_color = "#1e1e1e" if is_dark else "#ffffff"

        # Create modal dialog
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Events for {date.toString('MMMM d, yyyy')}")
        dialog.setMinimumWidth(500)
        dialog.setMinimumHeight(400)

        layout = QVBoxLayout(dialog)

        # Date label
        date_label = QLabel(f"<h2 style='color: {text_color};'>{date.toString('MMMM d, yyyy')}</h2>")
        date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(date_label)

        # Events list
        events_text = QTextBrowser()
        events_text.setReadOnly(True)

        # Build HTML content
        html_parts = []
        html_parts.append(f"<div style='padding: 10px; background-color: {bg_color};'>")

        # Sort events by time
        sorted_events = sorted(events, key=lambda e: e.date if e.date else datetime.min)

        for event in sorted_events:
            # Format time
            time_str = "All day"
            if event.date:
                try:
                    from celestron_nexstar.api.core.utils import get_local_timezone
                    from celestron_nexstar.api.location.observer import get_observer_location

                    location = get_observer_location()
                    tz = get_local_timezone(location.latitude, location.longitude)
                    if tz and event.date.tzinfo:
                        local_time = event.date.astimezone(tz)
                        time_str = local_time.strftime("%H:%M")
                    elif event.date:
                        time_str = event.date.strftime("%H:%M")
                except Exception:
                    if event.date:
                        time_str = event.date.strftime("%H:%M")

            # Format event type
            event_type = event.event_type.replace("_", " ").title()

            # Use semi-transparent background for event cards with theme-aware text
            bg_alpha = "40" if is_dark else "20"
            html_parts.append(
                f"<div style='margin-bottom: 15px; padding: 10px; border-left: 4px solid {event.color}; "
                f"background-color: {event.color}{bg_alpha}; border-radius: 4px;'>"
            )
            # Use theme-aware text color for title, but keep event color for border/accent
            html_parts.append(
                f"<div style='font-size: 14pt; font-weight: bold; color: {text_color};'>{event.title}</div>"
            )
            html_parts.append(f"<div style='color: {text_dim_color}; margin-top: 5px;'>Time: {time_str}</div>")
            html_parts.append(f"<div style='color: {text_dim_color};'>Type: {event_type}</div>")
            if event.description and event.description != event.title:
                html_parts.append(f"<div style='margin-top: 8px; color: {text_color};'>{event.description}</div>")
            html_parts.append("</div>")

        html_parts.append("</div>")
        events_text.setHtml("".join(html_parts))

        layout.addWidget(events_text)

        # Close button
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.exec()

    def _is_dark_theme(self) -> bool:
        """Detect if the current theme is dark mode."""
        from PySide6.QtGui import QGuiApplication, QPalette

        app = QGuiApplication.instance()
        if app and isinstance(app, QGuiApplication):
            palette = app.palette()
            window_color = palette.color(QPalette.ColorRole.Window)
            brightness = window_color.lightness()
            return bool(brightness < 128)
        return False

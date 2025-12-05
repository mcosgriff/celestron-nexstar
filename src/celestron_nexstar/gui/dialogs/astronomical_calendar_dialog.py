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
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
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


# Removed CustomCalendarWidget - no longer needed


class AstronomicalCalendarDialog(QDialog):
    """Dialog showing astronomical calendar with events."""

    # Signal to trigger UI updates from background threads
    _update_formatting_signal = Signal()
    _close_progress_signal = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the astronomical calendar dialog."""
        super().__init__(parent)
        self.setWindowTitle("Astronomical Calendar")
        self.setMinimumWidth(1200)
        self.setMinimumHeight(700)
        self.resize(1400, 800)

        # Store events by date (for calendar widget - kept for compatibility)
        self.events_by_date: dict[str, list[CalendarEvent]] = {}
        # Store all events in a flat list (for table)
        self.all_events: list[CalendarEvent] = []
        # Current filter settings
        self.filtered_date: QDate | None = None  # Filter to specific date (None = all dates)
        self.filtered_event_types: set[str] = set()
        self._current_month_filter: int | None = None  # Filter to specific month (None = all months)
        self._current_year_filter: int | None = None  # Filter to specific year (None = all years)

        # Create main layout
        main_layout = QVBoxLayout(self)

        # Top controls bar (Today/Show All/Current Month buttons)
        top_controls = QHBoxLayout()
        today_button = QPushButton("Today")
        today_button.clicked.connect(self._on_today_clicked)
        top_controls.addWidget(today_button)

        current_month_button = QPushButton("Current Month")
        current_month_button.clicked.connect(self._on_current_month_clicked)
        top_controls.addWidget(current_month_button)

        show_all_button = QPushButton("Show All")
        show_all_button.clicked.connect(self._on_show_all_clicked)
        top_controls.addWidget(show_all_button)

        top_controls.addStretch()
        main_layout.addLayout(top_controls)

        # Create horizontal splitter for filters (left) and table (right)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left side: Event type filters
        left_container = QWidget()
        left_container_layout = QVBoxLayout(left_container)
        left_container_layout.setContentsMargins(5, 5, 5, 5)
        left_container_layout.setSpacing(5)

        filter_label = QLabel("Filter by Event Type:")
        filter_label.setStyleSheet("font-weight: bold; font-size: 11pt;")
        left_container_layout.addWidget(filter_label)

        # Select All / Unselect All buttons
        select_buttons_layout = QHBoxLayout()
        select_all_button = QPushButton("Select All")
        select_all_button.clicked.connect(self._on_select_all_clicked)
        select_buttons_layout.addWidget(select_all_button)

        unselect_all_button = QPushButton("Unselect All")
        unselect_all_button.clicked.connect(self._on_unselect_all_clicked)
        select_buttons_layout.addWidget(unselect_all_button)
        left_container_layout.addLayout(select_buttons_layout)

        # Scrollable area for event type filters
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Widget containing the filter groups
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(5, 5, 5, 5)
        left_layout.setSpacing(10)

        # Event type filters grouped logically
        self.event_type_filters: dict[str, QCheckBox] = {}

        # Moon Events Group
        moon_group = QGroupBox("Moon Events")
        moon_layout = QVBoxLayout()
        moon_events = [
            ("moon_phase", "Moon Phases"),
            ("moon_perigee", "Moon at Perigee"),
            ("moon_apogee", "Moon at Apogee"),
            ("moon_ascending_node", "Moon at Ascending Node"),
            ("moon_descending_node", "Moon at Descending Node"),
        ]
        for event_type, label in moon_events:
            checkbox = QCheckBox(label)
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(self._on_filter_changed)
            self.event_type_filters[event_type] = checkbox
            moon_layout.addWidget(checkbox)
            self.filtered_event_types.add(event_type)
        moon_group.setLayout(moon_layout)
        left_layout.addWidget(moon_group)

        # Planetary Events Group
        planetary_group = QGroupBox("Planetary Events")
        planetary_layout = QVBoxLayout()
        planetary_events = [
            ("planetary_opposition", "Planetary Opposition"),
            ("planetary_elongation", "Planetary Elongation"),
            ("planetary_perihelion", "Planetary Perihelion"),
            ("planetary_aphelion", "Planetary Aphelion"),
            ("planetary_inferior_conjunction", "Inferior Conjunction"),
            ("planetary_superior_conjunction", "Superior Conjunction"),
            ("conjunction", "Conjunctions"),
        ]
        for event_type, label in planetary_events:
            checkbox = QCheckBox(label)
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(self._on_filter_changed)
            self.event_type_filters[event_type] = checkbox
            planetary_layout.addWidget(checkbox)
            self.filtered_event_types.add(event_type)
        planetary_group.setLayout(planetary_layout)
        left_layout.addWidget(planetary_group)

        # Celestial Events Group
        celestial_group = QGroupBox("Celestial Events")
        celestial_layout = QVBoxLayout()
        celestial_events = [
            ("meteor_shower", "Meteor Showers"),
            ("lunar_eclipse", "Lunar Eclipses"),
            ("solar_eclipse", "Solar Eclipses"),
            ("occultation", "Occultations"),
        ]
        for event_type, label in celestial_events:
            checkbox = QCheckBox(label)
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(self._on_filter_changed)
            self.event_type_filters[event_type] = checkbox
            celestial_layout.addWidget(checkbox)
            self.filtered_event_types.add(event_type)
        celestial_group.setLayout(celestial_layout)
        left_layout.addWidget(celestial_group)

        # Star Events Group
        star_group = QGroupBox("Star Events")
        star_layout = QVBoxLayout()
        star_events = [
            ("star_position", "Star Positions"),
        ]
        for event_type, label in star_events:
            checkbox = QCheckBox(label)
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(self._on_filter_changed)
            self.event_type_filters[event_type] = checkbox
            star_layout.addWidget(checkbox)
            self.filtered_event_types.add(event_type)
        star_group.setLayout(star_layout)
        left_layout.addWidget(star_group)

        # Seasonal Events Group
        seasonal_group = QGroupBox("Seasonal Events")
        seasonal_layout = QVBoxLayout()
        seasonal_events = [
            ("solstice", "Solstices"),
            ("equinox", "Equinoxes"),
        ]
        for event_type, label in seasonal_events:
            checkbox = QCheckBox(label)
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(self._on_filter_changed)
            self.event_type_filters[event_type] = checkbox
            seasonal_layout.addWidget(checkbox)
            self.filtered_event_types.add(event_type)
        seasonal_group.setLayout(seasonal_layout)
        left_layout.addWidget(seasonal_group)

        # Other Events Group
        other_group = QGroupBox("Other Events")
        other_layout = QVBoxLayout()
        other_events = [
            ("other", "Other Events"),
        ]
        for event_type, label in other_events:
            checkbox = QCheckBox(label)
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(self._on_filter_changed)
            self.event_type_filters[event_type] = checkbox
            other_layout.addWidget(checkbox)
            self.filtered_event_types.add(event_type)
        other_group.setLayout(other_layout)
        left_layout.addWidget(other_group)

        left_layout.addStretch()

        # Set the scrollable widget
        scroll_area.setWidget(left_widget)
        left_container_layout.addWidget(scroll_area)

        # Set fixed width for left panel
        left_container.setMaximumWidth(250)
        left_container.setMinimumWidth(200)
        splitter.addWidget(left_container)

        # Right side: Table
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(5, 5, 5, 5)

        # Table header with info
        table_header = QHBoxLayout()
        table_title = QLabel("Astronomical Events")
        table_title.setStyleSheet("font-size: 14pt; font-weight: bold;")
        table_header.addWidget(table_title)
        table_header.addStretch()
        self.event_count_label = QLabel("0 events")
        table_header.addWidget(self.event_count_label)
        right_layout.addLayout(table_header)

        # Create table
        self.events_table = QTableWidget()
        self.events_table.setColumnCount(5)
        header_labels = ["Date", "Time", "Event Name", "Type", "Description"]
        self.events_table.setHorizontalHeaderLabels(header_labels)

        # Configure table
        header = self.events_table.horizontalHeader()
        header.setStretchLastSection(True)  # Description column stretches
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Date
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Time
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)  # Event Name
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Type

        self.events_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.events_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.events_table.setAlternatingRowColors(True)
        self.events_table.setSortingEnabled(True)
        self.events_table.setShowGrid(True)

        right_layout.addWidget(self.events_table)
        splitter.addWidget(right_widget)

        # Set splitter proportions (filters get ~20%, table gets ~80%)
        splitter.setSizes([250, 1150])

        main_layout.addWidget(splitter)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

        # Store progress dialog as instance variable
        self._progress_dialog: QProgressDialog | None = None

        # Connect signals for thread-safe UI updates
        self._update_formatting_signal.connect(self._update_table)
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

                    # Always fetch and cache to ensure we have all events (force_refresh=True to update event types)
                    logger.info(f"Fetching AstroPixels almanac for {year} ({tz_str})")
                    await cache_astropixels_events(session, year, tz_str, force_refresh=True)
                    # Also cache next year if we're near the end of the year
                    if start_date.month >= 11:
                        await cache_astropixels_events(session, year + 1, tz_str, force_refresh=True)

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
                            "moon_perigee": "#95a5a6",
                            "moon_apogee": "#95a5a6",
                            "moon_ascending_node": "#95a5a6",
                            "moon_descending_node": "#95a5a6",
                            "meteor_shower": "#9b59b6",
                            "lunar_eclipse": "#e74c3c",
                            "solar_eclipse": "#c0392b",
                            "planetary_opposition": "#16a085",
                            "planetary_elongation": "#16a085",
                            "planetary_perihelion": "#16a085",
                            "planetary_aphelion": "#16a085",
                            "planetary_inferior_conjunction": "#16a085",
                            "planetary_superior_conjunction": "#16a085",
                            "solstice": "#27ae60",
                            "equinox": "#27ae60",
                            "conjunction": "#16a085",
                            "occultation": "#e67e22",
                            "star_position": "#9b59b6",
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
        # Also add to flat list for table
        self.all_events.append(event)

    def _update_table(self) -> None:
        """Update table with events."""
        logger.info(f"Updated with {len(self.events_by_date)} dates with events")
        # Populate table
        self._populate_table()

    def _populate_table(self) -> None:
        """Populate the events table with filtered events."""
        # Filter events
        filtered_events = self._filter_events()

        # Disable sorting while populating
        self.events_table.setSortingEnabled(False)

        # Clear table
        self.events_table.setRowCount(0)

        # Show message if no events
        if not filtered_events:
            # Ensure column count and headers are correct
            self.events_table.setColumnCount(5)
            header_labels = ["Date", "Time", "Event Name", "Type", "Description"]
            self.events_table.setHorizontalHeaderLabels(header_labels)

            self.events_table.setRowCount(1)

            # Create message item
            if self._current_month_filter is not None and self._current_year_filter is not None:
                month_name = QDate(self._current_year_filter, self._current_month_filter, 1).toString("MMMM yyyy")
                message = f"No events found for {month_name}."
            elif self.filtered_date:
                date_str = self.filtered_date.toString("MMMM d, yyyy")
                message = f"No events found for {date_str}."
            else:
                message = "No events found."

            message_item = QTableWidgetItem(message)
            message_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            message_item.setFlags(Qt.ItemFlag.NoItemFlags)  # Make it non-selectable

            # Style the message
            font = QFont()
            font.setPointSize(12)
            font.setItalic(True)
            message_item.setFont(font)

            self.events_table.setItem(0, 0, message_item)
            self.events_table.setSpan(0, 0, 1, 5)  # Span across all columns

            # Update event count label
            self.event_count_label.setText("0 events")

            # Re-enable sorting
            self.events_table.setSortingEnabled(True)
            return

        # Ensure column count and headers are correct
        if self.events_table.columnCount() != 5:
            self.events_table.setColumnCount(5)
        header_labels = ["Date", "Time", "Event Name", "Type", "Description"]
        self.events_table.setHorizontalHeaderLabels(header_labels)

        # Get local timezone for display
        try:
            from celestron_nexstar.api.core.utils import get_local_timezone
            from celestron_nexstar.api.location.observer import get_observer_location

            location = get_observer_location()
            tz = get_local_timezone(location.latitude, location.longitude)
        except Exception:
            tz = None

        # Populate table
        for event in filtered_events:
            row = self.events_table.rowCount()
            self.events_table.insertRow(row)

            # Date column
            if tz and event.date.tzinfo:
                local_date = event.date.astimezone(tz)
                date_str = local_date.strftime("%Y-%m-%d")
            else:
                date_str = event.date.strftime("%Y-%m-%d")
            date_item = QTableWidgetItem(date_str)
            date_item.setData(Qt.ItemDataRole.UserRole, event.date)  # Store datetime for sorting
            self.events_table.setItem(row, 0, date_item)

            # Time column
            if tz and event.date.tzinfo:
                local_time = event.date.astimezone(tz)
                time_str = local_time.strftime("%H:%M") if local_time.hour < 24 else "All day"
            else:
                time_str = event.date.strftime("%H:%M") if event.date.hour < 24 else "All day"
            time_item = QTableWidgetItem(time_str)
            time_item.setData(Qt.ItemDataRole.UserRole, event.date)  # Store datetime for sorting
            self.events_table.setItem(row, 1, time_item)

            # Event Name column
            name_item = QTableWidgetItem(event.title)
            self.events_table.setItem(row, 2, name_item)

            # Type column
            type_str = event.event_type.replace("_", " ").title()
            type_item = QTableWidgetItem(type_str)
            self.events_table.setItem(row, 3, type_item)

            # Description column
            desc_item = QTableWidgetItem(event.description)
            self.events_table.setItem(row, 4, desc_item)

        # Re-enable sorting
        self.events_table.setSortingEnabled(True)

        # Update event count label
        self.event_count_label.setText(f"{len(filtered_events)} event{'s' if len(filtered_events) != 1 else ''}")

    def _filter_events(self) -> list[CalendarEvent]:
        """Filter events based on current filter settings."""
        filtered = []

        # Get local timezone for date comparison
        try:
            from celestron_nexstar.api.core.utils import get_local_timezone
            from celestron_nexstar.api.location.observer import get_observer_location

            location = get_observer_location()
            tz = get_local_timezone(location.latitude, location.longitude)
        except Exception:
            tz = None

        for event in self.all_events:
            # Filter by month/year (for Current Month button)
            if self._current_month_filter is not None and self._current_year_filter is not None:
                # Convert event date to local timezone for comparison
                local_event_date = event.date.astimezone(tz) if tz and event.date.tzinfo else event.date

                # Compare month and year
                if (
                    local_event_date.month != self._current_month_filter
                    or local_event_date.year != self._current_year_filter
                ):
                    continue
            # Filter by specific date (for Today button)
            elif self.filtered_date is not None:
                # Convert event date to local timezone for comparison
                local_event_date = event.date.astimezone(tz) if tz and event.date.tzinfo else event.date

                # Compare year, month, and day
                event_qdate = QDate(local_event_date.year, local_event_date.month, local_event_date.day)
                if event_qdate != self.filtered_date:
                    continue

            # Filter by event type
            # Only filter if we have active filters (some checkboxes checked)
            # If all are unchecked, show nothing (empty set means filter everything out)
            if self.filtered_event_types:
                if event.event_type not in self.filtered_event_types:
                    continue
            else:
                # All filters unchecked - show nothing
                continue

            filtered.append(event)

        return filtered

    def _on_show_all_clicked(self) -> None:
        """Handle Show All button - show all events."""
        self.filtered_date = None
        self._current_month_filter = None
        self._current_year_filter = None
        self._populate_table()

    def _on_current_month_clicked(self) -> None:
        """Handle Current Month button - show all events in the current month."""
        today = QDate.currentDate()
        self.filtered_date = None  # Clear date filter
        self._current_month_filter = today.month()
        self._current_year_filter = today.year()
        self._populate_table()

    def _on_filter_changed(self) -> None:
        """Handle event type filter checkbox changes."""
        # Update filtered event types
        self.filtered_event_types = {
            event_type for event_type, checkbox in self.event_type_filters.items() if checkbox.isChecked()
        }
        self._populate_table()

    def _on_select_all_clicked(self) -> None:
        """Handle Select All button - check all event type filters."""
        for checkbox in self.event_type_filters.values():
            checkbox.setChecked(True)

    def _on_unselect_all_clicked(self) -> None:
        """Handle Unselect All button - uncheck all event type filters."""
        for checkbox in self.event_type_filters.values():
            checkbox.setChecked(False)

    def _on_today_clicked(self) -> None:
        """Handle Today button click - filter to show only today's events."""
        today = QDate.currentDate()
        self.filtered_date = today
        self._current_month_filter = None  # Clear month filter
        self._current_year_filter = None
        self._populate_table()

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

"""
Moon Calendar Grid Widgets

Custom widgets for displaying monthly moon calendar and phase timeline.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from celestron_nexstar.api.core.enums import MoonPhase


if TYPE_CHECKING:
    from celestron_nexstar.gui.workers.moon_workers import MoonDayData, MoonPhaseEvent


logger = logging.getLogger(__name__)


class MoonCalendarCell(QFrame):
    """
    Individual calendar cell showing date, moon phase, and events.

    Displays:
    - Date number
    - Moon phase icon (visual disk)
    - Illumination percentage
    - Special event badges
    """

    clicked = Signal(datetime)  # type: ignore[type-arg,misc]  # Emits date when clicked

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the calendar cell."""
        super().__init__(parent)

        self._date: datetime | None = None
        self._moon_data: MoonDayData | None = None
        self._is_current_day = False
        self._is_current_month = True
        self._special_events: list[str] = []

        # Set up frame - no border on frame itself
        self.setFrameShape(QFrame.Shape.NoFrame)

        # Enable mouse tracking for hover effects
        self.setMouseTracking(True)

        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # Date label (top)
        self.date_label = QLabel()
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        font = self.date_label.font()
        font.setPointSize(9)
        self.date_label.setFont(font)
        layout.addWidget(self.date_label)

        # Moon icon (center)
        self.moon_icon_label = QLabel()
        self.moon_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.moon_icon_label.setMinimumSize(40, 40)
        self.moon_icon_label.setMaximumSize(50, 50)
        layout.addWidget(self.moon_icon_label, 1)  # Stretch factor

        # Illumination label (bottom)
        self.illumination_label = QLabel()
        self.illumination_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = self.illumination_label.font()
        font.setPointSize(8)
        self.illumination_label.setFont(font)
        layout.addWidget(self.illumination_label)

        # Event badges container (overlay at top-left)
        self.badges_label = QLabel(self)
        self.badges_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.badges_label.setGeometry(2, 2, 20, 20)
        self.badges_label.setStyleSheet("background: transparent; border: none;")
        self.badges_label.hide()  # Hidden by default, shown only when there are events

        # Set size policy
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(QSize(80, 100))

        # Apply default styling
        self._update_styling()

    def set_data(
        self,
        date: datetime | None,
        moon_data: MoonDayData | None,
        is_current: bool,
        is_current_month: bool,
        events: list[str] | None = None,
    ) -> None:
        """
        Set the cell data and update display.

        Args:
            date: Date for this cell (None for empty cell)
            moon_data: Moon data for this date
            is_current: True if this is the current day
            is_current_month: True if this date is in the displayed month
            events: List of special event names
        """
        self._date = date
        self._moon_data = moon_data
        self._is_current_day = is_current
        self._is_current_month = is_current_month
        self._special_events = events or []

        # Update display
        if date is None:
            # Empty cell
            self.date_label.setText("")
            self.moon_icon_label.clear()
            self.illumination_label.setText("")
            self.badges_label.setText("")
            self.badges_label.hide()
            self.setEnabled(False)
        else:
            self.setEnabled(True)
            # Date label
            self.date_label.setText(str(date.day))

            # Moon data
            if moon_data:
                # Render moon icon
                icon = self._render_moon_icon(
                    moon_data.illumination, moon_data.phase_name, size=45
                )
                self.moon_icon_label.setPixmap(icon)

                # Illumination percentage
                percent = moon_data.illumination * 100
                self.illumination_label.setText(f"{percent:.0f}%")

                # Traditional name tooltip
                if moon_data.traditional_name:
                    self.setToolTip(
                        f"{date.strftime('%B %d, %Y')}\n"
                        f"{moon_data.phase_name.value}\n"
                        f"{moon_data.traditional_name}\n"
                        f"Illumination: {percent:.1f}%"
                    )
                else:
                    self.setToolTip(
                        f"{date.strftime('%B %d, %Y')}\n"
                        f"{moon_data.phase_name.value}\n"
                        f"Illumination: {percent:.1f}%"
                    )
            else:
                self.moon_icon_label.clear()
                self.illumination_label.setText("")
                self.setToolTip(date.strftime('%B %d, %Y'))

            # Event badges
            if self._special_events:
                badges = " ".join(self._special_events)
                self.badges_label.setText(badges)
                self.badges_label.show()
            else:
                self.badges_label.setText("")
                self.badges_label.hide()

        # Update styling
        self._update_styling()

    def _render_moon_icon(
        self, illumination: float, phase: MoonPhase, size: int = 45
    ) -> QPixmap:
        """
        Render moon phase icon using the EXACT same algorithm as Moon Info Dialog.

        This matches the algorithm in MoonDiskWorkerThread for consistency.

        Args:
            illumination: Illumination fraction (0.0 to 1.0)
            phase: Moon phase
            size: Icon size in pixels

        Returns:
            Rendered moon icon as QPixmap
        """
        import math

        # Create pixmap
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Determine colors based on theme
        palette = self.palette()
        bg_color = palette.color(QPalette.ColorRole.Window)
        is_dark = bg_color.lightness() < 128

        if is_dark:
            moon_color = QColor(220, 220, 200)  # Pale yellow (light)
            shadow_color = QColor(40, 40, 40)  # Dark gray (shadow)
        else:
            moon_color = QColor(255, 255, 200)  # Light yellow (light)
            shadow_color = QColor(80, 80, 80)  # Medium gray (shadow)

        # Draw moon circle
        center_x = size / 2
        center_y = size / 2
        radius = (size - 4) / 2

        # Clamp illumination to [0, 1]
        f = max(0.0, min(1.0, illumination))
        eps = 1e-4

        # Determine if waxing or waning
        is_waxing = phase in {
            MoonPhase.WAXING_CRESCENT,
            MoonPhase.FIRST_QUARTER,
            MoonPhase.WAXING_GIBBOUS,
        }

        # EXACT algorithm from Moon Info Dialog:
        # Base disk color depends on illumination
        base_color = shadow_color if f <= 0.5 else moon_color

        # Draw base circle
        painter.setPen(QPen(QColor(100, 100, 100), 1))
        painter.setBrush(QBrush(base_color))
        painter.drawEllipse(int(center_x - radius), int(center_y - radius), int(radius * 2), int(radius * 2))

        # Draw phase overlay
        if f <= eps:
            # New Moon: leave as shadow disk
            pass
        elif f >= 1.0 - eps:
            # Full Moon: overwrite with light disk
            painter.setPen(QPen(QColor(100, 100, 100), 1))
            painter.setBrush(QBrush(moon_color))
            painter.drawEllipse(int(center_x - radius), int(center_y - radius), int(radius * 2), int(radius * 2))
        else:
            # Crescent or gibbous - use terminator ellipse
            # Scale for terminator ellipse: |cos(phase_angle)| = |1 - 2f|
            scale = abs(1.0 - 2.0 * f)

            # lit_side: 1.0 for waxing (right), -1.0 for waning (left)
            lit_side = 1.0 if is_waxing else -1.0

            # Build polygon for crescent/gibbous overlay
            n_points = 100
            y_values = [(-1.0 + 2.0 * i / n_points) * radius for i in range(n_points + 1)]

            # Create path for the overlay crescent
            path = QPainterPath()

            # Calculate limb and terminator x-coordinates
            for i, y in enumerate(y_values):
                # Circular limb: x = sqrt(radius^2 - y^2)
                y_normalized = y / radius  # -1 to 1
                limb_x = math.sqrt(max(0.0, 1.0 - y_normalized * y_normalized)) * radius

                # Terminator: x = scale * limb_x
                term_x = scale * limb_x

                if f <= 0.5:
                    # Crescent: draw illuminated crescent on lit_side
                    # Path from limb edge to terminator
                    x_outer = center_x + lit_side * limb_x
                    x_inner = center_x + lit_side * term_x
                else:
                    # Gibbous: draw shadow crescent on opposite side
                    # Path from limb edge to terminator (on dark side)
                    x_outer = center_x - lit_side * limb_x
                    x_inner = center_x - lit_side * term_x

                if i == 0:
                    path.moveTo(x_outer, center_y + y)
                else:
                    path.lineTo(x_outer, center_y + y)

            # Return along terminator curve
            for i in range(n_points, -1, -1):
                y = y_values[i]
                y_normalized = y / radius
                limb_x = math.sqrt(max(0.0, 1.0 - y_normalized * y_normalized)) * radius
                term_x = scale * limb_x

                if f <= 0.5:
                    x_inner = center_x + lit_side * term_x
                else:
                    x_inner = center_x - lit_side * term_x

                path.lineTo(x_inner, center_y + y)

            path.closeSubpath()

            # Draw the overlay
            if f <= 0.5:
                # Add light crescent on top of shadow base
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(moon_color))
            else:
                # Add shadow crescent on top of light base
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(shadow_color))

            painter.drawPath(path)

        painter.end()
        return pixmap

    def _update_styling(self) -> None:
        """Update cell styling based on state."""
        palette = self.palette()
        bg_color = palette.color(QPalette.ColorRole.Window)

        if self._is_current_day:
            # Current day - thicker border on cell frame only
            self.setStyleSheet(
                """
                QFrame {
                    border: 2px solid #4A90E2;
                    background-color: rgba(74, 144, 226, 0.1);
                }
                """
            )
            self.date_label.setStyleSheet(
                """
                QLabel {
                    border: none;
                    font-weight: bold;
                }
                """
            )
        elif not self._is_current_month:
            # Other month - grayed out
            self.setStyleSheet(
                """
                QFrame {
                    border: none;
                }
                """
            )
            self.date_label.setStyleSheet(
                """
                QLabel {
                    color: #999999;
                    border: none;
                }
                """
            )
        else:
            # Normal cell - very faint border
            self.setStyleSheet(
                """
                QFrame {
                    border: 1px solid rgba(200, 200, 200, 0.3);
                }
                QFrame:hover {
                    border: 1px solid rgba(74, 144, 226, 0.4);
                    background-color: rgba(74, 144, 226, 0.05);
                }
                """
            )
            self.date_label.setStyleSheet(
                """
                QLabel {
                    border: none;
                }
                """
            )

    def mousePressEvent(self, event) -> None:
        """Handle mouse click."""
        if self._date and self.isEnabled():
            self.clicked.emit(self._date)
        super().mousePressEvent(event)


class MoonCalendarGrid(QWidget):
    """
    Calendar grid widget for displaying moon phases.

    7x6 grid (day headers + up to 6 weeks)
    Each cell shows date, moon phase icon, and illumination.
    """

    cell_clicked = Signal(datetime)  # type: ignore[type-arg,misc]  # Date clicked

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the calendar grid."""
        super().__init__(parent)

        self._year = 0
        self._month = 0
        self._cells: list[MoonCalendarCell] = []
        self._moon_data: dict[str, MoonDayData] = {}

        # Create layout
        self.layout = QGridLayout(self)
        self.layout.setSpacing(2)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Add day-of-week headers
        days_of_week = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        for col, day_name in enumerate(days_of_week):
            label = QLabel(day_name)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            font = label.font()
            font.setBold(True)
            label.setFont(font)
            self.layout.addWidget(label, 0, col)

        # Create 6 rows x 7 columns of cells
        for row in range(1, 7):  # Rows 1-6 (row 0 is headers)
            for col in range(7):
                cell = MoonCalendarCell(self)
                cell.clicked.connect(self._on_cell_clicked)
                self._cells.append(cell)
                self.layout.addWidget(cell, row, col)

        # Set row/column stretch
        for row in range(1, 7):
            self.layout.setRowStretch(row, 1)
        for col in range(7):
            self.layout.setColumnStretch(col, 1)

    def set_month_data(
        self, year: int, month: int, moon_data: dict[str, MoonDayData]
    ) -> None:
        """
        Set moon data for month and populate grid.

        Args:
            year: Year to display
            month: Month to display (1-12)
            moon_data: Dictionary of moon data keyed by date string "YYYY-MM-DD"
        """
        self._year = year
        self._month = month
        self._moon_data = moon_data

        # Get first and last day of month
        first_day = datetime(year, month, 1, tzinfo=UTC)

        # Find first day to display (might be from previous month)
        # Python weekday(): Monday=0, Sunday=6
        # We want to start on Sunday, so calculate days back
        from datetime import timedelta

        days_back = (first_day.weekday() + 1) % 7  # Days to go back to previous Sunday
        display_start = first_day - timedelta(days=days_back)

        # Get current date for highlighting
        today = datetime.now(UTC).date()

        # Populate cells
        from datetime import timedelta

        current_date = display_start
        for i, cell in enumerate(self._cells):
            # Check if in current month
            is_current_month = current_date.month == month and current_date.year == year

            # Check if current day
            is_current_day = current_date.date() == today

            # Get moon data
            date_key = current_date.strftime("%Y-%m-%d")
            day_moon_data = moon_data.get(date_key)

            # Get special events
            events = []
            if day_moon_data:
                if day_moon_data.traditional_name and day_moon_data.traditional_name != "Blue Moon":
                    # Don't show badge for regular traditional names, only special ones
                    pass
                if day_moon_data.traditional_name == "Blue Moon":
                    events.append("🔵")
                # Check for supermoon (need to check phase events)
                # For now, we'll add supermoon detection in the window

            # Set cell data
            cell.set_data(
                current_date, day_moon_data, is_current_day, is_current_month, events
            )

            # Move to next day
            current_date = current_date + timedelta(days=1)

    def _on_cell_clicked(self, date: datetime) -> None:
        """Handle cell click."""
        self.cell_clicked.emit(date)


class PhaseTimelineWidget(QWidget):
    """
    Timeline showing next 3-6 months of major moon phases.

    Displays:
    - Date
    - Phase (New, Quarter, Full)
    - Traditional name
    - Distance
    - Special events (supermoon, blue moon, eclipse)
    """

    phase_clicked = Signal(datetime, str)  # type: ignore[type-arg,misc]  # Date and phase name
    load_more_requested = Signal()  # type: ignore[type-arg,misc]  # Request to load more events

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the phase timeline widget."""
        super().__init__(parent)

        self._phase_events: list[MoonPhaseEvent] = []
        self._all_events: list[MoonPhaseEvent] = []  # Store all events before filtering
        self._filter_phases: set[MoonPhase] = set()  # Empty = show all
        self._filter_special_only = False

        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header with event count
        header_layout = QHBoxLayout()
        header = QLabel("Upcoming Major Phases")
        font = header.font()
        font.setBold(True)
        font.setPointSize(12)
        header.setFont(font)
        header_layout.addWidget(header)

        # Event count label
        self.count_label = QLabel()
        header_layout.addWidget(self.count_label)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Filter controls
        filter_layout = QHBoxLayout()
        filter_layout.setContentsMargins(0, 5, 0, 5)

        filter_label = QLabel("Show:")
        filter_layout.addWidget(filter_label)

        # Phase type checkboxes
        from PySide6.QtWidgets import QCheckBox

        self.filter_new = QCheckBox("New")
        self.filter_new.setChecked(True)
        self.filter_new.stateChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.filter_new)

        self.filter_quarters = QCheckBox("Quarters")
        self.filter_quarters.setChecked(True)
        self.filter_quarters.stateChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.filter_quarters)

        self.filter_full = QCheckBox("Full")
        self.filter_full.setChecked(True)
        self.filter_full.stateChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.filter_full)

        filter_layout.addSpacing(20)

        # Special events filter
        self.filter_special = QCheckBox("Special Events Only")
        self.filter_special.stateChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.filter_special)

        filter_layout.addStretch()

        layout.addLayout(filter_layout)

        # Create table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Date", "Phase", "Traditional Name", "Distance (km)", "Special"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)

        # Enable sorting
        self.table.setSortingEnabled(True)

        layout.addWidget(self.table)

        # Connect click signal
        self.table.cellClicked.connect(self._on_row_clicked)

        # Load More button
        from PySide6.QtWidgets import QPushButton

        self.load_more_button = QPushButton("Load More Events (next 6 months)")
        self.load_more_button.clicked.connect(self._on_load_more)
        self.load_more_button.setVisible(False)  # Hidden until data loaded
        layout.addWidget(self.load_more_button)

    def set_phase_events(self, events: list[MoonPhaseEvent], replace: bool = True) -> None:
        """
        Set phase events and populate table.

        Args:
            events: List of major phase events
            replace: If True, replace existing events. If False, append to existing.
        """
        if replace:
            self._all_events = events.copy()
        else:
            # Append new events, avoiding duplicates
            existing_dates = {e.date for e in self._all_events}
            new_events = [e for e in events if e.date not in existing_dates]
            self._all_events.extend(new_events)
            # Sort by date
            self._all_events.sort(key=lambda e: e.date)

        # Apply filters and populate
        self._apply_filters()

        # Show/update load more button
        self.load_more_button.setVisible(len(self._all_events) > 0)

    def _apply_filters(self) -> None:
        """Apply current filters and populate table."""
        # Get active phase filters
        active_phases = set()
        if self.filter_new.isChecked():
            active_phases.add(MoonPhase.NEW_MOON)
        if self.filter_quarters.isChecked():
            active_phases.add(MoonPhase.FIRST_QUARTER)
            active_phases.add(MoonPhase.LAST_QUARTER)
        if self.filter_full.isChecked():
            active_phases.add(MoonPhase.FULL_MOON)

        # Apply filters
        filtered_events = []
        for event in self._all_events:
            # Phase filter
            if active_phases and event.phase not in active_phases:
                continue

            # Special events filter
            if self.filter_special.isChecked():
                if not (event.is_supermoon or event.is_blue_moon or event.eclipse_type):
                    continue

            filtered_events.append(event)

        self._phase_events = filtered_events

        # Update count label
        self.count_label.setText(f"({len(filtered_events)} of {len(self._all_events)})")

        # Populate table
        self._populate_table()

    def _populate_table(self) -> None:
        """Populate table with current filtered events."""
        events = self._phase_events

        # Disable sorting while populating
        self.table.setSortingEnabled(False)

        # Clear and populate table
        self.table.setRowCount(len(events))

        for row, event in enumerate(events):
            # Date
            date_item = QTableWidgetItem(event.date.strftime("%Y-%m-%d"))
            self.table.setItem(row, 0, date_item)

            # Phase
            phase_item = QTableWidgetItem(event.phase.value)
            # Color code by phase
            if event.phase == MoonPhase.FULL_MOON:
                phase_item.setForeground(QBrush(QColor(255, 215, 0)))  # Gold
            elif event.phase == MoonPhase.NEW_MOON:
                phase_item.setForeground(QBrush(QColor(100, 100, 100)))  # Gray
            self.table.setItem(row, 1, phase_item)

            # Traditional name
            name_item = QTableWidgetItem(event.traditional_name or "")
            if event.traditional_name:
                font = name_item.font()
                font.setBold(True)
                name_item.setFont(font)
            self.table.setItem(row, 2, name_item)

            # Distance
            distance_item = QTableWidgetItem(f"{event.distance_km:,.0f}")
            distance_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 3, distance_item)

            # Special events
            special = []
            if event.is_supermoon:
                special.append("🌕 Supermoon")
            if event.is_blue_moon:
                special.append("🔵 Blue Moon")
            if event.eclipse_type:
                special.append(f"🌑 {event.eclipse_type}")

            special_item = QTableWidgetItem(" ".join(special))
            self.table.setItem(row, 4, special_item)

        # Re-enable sorting and auto-resize columns
        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _on_filter_changed(self) -> None:
        """Handle filter change."""
        self._apply_filters()

    def _on_load_more(self) -> None:
        """Handle load more button click."""
        self.load_more_requested.emit()

    def _on_row_clicked(self, row: int, column: int) -> None:
        """Handle row click."""
        if 0 <= row < len(self._phase_events):
            event = self._phase_events[row]
            self.phase_clicked.emit(event.date, event.phase.value)

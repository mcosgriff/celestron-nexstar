"""
Main application window for telescope control.
"""

import contextlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QMouseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from celestron_nexstar.api.core import format_local_time
from celestron_nexstar.api.location.observer import get_observer_location
from celestron_nexstar.gui.dialogs.gps_info_dialog import GPSInfoDialog
from celestron_nexstar.gui.dialogs.time_info_dialog import TimeInfoDialog


if TYPE_CHECKING:
    from celestron_nexstar import NexStarTelescope


class ClickableLabel(QLabel):
    """A clickable QLabel that emits a clicked signal."""

    clicked = Signal()  # type: ignore[type-arg,misc]

    def mouse_press_event(self, event: QMouseEvent) -> None:  # type: ignore[override]
        """Handle mouse press event."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    """Main application window for telescope control."""

    def __init__(self) -> None:
        """Initialize the main window."""
        super().__init__()
        self.setWindowTitle("Celestron NexStar Telescope Control")
        self.setMinimumSize(800, 600)

        # Telescope connection state
        self.telescope: NexStarTelescope | None = None

        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Create telescope control panel
        control_panel = self._create_control_panel()
        main_layout.addWidget(control_panel)

        # Create status bar at bottom
        self._create_status_bar()

        # Setup update timer for status bar
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_status_bar)
        self.update_timer.start(1000)  # Update every second

        # Initial status update
        self._update_status_bar()

    def _create_control_panel(self) -> QWidget:
        """Create the telescope control panel with buttons."""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Control buttons
        button_layout = QHBoxLayout()

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self._on_connect)
        button_layout.addWidget(self.connect_btn)

        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.clicked.connect(self._on_disconnect)
        self.disconnect_btn.setEnabled(False)
        button_layout.addWidget(self.disconnect_btn)

        self.goto_btn = QPushButton("Goto")
        self.goto_btn.clicked.connect(self._on_goto)
        self.goto_btn.setEnabled(False)
        button_layout.addWidget(self.goto_btn)

        self.align_btn = QPushButton("Align")
        self.align_btn.clicked.connect(self._on_align)
        self.align_btn.setEnabled(False)
        button_layout.addWidget(self.align_btn)

        self.calibrate_btn = QPushButton("Calibrate")
        self.calibrate_btn.clicked.connect(self._on_calibrate)
        self.calibrate_btn.setEnabled(False)
        button_layout.addWidget(self.calibrate_btn)

        layout.addLayout(button_layout)

        # Planning and Catalog buttons (open separate windows)
        secondary_button_layout = QHBoxLayout()

        self.planning_btn = QPushButton("Planning")
        self.planning_btn.clicked.connect(self._on_planning)
        secondary_button_layout.addWidget(self.planning_btn)

        self.catalog_btn = QPushButton("Catalog")
        self.catalog_btn.clicked.connect(self._on_catalog)
        secondary_button_layout.addWidget(self.catalog_btn)

        layout.addLayout(secondary_button_layout)

        # Add stretch to push buttons to top
        layout.addStretch()

        return panel

    def _create_status_bar(self) -> None:
        """Create the status bar with GPS, date/time, and telescope position."""
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)

        # GPS status (left side, temporary, clickable)
        self.gps_label = ClickableLabel()
        self.gps_label.setStyleSheet("color: black;")
        self.gps_label.setTextFormat(Qt.TextFormat.RichText)  # Enable HTML formatting
        self.gps_label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.gps_label.clicked.connect(self._on_gps_clicked)
        status_bar.addWidget(self.gps_label)

        # Vertical separator
        separator = QLabel("|")
        separator.setStyleSheet("color: gray;")
        status_bar.addWidget(separator)

        # Date & Time (left side, temporary, clickable, next to GPS)
        self.datetime_label = ClickableLabel()
        self.datetime_label.setStyleSheet("color: black;")
        self.datetime_label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.datetime_label.clicked.connect(self._on_datetime_clicked)
        status_bar.addWidget(self.datetime_label)

        # Add spacer to push permanent widgets to the right
        status_bar.addPermanentWidget(QLabel(""))  # Empty label as spacer

        # Telescope position (right side, permanent)
        self.position_label = QLabel("Position: --")
        status_bar.addPermanentWidget(self.position_label)

    def _update_status_bar(self) -> None:
        """Update the status bar with current information."""
        # Update GPS status
        self._update_gps_status()

        # Update date & time (without label prefix)
        try:
            location = get_observer_location()
            now = datetime.now(UTC)  # Use UTC time, then convert to local
            time_str = format_local_time(now, location.latitude, location.longitude)
            # Extract just the time part (remove date if needed, or show full string)
            self.datetime_label.setText(time_str)
        except Exception as e:
            # Log error for debugging
            import logging

            logger = logging.getLogger(__name__)
            logger.debug(f"Error updating date/time: {e}", exc_info=True)
            # Fallback to simple time display
            try:
                now = datetime.now()
                time_str = now.strftime("%Y-%m-%d %I:%M %p")
                self.datetime_label.setText(time_str)
            except Exception:
                self.datetime_label.setText("--")

        # Update telescope position if connected
        if self.telescope and self.telescope.protocol.is_open():
            try:
                coords = self.telescope.get_position_ra_dec()
                self.position_label.setText(f"Position: RA {coords.ra_hours:.4f}h, Dec {coords.dec_degrees:+.4f}°")
            except Exception:
                self.position_label.setText("Position: --")
        else:
            self.position_label.setText("Position: --")

    def _update_gps_status(self) -> None:
        """Update GPS status indicator color based on connection and GPS availability."""
        # Default: red (not connected or no GPS)
        icon_color = "red"

        # Check if telescope is connected
        if self.telescope and self.telescope.protocol.is_open():
            try:
                location_result = self.telescope.get_location()
                if location_result:
                    lat = location_result.latitude
                    lon = location_result.longitude
                    # Check if GPS coordinates are valid (not 0,0)
                    icon_color = "green" if lat != 0.0 and lon != 0.0 else "yellow"
            except Exception:
                # Red: Error reading GPS
                icon_color = "red"
        else:
            # Red: Not connected
            icon_color = "red"

        # Set text with HTML formatting: black text, colored icon
        status_text = f'GPS: <span style="color: {icon_color};">●</span>'
        self.gps_label.setText(status_text)

    def _on_gps_clicked(self) -> None:
        """Handle GPS status label click - opens GPS info dialog."""
        dialog = GPSInfoDialog(self, self.telescope)
        dialog.exec()

    def _on_datetime_clicked(self) -> None:
        """Handle date/time label click - opens time info dialog."""
        dialog = TimeInfoDialog(self, self.telescope)
        dialog.exec()

    def _on_connect(self) -> None:
        """Handle connect button click."""
        # TODO: Open connection dialog
        # For now, just enable/disable buttons
        self.connect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(True)
        self.goto_btn.setEnabled(True)
        self.align_btn.setEnabled(True)
        self.calibrate_btn.setEnabled(True)

    def _on_disconnect(self) -> None:
        """Handle disconnect button click."""
        if self.telescope:
            with contextlib.suppress(Exception):
                self.telescope.disconnect()

            self.telescope = None

        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)
        self.goto_btn.setEnabled(False)
        self.align_btn.setEnabled(False)
        self.calibrate_btn.setEnabled(False)

    def _on_goto(self) -> None:
        """Handle goto button click."""
        # TODO: Open goto dialog
        pass

    def _on_align(self) -> None:
        """Handle align button click."""
        # TODO: Open alignment dialog
        pass

    def _on_calibrate(self) -> None:
        """Handle calibrate button click."""
        # TODO: Open calibration dialog
        pass

    def _on_planning(self) -> None:
        """Handle planning button click - opens planning window."""
        # TODO: Open planning window
        pass

    def _on_catalog(self) -> None:
        """Handle catalog button click - opens catalog window."""
        # TODO: Open catalog window
        pass

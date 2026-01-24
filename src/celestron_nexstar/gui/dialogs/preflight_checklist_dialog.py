from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from celestron_nexstar.api.location.observer import get_observer_location


logger = logging.getLogger(__name__)


class PreflightChecklistDialog(QDialog):
    """Dialog to show a pre-flight checklist for observing."""

    def __init__(self, parent: Any, telescope: Any | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pre-Flight Checklist")
        self.setMinimumWidth(700)
        self.setMinimumHeight(420)
        self.telescope = telescope

        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Check", "Status", "Details"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSortingEnabled(False)
        layout.addWidget(self.table)

        actions_layout = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        actions_layout.addWidget(self.refresh_button)

        self.location_button = QPushButton("Open Location Settings")
        self.location_button.clicked.connect(self._open_location_settings)
        actions_layout.addWidget(self.location_button)

        self.connect_button = QPushButton("Connect Telescope")
        self.connect_button.clicked.connect(self._open_telescope_connection)
        actions_layout.addWidget(self.connect_button)

        actions_layout.addStretch(1)
        layout.addLayout(actions_layout)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.refresh()

    def _status_color(self, status: str) -> QColor:
        if status == "OK":
            return QColor("#2e7d32")
        if status == "WARN":
            return QColor("#f57c00")
        return QColor("#c62828")

    def _add_row(self, label: str, status: str, details: str) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)

        label_item = QTableWidgetItem(label)
        status_item = QTableWidgetItem(status)
        details_item = QTableWidgetItem(details)

        status_item.setForeground(self._status_color(status))
        status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        self.table.setItem(row, 0, label_item)
        self.table.setItem(row, 1, status_item)
        self.table.setItem(row, 2, details_item)

    def refresh(self) -> None:
        """Refresh checklist items."""
        self.table.setRowCount(0)

        # Location
        try:
            location = get_observer_location()
            lat = float(location.latitude)
            lon = float(location.longitude)
            if lat == 0.0 and lon == 0.0:
                self._add_row("Observer Location", "WARN", "Location is set to 0,0 (check configuration).")
            else:
                self._add_row("Observer Location", "OK", f"Lat {lat:.4f}, Lon {lon:.4f}")
        except Exception as exc:
            logger.debug("Location check failed", exc_info=True)
            self._add_row("Observer Location", "FAIL", f"Unavailable ({exc!s}).")

        # Time
        try:
            from celestron_nexstar.api.core.utils import get_local_timezone
            from celestron_nexstar.api.observation.observation_planner import ObservationPlanner

            planner = ObservationPlanner()
            conditions = planner.get_tonight_conditions()
            tz = get_local_timezone(conditions.latitude, conditions.longitude)
            local_time = conditions.timestamp.astimezone(tz)
            self._add_row("Observation Time", "OK", local_time.strftime("%Y-%m-%d %H:%M %Z"))
        except Exception as exc:
            logger.debug("Time check failed", exc_info=True)
            self._add_row("Observation Time", "WARN", f"Using system time ({exc!s}).")

        # Ephemeris
        try:
            from celestron_nexstar.api.ephemeris.ephemeris_manager import get_ephemeris_directory

            ephemeris_dir = get_ephemeris_directory()
            preferred = ["de421.bsp", "de440.bsp", "de421_2001.bsp"]
            found = next((name for name in preferred if (ephemeris_dir / name).exists()), None)
            if found:
                self._add_row("Ephemeris", "OK", f"{found} available")
            else:
                self._add_row("Ephemeris", "WARN", f"No BSP found in {ephemeris_dir}")
        except Exception as exc:
            logger.debug("Ephemeris check failed", exc_info=True)
            self._add_row("Ephemeris", "WARN", f"Unavailable ({exc!s}).")

        # Telescope connection
        try:
            if self.telescope and self.telescope.protocol.is_open():
                self._add_row("Telescope Connection", "OK", "Connected.")
            else:
                self._add_row("Telescope Connection", "WARN", "Not connected.")
        except Exception as exc:
            logger.debug("Telescope connection check failed", exc_info=True)
            self._add_row("Telescope Connection", "WARN", f"Unknown ({exc!s}).")

        # Alignment
        try:
            if self.telescope and self.telescope.protocol.is_open():
                self._add_row("Alignment", "WARN", "Alignment status not available yet.")
            else:
                self._add_row("Alignment", "WARN", "Connect telescope to verify alignment.")
        except Exception as exc:
            logger.debug("Alignment check failed", exc_info=True)
            self._add_row("Alignment", "WARN", f"Unavailable ({exc!s}).")

        self.table.resizeColumnsToContents()

    def _open_location_settings(self) -> None:
        """Open the location configuration dialog."""
        try:
            from celestron_nexstar.gui.dialogs.location_config_dialog import LocationConfigDialog

            dialog = LocationConfigDialog(self)
            dialog.exec()
            self.refresh()
        except Exception as exc:
            logger.debug("Failed to open location settings", exc_info=True)
            self._add_row("Location Settings", "FAIL", f"Failed to open ({exc!s}).")

    def _open_telescope_connection(self) -> None:
        """Open the telescope connection dialog."""
        try:
            from celestron_nexstar.gui.dialogs.telescope_connection_dialog import TelescopeConnectionDialog

            dialog = TelescopeConnectionDialog(self)
            dialog.exec()
            self.refresh()
        except Exception as exc:
            logger.debug("Failed to open telescope connection dialog", exc_info=True)
            self._add_row("Telescope Connection", "FAIL", f"Failed to open ({exc!s}).")

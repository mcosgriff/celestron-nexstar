"""
Observation Log Dialog

Dialog to view and manage observation logs.
"""

import asyncio
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from celestron_nexstar.api.database.database import get_database
from celestron_nexstar.api.observations import delete_observation, get_observations
from celestron_nexstar.gui.dialogs.observation_edit_dialog import ObservationEditDialog


if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


class ObservationLogDialog(QDialog):
    """Dialog to view and manage observation logs."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the observation log dialog."""
        super().__init__(parent)
        self.setWindowTitle("Observation Log")
        self.setMinimumWidth(900)
        self.setMinimumHeight(500)
        self.resize(1000, 600)

        # Create layout
        layout = QVBoxLayout(self)

        # Header
        header_label = QLabel("Observation Log")
        header_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(header_label)

        # Create table
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        header_labels = ["Date/Time", "Object", "Type", "Rating", "Location", "Telescope", "Notes", "Actions"]
        self.table.setHorizontalHeaderLabels(header_labels)

        # Set column resize modes - all columns are resizable with minimum width based on header text
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)

        # Calculate minimum widths based on header text
        font_metrics = QFontMetrics(header.font())
        min_widths = [font_metrics.horizontalAdvance(label) + 20 for label in header_labels]  # Add 20px padding

        # Set all columns to Interactive mode (resizable) and set minimum widths
        for col in range(self.table.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            header.setMinimumSectionSize(min_widths[col])

        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table)

        # Add button box
        button_layout = QHBoxLayout()
        new_button = QPushButton("New Observation")
        new_button.setToolTip("Create a new observation log entry")
        new_button.clicked.connect(self._on_new_observation)
        button_layout.addWidget(new_button)
        button_layout.addStretch()

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        button_layout.addWidget(button_box)
        layout.addLayout(button_layout)

        # Load observations
        self._load_observations()

    def _load_observations(self) -> None:
        """Load observations from database and populate table."""
        try:
            observations = asyncio.run(get_observations(limit=1000))
            self.table.setRowCount(len(observations))

            for row, obs in enumerate(observations):
                # Date/Time
                obs_time = obs.observed_at
                if obs_time.tzinfo:
                    # Convert to local time for display

                    local_time = obs_time.astimezone()
                    time_str = local_time.strftime("%Y-%m-%d %H:%M")
                else:
                    time_str = obs_time.strftime("%Y-%m-%d %H:%M")
                time_item = QTableWidgetItem(time_str)
                time_item.setData(Qt.ItemDataRole.UserRole, obs.id)  # Store observation ID
                self.table.setItem(row, 0, time_item)

                # Get object name from database
                object_name = self._get_object_name(obs.object_type, obs.object_id)
                name_item = QTableWidgetItem(object_name)
                self.table.setItem(row, 1, name_item)

                # Type
                type_item = QTableWidgetItem(obs.object_type)
                self.table.setItem(row, 2, type_item)

                # Rating
                rating_str = "★" * (obs.rating or 0) if obs.rating else "-"
                rating_item = QTableWidgetItem(rating_str)
                self.table.setItem(row, 3, rating_item)

                # Location
                location_str = (
                    obs.location_name or f"{obs.location_lat:.2f}, {obs.location_lon:.2f}"
                    if obs.location_lat and obs.location_lon
                    else "-"
                )
                location_item = QTableWidgetItem(location_str)
                self.table.setItem(row, 4, location_item)

                # Telescope
                telescope_str = obs.telescope or "-"
                telescope_item = QTableWidgetItem(telescope_str)
                self.table.setItem(row, 5, telescope_item)

                # Notes (truncated)
                notes_str = (obs.notes or "")[:50] + "..." if obs.notes and len(obs.notes) > 50 else (obs.notes or "-")
                notes_item = QTableWidgetItem(notes_str)
                self.table.setItem(row, 6, notes_item)

                # Actions
                actions_widget = QWidget()
                actions_layout = QHBoxLayout(actions_widget)
                actions_layout.setContentsMargins(2, 2, 2, 2)

                edit_button = QPushButton("Edit")
                edit_button.setToolTip("Edit observation")
                edit_button.clicked.connect(lambda checked, obs_id=obs.id: self._on_edit_observation(obs_id))
                actions_layout.addWidget(edit_button)

                delete_button = QPushButton("Delete")
                delete_button.setToolTip("Delete observation")
                delete_button.clicked.connect(lambda checked, obs_id=obs.id: self._on_delete_observation(obs_id))
                actions_layout.addWidget(delete_button)

                actions_layout.addStretch()
                self.table.setCellWidget(row, 7, actions_widget)

            # Sort by date descending by default
            self.table.sortItems(0, Qt.SortOrder.DescendingOrder)

            # Resize columns to contents after initial population
            header = self.table.horizontalHeader()
            # Temporarily switch to ResizeToContents to set initial sizes
            for col in range(self.table.columnCount()):
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
            # Force a resize event
            self.table.resizeColumnsToContents()
            # Switch back to Interactive mode for manual resizing
            for col in range(self.table.columnCount()):
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        except Exception as e:
            logger.error(f"Error loading observations: {e}", exc_info=True)

    def _get_object_name(self, object_type: str, object_id: int) -> str:
        """Get object name from database."""
        try:
            from celestron_nexstar.api.core.enums import CelestialObjectType

            db = get_database()
            obj = asyncio.run(db.get_by_id(object_id, CelestialObjectType(object_type)))
            if obj:
                return obj.common_name or obj.name
            return f"{object_type} #{object_id}"
        except Exception:
            return f"{object_type} #{object_id}"

    def _on_new_observation(self) -> None:
        """Handle new observation button click."""
        dialog = ObservationEditDialog(self)
        if dialog.exec():
            # Reload observations
            self._load_observations()

    def _on_edit_observation(self, observation_id: int) -> None:
        """Handle edit observation button click."""
        dialog = ObservationEditDialog(self, observation_id=observation_id)
        if dialog.exec():
            # Reload observations
            self._load_observations()

    def _on_delete_observation(self, observation_id: int) -> None:
        """Handle delete observation button click."""
        from PySide6.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            self,
            "Delete Observation",
            "Are you sure you want to delete this observation?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            success = asyncio.run(delete_observation(observation_id))
            if success:
                self._load_observations()
            else:
                QMessageBox.warning(self, "Error", "Failed to delete observation.")

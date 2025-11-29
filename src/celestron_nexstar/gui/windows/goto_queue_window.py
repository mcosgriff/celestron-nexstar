"""
Goto Queue/Sequence Window

Manages a queue of objects for automatic slewing with sequence planning and auto-advance.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from celestron_nexstar.api.catalogs.catalogs import CelestialObject
from celestron_nexstar.api.core.utils import angular_separation, format_dec, format_ra
from celestron_nexstar.api.observation.visibility import get_object_altitude_azimuth


if TYPE_CHECKING:
    from celestron_nexstar import NexStarTelescope

logger = logging.getLogger(__name__)


@dataclass
class QueuedObject:
    """Represents an object in the goto queue."""

    object: CelestialObject
    added_at: datetime
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "object": {
                "name": self.object.name,
                "common_name": self.object.common_name,
                "ra_hours": self.object.ra_hours,
                "dec_degrees": self.object.dec_degrees,
                "magnitude": self.object.magnitude,
                "object_type": self.object.object_type.value
                if hasattr(self.object.object_type, "value")
                else str(self.object.object_type),
                "catalog": self.object.catalog,
            },
            "added_at": self.added_at.isoformat(),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QueuedObject:
        """Create from dictionary."""
        from celestron_nexstar.api.core.enums import CelestialObjectType

        obj_data = data["object"]
        obj = CelestialObject(
            name=obj_data["name"],
            common_name=obj_data.get("common_name"),
            ra_hours=obj_data["ra_hours"],
            dec_degrees=obj_data["dec_degrees"],
            magnitude=obj_data.get("magnitude"),
            object_type=CelestialObjectType(obj_data["object_type"]),
            catalog=obj_data["catalog"],
        )
        return cls(
            object=obj,
            added_at=datetime.fromisoformat(data["added_at"]),
            notes=data.get("notes", ""),
        )


class GotoQueueWindow(QMainWindow):
    """Window for managing goto queue/sequence."""

    # Signal emitted when queue changes
    queue_changed = Signal()

    def __init__(self, parent: QWidget | None = None, telescope: NexStarTelescope | None = None) -> None:
        """Initialize the goto queue window."""
        super().__init__(parent)
        self.setWindowTitle("Goto Queue / Sequence")
        self.setMinimumWidth(900)
        self.setMinimumHeight(600)

        self.telescope = telescope
        self.queue: list[QueuedObject] = []
        self.current_index: int = -1  # -1 means not started
        self.is_running = False
        self.is_paused = False

        # Auto-advance timer
        self.auto_advance_timer = QTimer()
        self.auto_advance_timer.timeout.connect(self._on_auto_advance_timeout)
        self.auto_advance_delay_seconds = 60  # Default: 60 seconds

        # Slew completion check timer
        self.slew_check_timer = QTimer()
        self.slew_check_timer.timeout.connect(self._check_slew_completion)
        self.slew_check_timer.setInterval(1000)  # Check every second

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Controls toolbar
        controls_layout = QHBoxLayout()

        # Start/Pause/Stop buttons
        self.start_button = QPushButton("Start Sequence")
        self.start_button.clicked.connect(self._on_start_clicked)
        controls_layout.addWidget(self.start_button)

        self.pause_button = QPushButton("Pause")
        self.pause_button.setEnabled(False)
        self.pause_button.clicked.connect(self._on_pause_clicked)
        controls_layout.addWidget(self.pause_button)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._on_stop_clicked)
        controls_layout.addWidget(self.stop_button)

        controls_layout.addSpacing(20)

        # Skip button
        self.skip_button = QPushButton("Skip Current")
        self.skip_button.setEnabled(False)
        self.skip_button.clicked.connect(self._on_skip_clicked)
        controls_layout.addWidget(self.skip_button)

        controls_layout.addStretch()

        # Auto-advance controls
        auto_advance_label = QLabel("Auto-advance delay (seconds):")
        controls_layout.addWidget(auto_advance_label)

        self.auto_advance_spinbox = QSpinBox()
        self.auto_advance_spinbox.setMinimum(10)
        self.auto_advance_spinbox.setMaximum(3600)
        self.auto_advance_spinbox.setValue(60)
        self.auto_advance_spinbox.setSuffix(" s")
        self.auto_advance_spinbox.valueChanged.connect(self._on_auto_advance_delay_changed)
        controls_layout.addWidget(self.auto_advance_spinbox)

        controls_layout.addSpacing(20)

        # Sequence planning button
        self.plan_button = QPushButton("Optimize Sequence")
        self.plan_button.clicked.connect(self._on_plan_sequence_clicked)
        controls_layout.addWidget(self.plan_button)

        # Save/Load buttons
        self.save_button = QPushButton("Save Queue")
        self.save_button.clicked.connect(self._on_save_queue_clicked)
        controls_layout.addWidget(self.save_button)

        self.load_button = QPushButton("Load Queue")
        self.load_button.clicked.connect(self._on_load_queue_clicked)
        controls_layout.addWidget(self.load_button)

        layout.addLayout(controls_layout)

        # Queue table
        self.queue_table = QTableWidget()
        self.queue_table.setColumnCount(6)
        self.queue_table.setHorizontalHeaderLabels(["#", "Name", "Type", "RA", "Dec", "Status"])
        self.queue_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.queue_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.queue_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.queue_table.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.queue_table.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.queue_table.setDragEnabled(True)
        self.queue_table.setAcceptDrops(True)
        self.queue_table.setDropIndicatorShown(True)
        self.queue_table.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.queue_table.model().rowsMoved.connect(self._on_rows_moved)  # type: ignore[attr-defined]
        layout.addWidget(self.queue_table)

        # Status label
        self.status_label = QLabel("Queue is empty. Add objects from the main window.")
        layout.addWidget(self.status_label)

        # Action buttons
        buttons_layout = QHBoxLayout()

        self.remove_button = QPushButton("Remove Selected")
        self.remove_button.clicked.connect(self._on_remove_clicked)
        buttons_layout.addWidget(self.remove_button)

        self.clear_button = QPushButton("Clear Queue")
        self.clear_button.clicked.connect(self._on_clear_clicked)
        buttons_layout.addWidget(self.clear_button)

        buttons_layout.addStretch()

        layout.addLayout(buttons_layout)

        # Update UI
        self._update_queue_table()
        self._update_status()

    def add_object(self, obj: CelestialObject, notes: str = "") -> None:
        """Add an object to the queue."""
        queued_obj = QueuedObject(object=obj, added_at=datetime.now(UTC), notes=notes)
        self.queue.append(queued_obj)
        self._update_queue_table()
        self._update_status()
        self.queue_changed.emit()

    def _update_queue_table(self) -> None:
        """Update the queue table display."""
        self.queue_table.setRowCount(len(self.queue))

        for i, queued_obj in enumerate(self.queue):
            obj = queued_obj.object

            # Index
            index_item = QTableWidgetItem(str(i + 1))
            index_item.setData(Qt.ItemDataRole.UserRole, i)
            self.queue_table.setItem(i, 0, index_item)

            # Name
            display_name = obj.common_name or obj.name
            name_item = QTableWidgetItem(display_name)
            name_item.setData(Qt.ItemDataRole.UserRole, queued_obj)
            self.queue_table.setItem(i, 1, name_item)

            # Type
            type_str = obj.object_type.value if hasattr(obj.object_type, "value") else str(obj.object_type)
            type_item = QTableWidgetItem(type_str)
            self.queue_table.setItem(i, 2, type_item)

            # RA
            ra_str = format_ra(obj.ra_hours) if obj.ra_hours is not None else "N/A"
            ra_item = QTableWidgetItem(ra_str)
            self.queue_table.setItem(i, 3, ra_item)

            # Dec
            dec_str = format_dec(obj.dec_degrees) if obj.dec_degrees is not None else "N/A"
            dec_item = QTableWidgetItem(dec_str)
            self.queue_table.setItem(i, 4, dec_item)

            # Status
            if i == self.current_index:
                status_item = QTableWidgetItem("▶ Current")
                status_item.setForeground(Qt.GlobalColor.green)
            elif i < self.current_index:
                status_item = QTableWidgetItem("✓ Done")
                status_item.setForeground(Qt.GlobalColor.gray)
            else:
                status_item = QTableWidgetItem("Pending")
            self.queue_table.setItem(i, 5, status_item)

        # Resize columns to content
        self.queue_table.resizeColumnsToContents()

    def _update_status(self) -> None:
        """Update status label."""
        if not self.queue:
            self.status_label.setText("Queue is empty. Add objects from the main window.")
            return

        if self.current_index < 0:
            self.status_label.setText(f"Queue has {len(self.queue)} object(s). Click 'Start Sequence' to begin.")
        elif self.current_index >= len(self.queue):
            self.status_label.setText("Sequence complete! All objects have been visited.")
        else:
            current_obj = self.queue[self.current_index].object
            display_name = current_obj.common_name or current_obj.name
            remaining = len(self.queue) - self.current_index - 1
            if self.is_paused:
                self.status_label.setText(f"Paused at: {display_name} ({remaining} remaining)")
            elif self.is_running:
                self.status_label.setText(f"Current: {display_name} ({remaining} remaining)")
            else:
                self.status_label.setText(f"Stopped at: {display_name} ({remaining} remaining)")

    def _on_start_clicked(self) -> None:
        """Handle start button click."""
        if not self.queue:
            QMessageBox.warning(self, "Empty Queue", "Queue is empty. Add objects before starting.")
            return

        if not self.telescope:
            QMessageBox.warning(self, "No Telescope", "Telescope is not connected.")
            return

        if self.current_index < 0:
            # Start from beginning
            self.current_index = 0
        # else: resume from current position

        self.is_running = True
        self.is_paused = False
        self.start_button.setEnabled(False)
        self.pause_button.setEnabled(True)
        self.stop_button.setEnabled(True)
        self.skip_button.setEnabled(True)

        self._goto_current_object()

    def _on_pause_clicked(self) -> None:
        """Handle pause button click."""
        self.is_paused = True
        self.is_running = False
        self.auto_advance_timer.stop()
        self.slew_check_timer.stop()
        self.start_button.setEnabled(True)
        self.start_button.setText("Resume")
        self.pause_button.setEnabled(False)
        self._update_status()

    def _on_stop_clicked(self) -> None:
        """Handle stop button click."""
        self.is_running = False
        self.is_paused = False
        self.auto_advance_timer.stop()
        self.slew_check_timer.stop()
        self.start_button.setEnabled(True)
        self.start_button.setText("Start Sequence")
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.skip_button.setEnabled(False)
        self._update_status()

    def _on_skip_clicked(self) -> None:
        """Handle skip button click."""
        if self.current_index >= 0 and self.current_index < len(self.queue):
            self._advance_to_next()

    def _on_auto_advance_delay_changed(self, value: int) -> None:
        """Handle auto-advance delay change."""
        self.auto_advance_delay_seconds = value

    def _on_plan_sequence_clicked(self) -> None:
        """Handle optimize sequence button click."""
        if len(self.queue) < 2:
            QMessageBox.information(self, "Not Enough Objects", "Need at least 2 objects to optimize sequence.")
            return

        # Optimize sequence
        self._optimize_sequence()
        QMessageBox.information(self, "Sequence Optimized", "Queue order has been optimized for efficient observing.")

    def _on_save_queue_clicked(self) -> None:
        """Handle save queue button click."""
        if not self.queue:
            QMessageBox.warning(self, "Empty Queue", "Queue is empty. Nothing to save.")
            return

        from PySide6.QtWidgets import QFileDialog

        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Queue", "", "JSON Files (*.json);;All Files (*)", "JSON Files (*.json)"
        )
        if filename:
            try:
                queue_data = [qo.to_dict() for qo in self.queue]
                with Path(filename).open("w") as f:
                    json.dump(queue_data, f, indent=2)
                QMessageBox.information(self, "Queue Saved", f"Queue saved to {filename}")
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Failed to save queue: {e}")

    def _on_load_queue_clicked(self) -> None:
        """Handle load queue button click."""
        from PySide6.QtWidgets import QFileDialog

        filename, _ = QFileDialog.getOpenFileName(
            self, "Load Queue", "", "JSON Files (*.json);;All Files (*)", "JSON Files (*.json)"
        )
        if filename:
            try:
                with Path(filename).open("r") as f:
                    queue_data = json.load(f)
                self.queue = [QueuedObject.from_dict(qo_data) for qo_data in queue_data]
                self.current_index = -1
                self._on_stop_clicked()  # Reset state
                self._update_queue_table()
                self._update_status()
                self.queue_changed.emit()
                QMessageBox.information(self, "Queue Loaded", f"Loaded {len(self.queue)} objects from {filename}")
            except Exception as e:
                QMessageBox.critical(self, "Load Error", f"Failed to load queue: {e}")

    def _on_remove_clicked(self) -> None:
        """Handle remove button click."""
        selected_rows = self.queue_table.selectionModel().selectedRows()
        if not selected_rows:
            return

        # Remove in reverse order to maintain indices
        rows_to_remove = sorted([row.row() for row in selected_rows], reverse=True)
        for row in rows_to_remove:
            if row <= self.current_index:
                self.current_index -= 1
            self.queue.pop(row)

        self._update_queue_table()
        self._update_status()
        self.queue_changed.emit()

    def _on_clear_clicked(self) -> None:
        """Handle clear button click."""
        if self.is_running:
            reply = QMessageBox.question(
                self,
                "Clear Queue",
                "Sequence is running. Stop and clear queue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            self._on_stop_clicked()

        self.queue.clear()
        self.current_index = -1
        self._update_queue_table()
        self._update_status()
        self.queue_changed.emit()

    def _on_item_double_clicked(self, item: QTableWidgetItem) -> None:
        """Handle item double-click - show object info."""
        queued_obj = item.data(Qt.ItemDataRole.UserRole)
        if not queued_obj or not isinstance(queued_obj, QueuedObject):
            return

        from celestron_nexstar.gui.dialogs.object_info_dialog import ObjectInfoDialog

        dialog = ObjectInfoDialog(self, queued_obj.object.name)
        dialog.exec()

    def _on_rows_moved(self, parent: Any, start: int, end: int, destination: int, row: int) -> None:
        """Handle rows moved (drag and drop reordering)."""
        # Reorder queue based on new table order
        new_queue: list[QueuedObject] = []
        for i in range(self.queue_table.rowCount()):
            name_item = self.queue_table.item(i, 1)
            if name_item:
                queued_obj = name_item.data(Qt.ItemDataRole.UserRole)
                if queued_obj and isinstance(queued_obj, QueuedObject):
                    new_queue.append(queued_obj)

        self.queue = new_queue
        self._update_queue_table()
        self.queue_changed.emit()

    def _goto_current_object(self) -> None:
        """Slew to the current object in the queue."""
        if self.current_index < 0 or self.current_index >= len(self.queue):
            self._on_stop_clicked()
            return

        if not self.telescope:
            QMessageBox.warning(self, "No Telescope", "Telescope is not connected.")
            self._on_stop_clicked()
            return

        queued_obj = self.queue[self.current_index]
        obj = queued_obj.object

        # Update position for dynamic objects
        obj = obj.with_current_position()

        display_name = obj.common_name or obj.name
        logger.info(f"Slewing to queue object {self.current_index + 1}/{len(self.queue)}: {display_name}")

        # Start slew
        try:
            success = asyncio.run(self.telescope.goto_ra_dec(obj.ra_hours, obj.dec_degrees))
            if not success:
                QMessageBox.warning(self, "Slew Failed", f"Failed to slew to {display_name}")
                self._advance_to_next()
                return

            # Start checking for slew completion
            self.slew_check_timer.start()
            self._update_queue_table()
            self._update_status()

        except Exception as e:
            logger.error(f"Error slewing to {display_name}: {e}", exc_info=True)
            QMessageBox.critical(self, "Slew Error", f"Error slewing to {display_name}: {e}")
            self._advance_to_next()

    def _check_slew_completion(self) -> None:
        """Check if current slew is complete."""
        if not self.telescope:
            return

        try:
            is_slewing = asyncio.run(self.telescope.is_slewing())
            if not is_slewing:
                # Slew complete
                self.slew_check_timer.stop()
                self._on_slew_complete()
        except Exception as e:
            logger.error(f"Error checking slew status: {e}", exc_info=True)

    def _on_slew_complete(self) -> None:
        """Handle slew completion."""
        if self.current_index >= 0 and self.current_index < len(self.queue):
            queued_obj = self.queue[self.current_index]
            obj = queued_obj.object
            display_name = obj.common_name or obj.name
            logger.info(f"Arrived at {display_name}")

        # Start auto-advance timer
        if self.is_running and not self.is_paused:
            self.auto_advance_timer.start(self.auto_advance_delay_seconds * 1000)

    def _on_auto_advance_timeout(self) -> None:
        """Handle auto-advance timer timeout."""
        self.auto_advance_timer.stop()
        self._advance_to_next()

    def _advance_to_next(self) -> None:
        """Advance to the next object in the queue."""
        self.current_index += 1

        if self.current_index >= len(self.queue):
            # Sequence complete
            self._on_stop_clicked()
            QMessageBox.information(self, "Sequence Complete", "All objects in the queue have been visited.")
            return

        # Goto next object
        self._goto_current_object()

    def _optimize_sequence(self) -> None:
        """
        Optimize the sequence order for efficient observing.

        Uses a greedy nearest-neighbor algorithm to minimize total travel distance.
        """
        if len(self.queue) < 2:
            return

        # Get observer location for altitude-based optimization
        from celestron_nexstar.api.location.observer import get_observer_location

        try:
            observer = get_observer_location()
            observer_lat = observer.latitude
            observer_lon = observer.longitude
        except Exception:
            observer_lat = None
            observer_lon = None

        # Create list of objects with current positions
        objects_with_positions: list[tuple[QueuedObject, float, float]] = []
        for queued_obj in self.queue:
            obj = queued_obj.object.with_current_position()
            objects_with_positions.append((queued_obj, obj.ra_hours, obj.dec_degrees))

        # Greedy nearest-neighbor algorithm
        optimized: list[QueuedObject] = []
        remaining = objects_with_positions.copy()

        # Start with the object that has highest altitude (if observer location available)
        if observer_lat is not None and observer_lon is not None:
            from datetime import datetime

            now = datetime.now(UTC)
            best_start_idx = 0
            best_alt = -90.0

            for i, (queued_obj, _, _) in enumerate(remaining):
                try:
                    alt, _az = get_object_altitude_azimuth(
                        queued_obj.object.with_current_position(), observer_lat, observer_lon, now
                    )
                    if alt > best_alt:
                        best_alt = alt
                        best_start_idx = i
                except Exception:
                    pass

            # Start with best altitude object
            start_obj = remaining.pop(best_start_idx)
            optimized.append(start_obj[0])
            current_ra, current_dec = start_obj[1], start_obj[2]
        else:
            # No observer location, start with first object
            start_obj = remaining.pop(0)
            optimized.append(start_obj[0])
            current_ra, current_dec = start_obj[1], start_obj[2]

        # Greedily select nearest remaining object
        while remaining:
            best_idx = 0
            best_distance = float("inf")

            for i, (_, ra, dec) in enumerate(remaining):
                distance = angular_separation(current_ra, current_dec, ra, dec)
                if distance < best_distance:
                    best_distance = distance
                    best_idx = i

            # Add nearest object
            next_obj = remaining.pop(best_idx)
            optimized.append(next_obj[0])
            current_ra, current_dec = next_obj[1], next_obj[2]

        # Update queue
        self.queue = optimized
        if self.current_index >= 0 and self.current_index < len(self.queue):
            # Try to preserve current object if possible
            current_obj = self.queue[self.current_index]
            # Find it in optimized list
            try:
                new_index = optimized.index(current_obj)
                self.current_index = new_index
            except ValueError:
                # Current object not found, reset
                self.current_index = -1

        self._update_queue_table()
        self._update_status()
        self.queue_changed.emit()

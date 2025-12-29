"""
Command History Dialog

View, filter, and replay telescope command history.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

    from celestron_nexstar.api.telescope.command_tracker import CommandTracker


class CommandHistoryDialog(QDialog):
    """
    Dialog for viewing and replaying telescope command history.

    Features:
    - Sortable table with columns: Timestamp, Command, Response, Duration, Status, Decoded
    - Filter by: All, Successful, Failed, Specific command
    - Replay single command (with safety confirmation)
    - Export selection or all to JSON
    - Clear history
    """

    def __init__(self, command_tracker: CommandTracker, parent: QWidget | None = None) -> None:
        """
        Initialize the command history dialog.

        Args:
            command_tracker: CommandTracker instance with command history
            parent: Parent widget
        """
        super().__init__(parent)
        self.command_tracker = command_tracker

        self.setWindowTitle("Telescope Command History")
        self.setMinimumSize(900, 600)

        self._setup_ui()
        self._load_history()

    def _setup_ui(self) -> None:
        """Set up the UI layout."""
        layout = QVBoxLayout(self)

        # Filter controls
        filter_layout = QHBoxLayout()

        filter_label = QLabel("Filter:")
        filter_layout.addWidget(filter_label)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "Successful", "Failed"])
        self.filter_combo.currentTextChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.filter_combo)

        filter_layout.addStretch()

        # Statistics label
        self.stats_label = QLabel()
        self._update_statistics()
        filter_layout.addWidget(self.stats_label)

        layout.addLayout(filter_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Timestamp", "Command", "Response", "Duration (ms)", "Status", "Decoded"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)

        # Resize columns
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Timestamp
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Command
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # Response
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Duration
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Status
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)  # Decoded

        layout.addWidget(self.table)

        # Buttons
        button_layout = QHBoxLayout()

        self.replay_btn = QPushButton("Replay Selected")
        self.replay_btn.clicked.connect(self._on_replay_clicked)
        self.replay_btn.setEnabled(False)
        button_layout.addWidget(self.replay_btn)

        self.export_btn = QPushButton("Export to JSON")
        self.export_btn.clicked.connect(self._on_export_clicked)
        button_layout.addWidget(self.export_btn)

        self.clear_btn = QPushButton("Clear History")
        self.clear_btn.clicked.connect(self._on_clear_clicked)
        button_layout.addWidget(self.clear_btn)

        button_layout.addStretch()

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.close_btn)

        layout.addLayout(button_layout)

        # Connect table selection
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

    def _load_history(self, filter_type: str | None = None) -> None:
        """
        Load command history into table.

        Args:
            filter_type: Filter to apply ('success', 'failed', or None for all)
        """
        # Clear table
        self.table.setRowCount(0)
        self.table.setSortingEnabled(False)  # Disable sorting during population

        # Get history
        history = self.command_tracker.get_history(filter_type=filter_type)

        # Populate table
        for record in history:
            row_index = self.table.rowCount()
            self.table.insertRow(row_index)

            # Timestamp
            timestamp_item = QTableWidgetItem(record.timestamp)
            timestamp_item.setFlags(timestamp_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row_index, 0, timestamp_item)

            # Command
            command_item = QTableWidgetItem(record.command)
            command_item.setFlags(command_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row_index, 1, command_item)

            # Response
            response_item = QTableWidgetItem(record.response or "")
            response_item.setFlags(response_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row_index, 2, response_item)

            # Duration
            duration_str = f"{record.duration_ms:.2f}" if record.duration_ms is not None else "N/A"
            duration_item = QTableWidgetItem(duration_str)
            duration_item.setFlags(duration_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row_index, 3, duration_item)

            # Status
            status_str = "✓ Success" if record.success else f"✗ Failed: {record.error or 'Unknown'}"
            status_item = QTableWidgetItem(status_str)
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            # Color-code status
            if record.success:
                status_item.setForeground(Qt.GlobalColor.darkGreen)
            else:
                status_item.setForeground(Qt.GlobalColor.red)

            self.table.setItem(row_index, 4, status_item)

            # Decoded
            decoded_item = QTableWidgetItem(record.decoded or "")
            decoded_item.setFlags(decoded_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row_index, 5, decoded_item)

        # Re-enable sorting
        self.table.setSortingEnabled(True)

        # Update statistics
        self._update_statistics()

    def _update_statistics(self) -> None:
        """Update statistics label."""
        stats = self.command_tracker.get_statistics()

        stats_text = (
            f"Total: {stats['total_commands']} | "
            f"Success: {stats['successful_commands']} | "
            f"Failed: {stats['failed_commands']} | "
            f"Success Rate: {stats['success_rate']:.1f}% | "
            f"Avg Duration: {stats['average_duration_ms']:.2f}ms"
        )

        self.stats_label.setText(stats_text)

    def _on_filter_changed(self, filter_text: str) -> None:
        """
        Handle filter change.

        Args:
            filter_text: Selected filter option
        """
        if filter_text == "All":
            self._load_history(filter_type=None)
        elif filter_text == "Successful":
            self._load_history(filter_type="success")
        elif filter_text == "Failed":
            self._load_history(filter_type="failed")

    def _on_selection_changed(self) -> None:
        """Handle table selection change."""
        selected_rows = self.table.selectedIndexes()
        self.replay_btn.setEnabled(len(selected_rows) > 0)

    def _on_replay_clicked(self) -> None:
        """Handle replay button click."""
        # Get selected row
        selected_rows = self.table.selectedIndexes()
        if not selected_rows:
            return

        row = selected_rows[0].row()

        # Get command
        command = self.table.item(row, 1).text()
        response = self.table.item(row, 2).text()
        decoded = self.table.item(row, 5).text()

        # Safety confirmation
        msg = QMessageBox(self)
        msg.setWindowTitle("Confirm Replay")
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setText("Are you sure you want to send this command to the telescope?")
        msg.setInformativeText(
            f"Command: {command}\n"
            f"Previous Response: {response}\n"
            f"{decoded if decoded else ''}\n\n"
            "This will control the telescope immediately!"
        )

        # Add checkbox for understanding
        understand_checkbox = QCheckBox("I understand this will control the telescope")
        msg.setCheckBox(understand_checkbox)

        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.No)

        result = msg.exec()

        if result != QMessageBox.StandardButton.Yes or not understand_checkbox.isChecked():
            return

        # TODO: Implement actual command replay (requires telescope instance)
        QMessageBox.information(
            self,
            "Replay Not Implemented",
            f"Command replay functionality will be implemented when integrated with telescope control.\n\n"
            f"Would replay: {command}",
        )

    def _on_export_clicked(self) -> None:
        """Handle export button click."""
        # Prompt for save location
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Command History",
            str(Path.home() / "telescope_commands.json"),
            "JSON Files (*.json);;All Files (*)",
        )

        if not file_path:
            return  # User cancelled

        try:
            self.command_tracker.export_to_json(Path(file_path))
            QMessageBox.information(
                self,
                "Export Successful",
                f"Command history exported to:\n{file_path}",
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Failed to export command history:\n{e!s}",
            )

    def _on_clear_clicked(self) -> None:
        """Handle clear history button click."""
        # Confirmation
        result = QMessageBox.question(
            self,
            "Clear History",
            "Are you sure you want to clear all command history?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if result == QMessageBox.StandardButton.Yes:
            self.command_tracker.clear_history()
            self._load_history()
            QMessageBox.information(self, "History Cleared", "Command history has been cleared.")

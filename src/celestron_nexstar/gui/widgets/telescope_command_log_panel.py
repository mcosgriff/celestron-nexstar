"""
Telescope Command Log Panel

Enhanced log panel with filtering, export, and command history access.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QSizePolicy,
)

from celestron_nexstar.gui.widgets.collapsible_log_panel import CollapsibleLogPanel


if TYPE_CHECKING:
    from celestron_nexstar.api.telescope.command_tracker import CommandTracker


class TelescopeCommandLogPanel(CollapsibleLogPanel):
    """
    Enhanced collapsible log panel with filtering and export capabilities.

    Extends CollapsibleLogPanel with:
    - Filter dropdown (All, Commands, Responses, Errors, Connection Events)
    - Show Timestamps checkbox
    - Export to JSON button
    - View History button (opens CommandHistoryDialog)
    """

    def __init__(
        self,
        command_tracker: CommandTracker | None = None,
        parent: object = None,
    ) -> None:
        """
        Initialize the telescope command log panel.

        Args:
            command_tracker: Optional CommandTracker instance for history/export
            parent: Parent widget
        """
        self.command_tracker = command_tracker
        super().__init__(parent)  # type: ignore[arg-type]

        # Add additional controls
        self._add_enhanced_controls()

    def _add_enhanced_controls(self) -> None:
        """Add filtering and export controls to the header."""
        # Get the header layout
        header_layout: QHBoxLayout = self.header.layout()  # type: ignore[assignment]

        # Find the clear button and insert controls before it
        clear_btn_index = header_layout.indexOf(self.clear_btn)

        # Filter combo box
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(
            [
                "All",
                "Commands",
                "Responses",
                "Errors",
                "Connection Events",
            ]
        )
        self.filter_combo.setToolTip("Filter log messages")
        self.filter_combo.setMinimumWidth(120)
        self.filter_combo.currentTextChanged.connect(self._on_filter_changed)
        header_layout.insertWidget(clear_btn_index, self.filter_combo)

        # Show timestamps checkbox
        self.timestamps_checkbox = QCheckBox("Timestamps")
        self.timestamps_checkbox.setChecked(True)
        self.timestamps_checkbox.setToolTip("Show/hide timestamps in log messages")
        self.timestamps_checkbox.stateChanged.connect(self._on_timestamps_toggled)
        header_layout.insertWidget(clear_btn_index + 1, self.timestamps_checkbox)

        # Export button
        self.export_btn = QPushButton("Export")
        self.export_btn.setMinimumWidth(60)
        self.export_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        self.export_btn.setToolTip("Export command history to JSON")
        self.export_btn.clicked.connect(self._on_export_clicked)
        self.export_btn.setEnabled(self.command_tracker is not None)
        header_layout.insertWidget(clear_btn_index + 2, self.export_btn)

        # History button
        self.history_btn = QPushButton("History")
        self.history_btn.setMinimumWidth(60)
        self.history_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        self.history_btn.setToolTip("View command history and replay commands")
        self.history_btn.clicked.connect(self._on_history_clicked)
        self.history_btn.setEnabled(self.command_tracker is not None)
        header_layout.insertWidget(clear_btn_index + 3, self.history_btn)

    def _on_filter_changed(self, filter_text: str) -> None:
        """
        Handle filter selection change.

        Args:
            filter_text: Selected filter option
        """
        # Get current log text
        full_text = self.log_text.toPlainText()
        lines = full_text.split("\n")

        # Apply filter
        filtered_lines = []
        for line in lines:
            if self._matches_filter(line, filter_text):
                filtered_lines.append(line)

        # Update display
        self.log_text.setPlainText("\n".join(filtered_lines))

    def _matches_filter(self, line: str, filter_text: str) -> bool:
        """
        Check if log line matches the selected filter.

        Args:
            line: Log line text
            filter_text: Filter option

        Returns:
            True if line matches filter
        """
        if filter_text == "All":
            return True

        line_lower = line.lower()

        if filter_text == "Commands":
            return "sending command:" in line_lower
        elif filter_text == "Responses":
            return "received response:" in line_lower
        elif filter_text == "Errors":
            return "[error]" in line_lower or "[warning]" in line_lower
        elif filter_text == "Connection Events":
            return any(keyword in line_lower for keyword in ["connection", "connected", "disconnected", "reconnect"])

        return True

    def _on_timestamps_toggled(self, state: int) -> None:
        """
        Handle timestamps checkbox toggle.

        Args:
            state: Checkbox state (Qt.Checked or Qt.Unchecked)
        """
        show_timestamps = state == 2  # Qt.Checked = 2

        # Update log handler formatter
        if show_timestamps:
            formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
        else:
            formatter = logging.Formatter("[%(levelname)s] %(name)s: %(message)s")

        self.log_handler.setFormatter(formatter)

        # Note: This only affects new log messages, not existing ones
        # To update existing messages, we'd need to re-process all log records

    def _on_export_clicked(self) -> None:
        """Handle export button click."""
        if not self.command_tracker:
            QMessageBox.warning(
                self,
                "Export Failed",
                "Command tracker not available. Cannot export history.",
            )
            return

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

    def _on_history_clicked(self) -> None:
        """Handle history button click."""
        if not self.command_tracker:
            QMessageBox.warning(
                self,
                "History Unavailable",
                "Command tracker not available. Cannot view history.",
            )
            return

        # Import here to avoid circular dependency
        from celestron_nexstar.gui.dialogs.command_history_dialog import CommandHistoryDialog

        # Open history dialog
        dialog = CommandHistoryDialog(self.command_tracker, self)
        dialog.exec()

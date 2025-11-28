"""
Favorites Dialog

Dialog to view and manage favorite celestial objects.
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

from celestron_nexstar.api.favorites import clear_favorites, get_favorites, remove_favorite
from celestron_nexstar.gui.dialogs.object_info_dialog import ObjectInfoDialog


if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


class FavoritesDialog(QDialog):
    """Dialog to view and manage favorite celestial objects."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the favorites dialog."""
        super().__init__(parent)
        self.setWindowTitle("Favorites")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        self.resize(700, 500)

        # Create layout
        layout = QVBoxLayout(self)

        # Header with clear button
        header_layout = QHBoxLayout()
        header_label = QLabel("Favorite Objects")
        header_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        header_layout.addWidget(header_label)
        header_layout.addStretch()

        clear_button = QPushButton("Clear All")
        clear_button.setToolTip("Remove all favorites")
        clear_button.clicked.connect(self._on_clear_all)
        header_layout.addWidget(clear_button)
        layout.addLayout(header_layout)

        # Create table
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        header_labels = ["Name", "Type", "Actions"]
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
        layout.addWidget(self.table)

        # Add button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Load favorites
        self._load_favorites()

    def _load_favorites(self) -> None:
        """Load favorites from database and populate table."""
        try:
            favorites = asyncio.run(get_favorites())
            self.table.setRowCount(len(favorites))

            for row, fav in enumerate(favorites):
                name = fav.get("name", "") or ""
                obj_type = fav.get("type", "") or ""

                # Name column
                name_item = QTableWidgetItem(name)
                self.table.setItem(row, 0, name_item)

                # Type column
                type_item = QTableWidgetItem(obj_type or "")
                self.table.setItem(row, 1, type_item)

                # Actions column
                actions_widget = QWidget()
                actions_layout = QHBoxLayout(actions_widget)
                actions_layout.setContentsMargins(4, 2, 4, 2)
                actions_layout.setSpacing(4)

                # Info button
                info_button = QPushButton("Info")
                info_button.setToolTip("Show object information")
                info_button.clicked.connect(lambda checked, n=name: self._on_info_clicked(n))
                actions_layout.addWidget(info_button)

                # Remove button
                remove_button = QPushButton("Remove")
                remove_button.setToolTip("Remove from favorites")
                remove_button.clicked.connect(lambda checked, n=name: self._on_remove_clicked(n))
                actions_layout.addWidget(remove_button)

                actions_layout.addStretch()
                self.table.setCellWidget(row, 2, actions_widget)

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

            if not favorites:
                # Show message if no favorites
                self.table.setRowCount(1)
                no_favs_item = QTableWidgetItem(
                    "No favorites yet. Add objects to favorites from the object info dialog."
                )
                no_favs_item.setFlags(Qt.ItemFlag.NoItemFlags)  # Make it non-selectable
                no_favs_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(0, 0, no_favs_item)
                self.table.setSpan(0, 0, 1, 3)  # Span across all columns

        except Exception as e:
            logger.error(f"Error loading favorites: {e}", exc_info=True)

    def _on_info_clicked(self, object_name: str) -> None:
        """Handle info button click - show object information."""
        try:
            dialog = ObjectInfoDialog(self, object_name)
            dialog.exec()
            # Reload favorites in case it was removed from info dialog
            self._load_favorites()
        except Exception as e:
            logger.error(f"Error showing object info: {e}", exc_info=True)

    def _on_remove_clicked(self, object_name: str) -> None:
        """Handle remove button click - remove from favorites."""
        try:
            success = asyncio.run(remove_favorite(object_name))
            if success:
                self._load_favorites()
        except Exception as e:
            logger.error(f"Error removing favorite: {e}", exc_info=True)

    def _on_clear_all(self) -> None:
        """Handle clear all button click."""
        from PySide6.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            self,
            "Clear All Favorites",
            "Are you sure you want to remove all favorites?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                success = asyncio.run(clear_favorites())
                if success:
                    self._load_favorites()
            except Exception as e:
                logger.error(f"Error clearing favorites: {e}", exc_info=True)

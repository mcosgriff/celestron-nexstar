"""
Object Comparison Tool Dialog

Side-by-side comparison of celestial objects to help choose between similar objects.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from celestron_nexstar.api.catalogs.catalogs import CelestialObject, search_objects
from celestron_nexstar.api.core.utils import format_dec, format_ra
from celestron_nexstar.api.observation.planning_utils import DifficultyLevel, get_object_difficulty
from celestron_nexstar.api.observation.visibility import VisibilityInfo, assess_visibility


if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ObjectComparisonDialog(QDialog):
    """Dialog for comparing celestial objects side-by-side."""

    def __init__(self, parent: QWidget | None = None, initial_objects: list[str] | None = None) -> None:
        """Initialize the object comparison dialog."""
        super().__init__(parent)
        self.setWindowTitle("Object Comparison Tool")
        self.setMinimumWidth(1000)
        self.setMinimumHeight(600)

        self.objects_to_compare: list[CelestialObject] = []
        self.visibility_data: list[VisibilityInfo] = []
        self.difficulty_data: list[DifficultyLevel] = []

        # Main layout
        main_layout = QVBoxLayout(self)

        # Controls toolbar
        controls_layout = QHBoxLayout()

        # Search/Add object
        controls_layout.addWidget(QLabel("Add Object:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search for object name...")
        self.search_input.returnPressed.connect(self._on_add_object)
        controls_layout.addWidget(self.search_input)

        add_button = QPushButton("Add")
        add_button.clicked.connect(self._on_add_object)
        controls_layout.addWidget(add_button)

        controls_layout.addSpacing(20)

        # Remove button
        self.remove_button = QPushButton("Remove Selected")
        self.remove_button.clicked.connect(self._on_remove_clicked)
        controls_layout.addWidget(self.remove_button)

        # Clear button
        self.clear_button = QPushButton("Clear All")
        self.clear_button.clicked.connect(self._on_clear_clicked)
        controls_layout.addWidget(self.clear_button)

        controls_layout.addStretch()

        main_layout.addLayout(controls_layout)

        # Comparison table
        self.comparison_table = QTableWidget()
        self.comparison_table.setColumnCount(0)  # Will be set dynamically
        self.comparison_table.setRowCount(0)  # Will be set dynamically
        self.comparison_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.comparison_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.comparison_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        main_layout.addWidget(self.comparison_table)

        # Status label
        self.status_label = QLabel("Add objects to compare. Search for objects by name and click 'Add'.")
        main_layout.addWidget(self.status_label)

        # Button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

        # Add initial objects if provided
        if initial_objects:
            for obj_name in initial_objects:
                self._add_object_by_name(obj_name)

    def _on_add_object(self) -> None:
        """Handle add object button click."""
        query = self.search_input.text().strip()
        if not query:
            return

        self._add_object_by_name(query)
        self.search_input.clear()

    def _add_object_by_name(self, object_name: str) -> None:
        """Add an object to the comparison by name."""
        try:
            # Search for object
            matches = asyncio.run(search_objects(object_name, update_positions=True))
            if not matches:
                QMessageBox.warning(self, "Object Not Found", f"Could not find object: {object_name}")
                return

            # Use first match
            obj, _match_type = matches[0]
            obj = obj.with_current_position()

            # Check if already added
            if any(existing_obj.name == obj.name for existing_obj in self.objects_to_compare):
                QMessageBox.information(self, "Already Added", f"{obj.name} is already in the comparison.")
                return

            # Add object
            self.objects_to_compare.append(obj)

            # Get visibility and difficulty
            visibility_info = assess_visibility(obj)
            difficulty = get_object_difficulty(obj)

            self.visibility_data.append(visibility_info)
            self.difficulty_data.append(difficulty)

            # Update comparison table
            self._update_comparison_table()

        except Exception as e:
            logger.error(f"Error adding object to comparison: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to add object: {e}")

    def _on_remove_clicked(self) -> None:
        """Handle remove button click."""
        selected_rows = self.comparison_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "Please select a row to remove.")
            return

        # Remove in reverse order to maintain indices
        rows_to_remove = sorted([row.row() for row in selected_rows], reverse=True)
        for row in rows_to_remove:
            if row < len(self.objects_to_compare):
                self.objects_to_compare.pop(row)
                self.visibility_data.pop(row)
                self.difficulty_data.pop(row)

        self._update_comparison_table()

    def _on_clear_clicked(self) -> None:
        """Handle clear button click."""
        if not self.objects_to_compare:
            return

        reply = QMessageBox.question(
            self,
            "Clear All",
            "Remove all objects from comparison?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.objects_to_compare.clear()
            self.visibility_data.clear()
            self.difficulty_data.clear()
            self._update_comparison_table()

    def _update_comparison_table(self) -> None:
        """Update the comparison table with current objects."""
        if not self.objects_to_compare:
            self.comparison_table.setRowCount(0)
            self.comparison_table.setColumnCount(0)
            self.status_label.setText("Add objects to compare. Search for objects by name and click 'Add'.")
            return

        # Define comparison attributes
        # Format: (display_name, getter_func, is_comparable, comparison_getter_for_sorting)
        attributes = [
            ("Name", self._get_name, False, None),
            ("Common Name", self._get_common_name, False, None),
            ("Type", self._get_type, False, None),
            ("Magnitude", self._get_magnitude, True, self._get_magnitude),  # Lower is better
            ("Difficulty", self._get_difficulty, True, self._get_difficulty_numeric),  # Lower is better
            ("RA", self._get_ra, False, None),
            ("Dec", self._get_dec, False, None),
            ("Altitude", self._get_altitude, True, self._get_altitude),  # Higher is better
            ("Azimuth", self._get_azimuth, False, None),
            ("Visible", self._get_visible, True, self._get_visible),  # True is better
            ("Observability", self._get_observability, True, self._get_observability),  # Higher is better
            ("Constellation", self._get_constellation, False, None),
            ("Catalog", self._get_catalog, False, None),
        ]

        # Set up table
        num_objects = len(self.objects_to_compare)
        self.comparison_table.setColumnCount(num_objects + 1)  # +1 for attribute column
        self.comparison_table.setRowCount(len(attributes))

        # Set headers
        headers = ["Attribute"] + [obj.common_name or obj.name for obj in self.objects_to_compare]
        self.comparison_table.setHorizontalHeaderLabels(headers)

        # Get theme colors once for efficiency
        colors = self._get_theme_colors()
        text_color = QColor(colors["text"])

        # Populate rows
        for row, attr_info in enumerate(attributes):
            attr_name = attr_info[0]
            getter_func = attr_info[1]
            is_comparable = attr_info[2] if len(attr_info) > 2 else False
            comparison_getter = attr_info[3] if len(attr_info) > 3 else None

            # Attribute name
            attr_item = QTableWidgetItem(attr_name)
            attr_item.setFlags(Qt.ItemFlag.ItemIsEnabled)  # Not selectable
            font = attr_item.font()
            font.setBold(True)
            attr_item.setFont(font)
            # Set theme-aware text color
            attr_item.setForeground(text_color)
            self.comparison_table.setItem(row, 0, attr_item)

            # Get display values for all objects
            display_values = []
            for i, _obj in enumerate(self.objects_to_compare):
                value = getter_func(i)
                display_values.append(value)

            # Get comparison values for sorting (if comparable)
            comparison_values = []
            if is_comparable and comparison_getter:
                for i in range(len(self.objects_to_compare)):
                    comp_value = comparison_getter(i)
                    comparison_values.append(comp_value)

            # Determine best/worst for comparable attributes
            best_indices = []
            worst_indices = []
            if is_comparable and comparison_values:
                # Find best and worst values
                if isinstance(comparison_values[0], (int, float)):
                    # Numeric comparison
                    numeric_values = [
                        v
                        if isinstance(v, (int, float)) and v is not None
                        else (float("inf") if attr_name in ("Magnitude", "Difficulty") else float("-inf"))
                        for v in comparison_values
                    ]
                    if attr_name == "Magnitude" or attr_name == "Difficulty":
                        # Lower is better
                        valid_values = [v for v in numeric_values if v != float("inf") and v != float("-inf")]
                        if valid_values:
                            best_val = min(valid_values)
                            worst_val = max(valid_values)
                            best_indices = [i for i, v in enumerate(numeric_values) if v == best_val]
                            worst_indices = [i for i, v in enumerate(numeric_values) if v == worst_val]
                    else:
                        # Higher is better
                        valid_values = [v for v in numeric_values if v != float("inf") and v != float("-inf")]
                        if valid_values:
                            best_val = max(valid_values)
                            worst_val = min(valid_values)
                            best_indices = [i for i, v in enumerate(numeric_values) if v == best_val]
                            worst_indices = [i for i, v in enumerate(numeric_values) if v == worst_val]
                elif isinstance(comparison_values[0], bool):  # type: ignore[unreachable]
                    # Boolean comparison (True is better)
                    best_indices = [i for i, v in enumerate(comparison_values) if v is True]  # type: ignore[unreachable]
                    worst_indices = [i for i, v in enumerate(comparison_values) if v is False]

            # Set values in table
            for col, value in enumerate(display_values, start=1):
                # Format value for display
                if isinstance(value, float):
                    display_str = f"{value:.2f}" if value is not None else "N/A"
                elif isinstance(value, bool):  # type: ignore[unreachable]
                    display_str = "Yes" if value else "No"  # type: ignore[unreachable]
                else:
                    display_str = str(value) if value is not None else "N/A"

                item = QTableWidgetItem(display_str)
                # Set theme-aware text color
                item.setForeground(text_color)
                self.comparison_table.setItem(row, col, item)

                # Highlight best/worst with theme-aware colors
                if is_comparable and (col - 1) in best_indices:
                    item.setBackground(QColor(colors["bright_green"]))
                    # Ensure text is readable on green background
                    item.setForeground(text_color)
                elif is_comparable and (col - 1) in worst_indices:
                    item.setBackground(QColor(colors["bright_red"]))
                    # Ensure text is readable on red background
                    item.setForeground(text_color)

        # Resize columns to content
        self.comparison_table.resizeColumnsToContents()

        # Update status
        self.status_label.setText(
            f"Comparing {num_objects} object(s). Green = best, Red = worst for comparable attributes."
        )

    def _get_name(self, index: int) -> str:
        """Get object name."""
        return self.objects_to_compare[index].name

    def _get_common_name(self, index: int) -> str | None:
        """Get common name."""
        return self.objects_to_compare[index].common_name

    def _get_type(self, index: int) -> str:
        """Get object type."""
        obj_type = self.objects_to_compare[index].object_type
        return obj_type.value if hasattr(obj_type, "value") else str(obj_type)

    def _get_magnitude(self, index: int) -> float | None:
        """Get magnitude."""
        return self.objects_to_compare[index].magnitude

    def _get_difficulty(self, index: int) -> str:
        """Get difficulty level name."""
        difficulty = self.difficulty_data[index]
        return difficulty.value.upper() if hasattr(difficulty, "value") else str(difficulty)

    def _get_difficulty_numeric(self, index: int) -> int:
        """Get difficulty as numeric value for comparison."""
        difficulty = self.difficulty_data[index]
        difficulty_order = {
            DifficultyLevel.BEGINNER: 1,
            DifficultyLevel.INTERMEDIATE: 2,
            DifficultyLevel.ADVANCED: 3,
            DifficultyLevel.EXPERT: 4,
        }
        return difficulty_order.get(difficulty, 5)

    def _get_ra(self, index: int) -> str:
        """Get RA formatted."""
        obj = self.objects_to_compare[index]
        return format_ra(obj.ra_hours) if obj.ra_hours is not None else "N/A"

    def _get_dec(self, index: int) -> str:
        """Get Dec formatted."""
        obj = self.objects_to_compare[index]
        return format_dec(obj.dec_degrees) if obj.dec_degrees is not None else "N/A"

    def _get_altitude(self, index: int) -> float | None:
        """Get altitude."""
        vis_info = self.visibility_data[index]
        return vis_info.altitude_deg

    def _get_azimuth(self, index: int) -> float | None:
        """Get azimuth."""
        vis_info = self.visibility_data[index]
        return vis_info.azimuth_deg

    def _get_visible(self, index: int) -> bool:
        """Get visibility status."""
        vis_info = self.visibility_data[index]
        return vis_info.is_visible

    def _get_observability(self, index: int) -> float | None:
        """Get observability score."""
        vis_info = self.visibility_data[index]
        score = vis_info.observability_score
        return round(score, 3) if score is not None else None

    def _get_constellation(self, index: int) -> str | None:
        """Get constellation."""
        return self.objects_to_compare[index].constellation

    def _get_catalog(self, index: int) -> str:
        """Get catalog."""
        return self.objects_to_compare[index].catalog

    def _is_dark_theme(self) -> bool:
        """Detect if the current theme is dark mode."""
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
        return {
            "text": "#ffffff" if is_dark else "#000000",
            "text_dim": "#9e9e9e" if is_dark else "#666666",
            "green": "#4caf50" if is_dark else "#2e7d32",
            "bright_green": "#81c784" if is_dark else "#c8e6c9",  # Lighter green for highlighting
            "red": "#f44336" if is_dark else "#c62828",
            "bright_red": "#e57373" if is_dark else "#ffcdd2",  # Lighter red for highlighting
        }

"""
Catalog Search Window

A subwindow for searching celestial object catalogs.
"""

import asyncio
import logging
from collections import defaultdict

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QIcon, QPalette
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from celestron_nexstar.api.catalogs.catalogs import CelestialObject, search_objects
from celestron_nexstar.api.core.utils import format_dec, format_ra


logger = logging.getLogger(__name__)


class CatalogSearchWindow(QMainWindow):
    """Window for searching celestial object catalogs."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the catalog search window."""
        super().__init__(parent)
        self.setWindowTitle("Catalog Search")
        self.setMinimumWidth(1000)
        self.setMinimumHeight(600)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Search bar with info button
        search_layout = QHBoxLayout()
        search_label = QLabel()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter object name, type, or description...")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self._update_textbox_placeholder_style(self.search_input)

        # Clear button
        clear_icon = self._create_icon("close", ["edit-clear", "window-close"])
        self.clear_button = QPushButton()
        self.clear_button.setIcon(clear_icon)
        self.clear_button.setIconSize(QSize(22, 22))
        self.clear_button.setToolTip("Clear search")
        self.clear_button.clicked.connect(self._on_clear_clicked)
        # Style to match main window toolbar buttons (no border until hover)
        self.clear_button.setStyleSheet("""
            QPushButton {
                border: none;
                padding: 4px 8px;
                background: transparent;
            }
            QPushButton:hover {
                background: rgba(128, 128, 128, 0.2);
                border-radius: 4px;
            }
            QPushButton:pressed {
                background: rgba(128, 128, 128, 0.3);
            }
            QPushButton:disabled {
                opacity: 0.5;
            }
        """)

        # Info button (enabled when exactly one row is selected)
        info_icon = self._create_icon("info", ["dialog-information", "help-about"])
        self.info_button = QPushButton()
        self.info_button.setIcon(info_icon)
        self.info_button.setIconSize(QSize(22, 22))
        self.info_button.setToolTip("Show object information")
        self.info_button.setEnabled(False)
        self.info_button.clicked.connect(self._on_info_clicked)
        # Style to match main window toolbar buttons (no border until hover)
        self.info_button.setStyleSheet("""
            QPushButton {
                border: none;
                padding: 4px 8px;
                background: transparent;
            }
            QPushButton:hover {
                background: rgba(128, 128, 128, 0.2);
                border-radius: 4px;
            }
            QPushButton:pressed {
                background: rgba(128, 128, 128, 0.3);
            }
            QPushButton:disabled {
                opacity: 0.5;
            }
        """)

        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input, stretch=1)
        search_layout.addWidget(self.clear_button)
        search_layout.addWidget(self.info_button)
        layout.addLayout(search_layout)

        # Results tree (grouped by match type)
        self.results_table = QTreeWidget()
        self.results_table.setColumnCount(7)
        self.results_table.setHeaderLabels(["Name", "Catalog", "Type", "RA", "Dec", "Mag", "Description"])
        self.results_table.header().setStretchLastSection(True)
        self.results_table.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.results_table.setSortingEnabled(True)  # Enable sorting
        self.results_table.itemSelectionChanged.connect(self._on_selection_changed)
        self.results_table.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.results_table)

        # Store search results
        self.search_results: list[tuple[CelestialObject, str]] = []  # (CelestialObject, match_type)

        # Debounce timer for search
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self._perform_search)

        # Monitor system theme changes to refresh icons
        app = QGuiApplication.instance()
        if app and isinstance(app, QGuiApplication):
            app.paletteChanged.connect(self._on_theme_changed)  # type: ignore[attr-defined]

    def _create_icon(self, icon_name: str, fallback_theme_names: list[str] | None = None) -> QIcon:
        """Create an icon using FontAwesome icons (via qtawesome) with theme icon fallbacks."""
        # Detect theme for icon color
        is_dark = False
        app = QGuiApplication.instance()
        if app and isinstance(app, QGuiApplication):
            palette = app.palette()
            window_color = palette.color(QPalette.ColorRole.Window)
            brightness = window_color.lightness()
            is_dark = brightness < 128

        # Map icon names to FontAwesome icon names
        # Prefer outline versions where available
        icon_map: dict[str, str] = {
            "info": "mdi.information-outline",
            "close": "mdi.close-outline",
        }

        # Try FontAwesome icons via qtawesome first
        try:
            import qtawesome as qta  # type: ignore[import-untyped]

            fa_icon_name = icon_map.get(icon_name, icon_name)
            if fa_icon_name.startswith("mdi."):
                # Material Design Icons
                icon_name_mdi = fa_icon_name[4:]  # Remove "mdi." prefix
                # Set color based on theme
                color = "#ffffff" if is_dark else "#000000"
                color_on = "#000000" if is_dark else "#ffffff"
                icon = qta.icon(f"mdi.{icon_name_mdi}", color=color, color_on=color_on)
            else:
                # FontAwesome icons
                color = "#ffffff" if is_dark else "#000000"
                icon = qta.icon(fa_icon_name, color=color)
            return QIcon(icon)
        except Exception:
            # Fallback to theme icons if qtawesome fails
            if fallback_theme_names:
                from PySide6.QtGui import QIcon as QIconFallback

                for theme_name in fallback_theme_names:
                    icon = QIconFallback.fromTheme(theme_name)
                    if not icon.isNull():
                        return icon

        # Final fallback: return empty icon
        return QIcon()

    def _on_theme_changed(self) -> None:
        """Handle theme changes - refresh icons to match new theme."""
        self._refresh_icons()
        # Update textbox placeholder text colors
        self._update_textbox_placeholder_style(self.search_input)

    def _update_textbox_placeholder_style(self, textbox: QLineEdit) -> None:
        """Update placeholder text color to be theme-aware."""
        from PySide6.QtGui import QPalette

        is_dark = self._is_dark_theme()
        # Set placeholder text color based on theme
        # Use a lighter gray for dark mode, darker gray for light mode
        placeholder_color = "#999999" if is_dark else "#666666"
        app = QGuiApplication.instance()
        if app and isinstance(app, QGuiApplication):
            palette = app.palette()
            textbox.setStyleSheet(
                f"""
                QLineEdit {{
                    color: {palette.color(QPalette.ColorRole.Text).name()};
                }}
                QLineEdit::placeholder {{
                    color: {placeholder_color};
                }}
            """
            )

    def _is_dark_theme(self) -> bool:
        """Detect if the current theme is dark mode."""
        app = QGuiApplication.instance()
        if app and isinstance(app, QGuiApplication):
            palette = app.palette()
            window_color = palette.color(QPalette.ColorRole.Window)
            brightness = window_color.lightness()
            return bool(brightness < 128)
        return False

    def _refresh_icons(self) -> None:
        """Refresh button icons to match current theme."""
        clear_icon = self._create_icon("close", ["edit-clear", "window-close"])
        self.clear_button.setIcon(clear_icon)
        info_icon = self._create_icon("info", ["dialog-information", "help-about"])
        self.info_button.setIcon(info_icon)

    def _on_search_text_changed(self, text: str) -> None:
        """Handle search text changes with debouncing."""
        # Clear previous timer
        self.search_timer.stop()

        # If text is empty, clear results
        if not text.strip():
            self.results_table.clear()
            self.search_results = []
            self.info_button.setEnabled(False)
            return

        # Start timer for 1 second delay (1000ms)
        self.search_timer.start(1000)

    def _perform_search(self) -> None:
        """Perform the actual search."""
        query = self.search_input.text().strip()
        if not query:
            return

        try:
            # Show loading state
            self.results_table.clear()
            self.results_table.setEnabled(False)

            # Perform search in background
            # Use update_positions=False to avoid planetary position calculation errors
            try:
                results = asyncio.run(search_objects(query, catalog_name=None, update_positions=False))
            except Exception as search_error:
                # Handle search errors gracefully
                # Check if it's an ephemeris-related error
                from celestron_nexstar.api.core.exceptions import UnknownEphemerisObjectError

                error_msg = str(search_error)
                if "UnknownEphemerisObjectError" in str(type(search_error).__name__) or isinstance(
                    search_error.__cause__, UnknownEphemerisObjectError
                ):
                    error_msg = (
                        "Some objects could not be loaded due to missing ephemeris data. "
                        "Try searching for specific object names or install ephemeris files."
                    )
                elif "RaisesContractError" in str(type(search_error).__name__):
                    # Deal contract error - check the underlying cause
                    if search_error.__cause__:
                        if isinstance(search_error.__cause__, UnknownEphemerisObjectError):
                            error_msg = (
                                "Some objects could not be loaded due to missing ephemeris data. "
                                "Try searching for specific object names or install ephemeris files."
                            )
                        else:
                            error_msg = f"Error: {search_error.__cause__!s}"
                    else:
                        error_msg = f"Error: {error_msg}"

                logger.error(f"Error during catalog search: {search_error}", exc_info=True)
                # Show error message in tree
                error_item = QTreeWidgetItem(self.results_table)
                error_item.setText(0, error_msg)
                error_item.setFlags(Qt.ItemFlag.NoItemFlags)  # Make it non-selectable
                # Span across all columns
                for col in range(1, 7):
                    error_item.setText(col, "")
                self.results_table.setEnabled(True)
                return

            # Store results
            self.search_results = results

            # Group results by match type
            grouped_results: defaultdict[str, list[tuple[CelestialObject, str]]] = defaultdict(list)
            for obj, match_type in results:
                grouped_results[match_type].append((obj, match_type))

            # Match type order
            match_type_order = ["exact", "name", "alias", "description"]
            match_type_titles = {
                "exact": "Exact Matches",
                "name": "Name Matches",
                "alias": "Common Name Matches",
                "description": "Description Matches",
            }

            # Disable sorting temporarily while populating
            self.results_table.setSortingEnabled(False)

            # Populate tree with grouped results
            for match_type in match_type_order:
                if match_type not in grouped_results:
                    continue

                type_results = grouped_results[match_type]
                if not type_results:
                    continue

                # Create parent item for this match type group
                group_item = QTreeWidgetItem(self.results_table)
                group_item.setText(0, f"{match_type_titles.get(match_type, match_type)} ({len(type_results)})")
                group_item.setExpanded(True)  # Expand groups by default
                # Make group items bold and non-selectable
                font = group_item.font(0)
                font.setBold(True)
                group_item.setFont(0, font)
                group_item.setFlags(Qt.ItemFlag.ItemIsEnabled)  # Not selectable

                # Add child items for each object in this group
                for obj, _ in type_results:
                    try:
                        child_item = QTreeWidgetItem(group_item)

                        # Name - for alias matches, show common_name (the alias) prominently
                        if match_type == "alias" and obj.common_name:
                            # For alias matches, show "common_name (name)" to make it clear what matched
                            display_name = f"{obj.common_name} ({obj.name})" if obj.name else obj.common_name
                        else:
                            # For other matches, show name, with common_name in parentheses if available
                            display_name = obj.name or ""
                            if obj.common_name and obj.common_name != obj.name:
                                display_name = f"{display_name} ({obj.common_name})"
                        child_item.setText(0, display_name)
                        child_item.setData(0, Qt.ItemDataRole.UserRole, obj)

                        # Catalog
                        child_item.setText(1, obj.catalog or "")

                        # Type
                        type_str = obj.object_type.value if hasattr(obj.object_type, "value") else str(obj.object_type)
                        child_item.setText(2, type_str)

                        # RA
                        ra_str = format_ra(obj.ra_hours) if obj.ra_hours is not None else "N/A"
                        child_item.setText(3, ra_str)

                        # Dec
                        dec_str = format_dec(obj.dec_degrees) if obj.dec_degrees is not None else "N/A"
                        child_item.setText(4, dec_str)

                        # Mag
                        mag_str = f"{obj.magnitude:.2f}" if obj.magnitude is not None else "N/A"
                        child_item.setText(5, mag_str)

                        # Description - for alias matches, prefer description over common_name since common_name is shown in Name
                        if match_type == "alias":
                            desc_str = obj.description or ""
                        else:
                            # For other matches, show common_name or description
                            desc_str = obj.common_name or obj.description or ""
                        child_item.setText(6, desc_str)

                    except Exception as obj_error:
                        # Skip objects that fail to load (e.g., planetary position errors)
                        logger.debug(
                            f"Error loading object {obj.name if hasattr(obj, 'name') else 'unknown'}: {obj_error}"
                        )
                        continue

            # Resize columns to content
            for col in range(7):
                self.results_table.resizeColumnToContents(col)
            self.results_table.setEnabled(True)

            # Re-enable sorting
            self.results_table.setSortingEnabled(True)

            # Set default sort order (by Name ascending)
            self.results_table.sortItems(0, Qt.SortOrder.AscendingOrder)

        except Exception as e:
            logger.error(f"Error performing catalog search: {e}", exc_info=True)
            self.results_table.setEnabled(True)

    def _on_clear_clicked(self) -> None:
        """Handle clear button click."""
        self.search_input.clear()
        self.results_table.clear()
        self.search_results = []
        self.info_button.setEnabled(False)
        self.search_timer.stop()

    def _on_selection_changed(self) -> None:
        """Handle tree selection changes."""
        selected_items = self.results_table.selectedItems()
        # Only enable info button if exactly one child item (not a group) is selected
        if len(selected_items) == 1:
            item = selected_items[0]
            # Check if it's a child item (has a parent) and not a group item
            self.info_button.setEnabled(item.parent() is not None)
        else:
            self.info_button.setEnabled(False)

    def _on_info_clicked(self) -> None:
        """Handle info button click."""
        selected_items = self.results_table.selectedItems()
        if len(selected_items) != 1:
            return

        item = selected_items[0]
        # Only process child items (not group items)
        if item.parent() is None:
            return

        obj = item.data(0, Qt.ItemDataRole.UserRole)
        if not obj:
            return

        # Show progress dialog
        from PySide6.QtWidgets import QApplication, QProgressDialog

        progress = QProgressDialog("Loading object information...", "Cancel", 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)
        progress.show()
        QApplication.processEvents()

        # Open object info dialog
        from celestron_nexstar.gui.dialogs.object_info_dialog import ObjectInfoDialog

        dialog = ObjectInfoDialog(self, obj.name)
        progress.close()
        dialog.exec()

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle item double-click to copy text."""
        if item and item.parent() is not None:  # Only copy from child items, not groups
            from PySide6.QtWidgets import QApplication

            text = item.text(column) if column >= 0 else item.text(0)
            clipboard = QApplication.clipboard()
            clipboard.setText(text)

            # Show toast notification
            self._show_toast(f"Copied: {text}")

    def _show_toast(self, message: str, duration_ms: int = 2000) -> None:
        """Show a temporary toast notification."""
        # Detect theme for toast styling
        is_dark = self._is_dark_theme()
        # Theme-aware toast styling
        bg_color = "rgba(0, 0, 0, 200)" if not is_dark else "rgba(255, 255, 255, 200)"
        text_color = "white" if not is_dark else "black"
        # Create a simple label for toast
        toast = QLabel(message, self)
        toast.setStyleSheet(
            f"""
            QLabel {{
                background-color: {bg_color};
                color: {text_color};
                padding: 8px;
                border-radius: 4px;
            }}
        """
        )
        toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        toast.adjustSize()

        # Position at bottom center
        x = (self.width() - toast.width()) // 2
        y = self.height() - toast.height() - 50
        toast.move(x, y)
        toast.show()

        # Hide after duration
        QTimer.singleShot(duration_ms, toast.deleteLater)

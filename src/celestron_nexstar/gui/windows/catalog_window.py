"""
Catalog Search Window

A subwindow for searching celestial object catalogs.
"""

import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, QStringListModel, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QIcon, QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
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

from celestron_nexstar.gui.utils.table_utils import autosize_table_columns
from celestron_nexstar.api.catalogs.catalogs import CelestialObject, get_object_names_for_completion, search_objects
from celestron_nexstar.api.core.enums import CelestialObjectType
from celestron_nexstar.api.core.utils import format_dec, format_ra
from celestron_nexstar.api.database.database import get_database


if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


@dataclass
class SearchFilters:
    """Search filter parameters."""

    min_magnitude: float | None = None
    max_magnitude: float | None = None
    object_types: list[CelestialObjectType] | None = None
    catalog_name: str | None = None


class AdvancedFiltersDialog(QDialog):
    """Dialog for advanced search filters."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the advanced filters dialog."""
        super().__init__(parent)
        self.setWindowTitle("Advanced Search Filters")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        form_layout = QFormLayout()

        # Magnitude range
        magnitude_layout = QHBoxLayout()
        self.min_mag_spinbox = QDoubleSpinBox()
        self.min_mag_spinbox.setRange(-30.0, 30.0)
        self.min_mag_spinbox.setSingleStep(0.1)
        self.min_mag_spinbox.setSpecialValueText("No limit")
        self.min_mag_spinbox.setValue(-30.0)
        magnitude_layout.addWidget(QLabel("Min:"))
        magnitude_layout.addWidget(self.min_mag_spinbox)

        self.max_mag_spinbox = QDoubleSpinBox()
        self.max_mag_spinbox.setRange(-30.0, 30.0)
        self.max_mag_spinbox.setSingleStep(0.1)
        self.max_mag_spinbox.setSpecialValueText("No limit")
        self.max_mag_spinbox.setValue(30.0)
        magnitude_layout.addWidget(QLabel("Max:"))
        magnitude_layout.addWidget(self.max_mag_spinbox)
        magnitude_layout.addStretch()
        form_layout.addRow("Magnitude Range:", magnitude_layout)

        # Object types
        self.object_type_checkboxes: dict[CelestialObjectType, QCheckBox] = {}
        types_layout = QVBoxLayout()
        for obj_type in CelestialObjectType:
            checkbox = QCheckBox(obj_type.value.replace("_", " ").title())
            checkbox.setChecked(True)  # All checked by default
            self.object_type_checkboxes[obj_type] = checkbox
            types_layout.addWidget(checkbox)
        form_layout.addRow("Object Types:", types_layout)

        # Catalog filter
        self.catalog_combo = QComboBox()
        self.catalog_combo.setEditable(False)
        self.catalog_combo.addItem("All Catalogs", None)
        # Load catalogs asynchronously (will be called when dialog is shown)
        form_layout.addRow("Catalog:", self.catalog_combo)

        layout.addLayout(form_layout)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Reset
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        reset_button = button_box.button(QDialogButtonBox.StandardButton.Reset)
        reset_button.clicked.connect(self._reset_filters)
        layout.addWidget(button_box)

    def showEvent(self, event: object) -> None:  # noqa: N802
        """Handle dialog show event - load catalogs."""
        super().showEvent(event)  # type: ignore[arg-type]
        # Load catalogs when dialog is shown
        if self.catalog_combo.count() == 1:  # Only "All Catalogs" item
            self._load_catalogs()

    def _load_catalogs(self) -> None:
        """Load available catalogs."""
        try:
            db = get_database()
            catalogs = db.get_all_catalogs()
            for catalog in sorted(catalogs):
                self.catalog_combo.addItem(catalog, catalog)
        except Exception as e:
            logger.error(f"Error loading catalogs: {e}")

    def _reset_filters(self) -> None:
        """Reset all filters to default values."""
        self.min_mag_spinbox.setValue(-30.0)
        self.max_mag_spinbox.setValue(30.0)
        for checkbox in self.object_type_checkboxes.values():
            checkbox.setChecked(True)
        self.catalog_combo.setCurrentIndex(0)

    def get_filters(self) -> SearchFilters:
        """Get current filter values."""
        min_mag = self.min_mag_spinbox.value() if self.min_mag_spinbox.value() > -30.0 else None
        max_mag = self.max_mag_spinbox.value() if self.max_mag_spinbox.value() < 30.0 else None
        object_types = [obj_type for obj_type, checkbox in self.object_type_checkboxes.items() if checkbox.isChecked()]
        catalog_name = self.catalog_combo.currentData()
        return SearchFilters(
            min_magnitude=min_mag,
            max_magnitude=max_mag,
            object_types=object_types if len(object_types) < len(CelestialObjectType) else None,
            catalog_name=catalog_name,
        )

    def set_filters(self, filters: SearchFilters) -> None:
        """Set filter values."""
        self.min_mag_spinbox.setValue(filters.min_magnitude if filters.min_magnitude is not None else -30.0)
        self.max_mag_spinbox.setValue(filters.max_magnitude if filters.max_magnitude is not None else 30.0)
        if filters.object_types:
            for obj_type, checkbox in self.object_type_checkboxes.items():
                checkbox.setChecked(obj_type in filters.object_types)
        if filters.catalog_name:
            index = self.catalog_combo.findData(filters.catalog_name)
            if index >= 0:
                self.catalog_combo.setCurrentIndex(index)


class CatalogSearchWindow(QMainWindow):
    """Window for searching celestial object catalogs."""

    MAX_RECENT_SEARCHES = 20

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the catalog search window."""
        super().__init__(parent)
        self.setWindowTitle("Catalog Search")
        self.setMinimumWidth(1000)
        self.setMinimumHeight(600)

        # Store current filters
        self.current_filters = SearchFilters()

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Search bar with controls
        search_layout = QHBoxLayout()
        search_label = QLabel()

        # Recent searches dropdown
        self.recent_searches_combo = QComboBox()
        self.recent_searches_combo.setEditable(False)
        self.recent_searches_combo.setMaximumWidth(150)
        self.recent_searches_combo.setToolTip("Recent searches")
        self.recent_searches_combo.currentTextChanged.connect(self._on_recent_search_selected)
        self._load_recent_searches()

        # Search input with autocomplete
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter object name, type, or description...")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.search_input.returnPressed.connect(self._on_search_enter_pressed)
        self._update_textbox_placeholder_style(self.search_input)
        self._setup_autocomplete()

        # Advanced filters button
        filters_icon = self._create_icon("filter", ["view-filter", "filter"])
        self.filters_button = QPushButton("Filters")
        self.filters_button.setIcon(filters_icon)
        self.filters_button.setToolTip("Advanced filters")
        self.filters_button.clicked.connect(self._on_filters_clicked)

        # Clear button
        clear_icon = self._create_icon("close", ["edit-clear", "window-close"])
        self.clear_button = QPushButton()
        self.clear_button.setIcon(clear_icon)
        self.clear_button.setIconSize(QSize(22, 22))
        self.clear_button.setToolTip("Clear search")
        self.clear_button.clicked.connect(self._on_clear_clicked)
        self._style_button(self.clear_button)

        # Info button (enabled when exactly one row is selected)
        info_icon = self._create_icon("info", ["dialog-information", "help-about"])
        self.info_button = QPushButton()
        self.info_button.setIcon(info_icon)
        self.info_button.setIconSize(QSize(22, 22))
        self.info_button.setToolTip("Show object information")
        self.info_button.setEnabled(False)
        self.info_button.clicked.connect(self._on_info_clicked)
        self._style_button(self.info_button)

        search_layout.addWidget(search_label)
        search_layout.addWidget(self.recent_searches_combo)
        search_layout.addWidget(self.search_input, stretch=1)
        search_layout.addWidget(self.filters_button)
        search_layout.addWidget(self.clear_button)
        search_layout.addWidget(self.info_button)
        layout.addLayout(search_layout)

        # Results tree (grouped by match type)
        self.results_table = QTreeWidget()
        self.results_table.setColumnCount(7)
        self.results_table.setHeaderLabels(["Name", "Catalog", "Type", "RA", "Dec", "Mag", "Description"])
        autosize_table_columns(self.results_table, stretch_last=False)
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

        # Autocomplete update timer
        self.autocomplete_timer = QTimer()
        self.autocomplete_timer.setSingleShot(True)
        self.autocomplete_timer.timeout.connect(self._update_autocomplete)

        # Monitor system theme changes to refresh icons
        app = QGuiApplication.instance()
        if app and isinstance(app, QGuiApplication):
            app.paletteChanged.connect(self._on_theme_changed)  # type: ignore[attr-defined]

    def showEvent(self, event: object) -> None:  # noqa: N802
        """Handle window show event - refresh icons after window is shown."""
        super().showEvent(event)  # type: ignore[arg-type]
        # Refresh icons to ensure they match the current theme
        self._refresh_icons()

    def _setup_autocomplete(self) -> None:
        """Set up autocomplete for search input."""
        self.completer = QCompleter(self)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.completer_model = QStringListModel()
        self.completer.setModel(self.completer_model)
        self.search_input.setCompleter(self.completer)

    def _update_autocomplete(self) -> None:
        """Update autocomplete suggestions based on current text."""
        text = self.search_input.text().strip()
        if len(text) < 2:  # Don't search for very short strings
            self.completer_model.setStringList([])
            return

        try:
            # Get suggestions asynchronously
            suggestions = get_object_names_for_completion(prefix=text, limit=20)
            self.completer_model.setStringList(suggestions)
        except Exception as e:
            logger.debug(f"Error updating autocomplete: {e}")

    def _load_recent_searches(self) -> None:
        """Load recent searches from database."""
        try:
            recent_searches = self._get_recent_searches()
            self.recent_searches_combo.clear()
            self.recent_searches_combo.addItem("Recent searches...")
            for search in recent_searches:
                self.recent_searches_combo.addItem(search)
        except Exception as e:
            logger.error(f"Error loading recent searches: {e}")

    def _get_recent_searches(self) -> list[str]:
        """Get recent searches from database."""
        try:
            from celestron_nexstar.api.database.models import UserPreferenceModel

            db = get_database()
            with db._get_session() as session:
                pref = session.get(UserPreferenceModel, "catalog_recent_searches")
                if pref:
                    data = json.loads(pref.value)
                    searches = data.get("searches", [])
                    if isinstance(searches, list):
                        return [str(s) for s in searches]  # Ensure all are strings
                    return []
        except Exception as e:
            logger.debug(f"Error getting recent searches: {e}")
        return []

    def _save_recent_search(self, query: str) -> None:
        """Save a search query to recent searches."""
        if not query or not query.strip():
            return

        try:
            from datetime import UTC, datetime

            from celestron_nexstar.api.database.models import UserPreferenceModel

            db = get_database()
            with db._get_session() as session:
                pref = session.get(UserPreferenceModel, "catalog_recent_searches")
                searches: list[str] = []
                if pref:
                    data = json.loads(pref.value)
                    searches = data.get("searches", [])

                # Remove if already exists and add to front
                query = query.strip()
                if query in searches:
                    searches.remove(query)
                searches.insert(0, query)

                # Limit to MAX_RECENT_SEARCHES
                searches = searches[: self.MAX_RECENT_SEARCHES]

                # Save back
                value = json.dumps({"searches": searches})
                if pref:
                    pref.value = value
                    pref.updated_at = datetime.now(UTC)
                else:
                    pref = UserPreferenceModel(
                        key="catalog_recent_searches",
                        value=value,
                        category="catalog",
                        description="Recent catalog search queries",
                    )
                    session.add(pref)
                session.commit()

                # Reload recent searches in UI
                self._load_recent_searches()
        except Exception as e:
            logger.error(f"Error saving recent search: {e}")

    def _on_recent_search_selected(self, text: str) -> None:
        """Handle recent search selection."""
        if text and text != "Recent searches...":
            self.search_input.setText(text)
            self.search_input.setFocus()
            # Reset combo to first item
            self.recent_searches_combo.setCurrentIndex(0)

    def _on_search_enter_pressed(self) -> None:
        """Handle Enter key press in search input."""
        query = self.search_input.text().strip()
        if query:
            # Save to recent searches (async, but don't wait)
            try:
                self._save_recent_search(query)
            except Exception as e:
                logger.debug(f"Error saving recent search: {e}")
            # Perform search immediately
            self.search_timer.stop()
            self._perform_search()

    def _on_filters_clicked(self) -> None:
        """Handle filters button click."""
        dialog = AdvancedFiltersDialog(self)
        dialog.set_filters(self.current_filters)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.current_filters = dialog.get_filters()
            # Update filters button to show active state
            has_filters = (
                self.current_filters.min_magnitude is not None
                or self.current_filters.max_magnitude is not None
                or self.current_filters.object_types is not None
                or self.current_filters.catalog_name is not None
            )
            if has_filters:
                self.filters_button.setStyleSheet("font-weight: bold;")
            else:
                self.filters_button.setStyleSheet("")
            # Re-run search with new filters
            if self.search_input.text().strip():
                self._perform_search()

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
            "filter": "mdi.filter-outline",
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

    def _style_button(self, button: QPushButton) -> None:
        """Apply standard button styling."""
        button.setStyleSheet("""
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
        filters_icon = self._create_icon("filter", ["view-filter", "filter"])
        self.filters_button.setIcon(filters_icon)

    def _on_search_text_changed(self, text: str) -> None:
        """Handle search text changes with debouncing."""
        # Clear previous timer
        self.search_timer.stop()
        self.autocomplete_timer.stop()

        # If text is empty, clear results
        if not text.strip():
            self.results_table.clear()
            self.search_results = []
            self.info_button.setEnabled(False)
            self.completer_model.setStringList([])
            return

        # Update autocomplete after short delay
        self.autocomplete_timer.start(300)

        # Start timer for 1 second delay (1000ms) for actual search
        self.search_timer.start(1000)

    def _apply_filters(self, results: list[tuple[CelestialObject, str]]) -> list[tuple[CelestialObject, str]]:
        """Apply current filters to search results."""
        filtered = []
        for obj, match_type in results:
            # Magnitude filter
            if self.current_filters.min_magnitude is not None and (
                obj.magnitude is None or obj.magnitude < self.current_filters.min_magnitude
            ):
                continue
            if self.current_filters.max_magnitude is not None and (
                obj.magnitude is None or obj.magnitude > self.current_filters.max_magnitude
            ):
                continue

            # Object type filter
            if self.current_filters.object_types and obj.object_type not in self.current_filters.object_types:
                continue

            # Catalog filter (already applied in search_objects, but double-check)
            if self.current_filters.catalog_name and obj.catalog != self.current_filters.catalog_name:
                continue

            filtered.append((obj, match_type))
        return filtered

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
            # Apply catalog filter if specified
            catalog_name = self.current_filters.catalog_name
            try:
                results = search_objects(query, catalog_name=catalog_name, update_positions=False)
                # Apply other filters
                results = self._apply_filters(results)
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

            # Save to recent searches (after successful search)
            try:
                self._save_recent_search(query)
            except Exception as e:
                logger.debug(f"Error saving recent search: {e}")

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
            autosize_table_columns(self.results_table, stretch_last=False)
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
        self.autocomplete_timer.stop()
        self.completer_model.setStringList([])

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

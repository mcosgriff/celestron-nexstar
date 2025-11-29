"""
Main application window for telescope control.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import logging
import threading
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPoint, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QActionGroup, QCursor, QFontMetrics, QGuiApplication, QIcon, QMouseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QProgressDialog,
    QSizeGrip,
    QSizePolicy,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from celestron_nexstar.api.core import format_local_time, get_local_timezone
from celestron_nexstar.api.core.enums import CelestialObjectType
from celestron_nexstar.api.location.observer import get_observer_location
from celestron_nexstar.gui.dialogs.gps_info_dialog import GPSInfoDialog
from celestron_nexstar.gui.dialogs.time_info_dialog import TimeInfoDialog
from celestron_nexstar.gui.dialogs.weather_info_dialog import WeatherInfoDialog
from celestron_nexstar.gui.themes import FusionTheme, ThemeMode
from celestron_nexstar.gui.widgets.collapsible_log_panel import CollapsibleLogPanel


if TYPE_CHECKING:
    from celestron_nexstar import NexStarTelescope
    from celestron_nexstar.api.observation.observation_planner import RecommendedObject

logger = logging.getLogger(__name__)


def _run_async_safe(coro: Coroutine[Any, Any, Any]) -> Any:
    """
    Run an async coroutine from a sync context, handling both cases:
    - If called from sync context: uses asyncio.run()
    - If called from async context: creates new event loop in thread

    Args:
        coro: The coroutine to run

    Returns:
        The result of the coroutine
    """
    try:
        # Check if we're in an async context
        asyncio.get_running_loop()
        # We're in an async context, need to use a thread with new event loop
        future: concurrent.futures.Future[Any] = concurrent.futures.Future()

        def run_in_thread() -> None:
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                result = new_loop.run_until_complete(coro)
                future.set_result(result)
                new_loop.close()
            except Exception as e:
                future.set_exception(e)

        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()
        return future.result()
    except RuntimeError:
        # No running loop, use asyncio.run()
        return asyncio.run(coro)


class ObjectsLoaderThread(QThread):
    """Worker thread to load objects data in the background."""

    data_loaded = Signal(object, object)  # type: ignore[type-arg,misc]  # Emits (obj_type_str, objects_list)

    def __init__(self, obj_type_str: str) -> None:
        """Initialize the loader thread."""
        super().__init__()
        self.obj_type_str = obj_type_str

    def run(self) -> None:
        """Load objects data in background thread."""
        try:
            import asyncio

            from celestron_nexstar.api.astronomy.constellations import get_visible_asterisms, get_visible_constellations
            from celestron_nexstar.api.core.enums import CelestialObjectType
            from celestron_nexstar.api.database.database import get_database
            from celestron_nexstar.api.observation.observation_planner import ObservationPlanner

            obj_type = CelestialObjectType(self.obj_type_str)
            planner = ObservationPlanner()
            conditions = planner.get_tonight_conditions()

            # Special handling for constellation type: show constellations
            if obj_type == CelestialObjectType.CONSTELLATION:
                # Load visible constellations
                async def _load_constellations() -> list[Any]:
                    db = get_database()
                    async with db._AsyncSession() as session:
                        return await get_visible_constellations(
                            session,
                            conditions.latitude,
                            conditions.longitude,
                            conditions.timestamp,
                            min_altitude_deg=20.0,
                        )

                constellations = asyncio.run(_load_constellations())
                # Convert to list of constellation names for display
                objects = [const[0].name for const in constellations]  # const[0] is the Constellation object
            elif obj_type == CelestialObjectType.ASTERISM:
                # Load visible asterisms
                async def _load_asterisms() -> list[Any]:
                    db = get_database()
                    async with db._AsyncSession() as session:
                        return await get_visible_asterisms(
                            session,
                            conditions.latitude,
                            conditions.longitude,
                            conditions.timestamp,
                            min_altitude_deg=20.0,
                        )

                asterisms = asyncio.run(_load_asterisms())
                # Store full asterism objects (tuples of (Asterism, alt, az)) so we can access member_stars
                objects = asterisms  # Keep full objects for asterisms
            else:
                # Get recommended objects for this type
                objects = planner.get_recommended_objects(conditions, obj_type, max_results=100, best_for_seeing=False)

            # Emit signal with loaded data
            self.data_loaded.emit(self.obj_type_str, objects)

        except Exception as e:
            # Emit None to indicate error
            logger.error(f"Error loading objects for type {self.obj_type_str}: {e}", exc_info=True)
            self.data_loaded.emit(self.obj_type_str, None)


class ClickableLabel(QLabel):
    """A clickable QLabel that emits a clicked signal."""

    clicked = Signal()  # type: ignore[type-arg,misc]

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]  # noqa: N802
        """Handle mouse press event."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class FavoriteTableWidgetItem(QTableWidgetItem):
    """Custom QTableWidgetItem for favorites column that sorts by favorite status."""

    def __lt__(self, other: QTableWidgetItem) -> bool:
        """Compare items for sorting - favorites (1) come before non-favorites (0)."""
        # Get sort value from UserRole + 1 (1 = favorite, 0 = not favorite)
        self_val = self.data(Qt.ItemDataRole.UserRole + 1) or 0
        other_val = other.data(Qt.ItemDataRole.UserRole + 1) or 0
        return self_val < other_val


class VisibilityTableWidgetItem(QTableWidgetItem):
    """Custom QTableWidgetItem for visibility column that sorts by visibility status."""

    def __lt__(self, other: QTableWidgetItem) -> bool:
        """Compare items for sorting - Visible (0) < Marginal (1) < Not Visible (2)."""
        # Get sort value from UserRole + 1 (0 = Visible, 1 = Marginal, 2 = Not Visible)
        self_val = self.data(Qt.ItemDataRole.UserRole + 1) or 0
        other_val = other.data(Qt.ItemDataRole.UserRole + 1) or 0
        return self_val < other_val


class MainWindow(QMainWindow):
    """Main application window for telescope control."""

    def _create_icon(self, icon_name: str, fallback_theme_names: list[str] | None = None) -> QIcon:
        """Create an icon using FontAwesome icons (via qtawesome) with theme icon fallbacks."""
        # Detect theme for icon color
        from PySide6.QtGui import QGuiApplication, QPalette

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
            # Telescope operations
            "link": "mdi.lan-connect",  # No outline version available
            "link_off": "mdi.lan-disconnect",  # No outline version available
            "my_location": "fa5s.map-marker-alt",  # FontAwesome Regular (outline)
            "tune": "mdi.cog-outline",
            "crosshairs": "mdi.crosshairs-gps",
            # Planning tools
            "catalog": "mdi.folder-outline",
            "dashboard": "mdi.view-dashboard-outline",
            "list": "mdi.playlist-play",
            "weather": "mdi.weather-cloudy",  # No outline version available
            "checklist": "mdi.check-circle-outline",
            "time_slots": "mdi.clock-outline",
            "quick_reference": "mdi.book-open-variant",
            "transit_times": "mdi.transit-connection",
            "glossary": "mdi.book-open-page-variant",
            "settings": "mdi.cog-outline",
            "star": "mdi.star",
            "favorite": "mdi.star",
            "bookmark": "mdi.bookmark",
            # Celestial objects (using alpha-box-outline pattern)
            "aurora": "mdi.alpha-a-box-outline",
            "binoculars": "mdi.alpha-b-box-outline",
            "comets": "mdi.alpha-c-box-outline",
            "eclipse": "mdi.alpha-e-box-outline",
            "iss": "mdi.alpha-i-box-outline",
            "meteors": "mdi.alpha-m-box-outline",
            "milky_way": "mdi.alpha-m-box-outline",  # Same as meteors (both start with 'm')
            "naked_eye": "mdi.alpha-n-box-outline",
            "occultations": "mdi.alpha-o-box-outline",
            "planets": "mdi.alpha-p-box-outline",
            "satellites": "mdi.alpha-s-box-outline",
            "space_weather": "mdi.alpha-s-box-outline",  # Same as satellites (both start with 's')
            "variables": "mdi.alpha-v-box-outline",
            "zodiacal": "mdi.alpha-z-box-outline",
            # Legacy
            "event": "fa5s.calendar",  # FontAwesome Regular (outline)
            "menu_book": "fa5s.book",  # FontAwesome Regular (outline)
            # Table controls
            "refresh": "mdi.refresh",
            "info": "mdi.information-outline",
            "download": "mdi.download-outline",
            "close": "mdi.close-outline",
            "close-circle": "mdi.close-circle-outline",
            "check-circle": "mdi.check-circle",
            "check": "mdi.check",
            # Communication
            "console": "mdi.console",  # No outline version available
            "chart": "mdi.chart-line",
            "graph": "mdi.chart-timeline-variant",
            "analytics": "mdi.chart-box",
            "compare": "mdi.compare",
            "diff": "mdi.diff",
        }

        # Try FontAwesome icons via qtawesome first
        try:
            import qtawesome as qta  # type: ignore[import-not-found,import-untyped]

            # Get the FontAwesome icon name
            fa_icon_name = icon_map.get(icon_name)
            if fa_icon_name:
                # Use theme-appropriate color for icons
                icon_color = "#ffffff" if is_dark else "#000000"

                # Try the specified icon first
                try:
                    icon = qta.icon(fa_icon_name, color=icon_color)
                    if not icon.isNull():
                        return QIcon(icon)  # Cast to QIcon to satisfy type checker
                except (ValueError, KeyError, AttributeError):
                    # Icon doesn't exist, try fallback
                    pass

                # If icon failed and it's a Material Design icon without -outline, try outline version
                if fa_icon_name.startswith("mdi.") and not fa_icon_name.endswith("-outline"):
                    outline_name = f"{fa_icon_name}-outline"
                    try:
                        icon = qta.icon(outline_name, color=icon_color)
                        if not icon.isNull():
                            return QIcon(icon)
                    except (ValueError, KeyError, AttributeError, TypeError):
                        pass

                # If icon failed and it's FontAwesome Solid (fa5s), try Regular (fa5r) outline version
                if fa_icon_name.startswith("fa5s."):
                    regular_name = fa_icon_name.replace("fa5s.", "fa5r.", 1)
                    try:
                        icon = qta.icon(regular_name, color=icon_color)
                        if not icon.isNull():
                            return QIcon(icon)
                    except (ValueError, KeyError, AttributeError, TypeError):
                        pass
        except (ImportError, AttributeError, ValueError, TypeError, KeyError) as e:
            # Log the error for debugging
            logger.debug(f"qtawesome icon failed for '{icon_name}': {e}")

        # Try theme icons as fallback
        if fallback_theme_names:
            for theme_name in fallback_theme_names:
                icon = QIcon.fromTheme(theme_name)
                if not icon.isNull():
                    return icon

        # Fallback to empty icon (will show as blank button)
        return QIcon()

    def _create_favorite_item(self, is_favorite: bool) -> FavoriteTableWidgetItem:
        """Create a FavoriteTableWidgetItem with check icon for favorites, blank for non-favorites."""
        if is_favorite:
            # Create check icon for favorite (green checkmark)
            try:
                import qtawesome as qta  # type: ignore[import-not-found,import-untyped]

                check_icon = qta.icon("mdi.check-circle", color="#4caf50")  # Green
                if check_icon.isNull():
                    check_icon = self._create_icon("check-circle", ["check-circle", "check", "dialog-ok"])
                item = FavoriteTableWidgetItem(QIcon(check_icon), "")
            except Exception:
                # Fallback to uncolored icon
                check_icon = self._create_icon("check-circle", ["check-circle", "check", "dialog-ok"])
                item = FavoriteTableWidgetItem(check_icon, "")

            # Center align the icon
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        else:
            # Blank item for non-favorites (no icon, no text)
            item = FavoriteTableWidgetItem("")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

        return item

    def _determine_visibility_status(self, altitude: float, visibility_probability: float) -> tuple[str, str]:
        """
        Determine visibility status based on altitude and visibility probability.

        Returns:
            Tuple of (status, color) where status is "Visible", "Marginal", or "Not Visible"
            and color is "green", "yellow", or "red"
        """
        # Consider both altitude and visibility probability
        if altitude >= 20.0 and visibility_probability >= 0.5:
            return ("Visible", "green")
        elif altitude >= 10.0 and visibility_probability >= 0.3:
            return ("Marginal", "yellow")
        else:
            return ("Not Visible", "red")

    def _create_visibility_item(self, altitude: float, visibility_probability: float) -> VisibilityTableWidgetItem:
        """Create a VisibilityTableWidgetItem with visibility indicator icon."""
        status, _color = self._determine_visibility_status(altitude, visibility_probability)

        try:
            import qtawesome as qta  # type: ignore[import-not-found,import-untyped]

            if status == "Visible":
                # Green checkmark
                icon = qta.icon("mdi.check-circle", color="#4caf50")  # Green
                if icon.isNull():
                    icon = self._create_icon("check-circle", ["check-circle", "check", "dialog-ok"])
            elif status == "Marginal":
                # Yellow warning
                icon = qta.icon("mdi.alert-circle", color="#ffc107")  # Yellow/Amber
                if icon.isNull():
                    icon = self._create_icon("dialog-warning", ["warning", "alert"])
            else:  # Not Visible
                # Red X
                icon = qta.icon("mdi.close-circle", color="#f44336")  # Red
                if icon.isNull():
                    icon = self._create_icon("dialog-cancel", ["cancel", "close"])

            item = VisibilityTableWidgetItem(QIcon(icon), status)
        except Exception:
            # Fallback to text-only with color
            if status == "Visible":
                icon = self._create_icon("check-circle", ["check-circle", "check", "dialog-ok"])
            elif status == "Marginal":
                icon = self._create_icon("dialog-warning", ["warning", "alert"])
            else:
                icon = self._create_icon("dialog-cancel", ["cancel", "close"])
            item = VisibilityTableWidgetItem(QIcon(icon), status)

        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        # Store status for sorting: 0 = Visible, 1 = Marginal, 2 = Not Visible
        sort_value = 0 if status == "Visible" else (1 if status == "Marginal" else 2)
        item.setData(Qt.ItemDataRole.UserRole + 1, sort_value)
        return item

    def __init__(self, theme: FusionTheme | None = None) -> None:
        """Initialize the main window."""
        super().__init__()
        self._catalog_window = None  # Store reference to catalog window
        self._goto_queue_window = None  # Store reference to goto queue window
        self.setWindowTitle("Celestron NexStar Telescope Control")
        self.setMinimumSize(800, 600)

        # Telescope connection state
        self.telescope: NexStarTelescope | None = None

        # Cache for loaded objects data (key: obj_type_str, value: list of objects)
        # Can be list[RecommendedObject] or list[str] for constellations/asterisms
        self._objects_cache: dict[str, list[RecommendedObject] | list[str]] = {}
        self._asterism_objects_cache: dict[str, Any] = {}  # Cache asterism objects for member_stars access

        # Track loading threads to prevent duplicate loads
        self._loading_threads: dict[str, ObjectsLoaderThread] = {}

        # Initialize theme (use provided theme or create default)
        if theme is None:
            from PySide6.QtWidgets import QApplication

            self.theme = FusionTheme(ThemeMode.SYSTEM)
            # Apply theme if app exists
            qapp = QApplication.instance()
            if qapp and isinstance(qapp, QApplication):
                self.theme.apply(qapp)
        else:
            self.theme = theme
        self.theme_mode_preference = self.theme.mode  # Track user preference

        # Create menu bar with theme toggle
        self._create_menus()

        # Create toolbar with telescope control buttons
        self._create_toolbar()

        # Create top toolbar for table controls
        self._create_table_toolbar()

        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Create telescope control panel
        self.control_panel = self._create_control_panel()
        main_layout.addWidget(self.control_panel)

        # Create collapsible log panel at bottom (header will be hidden, controlled by toolbar button)
        self.log_panel = CollapsibleLogPanel()
        self.log_panel.header.hide()  # Hide the header since we'll use a toolbar button
        # Ensure log panel starts collapsed (hidden)
        self.log_panel.log_text.hide()
        self.log_panel.setMaximumHeight(0)  # Start with no height
        self.log_panel.setMinimumHeight(0)
        main_layout.addWidget(self.log_panel)

        # Create status bar at bottom
        self._create_status_bar()

        # Setup update timer for status bar
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_status_bar)
        self.update_timer.start(1000)  # Update every second

        # Initial status update
        self._update_status_bar()

        # Load data for the first tab
        if hasattr(self, "tab_widget") and self.tab_widget.count() > 0:
            first_tab = self.tab_widget.widget(0)
            if isinstance(first_tab, QTableWidget):
                self._load_objects_table(first_tab)

        # Hide any unwanted elements that might appear (like ".EA" button)
        # This could be a qt-material CSS element or toolbar overflow button
        self._hide_unwanted_elements()

        # Debug: Print all widgets to help identify the ".EA" button
        # Uncomment the line below to see all widgets in the console when the app starts
        # self._debug_print_widgets()

    def _debug_print_widgets(self) -> None:
        """Debug method to print all widgets and their text."""

        def print_widget_tree(widget: QWidget, indent: int = 0) -> None:
            prefix = "  " * indent
            widget_text = ""
            if hasattr(widget, "text"):
                widget_text = widget.text()
            elif hasattr(widget, "windowTitle"):
                widget_text = widget.windowTitle()
            elif hasattr(widget, "toolTip"):
                widget_text = widget.toolTip()
            obj_name = widget.objectName() or "<no name>"
            class_name = widget.__class__.__name__
            # Check if text contains "EA" or similar
            if "EA" in widget_text.upper() or "EA" in obj_name.upper() or "EA" in class_name.upper():
                print(f"*** FOUND EA: {prefix}{class_name} (name: {obj_name}, text: '{widget_text}')")
            print(f"{prefix}{class_name} (name: {obj_name}, text: '{widget_text}')")
            for child in widget.children():
                if isinstance(child, QWidget):
                    print_widget_tree(child, indent + 1)

        print("=== Widget Tree (looking for .EA) ===")
        print_widget_tree(self)
        print("=== Checking toolbar widgets ===")
        for toolbar in self.findChildren(QToolBar):
            print(f"Toolbar: {toolbar.objectName()}, widgets: {toolbar.findChildren(QWidget)}")
        print("=== Checking status bar widgets ===")
        if self.statusBar():
            for widget in self.statusBar().findChildren(QWidget):
                print(
                    f"StatusBar widget: {widget.__class__.__name__}, text: '{getattr(widget, 'text', lambda: '')()}', name: {widget.objectName()}"
                )

    def _hide_unwanted_elements(self) -> None:
        """Hide any unwanted UI elements that might appear."""
        # Try to find and hide the ".EA" button by checking all widgets after window is shown
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QLabel, QPushButton, QToolButton

        def find_and_hide_ea_element() -> None:
            """Find any widget with '.EA' in its text and hide it."""
            # Check all buttons
            for button in self.findChildren(QPushButton):
                text = button.text()
                if ".EA" in text or text == ".EA":
                    button.hide()
                    button.setVisible(False)
                    print(f"Found and hiding button with text: '{text}'")

            for tool_button in self.findChildren(QToolButton):
                text = tool_button.text()
                if ".EA" in text or text == ".EA":
                    tool_button.hide()
                    tool_button.setVisible(False)
                    print(f"Found and hiding tool button with text: '{text}'")

            for label in self.findChildren(QLabel):
                text = label.text()
                if ".EA" in text or text == ".EA":
                    label.hide()
                    label.setVisible(False)
                    print(f"Found and hiding label with text: '{text}'")

            # Also try CSS approach - more aggressive
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app and isinstance(app, QApplication):
                current_stylesheet = app.styleSheet()  # type: ignore[attr-defined]
                hide_css = """
                    /* Hide toolbar overflow and separators */
                    QToolBar::handle { width: 0px; }
                    QToolBar::separator { width: 0px; }
                """
                app.setStyleSheet(current_stylesheet + hide_css)  # type: ignore[attr-defined]

        # Try multiple times with delays to catch dynamically created elements
        QTimer.singleShot(0, find_and_hide_ea_element)
        QTimer.singleShot(100, find_and_hide_ea_element)
        QTimer.singleShot(500, find_and_hide_ea_element)
        QTimer.singleShot(1000, find_and_hide_ea_element)

    def _create_menus(self) -> None:
        """Create the application menu bar with menus."""
        # Create View menu
        view_menu = self.menuBar().addMenu("&View")

        # Create Theme submenu
        theme_menu = view_menu.addMenu("&Theme")

        # Create action group for theme selection (exclusive)
        self.theme_action_group = QActionGroup(self)
        self.theme_action_group.setExclusive(True)

        # Light theme action
        self.light_theme_action = theme_menu.addAction("☀️ Light Mode")
        self.light_theme_action.setCheckable(True)
        self.light_theme_action.setStatusTip("Switch to light theme")
        self.light_theme_action.triggered.connect(lambda: self._set_theme(ThemeMode.LIGHT))
        self.theme_action_group.addAction(self.light_theme_action)

        # Dark theme action
        self.dark_theme_action = theme_menu.addAction("🌙 Dark Mode")
        self.dark_theme_action.setCheckable(True)
        self.dark_theme_action.setStatusTip("Switch to dark theme")
        self.dark_theme_action.triggered.connect(lambda: self._set_theme(ThemeMode.DARK))
        self.theme_action_group.addAction(self.dark_theme_action)

        # System theme action
        self.system_theme_action = theme_menu.addAction("🖥️ System")
        self.system_theme_action.setCheckable(True)
        self.system_theme_action.setStatusTip("Follow OS system theme")
        self.system_theme_action.triggered.connect(lambda: self._set_theme(ThemeMode.SYSTEM))
        self.theme_action_group.addAction(self.system_theme_action)

        # Set initial checked state based on current theme
        self._update_theme_menu_state()

        # Monitor system theme changes
        app = QGuiApplication.instance()
        if app and isinstance(app, QGuiApplication):
            app.paletteChanged.connect(self._on_system_theme_changed)  # type: ignore[attr-defined]

    def showEvent(self, event: object) -> None:  # noqa: N802
        """Handle window show event - refresh icons after window is shown."""
        super().showEvent(event)  # type: ignore[arg-type]
        # Refresh toolbar icons after window is shown to ensure FontAwesome fonts are loaded
        self._refresh_toolbar_icons()

    def _create_toolbar(self) -> None:
        """Create multiple toolbars organized by function."""

        # Common toolbar settings
        def create_toolbar(name: str, area: Qt.ToolBarArea) -> QToolBar:
            """Helper to create a toolbar with common settings."""
            toolbar = QToolBar(name)
            toolbar.setMovable(True)
            toolbar.setIconSize(QSize(22, 22))
            toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            toolbar.setFloatable(True)
            # Set orientation based on toolbar area (left/right = vertical, top/bottom = horizontal)
            if area in (Qt.ToolBarArea.LeftToolBarArea, Qt.ToolBarArea.RightToolBarArea):
                toolbar.setOrientation(Qt.Orientation.Vertical)
            else:
                toolbar.setOrientation(Qt.Orientation.Horizontal)
            toolbar.setStyleSheet("""
                QToolBar::separator { width: 0px; }
                QToolBar QToolButton {
                    padding: 4px 8px;
                }
            """)
            self.addToolBar(area, toolbar)
            return toolbar

        # Left side toolbar - organized with QToolButton menus
        left_toolbar = create_toolbar("Left Toolbar", Qt.ToolBarArea.LeftToolBarArea)

        # Telescope Operations menu button
        telescope_menu = QMenu("Telescope Operations", self)

        connect_icon = self._create_icon("link", ["network-connect", "network-wired", "network-workgroup"])
        self.connect_action = telescope_menu.addAction(connect_icon, "Connect")
        self.connect_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.connect_action.setToolTip("CONNECT")
        self.connect_action.setStatusTip("Connect to telescope")
        self.connect_action.triggered.connect(self._on_connect)

        disconnect_icon = self._create_icon("link_off", ["network-disconnect", "network-offline", "network-error"])
        self.disconnect_action = telescope_menu.addAction(disconnect_icon, "Disconnect")
        self.disconnect_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.disconnect_action.setToolTip("DISCONNECT")
        self.disconnect_action.setStatusTip("Disconnect from telescope")
        self.disconnect_action.triggered.connect(self._on_disconnect)
        self.disconnect_action.setEnabled(False)

        telescope_menu.addSeparator()

        calibrate_icon = self._create_icon("crosshairs", ["tools-check-spelling", "preferences-system", "configure"])
        self.calibrate_action = telescope_menu.addAction(calibrate_icon, "Calibrate")
        self.calibrate_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.calibrate_action.setToolTip("CALIBRATE")
        self.calibrate_action.setStatusTip("Calibrate telescope")
        self.calibrate_action.triggered.connect(self._on_calibrate)
        self.calibrate_action.setEnabled(False)

        align_icon = self._create_icon("my_location", ["edit-find", "system-search", "find-location"])
        self.align_action = telescope_menu.addAction(align_icon, "Align")
        self.align_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.align_action.setToolTip("ALIGN")
        self.align_action.setStatusTip("Align telescope")
        self.align_action.triggered.connect(self._on_align)
        self.align_action.setEnabled(False)

        telescope_menu.addSeparator()

        # Tracking History action
        tracking_icon = self._create_icon("chart", ["chart-line", "graph", "analytics"])
        self.tracking_history_action = telescope_menu.addAction(tracking_icon, "Tracking History Graph")
        self.tracking_history_action.setIconVisibleInMenu(True)
        self.tracking_history_action.setToolTip("TRACKING HISTORY")
        self.tracking_history_action.setStatusTip("View real-time tracking history graph")
        self.tracking_history_action.triggered.connect(self._on_tracking_history)
        self.tracking_history_action.setEnabled(False)

        telescope_button = QToolButton()
        telescope_button.setText("Telescope")
        telescope_button.setIcon(connect_icon)  # Use connect icon as default
        telescope_button.setMenu(telescope_menu)
        telescope_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        telescope_button.setToolTip("TELESCOPE OPERATIONS")
        telescope_button.setStatusTip("Telescope connection and control operations")
        left_toolbar.addWidget(telescope_button)

        # Planning Tools menu button
        planning_menu = QMenu("Planning Tools", self)

        catalog_icon = self._create_icon("catalog", ["folder", "folder-open", "database"])
        self.catalog_action = planning_menu.addAction(catalog_icon, "Catalog")
        self.catalog_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.catalog_action.setToolTip("CATALOG")
        self.catalog_action.setStatusTip("Open catalog search window")
        self.catalog_action.triggered.connect(self._on_catalog)

        # Goto Queue action
        queue_icon = self._create_icon("list", ["view-list", "format-list-bulleted", "playlist-play", "list"])
        self.goto_queue_action = planning_menu.addAction(queue_icon, "Goto Queue / Sequence")
        self.goto_queue_action.setIconVisibleInMenu(True)
        self.goto_queue_action.setToolTip("GOTO QUEUE")
        self.goto_queue_action.setStatusTip("Open goto queue/sequence window")
        self.goto_queue_action.triggered.connect(self._on_goto_queue)

        favorites_icon = self._create_icon("star", ["star", "bookmark", "favorite"])
        self.favorites_action = planning_menu.addAction(favorites_icon, "Favorites")
        self.favorites_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.favorites_action.setToolTip("FAVORITES")
        self.favorites_action.setStatusTip("View favorite objects")
        self.favorites_action.triggered.connect(self._on_favorites)

        observation_log_icon = self._create_icon("menu_book", ["book-open-variant", "book", "document"])
        self.observation_log_action = planning_menu.addAction(observation_log_icon, "Observation Log")
        self.observation_log_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.observation_log_action.setToolTip("OBSERVATION LOG")
        self.observation_log_action.setStatusTip("View and manage observation logs")
        self.observation_log_action.triggered.connect(self._on_observation_log)

        dashboard_icon = self._create_icon("dashboard", ["view-dashboard", "chart-line", "monitor-dashboard"])
        self.dashboard_action = planning_menu.addAction(dashboard_icon, "Live Dashboard")
        self.dashboard_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.dashboard_action.setToolTip("LIVE DASHBOARD")
        self.dashboard_action.setStatusTip("View real-time observing conditions dashboard")
        self.dashboard_action.triggered.connect(self._on_live_dashboard)

        planning_menu.addSeparator()

        # Equipment Manager
        equipment_icon = self._create_icon("settings", ["cog", "tools", "wrench"])
        self.equipment_action = planning_menu.addAction(equipment_icon, "Equipment Manager")
        self.equipment_action.setIconVisibleInMenu(True)
        self.equipment_action.setToolTip("EQUIPMENT MANAGER")
        self.equipment_action.setStatusTip("Manage eyepieces, filters, and cameras")
        self.equipment_action.triggered.connect(self._on_equipment_manager)

        planning_menu.addSeparator()

        weather_icon = self._create_icon("weather", ["weather-cloudy", "weather-partly-cloudy", "weather-sunny"])
        self.weather_action = planning_menu.addAction(weather_icon, "Weather")
        self.weather_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.weather_action.setToolTip("WEATHER")
        self.weather_action.setStatusTip("View current weather conditions")
        self.weather_action.triggered.connect(self._on_weather)

        checklist_icon = self._create_icon("checklist", ["format-list-checks", "check-circle"])
        self.checklist_action = planning_menu.addAction(checklist_icon, "Checklist")
        self.checklist_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.checklist_action.setToolTip("CHECKLIST")
        self.checklist_action.setStatusTip("View observation checklist")
        self.checklist_action.triggered.connect(self._on_checklist)

        time_slots_icon = self._create_icon("time_slots", ["clock-outline", "timer"])
        self.time_slots_action = planning_menu.addAction(time_slots_icon, "Time Slots")
        self.time_slots_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.time_slots_action.setToolTip("TIME SLOTS")
        self.time_slots_action.setStatusTip("View available time slots")
        self.time_slots_action.triggered.connect(self._on_time_slots)

        transit_times_icon = self._create_icon("transit_times", ["transit-connection", "arrow-right-bold"])
        self.transit_times_action = planning_menu.addAction(transit_times_icon, "Transit Times")
        self.transit_times_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.transit_times_action.setToolTip("TRANSIT TIMES")
        self.transit_times_action.setStatusTip("View transit times")
        self.transit_times_action.triggered.connect(self._on_transit_times)

        planning_menu.addSeparator()

        quick_ref_icon = self._create_icon("quick_reference", ["book-open-variant", "information"])
        self.quick_reference_action = planning_menu.addAction(quick_ref_icon, "Quick Reference")
        self.quick_reference_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.quick_reference_action.setToolTip("QUICK REFERENCE")
        self.quick_reference_action.setStatusTip("Open quick reference guide")
        self.quick_reference_action.triggered.connect(self._on_quick_reference)

        glossary_icon = self._create_icon("glossary", ["book-open-page-variant", "book-open-variant"])
        self.glossary_action = planning_menu.addAction(glossary_icon, "Glossary")
        self.glossary_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.glossary_action.setToolTip("GLOSSARY")
        self.glossary_action.setStatusTip("View astronomical glossary")
        self.glossary_action.triggered.connect(self._on_glossary)

        planning_menu.addSeparator()

        # Object Comparison Tool
        compare_icon = self._create_icon("compare", ["compare", "view-split-vertical", "diff"])
        self.compare_action = planning_menu.addAction(compare_icon, "Compare Objects")
        self.compare_action.setIconVisibleInMenu(True)
        self.compare_action.setToolTip("COMPARE OBJECTS")
        self.compare_action.setStatusTip("Compare objects side-by-side")
        self.compare_action.triggered.connect(self._on_compare_objects)

        planning_button = QToolButton()
        planning_button.setText("Planning")
        planning_button.setIcon(catalog_icon)  # Icon for the button itself
        planning_button.setMenu(planning_menu)
        planning_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)  # Only opens menu
        planning_button.setToolTip("PLANNING TOOLS")
        planning_button.setStatusTip("Observation planning and reference tools")
        left_toolbar.addWidget(planning_button)

        # Spacer widget
        spacer_widget = QWidget()
        spacer_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        spacer_widget.setMinimumHeight(1)
        left_toolbar.addWidget(spacer_widget)

        # Tools menu button (Communication Log, Settings)
        tools_menu = QMenu("Tools", self)

        log_icon = self._create_icon("console", ["terminal", "code-tags", "text-box"])
        self.log_toggle_action = tools_menu.addAction(log_icon, "Communication Log")
        self.log_toggle_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.log_toggle_action.setToolTip("COMMUNICATION LOG")
        self.log_toggle_action.setStatusTip("Toggle communication log panel")
        self.log_toggle_action.setCheckable(True)
        self.log_toggle_action.setChecked(False)
        self.log_toggle_action.triggered.connect(self._on_toggle_log)

        tools_menu.addSeparator()

        settings_icon = self._create_icon("settings", ["cog", "settings"])
        self.settings_action = tools_menu.addAction(settings_icon, "Settings")
        self.settings_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.settings_action.setToolTip("SETTINGS")
        self.settings_action.setStatusTip("View and manage settings")
        self.settings_action.triggered.connect(self._on_settings)

        tools_button = QToolButton()
        tools_button.setText("Tools")
        tools_button.setIcon(settings_icon)  # Icon for the button itself
        tools_button.setMenu(tools_menu)
        tools_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)  # Only opens menu
        tools_button.setToolTip("TOOLS")
        tools_button.setStatusTip("Application tools and settings")
        left_toolbar.addWidget(tools_button)

        # Right side toolbar - Celestial Objects menu
        right_toolbar = create_toolbar("Right Toolbar", Qt.ToolBarArea.RightToolBarArea)

        # Celestial Objects menu button
        celestial_menu = QMenu("Celestial Objects", self)

        # Celestial object actions (using alpha-box-outline pattern)
        celestial_objects = [
            ("aurora", "Aurora", ["alpha-a-box-outline"]),
            ("binoculars", "Binoculars", ["alpha-b-box-outline"]),
            ("comets", "Comets", ["alpha-c-box-outline"]),
            ("eclipse", "Eclipse", ["alpha-e-box-outline"]),
            ("iss", "ISS", ["alpha-i-box-outline"]),
            ("meteors", "Meteors", ["alpha-m-box-outline"]),
            ("milky_way", "Milky Way", ["alpha-m-box-outline"]),
            ("naked_eye", "Naked Eye", ["alpha-n-box-outline"]),
            ("occultations", "Occultations", ["alpha-o-box-outline"]),
            ("planets", "Planets", ["alpha-p-box-outline"]),
            ("satellites", "Satellites", ["alpha-s-box-outline"]),
            ("space_weather", "Space Weather", ["alpha-s-box-outline"]),
            ("variables", "Variables", ["alpha-v-box-outline"]),
            ("zodiacal", "Zodiacal", ["alpha-z-box-outline"]),
        ]

        # Store planets action for default button action

        for obj_name, display_name, icon_names in celestial_objects:
            icon = self._create_icon(obj_name, icon_names)
            action = celestial_menu.addAction(icon, display_name)
            action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
            action.setToolTip(display_name.upper())
            action.setStatusTip(f"View {display_name} information")
            action.triggered.connect(lambda checked, name=obj_name: self._on_celestial_object(name))
            # Store action for later reference
            setattr(self, f"{obj_name}_action", action)
            # Save planets action for default button
            if obj_name == "planets":
                pass
            # Disable buttons until API is implemented
            if obj_name == "occultations":
                action.setEnabled(False)
                action.setToolTip("Occultations (Coming Soon)")
                action.setStatusTip("Occultations feature is not yet implemented")
            elif obj_name == "variables":
                action.setEnabled(False)
                action.setToolTip("Variables (Coming Soon)")
                action.setStatusTip("Variables feature is not yet implemented")
            elif obj_name == "zodiacal":
                action.setEnabled(False)
                action.setToolTip("Zodiacal (Coming Soon)")
                action.setStatusTip("Zodiacal feature is not yet implemented")

        celestial_button = QToolButton()
        celestial_button.setText("Objects")
        # Use planets icon for the button itself
        planets_icon = self._create_icon("planets", ["alpha-p-box-outline"])
        celestial_button.setIcon(planets_icon)
        celestial_button.setMenu(celestial_menu)
        celestial_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)  # Only opens menu
        celestial_button.setToolTip("CELESTIAL OBJECTS")
        celestial_button.setStatusTip("View information about celestial objects")
        right_toolbar.addWidget(celestial_button)

    def _refresh_toolbar_icons(self) -> None:
        """Refresh toolbar icons after window is shown."""
        # Recreate icons to ensure FontAwesome/MDI fonts are loaded
        # Telescope operations
        self.connect_action.setIcon(
            self._create_icon("link", ["network-connect", "network-wired", "network-workgroup"])
        )
        self.disconnect_action.setIcon(
            self._create_icon("link_off", ["network-disconnect", "network-offline", "network-error"])
        )
        self.calibrate_action.setIcon(
            self._create_icon("crosshairs", ["tools-check-spelling", "preferences-system", "configure"])
        )
        self.align_action.setIcon(self._create_icon("my_location", ["edit-find", "system-search", "find-location"]))
        if hasattr(self, "tracking_history_action"):
            self.tracking_history_action.setIcon(self._create_icon("chart", ["chart-line", "graph", "analytics"]))
        # Planning tools
        if hasattr(self, "favorites_action"):
            self.favorites_action.setIcon(self._create_icon("star", ["star", "bookmark", "favorite"]))
        if hasattr(self, "observation_log_action"):
            self.observation_log_action.setIcon(
                self._create_icon("menu_book", ["book-open-variant", "book", "document"])
            )
        if hasattr(self, "dashboard_action"):
            self.dashboard_action.setIcon(
                self._create_icon("dashboard", ["view-dashboard", "chart-line", "monitor-dashboard"])
            )
        if hasattr(self, "equipment_action"):
            self.equipment_action.setIcon(self._create_icon("settings", ["cog", "tools", "wrench"]))
        self.weather_action.setIcon(
            self._create_icon("weather", ["weather-cloudy", "weather-partly-cloudy", "weather-sunny"])
        )
        self.checklist_action.setIcon(self._create_icon("checklist", ["format-list-checks", "check-circle"]))
        self.time_slots_action.setIcon(self._create_icon("time_slots", ["clock-outline", "timer"]))
        self.quick_reference_action.setIcon(self._create_icon("quick_reference", ["book-open-variant", "information"]))
        self.transit_times_action.setIcon(
            self._create_icon("transit_times", ["transit-connection", "arrow-right-bold"])
        )
        self.glossary_action.setIcon(self._create_icon("glossary", ["book-open-page-variant", "book-open-variant"]))
        if hasattr(self, "compare_action"):
            self.compare_action.setIcon(self._create_icon("compare", ["compare", "view-split-vertical", "diff"]))
        self.settings_action.setIcon(self._create_icon("settings", ["cog", "settings"]))
        # Celestial objects (using alpha-box-outline pattern)
        for obj_name in [
            "aurora",
            "binoculars",
            "comets",
            "eclipse",
            "iss",
            "meteors",
            "milky_way",
            "naked_eye",
            "occultations",
            "planets",
            "satellites",
            "space_weather",
            "variables",
            "zodiacal",
        ]:
            action = getattr(self, f"{obj_name}_action", None)
            if action:
                # Get first letter of object name for alpha-box-outline icon
                first_letter = obj_name[0].lower()
                fallback_icon = f"alpha-{first_letter}-box-outline"
                action.setIcon(self._create_icon(obj_name, [fallback_icon]))
        # Communication log toggle
        if hasattr(self, "log_toggle_action"):
            self.log_toggle_action.setIcon(self._create_icon("console", ["terminal", "code-tags", "text-box"]))
        # Catalog button
        if hasattr(self, "catalog_action"):
            self.catalog_action.setIcon(self._create_icon("catalog", ["folder", "folder-open", "folder-documents"]))
        # Goto Queue button
        if hasattr(self, "goto_queue_action"):
            self.goto_queue_action.setIcon(
                self._create_icon("list", ["view-list", "format-list-bulleted", "playlist-play", "list"])
            )
        # Table toolbar buttons
        if hasattr(self, "refresh_action"):
            self.refresh_action.setIcon(self._create_icon("refresh", ["view-refresh", "reload"]))
        if hasattr(self, "load_all_action"):
            self.load_all_action.setIcon(self._create_icon("download", ["download", "folder-download"]))
        if hasattr(self, "info_action"):
            self.info_action.setIcon(self._create_icon("info", ["dialog-information", "help-about"]))

    def _set_theme(self, mode: ThemeMode) -> None:
        """Set the theme to the specified mode."""
        self.theme_mode_preference = mode
        self.theme.set_mode(mode)
        self._update_theme_menu_state()

        # Ensure theme is applied to app
        from PySide6.QtWidgets import QApplication

        qapp = QApplication.instance()
        if qapp and isinstance(qapp, QApplication):
            self.theme.apply(qapp)

        # Refresh icons to match new theme
        self._refresh_toolbar_icons()
        # Update textbox placeholder text colors
        if hasattr(self, "filter_textbox"):
            self._update_textbox_placeholder_style(self.filter_textbox)

    def _update_textbox_placeholder_style(self, textbox: QLineEdit) -> None:
        """Update placeholder text color to be theme-aware."""
        from PySide6.QtGui import QPalette

        app = QGuiApplication.instance()
        if app and isinstance(app, QGuiApplication):
            palette = app.palette()
            window_color = palette.color(QPalette.ColorRole.Window)
            brightness = window_color.lightness()
            is_dark = brightness < 128

            # Set placeholder text color based on theme
            # Use a lighter gray for dark mode, darker gray for light mode
            placeholder_color = "#999999" if is_dark else "#666666"
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

    def _on_system_theme_changed(self) -> None:
        """Handle system theme changes."""
        # Only update if user preference is SYSTEM
        if self.theme_mode_preference == ThemeMode.SYSTEM:
            self.theme.set_mode(ThemeMode.SYSTEM)
            # Refresh icons to match new theme
            self._refresh_toolbar_icons()
            # Update textbox placeholder text colors
            if hasattr(self, "filter_textbox"):
                self._update_textbox_placeholder_style(self.filter_textbox)

    def _update_theme_menu_state(self) -> None:
        """Update the checked state of theme menu actions."""
        # Uncheck all first
        for action in self.theme_action_group.actions():
            action.setChecked(False)

        # Check based on user preference
        if self.theme_mode_preference == ThemeMode.SYSTEM:
            self.system_theme_action.setChecked(True)
        elif self.theme_mode_preference == ThemeMode.DARK:
            self.dark_theme_action.setChecked(True)
        else:  # ThemeMode.LIGHT
            self.light_theme_action.setChecked(True)

    def _create_control_panel(self) -> QWidget:
        """Create the telescope control panel with tabs for celestial object types."""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Create tab bar for celestial object types
        self.tab_widget = QTabWidget()
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        # Add a tab for each CelestialObjectType
        for obj_type in CelestialObjectType:
            # Create human-readable label (capitalize and replace underscores)
            label = obj_type.value.replace("_", " ").title()
            # Create a table widget for each tab
            table = self._create_objects_table(obj_type)
            self.tab_widget.addTab(table, label)

        layout.addWidget(self.tab_widget)

        return panel

    def _create_objects_table(self, obj_type: CelestialObjectType) -> QTableWidget:
        """Create a table widget displaying objects of the specified type."""
        table = QTableWidget()
        # For constellation and asterism tabs, show name list with favorites
        if obj_type == CelestialObjectType.CONSTELLATION:
            table.setColumnCount(3)
            table.setHorizontalHeaderLabels(["Constellation", "Visible Stars", "Favorite"])
        elif obj_type == CelestialObjectType.ASTERISM:
            table.setColumnCount(3)
            table.setHorizontalHeaderLabels(["Asterism", "Visible Stars", "Favorite"])
        # For star tab, add a Constellation column
        elif obj_type == CelestialObjectType.STAR:
            table.setColumnCount(12)
            table.setHorizontalHeaderLabels(
                [
                    "Priority",
                    "Name",
                    "Type",
                    "Constellation",
                    "Mag",
                    "Alt",
                    "Visibility",
                    "Transit",
                    "Moon Sep",
                    "Chance",
                    "Tips",
                    "Favorite",
                ]
            )
        else:
            table.setColumnCount(11)
            table.setHorizontalHeaderLabels(
                [
                    "Priority",
                    "Name",
                    "Type",
                    "Mag",
                    "Alt",
                    "Visibility",
                    "Transit",
                    "Moon Sep",
                    "Chance",
                    "Tips",
                    "Favorite",
                ]
            )

        # Set column widths - all columns are resizable with minimum width based on header text
        header = table.horizontalHeader()

        # Get header labels for minimum width calculation
        if obj_type == CelestialObjectType.CONSTELLATION:
            header_labels = ["Constellation", "Visible Stars", "Favorite"]
        elif obj_type == CelestialObjectType.ASTERISM:
            header_labels = ["Asterism", "Visible Stars", "Favorite"]
        elif obj_type == CelestialObjectType.STAR:
            header_labels = [
                "Priority",
                "Name",
                "Type",
                "Constellation",
                "Mag",
                "Alt",
                "Visibility",
                "Transit",
                "Moon Sep",
                "Chance",
                "Tips",
                "Favorite",
            ]
        else:
            header_labels = [
                "Priority",
                "Name",
                "Type",
                "Mag",
                "Alt",
                "Visibility",
                "Transit",
                "Moon Sep",
                "Chance",
                "Tips",
                "Favorite",
            ]

        # Calculate minimum widths based on header text
        font_metrics = QFontMetrics(header.font())
        min_widths = [font_metrics.horizontalAdvance(label) + 20 for label in header_labels]  # Add 20px padding

        # Set all columns to Interactive mode (resizable) and set minimum widths
        for col in range(table.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            header.setMinimumSectionSize(min_widths[col])

        # Store property to track if initial resize has been done
        table.setProperty("initial_resize_done", False)

        # Enable sorting
        table.setSortingEnabled(True)

        # Set selection behavior
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        # Connect selection change to update info button state
        table.itemSelectionChanged.connect(self._on_table_selection_changed)

        # Connect sort indicator change to track sorting
        header.sortIndicatorChanged.connect(
            lambda logical_index, order: self._on_sort_changed(table, logical_index, order)
        )

        # Connect double-click to copy cell text
        table.itemDoubleClicked.connect(self._on_cell_double_clicked)

        # Enable context menu for favorites
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(lambda pos: self._on_table_context_menu(table, pos))

        # Load data asynchronously (will be populated when tab is shown)
        # Store the object type for later loading
        table.setProperty("object_type", obj_type.value)

        # Store sort state (column index, order)
        table.setProperty("sort_column", -1)
        table.setProperty("sort_order", Qt.SortOrder.AscendingOrder)

        return table

    def _load_objects_table(self, table: QTableWidget, show_progress: bool = True) -> None:
        """Load objects data into the table (checks cache first, then loads in background)."""
        obj_type_str = table.property("object_type")
        if not obj_type_str:
            return

        # Check cache first
        if obj_type_str in self._objects_cache:
            objects = self._objects_cache[obj_type_str]
            if objects:
                # Type ignore: objects can be list[str] for constellations/asterisms
                # but this method only handles list[RecommendedObject]
                if obj_type_str in ("constellation", "asterism"):
                    # These are handled separately in _on_tab_changed
                    return
                self._populate_table(table, objects)  # type: ignore[arg-type]
            return

        # Check if already loading
        if obj_type_str in self._loading_threads:
            return

        # Show loading dialog only if requested
        progress: QProgressDialog | None = None
        if show_progress:
            progress = QProgressDialog(
                f"Loading {obj_type_str.replace('_', ' ').title()} objects...", "Cancel", 0, 0, self
            )
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setCancelButton(None)  # Disable cancel button
            progress.show()

        # Create and start worker thread
        thread = ObjectsLoaderThread(obj_type_str)
        thread.data_loaded.connect(lambda obj_type, objs: self._on_objects_loaded(obj_type, objs, table, progress))
        self._loading_threads[obj_type_str] = thread
        thread.start()

    def _on_objects_loaded(
        self,
        obj_type_str: str,
        objects: list[RecommendedObject] | list[str] | None,
        table: QTableWidget,
        progress: QProgressDialog | None,
    ) -> None:
        """Handle objects data loaded signal from worker thread."""
        # Close loading dialog if it was shown
        if progress is not None and progress.isVisible():
            progress.close()

        # Remove thread from tracking
        if obj_type_str in self._loading_threads:
            del self._loading_threads[obj_type_str]

        if objects is None:
            # Error occurred, already logged in thread
            return

        # Populate table (must be done on main thread)
        if objects:
            if obj_type_str == "constellation":
                # Cache the names for constellations
                self._objects_cache[obj_type_str] = objects  # type: ignore[assignment]
                self._populate_constellation_table(table, objects)  # type: ignore[arg-type]
            elif obj_type_str == "asterism":
                # For asterisms, objects is list of tuples (Asterism, alt, az)
                # Extract just the names for the table population and cache
                if isinstance(objects, list) and objects and isinstance(objects[0], tuple):
                    asterism_names = [asterism[0].name for asterism in objects]  # type: ignore[index,union-attr]
                    # Store names in cache (for refresh operations)
                    self._objects_cache[obj_type_str] = asterism_names  # type: ignore[assignment]
                    self._populate_constellation_table(table, asterism_names)  # type: ignore[arg-type]
                    # Store full objects in separate cache for member_stars access
                    self._asterism_objects_cache = {asterism[0].name: asterism[0] for asterism in objects}  # type: ignore[index,union-attr]
                else:
                    asterism_names = []
                    self._objects_cache[obj_type_str] = asterism_names
                    self._populate_constellation_table(table, asterism_names)
                    self._asterism_objects_cache = {}
            else:
                # Cache the data (even if empty, to indicate data was loaded)
                self._objects_cache[obj_type_str] = objects
                self._populate_table(table, objects)  # type: ignore[arg-type]
        else:
            # Data was loaded but no objects match criteria - show message
            self._show_no_data_message(table, obj_type_str)

    def _populate_table(self, table: QTableWidget, objects: list[RecommendedObject]) -> None:
        """Populate table with objects data (must be called on main thread)."""
        if not objects:
            return

        # Temporarily disable sorting while populating to improve performance
        table.setSortingEnabled(False)

        table.setRowCount(len(objects))

        # Get conditions for timezone (use cached if available, otherwise get fresh)
        try:
            from celestron_nexstar.api.observation.observation_planner import ObservationPlanner

            planner = ObservationPlanner()
            conditions = planner.get_tonight_conditions()
            tz = get_local_timezone(conditions.latitude, conditions.longitude)
        except Exception:
            tz = None

        # Check if this is the star tab (needs constellation column)
        is_star_tab = table.property("object_type") == "star"

        # Check all favorites in a single batch query (much more efficient)
        from celestron_nexstar.api.favorites import are_favorites

        object_names = [obj_rec.obj.name for obj_rec in objects]
        try:
            favorite_dict = asyncio.run(are_favorites(object_names))
            # Convert dict to list in same order as objects
            favorite_statuses = [favorite_dict.get(name, False) for name in object_names]
        except Exception:
            # If batch check fails, fall back to all False
            favorite_statuses = [False] * len(objects)

        # Now populate table with all data
        for row, obj_rec in enumerate(objects):
            # Priority (stars)
            priority_stars = "★" * (6 - obj_rec.priority)
            table.setItem(row, 0, QTableWidgetItem(priority_stars))

            # Name (no star indicator - we have a dedicated favorites column)
            obj = obj_rec.obj
            display_name = obj.common_name or obj.name

            name_item = QTableWidgetItem(display_name)
            # Store object name in item data for context menu
            name_item.setData(Qt.ItemDataRole.UserRole, obj.name)
            table.setItem(row, 1, name_item)

            # Type
            table.setItem(row, 2, QTableWidgetItem(obj.object_type.value))

            # Column offset for star tab (has constellation column)
            col_offset = 1 if is_star_tab else 0

            # Constellation (only for star tab)
            if is_star_tab:
                constellation_text = obj.constellation or "-"
                table.setItem(row, 3, QTableWidgetItem(constellation_text))

            # Magnitude
            mag_text = f"{obj_rec.apparent_magnitude:.2f}" if obj_rec.apparent_magnitude else "-"
            table.setItem(row, 3 + col_offset, QTableWidgetItem(mag_text))

            # Altitude
            alt_text = f"{obj_rec.altitude:.0f}°"
            table.setItem(row, 4 + col_offset, QTableWidgetItem(alt_text))

            # Visibility indicator
            visibility_item = self._create_visibility_item(obj_rec.altitude, obj_rec.visibility_probability)
            table.setItem(row, 5 + col_offset, visibility_item)

            # Transit time
            best_time = obj_rec.best_viewing_time
            if best_time.tzinfo is None:
                best_time = best_time.replace(tzinfo=UTC)
            if tz:
                local_time = best_time.astimezone(tz)
                time_str = local_time.strftime("%I:%M %p")
            else:
                time_str = best_time.strftime("%I:%M %p UTC")
            table.setItem(row, 6 + col_offset, QTableWidgetItem(time_str))

            # Moon separation
            moon_sep_text = "-"
            if obj_rec.moon_separation_deg is not None:
                moon_sep_text = f"{obj_rec.moon_separation_deg:.0f}°"
            table.setItem(row, 7 + col_offset, QTableWidgetItem(moon_sep_text))

            # Visibility probability
            prob = obj_rec.visibility_probability
            prob_text = f"{prob:.0%}"
            table.setItem(row, 8 + col_offset, QTableWidgetItem(prob_text))

            # Tips
            tips_text = "; ".join(obj_rec.viewing_tips[:2]) if obj_rec.viewing_tips else ""
            if len(tips_text) > 50:
                tips_text = tips_text[:47] + "..."
            table.setItem(row, 9 + col_offset, QTableWidgetItem(tips_text))

            # Favorite (check/X icon) - use pre-fetched result
            favorite_col = 10 + col_offset  # Last column
            is_fav = favorite_statuses[row]
            favorite_item = self._create_favorite_item(is_fav)
            # Store object name in item data for context menu
            favorite_item.setData(Qt.ItemDataRole.UserRole, obj.name)
            # Store sort value in a custom role (UserRole + 1) for sorting: 1 = favorite, 0 = not
            # DisplayRole is empty string so no text shows
            favorite_item.setData(Qt.ItemDataRole.UserRole + 1, 1 if is_fav else 0)
            table.setItem(row, favorite_col, favorite_item)

        # Re-enable sorting after populating
        table.setSortingEnabled(True)

        # Restore previous sort state if available, otherwise default to Priority (column 0)
        sort_column = table.property("sort_column")
        sort_order = table.property("sort_order")
        header = table.horizontalHeader()
        if sort_column >= 0:
            header.setSortIndicator(sort_column, sort_order)
        else:
            # Default to Priority column (0) descending on first load
            header.setSortIndicator(0, Qt.SortOrder.DescendingOrder)
            table.setProperty("sort_column", 0)
            table.setProperty("sort_order", Qt.SortOrder.DescendingOrder)

        # Resize columns to contents after initial population (one-time)
        if not table.property("initial_resize_done"):
            # Temporarily switch to ResizeToContents to set initial sizes
            for col in range(table.columnCount()):
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
            # Force a resize event
            table.resizeColumnsToContents()
            # Switch back to Interactive mode for manual resizing
            for col in range(table.columnCount()):
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            table.setProperty("initial_resize_done", True)

    def _show_no_data_message(self, table: QTableWidget, obj_type_str: str) -> None:
        """Show a message when data was loaded but no objects match criteria."""
        # Temporarily disable sorting
        table.setSortingEnabled(False)

        # Get human-readable type name
        type_name = obj_type_str.replace("_", " ").title()

        # Get original column count (preserve table structure)
        original_cols = table.columnCount()
        if original_cols == 0:
            # If no columns, set to 1 for the message
            table.setColumnCount(1)
            original_cols = 1

        # Set table to show one row with message
        table.setRowCount(1)

        # Create a message item
        message = f"No {type_name} objects match the current criteria.\n\n"
        message += "This could be due to:\n"
        message += "• Objects are below the horizon (< 20° altitude)\n"
        message += "• Objects are too faint for current conditions\n"
        message += "• No objects of this type are currently visible\n"
        message += "• Filter text is hiding all results"

        message_item = QTableWidgetItem(message)
        message_item.setFlags(Qt.ItemFlag.NoItemFlags)  # Make it non-selectable
        table.setItem(0, 0, message_item)

        # Center align the message
        item = table.item(0, 0)
        if item:
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

        # Make the message row span all columns
        if original_cols > 1:
            table.setSpan(0, 0, 1, original_cols)

        # Set column widths to prevent horizontal scrolling
        # Make columns stretch to fill available space without exceeding table width
        header = table.horizontalHeader()
        if original_cols > 1:
            # Set all columns to stretch mode so they fill the table width
            for col in range(original_cols):
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        else:
            # Single column - make it stretch
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        # Enable word wrapping for the table to handle long messages
        table.setWordWrap(True)

        # Set row height to accommodate message (with word wrapping)
        table.setRowHeight(0, 120)

        # Re-enable sorting (though it won't do much with one row)
        table.setSortingEnabled(True)

    def _show_no_data_message_alt(self, table: QTableWidget, obj_type_str: str) -> None:
        """Show a message when data was loaded but no objects match criteria."""
        # Temporarily disable sorting
        table.setSortingEnabled(False)

        # Get human-readable type name
        type_name = obj_type_str.replace("_", " ").title()

        # Set table to show one row with message
        table.setRowCount(1)
        # Keep original column count
        original_cols = table.columnCount()
        if original_cols == 0:
            table.setColumnCount(1)

        # Create a message item
        message = f"No {type_name} objects match the current criteria.\n\n"
        message += "This could be due to:\n"
        message += "• Objects are below the horizon (< 20° altitude)\n"
        message += "• Objects are too faint for current conditions\n"
        message += "• No objects of this type are currently visible\n"
        message += "• Filter text is hiding all results"

        message_item = QTableWidgetItem(message)
        message_item.setFlags(Qt.ItemFlag.NoItemFlags)  # Make it non-selectable
        table.setItem(0, 0, message_item)

        # Center align the message
        item = table.item(0, 0)
        if item:
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

        # Make the message row span all columns
        if original_cols > 1:
            table.setSpan(0, 0, 1, original_cols)

        # Set row height to accommodate message
        table.setRowHeight(0, 120)

        # Re-enable sorting (though it won't do much with one row)
        table.setSortingEnabled(True)

    def _count_visible_stars_for_asterisms_batch(
        self, asterism_names: list[str], asterism_objects: dict[str, Any]
    ) -> dict[str, int]:
        """Count the number of visible component stars for multiple asterisms in a single batch operation."""
        try:
            from celestron_nexstar.api.core.enums import SkyBrightness
            from celestron_nexstar.api.database.database import get_database
            from celestron_nexstar.api.location.light_pollution import get_light_pollution_data
            from celestron_nexstar.api.location.observer import get_observer_location
            from celestron_nexstar.api.observation.observation_planner import ObservationPlanner
            from celestron_nexstar.api.observation.optics import get_current_configuration
            from celestron_nexstar.api.observation.visibility import assess_visibility

            async def _count_all_stars() -> dict[str, int]:
                db = get_database()
                location = get_observer_location()
                config = get_current_configuration()
                planner = ObservationPlanner()
                conditions = planner.get_tonight_conditions()

                async with db._AsyncSession() as session:
                    # Get sky brightness from light pollution (once for all asterisms)
                    light_pollution = await get_light_pollution_data(session, location.latitude, location.longitude)
                    # Map Bortle class to SkyBrightness
                    bortle_to_sky_brightness = {
                        1: SkyBrightness.EXCELLENT,
                        2: SkyBrightness.EXCELLENT,
                        3: SkyBrightness.GOOD,
                        4: SkyBrightness.FAIR,
                        5: SkyBrightness.FAIR,
                        6: SkyBrightness.POOR,
                        7: SkyBrightness.URBAN,
                        8: SkyBrightness.URBAN,
                        9: SkyBrightness.URBAN,
                    }
                    sky_brightness = bortle_to_sky_brightness.get(
                        light_pollution.bortle_class.value, SkyBrightness.FAIR
                    )

                    # Count visible stars for each asterism
                    counts: dict[str, int] = {}
                    for asterism_name in asterism_names:
                        asterism = asterism_objects.get(asterism_name)
                        if not asterism or not asterism.member_stars:
                            counts[asterism_name] = 0
                            continue

                        visible_count = 0
                        # Look up each member star by name
                        for star_name in asterism.member_stars:
                            # Try to find the star in the database
                            star = await db.get_by_name(star_name.strip())
                            if not star:
                                continue

                            # Calculate visibility info
                            vis_info = assess_visibility(
                                star,
                                config=config,
                                sky_brightness=sky_brightness,
                                min_altitude_deg=20.0,
                                observer_lat=location.latitude,
                                observer_lon=location.longitude,
                                dt=conditions.timestamp,
                            )

                            # Calculate visibility probability
                            visibility_probability = vis_info.observability_score

                            # Apply seeing and weather factors
                            if visibility_probability > 0:
                                seeing_factor = min(1.0, conditions.seeing_score / 100.0)
                                cloud_cover = conditions.weather.cloud_cover_percent or 0.0
                                cloud_factor = 1.0 - (cloud_cover / 100.0)
                                visibility_probability *= seeing_factor * cloud_factor

                            # Count as visible if probability > 0
                            if visibility_probability > 0:
                                visible_count += 1

                        counts[asterism_name] = visible_count

                    return counts

            result = _run_async_safe(_count_all_stars())
            return result if isinstance(result, dict) else dict.fromkeys(asterism_names, 0)
        except Exception as e:
            logger.debug(f"Error counting visible stars for asterisms: {e}")
            # Return zeros for all asterisms on error
            return dict.fromkeys(asterism_names, 0)

    def _count_visible_stars_batch(self, constellation_names: list[str]) -> dict[str, int]:
        """Count the number of visible stars for multiple constellations in a single batch operation."""
        try:
            from celestron_nexstar.api.core.enums import SkyBrightness
            from celestron_nexstar.api.database.database import get_database
            from celestron_nexstar.api.location.light_pollution import get_light_pollution_data
            from celestron_nexstar.api.location.observer import get_observer_location
            from celestron_nexstar.api.observation.observation_planner import ObservationPlanner
            from celestron_nexstar.api.observation.optics import get_current_configuration
            from celestron_nexstar.api.observation.visibility import assess_visibility

            async def _count_all_stars() -> dict[str, int]:
                db = get_database()
                location = get_observer_location()
                config = get_current_configuration()
                planner = ObservationPlanner()
                conditions = planner.get_tonight_conditions()

                async with db._AsyncSession() as session:
                    # Get sky brightness from light pollution (once for all constellations)
                    light_pollution = await get_light_pollution_data(session, location.latitude, location.longitude)
                    # Map Bortle class to SkyBrightness
                    bortle_to_sky_brightness = {
                        1: SkyBrightness.EXCELLENT,
                        2: SkyBrightness.EXCELLENT,
                        3: SkyBrightness.GOOD,
                        4: SkyBrightness.FAIR,
                        5: SkyBrightness.FAIR,
                        6: SkyBrightness.POOR,
                        7: SkyBrightness.URBAN,
                        8: SkyBrightness.URBAN,
                        9: SkyBrightness.URBAN,
                    }
                    sky_brightness = bortle_to_sky_brightness.get(
                        light_pollution.bortle_class.value, SkyBrightness.FAIR
                    )

                    # Count stars for each constellation
                    counts: dict[str, int] = {}
                    for constellation_name in constellation_names:
                        # Get stars in this constellation
                        stars = await db.filter_objects(object_type="star", constellation=constellation_name, limit=100)

                        visible_count = 0
                        for star in stars:
                            # Calculate visibility info
                            vis_info = assess_visibility(
                                star,
                                config=config,
                                sky_brightness=sky_brightness,
                                min_altitude_deg=20.0,
                                observer_lat=location.latitude,
                                observer_lon=location.longitude,
                                dt=conditions.timestamp,
                            )

                            # Calculate visibility probability
                            visibility_probability = vis_info.observability_score

                            # Apply seeing and weather factors
                            if visibility_probability > 0:
                                seeing_factor = min(1.0, conditions.seeing_score / 100.0)
                                cloud_cover = conditions.weather.cloud_cover_percent or 0.0
                                cloud_factor = 1.0 - (cloud_cover / 100.0)
                                visibility_probability *= seeing_factor * cloud_factor

                            # Count as visible if probability > 0
                            if visibility_probability > 0:
                                visible_count += 1

                        counts[constellation_name] = visible_count

                    return counts

            result = _run_async_safe(_count_all_stars())
            return result if isinstance(result, dict) else dict.fromkeys(constellation_names, 0)
        except Exception as e:
            logger.debug(f"Error counting visible stars: {e}")
            # Return zeros for all constellations on error
            return dict.fromkeys(constellation_names, 0)

    def _populate_constellation_table(self, table: QTableWidget, constellation_names: list[str]) -> None:
        """Populate table with constellation names (must be called on main thread)."""
        if not constellation_names:
            # Show no data message for constellations/asterisms
            obj_type_str = table.property("object_type")
            if obj_type_str:
                self._show_no_data_message(table, obj_type_str)
            return

        # Sort constellation names alphabetically (A-Z)
        sorted_names = sorted(constellation_names, key=str.lower)

        # Temporarily disable sorting while populating to improve performance
        table.setSortingEnabled(False)

        table.setRowCount(len(sorted_names))

        # Check all favorites in a single batch query (much more efficient)
        from celestron_nexstar.api.favorites import are_favorites

        try:
            favorite_dict = asyncio.run(are_favorites(sorted_names))
            # Convert dict to list in same order as sorted_names
            favorite_statuses = [favorite_dict.get(name, False) for name in sorted_names]
        except Exception:
            # If batch check fails, fall back to all False
            favorite_statuses = [False] * len(sorted_names)

        # Check if this is a constellation table (has 3 columns) or asterism table (has 3 columns now)
        is_constellation_table = table.columnCount() == 3
        obj_type_str = table.property("object_type")
        is_asterism_table = obj_type_str == "asterism"

        # Count visible stars for all constellations/asterisms in a single batch operation (much more efficient)
        visible_star_counts: dict[str, int] = {}
        if is_constellation_table:
            try:
                if is_asterism_table:
                    # For asterisms, use the cached asterism objects to access member_stars
                    visible_star_counts = self._count_visible_stars_for_asterisms_batch(
                        sorted_names, self._asterism_objects_cache
                    )
                else:
                    # For constellations, count stars by constellation name
                    visible_star_counts = self._count_visible_stars_batch(sorted_names)
            except Exception as e:
                logger.debug(f"Error counting visible stars: {e}")
                # Fall back to zeros for all
                visible_star_counts = dict.fromkeys(sorted_names, 0)

        # Now populate table with all data
        for row, constellation_name in enumerate(sorted_names):
            # Constellation name (no star indicator - we have a dedicated favorites column)
            name_item = QTableWidgetItem(constellation_name)
            # Store object name in item data for context menu
            name_item.setData(Qt.ItemDataRole.UserRole, constellation_name)
            table.setItem(row, 0, name_item)

            if is_constellation_table:
                # Get visible star count from pre-calculated batch result
                visible_count = visible_star_counts.get(constellation_name, 0)
                stars_item = QTableWidgetItem(str(visible_count))
                stars_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                # Store count as numeric value for proper sorting
                stars_item.setData(Qt.ItemDataRole.UserRole, visible_count)
                table.setItem(row, 1, stars_item)

                # Favorite (check/X icon) - use pre-fetched result
                is_fav = favorite_statuses[row]
                favorite_item = self._create_favorite_item(is_fav)
                # Store object name in item data for context menu
                favorite_item.setData(Qt.ItemDataRole.UserRole, constellation_name)
                # Store sort value in a custom role (UserRole + 1) for sorting: 1 = favorite, 0 = not
                # DisplayRole is empty string so no text shows
                favorite_item.setData(Qt.ItemDataRole.UserRole + 1, 1 if is_fav else 0)
                table.setItem(row, 2, favorite_item)

        # Re-enable sorting after populating
        table.setSortingEnabled(True)

        # Set default sort indicator on Constellation column (A-Z ascending)
        header = table.horizontalHeader()
        header.setSortIndicator(0, Qt.SortOrder.AscendingOrder)
        table.setProperty("sort_column", 0)
        table.setProperty("sort_order", Qt.SortOrder.AscendingOrder)

        # Set column resize modes and minimum widths
        obj_type_str = table.property("object_type")
        if obj_type_str == "constellation":
            header_labels = ["Constellation", "Visible Stars", "Favorite"]
        elif obj_type_str == "asterism":
            header_labels = ["Asterism", "Visible Stars", "Favorite"]
        else:
            header_labels = ["Constellation", "Visible Stars", "Favorite"]  # Fallback

        # Calculate minimum widths based on header text
        font_metrics = QFontMetrics(header.font())
        min_widths = [font_metrics.horizontalAdvance(label) + 20 for label in header_labels]  # Add 20px padding

        # Set all columns to Interactive mode and minimum widths
        for col in range(table.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            header.setMinimumSectionSize(min_widths[col])

    def _create_table_toolbar(self) -> None:
        """Create toolbar for table controls in the top toolbar area."""
        toolbar = QToolBar("Table Controls")
        toolbar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

        # Filter textbox (left side)
        filter_label = QLabel()
        toolbar.addWidget(filter_label)
        self.filter_textbox = QLineEdit()
        self.filter_textbox.setPlaceholderText("Filter objects...")
        self.filter_textbox.textChanged.connect(self._on_filter_changed)
        self._update_textbox_placeholder_style(self.filter_textbox)
        toolbar.addWidget(self.filter_textbox)

        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        # Refresh button
        refresh_icon = self._create_icon("refresh", ["view-refresh", "reload"])
        self.refresh_action = toolbar.addAction(refresh_icon, "Refresh")
        self.refresh_action.setToolTip("REFRESH")
        self.refresh_action.setStatusTip("Refresh current tab")
        self.refresh_action.triggered.connect(self._on_refresh_clicked)

        # Load All button
        load_all_icon = self._create_icon("download", ["download", "folder-download"])
        self.load_all_action = toolbar.addAction(load_all_icon, "Load All")
        self.load_all_action.setToolTip("LOAD ALL")
        self.load_all_action.setStatusTip("Load all tabs")
        self.load_all_action.triggered.connect(self._on_load_all_clicked)

        # Info button (right side, initially disabled)
        info_icon = self._create_icon("info", ["dialog-information", "help-about"])
        self.info_action = toolbar.addAction(info_icon, "Info")
        self.info_action.setToolTip("INFO")
        self.info_action.setStatusTip("Show object information")
        self.info_action.setEnabled(False)  # Disabled until selection
        self.info_action.triggered.connect(self._on_info_clicked)

    def _on_table_selection_changed(self) -> None:
        """Handle table selection change - enable/disable info button."""
        # Get current table
        current_table = self._get_current_table()
        if current_table:
            selected_rows = current_table.selectionModel().selectedRows()
            # Enable if exactly 1 row is selected
            self.info_action.setEnabled(len(selected_rows) == 1)

    def _get_current_table(self) -> QTableWidget | None:
        """Get the currently visible table widget."""
        if not hasattr(self, "tab_widget"):
            return None
        current_index = self.tab_widget.currentIndex()
        if current_index < 0:
            return None
        widget = self.tab_widget.widget(current_index)
        if isinstance(widget, QTableWidget):
            return widget
        return None

    def _on_refresh_clicked(self) -> None:
        """Handle refresh button click - reload current tab."""
        current_table = self._get_current_table()
        if current_table:
            # Clear cache for this object type
            obj_type_str = current_table.property("object_type")
            if obj_type_str and obj_type_str in self._objects_cache:
                del self._objects_cache[obj_type_str]
            if obj_type_str == "asterism":
                self._asterism_objects_cache.clear()

            # Clear table
            current_table.setRowCount(0)

            # Reload
            self._load_objects_table(current_table)

    def _on_load_all_clicked(self) -> None:
        """Handle load all button click - load data for all tabs."""
        if not hasattr(self, "tab_widget"):
            return

        # Get all tabs that need loading
        tabs_to_load = []
        for i in range(self.tab_widget.count()):
            tab_widget = self.tab_widget.widget(i)
            if isinstance(tab_widget, QTableWidget):
                obj_type_str = tab_widget.property("object_type")
                # Load if not cached and not already loading
                if (
                    obj_type_str
                    and obj_type_str not in self._objects_cache
                    and obj_type_str not in self._loading_threads
                ):
                    tabs_to_load.append((i, tab_widget, obj_type_str))

        if not tabs_to_load:
            # All tabs are already loaded or loading
            return

        # Show loading dialog
        progress = QProgressDialog(
            f"Loading all tabs ({len(tabs_to_load)} tabs)...", "Cancel", 0, len(tabs_to_load), self
        )
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)  # Disable cancel button
        progress.show()

        # Process events to show the dialog immediately
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents()

        # Load each tab
        for idx, (_tab_index, table, obj_type_str) in enumerate(tabs_to_load):
            progress.setValue(idx)
            progress.setLabelText(
                f"Loading {obj_type_str.replace('_', ' ').title()} ({idx + 1}/{len(tabs_to_load)})..."
            )
            QApplication.processEvents()

            # Load the table (suppress individual progress dialog)
            self._load_objects_table(table, show_progress=False)

            # Wait for loading to complete (check if thread is done)
            if obj_type_str in self._loading_threads:
                thread = self._loading_threads[obj_type_str]
                thread.wait(5000)  # Wait up to 5 seconds for each tab

        progress.setValue(len(tabs_to_load))
        progress.close()

    def _on_filter_changed(self, text: str) -> None:
        """Handle filter text change - filter table rows."""
        current_table = self._get_current_table()
        if not current_table:
            return

        filter_text = text.lower().strip()

        # Show all rows if filter is empty
        if not filter_text:
            for row in range(current_table.rowCount()):
                current_table.showRow(row)
            return

        # Filter rows based on text matching any column
        for row in range(current_table.rowCount()):
            match = False
            for col in range(current_table.columnCount()):
                item = current_table.item(row, col)
                if item and filter_text in item.text().lower():
                    match = True
                    break
            current_table.setRowHidden(row, not match)

    def _on_info_clicked(self) -> None:
        """Handle info button click - show object information dialog."""
        current_table = self._get_current_table()
        if not current_table:
            return

        # Get selected row
        selected_rows = current_table.selectionModel().selectedRows()
        if not selected_rows or len(selected_rows) != 1:
            return

        row = selected_rows[0].row()

        # Check if this is the constellation or asterism tab
        obj_type = current_table.property("object_type")
        if obj_type == "constellation":
            # Get constellation name from column 0
            name_item = current_table.item(row, 0)
            if not name_item:
                return
            # Try to get from UserRole data first (clean name without star)
            constellation_name = name_item.data(Qt.ItemDataRole.UserRole)
            if not constellation_name:
                # Fallback: extract from display text (remove star if present)
                display_text = name_item.text()
                constellation_name = display_text.removeprefix("★ ").strip()

            # Show loading dialog
            progress = QProgressDialog(f"Loading information for {constellation_name}...", "Cancel", 0, 0, self)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setCancelButton(None)  # Disable cancel button
            progress.show()

            # Process events to show the dialog immediately
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()

            # Show constellation info dialog
            from celestron_nexstar.gui.dialogs.constellation_info_dialog import ConstellationInfoDialog

            constellation_dialog = ConstellationInfoDialog(self, constellation_name)
            progress.close()
            constellation_dialog.exec()
        elif obj_type == "asterism":
            # Get asterism name from the table
            name_item = current_table.item(row, 0)
            if not name_item:
                return
            # Try to get from UserRole data first (clean name without star)
            asterism_name = name_item.data(Qt.ItemDataRole.UserRole)
            if not asterism_name:
                # Fallback: extract from display text (remove star if present)
                display_text = name_item.text()
                asterism_name = display_text.removeprefix("★ ").strip()

            # Show asterism info dialog
            from celestron_nexstar.gui.dialogs.asterism_info_dialog import AsterismInfoDialog

            asterism_dialog = AsterismInfoDialog(self, asterism_name)
            asterism_dialog.exec()
        else:
            # Get object name from the Name column (column 1)
            name_item = current_table.item(row, 1)
            if not name_item:
                return

            # Try to get from UserRole data first (clean name without star)
            object_name = name_item.data(Qt.ItemDataRole.UserRole)
            if not object_name:
                # Fallback: extract from display text (remove star if present)
                display_text = name_item.text()
                object_name = display_text.removeprefix("★ ").strip()

            # Show loading dialog
            progress = QProgressDialog(f"Loading information for {object_name}...", "Cancel", 0, 0, self)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setCancelButton(None)  # Disable cancel button
            progress.show()

            # Process events to show the dialog immediately
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()

            # Show info dialog (it will load data in its constructor)
            from celestron_nexstar.gui.dialogs.object_info_dialog import ObjectInfoDialog

            obj_dialog = ObjectInfoDialog(self, object_name)
            progress.close()
            obj_dialog.exec()

    def _on_sort_changed(self, table: QTableWidget, logical_index: int, order: Qt.SortOrder) -> None:
        """Handle sort indicator change - track sort column and order."""
        table.setProperty("sort_column", logical_index)
        table.setProperty("sort_order", order)

    def _on_table_context_menu(self, table: QTableWidget, position: QPoint) -> None:
        """Handle context menu request on table."""
        item = table.itemAt(position)
        if not item:
            return

        # Get the row
        row = item.row()

        # Determine which column has the name based on object type
        obj_type = table.property("object_type")
        name_item = table.item(row, 0) if obj_type in ("constellation", "asterism") else table.item(row, 1)

        if not name_item:
            return

        # Try to get from UserRole data first (clean name without star)
        object_name = name_item.data(Qt.ItemDataRole.UserRole)
        if not object_name:
            # Fallback: try to extract from display text (remove star if present)
            display_text = name_item.text()
            object_name = display_text.removeprefix("★ ").strip()

        if not object_name:
            return

        # Check if favorite
        import asyncio

        from celestron_nexstar.api.favorites import is_favorite

        try:
            is_fav = asyncio.run(is_favorite(object_name))
        except Exception:
            is_fav = False

        # Create context menu
        menu = QMenu(self)

        # Info action
        info_action = menu.addAction("Show Info")
        info_action.triggered.connect(lambda: self._on_context_menu_info(table, row))

        menu.addSeparator()

        # Favorite/Unfavorite action
        if is_fav:
            fav_action = menu.addAction("★ Remove from Favorites")
            fav_action.triggered.connect(lambda: self._on_context_menu_unfavorite(object_name, table))
        else:
            fav_action = menu.addAction("☆ Add to Favorites")
            fav_action.triggered.connect(lambda: self._on_context_menu_favorite(object_name, table))

        menu.addSeparator()

        # Add to Queue action
        add_to_queue_action = menu.addAction("Add to Goto Queue")
        add_to_queue_action.triggered.connect(lambda: self._on_context_menu_add_to_queue(table, row))

        # Compare Objects action
        compare_action = menu.addAction("Compare Objects")
        compare_action.triggered.connect(lambda: self._on_context_menu_compare_objects(table, row))

        menu.addSeparator()

        # Log Observation action
        log_observation_action = menu.addAction("Log Observation")
        log_observation_action.triggered.connect(lambda: self._on_context_menu_log_observation(object_name))

        # Show menu at cursor position
        menu.exec(table.mapToGlobal(position))

    def _on_context_menu_info(self, table: QTableWidget, row: int) -> None:
        """Handle context menu info action."""
        # Determine which column has the name based on object type
        obj_type = table.property("object_type")
        name_item = table.item(row, 0) if obj_type in ("constellation", "asterism") else table.item(row, 1)

        if not name_item:
            return

        # Try to get from UserRole data first (clean name without star)
        object_name = name_item.data(Qt.ItemDataRole.UserRole)
        if not object_name:
            # Fallback: try to extract from display text
            display_text = name_item.text()
            object_name = display_text.removeprefix("★ ").strip()

        if object_name:
            # Use the existing info dialog functionality
            if obj_type == "constellation":
                from celestron_nexstar.gui.dialogs.constellation_info_dialog import ConstellationInfoDialog

                constellation_dialog = ConstellationInfoDialog(self, object_name)
                constellation_dialog.exec()
            elif obj_type == "asterism":
                from celestron_nexstar.gui.dialogs.asterism_info_dialog import AsterismInfoDialog

                asterism_dialog = AsterismInfoDialog(self, object_name)
                asterism_dialog.exec()
            else:
                from celestron_nexstar.gui.dialogs.object_info_dialog import ObjectInfoDialog

                obj_dialog = ObjectInfoDialog(self, object_name)
                obj_dialog.exec()
            # Refresh table in case favorite status changed
            self._refresh_table_favorites(table)

    def _on_context_menu_favorite(self, object_name: str, table: QTableWidget) -> None:
        """Handle context menu add to favorites action."""
        import asyncio

        from celestron_nexstar.api.favorites import add_favorite

        try:
            # Get object type from table property
            obj_type = table.property("object_type")
            success = asyncio.run(add_favorite(object_name, obj_type))
            if success:
                self._show_toast(f"Added '{object_name}' to favorites")
                # Refresh the table to show the star indicator
                self._refresh_table_favorites(table)
        except Exception as e:
            logger.error(f"Error adding favorite: {e}", exc_info=True)

    def _on_context_menu_unfavorite(self, object_name: str, table: QTableWidget) -> None:
        """Handle context menu remove from favorites action."""
        import asyncio

        from celestron_nexstar.api.favorites import remove_favorite

        try:
            success = asyncio.run(remove_favorite(object_name))
            if success:
                self._show_toast(f"Removed '{object_name}' from favorites")
                # Refresh the table to remove the star indicator
                self._refresh_table_favorites(table)
        except Exception as e:
            logger.error(f"Error removing favorite: {e}", exc_info=True)

    def _on_context_menu_add_to_queue(self, table: QTableWidget, row: int) -> None:
        """Handle context menu add to queue action."""
        # Get object name
        obj_type = table.property("object_type")
        name_item = table.item(row, 0) if obj_type in ("constellation", "asterism") else table.item(row, 1)

        if not name_item:
            return

        object_name = name_item.data(Qt.ItemDataRole.UserRole)
        if not object_name:
            display_text = name_item.text()
            object_name = display_text.removeprefix("★ ").strip()

        if not object_name:
            return

        # Get the CelestialObject
        import asyncio

        from celestron_nexstar.api.catalogs.catalogs import get_object_by_name

        try:
            matches = asyncio.run(get_object_by_name(object_name))
            if not matches:
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.warning(self, "Object Not Found", f"Could not find object: {object_name}")
                return

            obj = matches[0].with_current_position()

            # Open or get goto queue window
            if not hasattr(self, "_goto_queue_window") or self._goto_queue_window is None:
                self._on_goto_queue()

            # Add object to queue
            # Update telescope reference if needed
            if self._goto_queue_window is not None:
                if self._goto_queue_window.telescope != self.telescope:
                    self._goto_queue_window.telescope = self.telescope
                self._goto_queue_window.add_object(obj)
                self._goto_queue_window.show()
                self._goto_queue_window.raise_()
                self._goto_queue_window.activateWindow()

        except Exception as e:
            logger.error(f"Error adding object to queue: {e}", exc_info=True)
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "Error", f"Failed to add object to queue: {e}")

    def _on_context_menu_log_observation(self, object_name: str) -> None:
        """Handle context menu log observation action."""
        from celestron_nexstar.gui.dialogs.observation_edit_dialog import ObservationEditDialog

        dialog = ObservationEditDialog(self, object_name=object_name)
        dialog.exec()

    def _refresh_table_favorites(self, table: QTableWidget) -> None:
        """Refresh favorite indicators in a table."""
        obj_type_str = table.property("object_type")
        if not obj_type_str:
            return

        # Reload the table data
        if obj_type_str in self._objects_cache:
            objects = self._objects_cache[obj_type_str]
            if objects:
                if obj_type_str in ("constellation", "asterism"):
                    self._populate_constellation_table(table, objects)  # type: ignore[arg-type]
                else:
                    self._populate_table(table, objects)  # type: ignore[arg-type]

    def _on_cell_double_clicked(self, item: QTableWidgetItem) -> None:
        """Handle cell double-click - copy cell text to clipboard."""
        text = item.text()
        if text:
            from PySide6.QtWidgets import QApplication

            clipboard = QApplication.clipboard()
            clipboard.setText(text)

            # Show toast notification with copied text
            self._show_toast(f"Copied: {text}")

    def _show_toast(self, message: str, duration_ms: int = 2000) -> None:
        """Show a toast notification message."""
        # Truncate long messages to prevent toast from being too wide
        max_length = 50
        display_message = message
        if len(message) > max_length:
            display_message = message[: max_length - 3] + "..."

        # Detect theme for toast styling
        from PySide6.QtGui import QPalette

        is_dark = False
        app = QGuiApplication.instance()
        if app and isinstance(app, QGuiApplication):
            palette = app.palette()
            window_color = palette.color(QPalette.ColorRole.Window)
            brightness = window_color.lightness()
            is_dark = brightness < 128

        # Create a label for the toast
        toast = QLabel(display_message, self)
        # Theme-aware toast styling
        bg_color = "rgba(0, 0, 0, 200)" if not is_dark else "rgba(255, 255, 255, 200)"
        text_color = "white" if not is_dark else "black"
        toast.setStyleSheet(
            f"""
            QLabel {{
                background-color: {bg_color};
                color: {text_color};
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 12px;
            }}
        """
        )
        toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        toast.adjustSize()

        # Position toast in the center of the window
        x = (self.width() - toast.width()) // 2
        y = self.height() // 3  # Position in upper third
        toast.move(x, y)
        toast.raise_()
        toast.show()

        # Hide toast after duration
        QTimer.singleShot(duration_ms, toast.deleteLater)

    def _on_tab_changed(self, index: int) -> None:
        """Handle tab change - load data for the selected tab if not already loaded."""
        if index < 0:
            return

        tab_widget = self.tab_widget.widget(index)
        if isinstance(tab_widget, QTableWidget):
            obj_type_str = tab_widget.property("object_type")
            # Check if data has been loaded (is in cache) vs not loaded yet
            if obj_type_str and obj_type_str not in self._objects_cache and tab_widget.rowCount() == 0:
                # Not loaded yet - load it
                self._load_objects_table(tab_widget)
            # If data is in cache but table is empty, it means no data matches criteria
            # (the _show_no_data_message will have been called)

    def _create_status_bar(self) -> None:
        """Create the status bar with GPS, date/time, and telescope position."""
        status_bar = QStatusBar()
        status_bar.setSizeGripEnabled(False)  # Disable default resize grip (on right)
        self.setStatusBar(status_bar)

        # GPS status (left side, temporary, clickable)
        self.gps_label = ClickableLabel()
        self.gps_label.setTextFormat(Qt.TextFormat.RichText)  # Enable HTML formatting
        self.gps_label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.gps_label.clicked.connect(self._on_gps_clicked)
        status_bar.addWidget(self.gps_label)

        # Vertical separator
        self.separator = QLabel("|")
        self.separator.setObjectName("separator")
        status_bar.addWidget(self.separator)

        # Date & Time (left side, temporary, clickable, next to GPS)
        self.datetime_label = ClickableLabel()
        self.datetime_label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.datetime_label.clicked.connect(self._on_datetime_clicked)
        status_bar.addWidget(self.datetime_label)

        # Add spacer to push permanent widgets to the right
        spacer = QLabel("")
        spacer.setMinimumWidth(0)
        spacer.setMaximumWidth(16777215)  # QWIDGETSIZE_MAX
        spacer.setObjectName("status_bar_spacer")
        status_bar.addPermanentWidget(spacer)

        # Telescope position (right side, permanent)
        self.position_label = QLabel("Position: --")
        status_bar.addPermanentWidget(self.position_label)

        # Add resize grip after the position control (on the right side)
        # Create a container widget for the resize grip
        resize_grip_container = QWidget()
        resize_grip_layout = QHBoxLayout(resize_grip_container)
        resize_grip_layout.setContentsMargins(0, 0, 0, 0)
        resize_grip_layout.setSpacing(0)

        # Create a size grip and add it to the container
        resize_grip = QSizeGrip(resize_grip_container)
        resize_grip_layout.addWidget(resize_grip)
        resize_grip_container.setFixedWidth(16)  # Set fixed width for the grip

        # Add the resize grip container after the position label
        status_bar.addPermanentWidget(resize_grip_container)

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
                coords = _run_async_safe(self.telescope.get_position_ra_dec())
                self.position_label.setText(f"Position: RA {coords.ra_hours:.4f}h, Dec {coords.dec_degrees:+.4f}°")
            except Exception:
                self.position_label.setText("Position: --")
        else:
            self.position_label.setText("Position: --")

    def _update_gps_status(self) -> None:
        """Update GPS status indicator color based on connection and GPS availability."""
        # Default: red (not connected or no GPS)
        icon_color = "#dc3545"  # Material red/danger color

        # Check if telescope is connected
        if self.telescope and self.telescope.protocol.is_open():
            try:
                location_result = _run_async_safe(self.telescope.get_location())
                if location_result:
                    lat = location_result.latitude
                    lon = location_result.longitude
                    # Check if GPS coordinates are valid (not 0,0)
                    icon_color = (
                        "#28a745" if lat != 0.0 and lon != 0.0 else "#ffc107"
                    )  # Green if valid, yellow if searching
            except Exception:
                # Red: Error reading GPS
                icon_color = "#dc3545"
        else:
            # Red: Not connected
            icon_color = "#dc3545"

        # Set text with HTML formatting: colored icon
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
        self.connect_action.setEnabled(False)
        self.disconnect_action.setEnabled(True)
        self.align_action.setEnabled(True)
        self.calibrate_action.setEnabled(True)
        if hasattr(self, "tracking_history_action"):
            self.tracking_history_action.setEnabled(True)

    def _on_disconnect(self) -> None:
        """Handle disconnect button click."""
        if self.telescope:
            with contextlib.suppress(Exception):
                _run_async_safe(self.telescope.disconnect())

            self.telescope = None

        self.connect_action.setEnabled(True)
        self.disconnect_action.setEnabled(False)
        self.align_action.setEnabled(False)
        self.calibrate_action.setEnabled(False)
        if hasattr(self, "tracking_history_action"):
            self.tracking_history_action.setEnabled(False)

    def _on_align(self) -> None:
        """Handle align button click."""
        from celestron_nexstar.gui.dialogs.alignment_assistant_dialog import AlignmentAssistantDialog

        dialog = AlignmentAssistantDialog(self, telescope=self.telescope)
        dialog.exec()

    def _on_calibrate(self) -> None:
        """Handle calibrate button click."""
        from celestron_nexstar.gui.dialogs.calibration_assistant_dialog import CalibrationAssistantDialog

        dialog = CalibrationAssistantDialog(self, telescope=self.telescope)
        dialog.exec()

    def _on_tracking_history(self) -> None:
        """Handle tracking history button click."""
        from celestron_nexstar.gui.dialogs.tracking_history_dialog import TrackingHistoryDialog

        dialog = TrackingHistoryDialog(self, telescope=self.telescope)
        dialog.exec()

    def _on_planning(self) -> None:
        """Handle planning button click - opens planning window."""
        # TODO: Open planning window
        pass

    def _on_catalog(self) -> None:
        """Handle catalog button click - open catalog search window."""
        from celestron_nexstar.gui.windows.catalog_window import CatalogSearchWindow

        # Check if window already exists
        if not hasattr(self, "_catalog_window") or self._catalog_window is None:
            self._catalog_window = CatalogSearchWindow(self)
            self._catalog_window.destroyed.connect(lambda: setattr(self, "_catalog_window", None))

        self._catalog_window.show()
        self._catalog_window.raise_()
        self._catalog_window.activateWindow()

    def _on_goto_queue(self) -> None:
        """Handle goto queue button click - open goto queue window."""
        from celestron_nexstar.gui.windows.goto_queue_window import GotoQueueWindow

        # Check if window already exists
        if not hasattr(self, "_goto_queue_window") or self._goto_queue_window is None:
            self._goto_queue_window = GotoQueueWindow(self, telescope=self.telescope)
            self._goto_queue_window.destroyed.connect(lambda: setattr(self, "_goto_queue_window", None))
        else:
            # Update telescope reference if it changed
            self._goto_queue_window.telescope = self.telescope

        self._goto_queue_window.show()
        self._goto_queue_window.raise_()
        self._goto_queue_window.activateWindow()

    def _on_weather(self) -> None:
        """Handle weather button click."""
        dialog = WeatherInfoDialog(self)
        dialog.exec()

    def _on_favorites(self) -> None:
        """Handle favorites button click."""
        from celestron_nexstar.gui.dialogs.favorites_dialog import FavoritesDialog

        dialog = FavoritesDialog(self)
        dialog.exec()

    def _on_observation_log(self) -> None:
        """Handle observation log button click."""
        from celestron_nexstar.gui.dialogs.observation_log_dialog import ObservationLogDialog

        dialog = ObservationLogDialog(self)
        dialog.exec()

    def _on_live_dashboard(self) -> None:
        """Handle live dashboard button click."""
        from celestron_nexstar.gui.dialogs.live_dashboard_dialog import LiveDashboardDialog

        dialog = LiveDashboardDialog(self)
        dialog.exec()

    def _on_equipment_manager(self) -> None:
        """Handle equipment manager button click."""
        from celestron_nexstar.gui.dialogs.equipment_manager_dialog import EquipmentManagerDialog

        dialog = EquipmentManagerDialog(self)
        dialog.exec()

    def _on_checklist(self) -> None:
        """Handle checklist button click."""
        # TODO: Open checklist window
        pass

    def _on_time_slots(self) -> None:
        """Handle time slots button click."""
        # Show progress dialog while loading
        progress = QProgressDialog("Loading time slots and recommendations...", "Cancel", 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)  # Disable cancel button
        progress.show()

        # Process events to show the dialog immediately
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents()

        # Show time slots dialog (it will load data in its constructor)
        from celestron_nexstar.gui.dialogs.time_slots_dialog import TimeSlotsInfoDialog

        dialog = TimeSlotsInfoDialog(self)
        progress.close()
        dialog.exec()

    def _on_quick_reference(self) -> None:
        """Handle quick reference button click."""
        # TODO: Open quick reference window
        pass

    def _on_transit_times(self) -> None:
        """Handle transit times button click."""
        # Show progress dialog while loading
        progress = QProgressDialog("Loading transit times...", "Cancel", 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)  # Disable cancel button
        progress.show()

        # Process events to show the dialog immediately
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents()

        # Show transit times dialog (it will load data in its constructor)
        from celestron_nexstar.gui.dialogs.transit_times_dialog import TransitTimesInfoDialog

        dialog = TransitTimesInfoDialog(self)
        progress.close()
        dialog.exec()

    def _on_glossary(self) -> None:
        """Handle glossary button click."""
        from celestron_nexstar.gui.dialogs.glossary_dialog import GlossaryDialog

        dialog = GlossaryDialog(self)
        dialog.exec()

    def _on_compare_objects(self) -> None:
        """Handle compare objects button click."""
        from celestron_nexstar.gui.dialogs.object_comparison_dialog import ObjectComparisonDialog

        dialog = ObjectComparisonDialog(self)
        dialog.exec()

    def _on_context_menu_compare_objects(self, table: QTableWidget, row: int) -> None:
        """Handle context menu compare objects action."""
        # Get all selected rows, or fall back to the clicked row if none selected
        selected_indices = table.selectionModel().selectedRows()
        rows_to_process = [idx.row() for idx in selected_indices] if selected_indices else [row]

        obj_type = table.property("object_type")
        object_names = []

        # Extract object names from all selected rows
        for row_num in rows_to_process:
            name_item = table.item(row_num, 0) if obj_type in ("constellation", "asterism") else table.item(row_num, 1)

            if not name_item:
                continue

            object_name = name_item.data(Qt.ItemDataRole.UserRole)
            if not object_name:
                display_text = name_item.text()
                object_name = display_text.removeprefix("★ ").strip()

            if object_name and object_name not in object_names:
                object_names.append(object_name)

        if not object_names:
            return

        # Open comparison dialog with all selected objects
        from celestron_nexstar.gui.dialogs.object_comparison_dialog import ObjectComparisonDialog

        dialog = ObjectComparisonDialog(self, initial_objects=object_names)
        dialog.exec()

    def _on_settings(self) -> None:
        """Handle settings button click."""
        from celestron_nexstar.gui.dialogs.settings_dialog import SettingsDialog

        dialog = SettingsDialog(self)
        dialog.exec()

    def _on_celestial_object(self, object_name: str) -> None:
        """Handle celestial object button click."""
        if object_name == "aurora":
            # Show progress dialog while loading
            progress = QProgressDialog("Loading aurora visibility information...", "Cancel", 0, 0, self)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setCancelButton(None)  # Disable cancel button
            progress.show()

            # Process events to show the dialog immediately
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()

            # Show aurora dialog (it will load data in its constructor)
            from celestron_nexstar.gui.dialogs.aurora_info_dialog import AuroraInfoDialog

            dialog = AuroraInfoDialog(self)
            progress.close()
            dialog.exec()
        elif object_name == "iss":
            # Show progress dialog while loading
            progress = QProgressDialog("Loading ISS pass predictions...", "Cancel", 0, 0, self)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setCancelButton(None)  # Disable cancel button
            progress.show()

            # Process events to show the dialog immediately
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()

            # Show ISS dialog (it will load data in its constructor)
            from celestron_nexstar.gui.dialogs.iss_info_dialog import ISSInfoDialog

            iss_dialog = ISSInfoDialog(self)
            progress.close()
            iss_dialog.exec()
        elif object_name == "binoculars":
            # Show progress dialog while loading
            progress = QProgressDialog("Loading binocular viewing information...", "Cancel", 0, 0, self)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setCancelButton(None)  # Disable cancel button
            progress.show()

            # Process events to show the dialog immediately
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()

            # Show binoculars dialog (it will load data in its constructor)
            from celestron_nexstar.gui.dialogs.binoculars_info_dialog import BinocularsInfoDialog

            binoculars_dialog = BinocularsInfoDialog(self)
            progress.close()
            binoculars_dialog.exec()
        elif object_name == "naked_eye":
            # Show progress dialog while loading
            progress = QProgressDialog("Loading naked-eye viewing information...", "Cancel", 0, 0, self)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setCancelButton(None)  # Disable cancel button
            progress.show()

            # Process events to show the dialog immediately
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()

            # Show naked-eye dialog (it will load data in its constructor)
            from celestron_nexstar.gui.dialogs.naked_eye_info_dialog import NakedEyeInfoDialog

            naked_eye_dialog = NakedEyeInfoDialog(self)
            progress.close()
            naked_eye_dialog.exec()
        elif object_name == "comets":
            # Show progress dialog while loading
            progress = QProgressDialog("Loading comet visibility information...", "Cancel", 0, 0, self)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setCancelButton(None)  # Disable cancel button
            progress.show()

            # Process events to show the dialog immediately
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()

            # Show comets dialog (it will load data in its constructor)
            from celestron_nexstar.gui.dialogs.comets_info_dialog import CometsInfoDialog

            comets_dialog = CometsInfoDialog(self)
            progress.close()
            comets_dialog.exec()
        elif object_name == "eclipse":
            # Show progress dialog while loading
            progress = QProgressDialog("Loading eclipse information...", "Cancel", 0, 0, self)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setCancelButton(None)  # Disable cancel button
            progress.show()

            # Process events to show the dialog immediately
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()

            # Show eclipse dialog (it will load data in its constructor)
            from celestron_nexstar.gui.dialogs.eclipse_info_dialog import EclipseInfoDialog

            eclipse_dialog = EclipseInfoDialog(self, progress=progress)
            progress.close()
            eclipse_dialog.exec()
        elif object_name == "planets":
            # Show progress dialog while loading
            progress = QProgressDialog("Loading planetary events information...", "Cancel", 0, 0, self)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setCancelButton(None)  # Disable cancel button
            progress.show()

            # Process events to show the dialog immediately
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()

            # Show planets dialog (it will load data in its constructor)
            from celestron_nexstar.gui.dialogs.planets_info_dialog import PlanetsInfoDialog

            planets_dialog = PlanetsInfoDialog(self, progress=progress)
            progress.close()
            planets_dialog.exec()
        elif object_name == "space_weather":
            # Show progress dialog while loading
            progress = QProgressDialog("Loading space weather information...", "Cancel", 0, 0, self)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setCancelButton(None)  # Disable cancel button
            progress.show()

            # Process events to show the dialog immediately
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()

            # Show space weather dialog (it will load data in its constructor)
            from celestron_nexstar.gui.dialogs.space_weather_info_dialog import SpaceWeatherInfoDialog

            space_weather_dialog = SpaceWeatherInfoDialog(self)
            progress.close()
            space_weather_dialog.exec()
        elif object_name == "satellites":
            # Show progress dialog while loading
            progress = QProgressDialog("Loading satellite passes information...", "Cancel", 0, 0, self)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setCancelButton(None)  # Disable cancel button
            progress.show()

            # Process events to show the dialog immediately
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()

            # Show satellites dialog (it will load data in its constructor)
            from celestron_nexstar.gui.dialogs.satellites_info_dialog import SatellitesInfoDialog

            satellites_dialog = SatellitesInfoDialog(self, progress=progress)
            progress.close()
            satellites_dialog.exec()
        elif object_name == "meteors":
            # Show progress dialog while loading
            progress = QProgressDialog("Loading meteor shower predictions...", "Cancel", 0, 0, self)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setCancelButton(None)  # Disable cancel button
            progress.show()

            # Process events to show the dialog immediately
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()

            # Show meteors dialog (it will load data in its constructor)
            from celestron_nexstar.gui.dialogs.meteors_info_dialog import MeteorsInfoDialog

            meteors_dialog = MeteorsInfoDialog(self, progress=progress)
            progress.close()
            meteors_dialog.exec()
        elif object_name == "milky_way":
            # Show progress dialog while loading
            progress = QProgressDialog("Loading Milky Way visibility information...", "Cancel", 0, 0, self)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setCancelButton(None)  # Disable cancel button
            progress.show()

            # Process events to show the dialog immediately
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()

            from celestron_nexstar.gui.dialogs.milky_way_info_dialog import MilkyWayInfoDialog

            milky_way_dialog = MilkyWayInfoDialog(self, progress=progress)
            progress.close()
            milky_way_dialog.exec()
        else:
            # TODO: Open celestial object window for other objects
            pass

    def _on_toggle_log(self, checked: bool) -> None:
        """Handle communication log toggle button click."""
        if checked:
            # Show log panel
            self.log_panel.log_text.show()
            self.log_panel.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX
            self.log_panel.setMinimumHeight(150)  # Minimum height when expanded
        else:
            # Hide log panel
            self.log_panel.log_text.hide()
            self.log_panel.setMaximumHeight(30)  # Collapsed height
            self.log_panel.setMinimumHeight(30)

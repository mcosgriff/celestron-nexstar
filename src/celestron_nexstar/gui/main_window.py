"""
Main application window for telescope control.
"""

import contextlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QActionGroup, QCursor, QGuiApplication, QIcon, QMouseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSizeGrip,
    QSizePolicy,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from celestron_nexstar.api.core import format_local_time
from celestron_nexstar.api.location.observer import get_observer_location
from celestron_nexstar.gui.dialogs.gps_info_dialog import GPSInfoDialog
from celestron_nexstar.gui.dialogs.time_info_dialog import TimeInfoDialog
from celestron_nexstar.gui.themes import FusionTheme, ThemeMode
from celestron_nexstar.gui.widgets.collapsible_log_panel import CollapsibleLogPanel


if TYPE_CHECKING:
    from celestron_nexstar import NexStarTelescope


class ClickableLabel(QLabel):
    """A clickable QLabel that emits a clicked signal."""

    clicked = Signal()  # type: ignore[type-arg,misc]

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]  # noqa: N802
        """Handle mouse press event."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    """Main application window for telescope control."""

    @staticmethod
    def _create_icon(icon_name: str, fallback_theme_names: list[str] | None = None) -> QIcon:
        """Create an icon using FontAwesome icons (via qtawesome) with theme icon fallbacks."""
        # Map icon names to FontAwesome icon names
        # Using FontAwesome 5 Solid (fa5s) icons
        icon_map: dict[str, str] = {
            # Telescope operations
            "link": "mdi.lan-connect",
            "link_off": "mdi.lan-disconnect",
            "my_location": "fa5s.map-marker-alt",
            "tune": "fa5s.cog",
            "crosshairs": "mdi.crosshairs-gps",
            # Planning tools
            "checklist": "mdi.check-circle",
            "time_slots": "mdi.clock-outline",
            "moon_impact": "mdi.moon-waning-crescent",
            "quick_reference": "mdi.book-open-variant",
            "transit_times": "mdi.transit-connection",
            "timeline": "mdi.timeline",
            # Celestial objects (using alpha-box-outline pattern)
            "aurora": "mdi.alpha-a-box-outline",
            "binoculars": "mdi.alpha-b-box-outline",
            "comets": "mdi.alpha-c-box-outline",
            "eclipse": "mdi.alpha-e-box-outline",
            "events": "mdi.alpha-e-box-outline",  # Same as eclipse (both start with 'e')
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
            "event": "fa5s.calendar",
            "menu_book": "fa5s.book",
        }

        # Try FontAwesome icons via qtawesome first
        try:
            import qtawesome as qta  # type: ignore[import-not-found,import-untyped]

            # Get the FontAwesome icon name
            fa_icon_name = icon_map.get(icon_name)
            if fa_icon_name:
                icon = qta.icon(fa_icon_name)
                if not icon.isNull():
                    return icon
        except (ImportError, AttributeError, ValueError, TypeError, KeyError) as e:
            # Log the error for debugging
            import logging

            logger = logging.getLogger(__name__)
            logger.debug(f"qtawesome icon failed for '{icon_name}': {e}")

        # Try theme icons as fallback
        if fallback_theme_names:
            for theme_name in fallback_theme_names:
                icon = QIcon.fromTheme(theme_name)
                if not icon.isNull():
                    return icon

        # Fallback to empty icon (will show as blank button)
        return QIcon()

    def __init__(self, theme: FusionTheme | None = None) -> None:
        """Initialize the main window."""
        super().__init__()
        self.setWindowTitle("Celestron NexStar Telescope Control")
        self.setMinimumSize(800, 600)

        # Telescope connection state
        self.telescope: NexStarTelescope | None = None

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

        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Create telescope control panel
        control_panel = self._create_control_panel()
        main_layout.addWidget(control_panel)

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

        # Left side toolbar - combined Telescope Operations and Planning Tools
        left_toolbar = create_toolbar("Left Toolbar", Qt.ToolBarArea.LeftToolBarArea)

        # Telescope Operations buttons
        connect_icon = self._create_icon("link", ["network-connect", "network-wired", "network-workgroup"])
        self.connect_action = left_toolbar.addAction(connect_icon, "Connect")
        self.connect_action.setToolTip("CONNECT")
        self.connect_action.setStatusTip("Connect to telescope")
        self.connect_action.triggered.connect(self._on_connect)
        self.connect_action.setIcon(connect_icon)

        disconnect_icon = self._create_icon("link_off", ["network-disconnect", "network-offline", "network-error"])
        self.disconnect_action = left_toolbar.addAction(disconnect_icon, "Disconnect")
        self.disconnect_action.setToolTip("DISCONNECT")
        self.disconnect_action.setStatusTip("Disconnect from telescope")
        self.disconnect_action.triggered.connect(self._on_disconnect)
        self.disconnect_action.setEnabled(False)
        self.disconnect_action.setIcon(disconnect_icon)

        calibrate_icon = self._create_icon("crosshairs", ["tools-check-spelling", "preferences-system", "configure"])
        self.calibrate_action = left_toolbar.addAction(calibrate_icon, "Calibrate")
        self.calibrate_action.setToolTip("CALIBRATE")
        self.calibrate_action.setStatusTip("Calibrate telescope")
        self.calibrate_action.triggered.connect(self._on_calibrate)
        self.calibrate_action.setEnabled(False)
        self.calibrate_action.setIcon(calibrate_icon)

        align_icon = self._create_icon("my_location", ["edit-find", "system-search", "find-location"])
        self.align_action = left_toolbar.addAction(align_icon, "Align")
        self.align_action.setToolTip("ALIGN")
        self.align_action.setStatusTip("Align telescope")
        self.align_action.triggered.connect(self._on_align)
        self.align_action.setEnabled(False)
        self.align_action.setIcon(align_icon)

        # Communication Log button
        log_icon = self._create_icon("console", ["terminal", "code-tags", "text-box"])
        self.log_toggle_action = left_toolbar.addAction(log_icon, "Communication Log")
        self.log_toggle_action.setToolTip("COMMUNICATION LOG")
        self.log_toggle_action.setStatusTip("Toggle communication log panel")
        self.log_toggle_action.setCheckable(True)  # Make it a toggle button
        self.log_toggle_action.setChecked(False)  # Start unchecked (log panel hidden)
        self.log_toggle_action.triggered.connect(self._on_toggle_log)
        self.log_toggle_action.setIcon(log_icon)

        # Spacer widget to push Planning Tools to the bottom
        spacer_widget = QWidget()
        spacer_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        spacer_widget.setMinimumHeight(1)
        left_toolbar.addWidget(spacer_widget)

        # Planning Tools buttons

        checklist_icon = self._create_icon("checklist", ["format-list-checks", "check-circle"])
        self.checklist_action = left_toolbar.addAction(checklist_icon, "Checklist")
        self.checklist_action.setToolTip("CHECKLIST")
        self.checklist_action.setStatusTip("View observation checklist")
        self.checklist_action.triggered.connect(self._on_checklist)
        self.checklist_action.setIcon(checklist_icon)

        time_slots_icon = self._create_icon("time_slots", ["clock-outline", "timer"])
        self.time_slots_action = left_toolbar.addAction(time_slots_icon, "Time Slots")
        self.time_slots_action.setToolTip("TIME SLOTS")
        self.time_slots_action.setStatusTip("View available time slots")
        self.time_slots_action.triggered.connect(self._on_time_slots)
        self.time_slots_action.setIcon(time_slots_icon)

        moon_impact_icon = self._create_icon("moon_impact", ["moon-waning-crescent", "moon-full"])
        self.moon_impact_action = left_toolbar.addAction(moon_impact_icon, "Moon Impact")
        self.moon_impact_action.setToolTip("MOON IMPACT")
        self.moon_impact_action.setStatusTip("View moon impact on observations")
        self.moon_impact_action.triggered.connect(self._on_moon_impact)
        self.moon_impact_action.setIcon(moon_impact_icon)

        quick_ref_icon = self._create_icon("quick_reference", ["book-open-variant", "information"])
        self.quick_reference_action = left_toolbar.addAction(quick_ref_icon, "Quick Reference")
        self.quick_reference_action.setToolTip("QUICK REFERENCE")
        self.quick_reference_action.setStatusTip("Open quick reference guide")
        self.quick_reference_action.triggered.connect(self._on_quick_reference)
        self.quick_reference_action.setIcon(quick_ref_icon)

        transit_times_icon = self._create_icon("transit_times", ["transit-connection", "arrow-right-bold"])
        self.transit_times_action = left_toolbar.addAction(transit_times_icon, "Transit Times")
        self.transit_times_action.setToolTip("TRANSIT TIMES")
        self.transit_times_action.setStatusTip("View transit times")
        self.transit_times_action.triggered.connect(self._on_transit_times)
        self.transit_times_action.setIcon(transit_times_icon)

        timeline_icon = self._create_icon("timeline", ["timeline", "chart-timeline-variant"])
        self.timeline_action = left_toolbar.addAction(timeline_icon, "Timeline")
        self.timeline_action.setToolTip("TIMELINE")
        self.timeline_action.setStatusTip("View observation timeline")
        self.timeline_action.triggered.connect(self._on_timeline)
        self.timeline_action.setIcon(timeline_icon)

        # Right side toolbar - combined Celestial Objects and Communication Log
        right_toolbar = create_toolbar("Right Toolbar", Qt.ToolBarArea.RightToolBarArea)

        # Celestial object actions (using alpha-box-outline pattern)
        celestial_objects = [
            ("aurora", "Aurora", ["alpha-a-box-outline"]),
            ("binoculars", "Binoculars", ["alpha-b-box-outline"]),
            ("comets", "Comets", ["alpha-c-box-outline"]),
            ("eclipse", "Eclipse", ["alpha-e-box-outline"]),
            ("events", "Events", ["alpha-e-box-outline"]),
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

        for obj_name, display_name, icon_names in celestial_objects:
            icon = self._create_icon(obj_name, icon_names)
            action = right_toolbar.addAction(icon, display_name)
            action.setToolTip(display_name.upper())
            action.setStatusTip(f"View {display_name} information")
            action.triggered.connect(lambda checked, name=obj_name: self._on_celestial_object(name))
            action.setIcon(icon)
            # Store action for later reference
            setattr(self, f"{obj_name}_action", action)

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
        # Planning tools
        self.checklist_action.setIcon(self._create_icon("checklist", ["format-list-checks", "check-circle"]))
        self.time_slots_action.setIcon(self._create_icon("time_slots", ["clock-outline", "timer"]))
        self.moon_impact_action.setIcon(self._create_icon("moon_impact", ["moon-waning-crescent", "moon-full"]))
        self.quick_reference_action.setIcon(self._create_icon("quick_reference", ["book-open-variant", "information"]))
        self.transit_times_action.setIcon(
            self._create_icon("transit_times", ["transit-connection", "arrow-right-bold"])
        )
        self.timeline_action.setIcon(self._create_icon("timeline", ["timeline", "chart-timeline-variant"]))
        # Celestial objects (using alpha-box-outline pattern)
        for obj_name in [
            "aurora",
            "binoculars",
            "comets",
            "eclipse",
            "events",
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

    def _on_system_theme_changed(self) -> None:
        """Handle system theme changes."""
        # Only update if user preference is SYSTEM
        if self.theme_mode_preference == ThemeMode.SYSTEM:
            self.theme.set_mode(ThemeMode.SYSTEM)

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
        """Create the telescope control panel with buttons."""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Add stretch to push content to top
        layout.addStretch()

        return panel

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
            import logging

            logger = logging.getLogger(__name__)
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
                coords = self.telescope.get_position_ra_dec()
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
                location_result = self.telescope.get_location()
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

    def _on_disconnect(self) -> None:
        """Handle disconnect button click."""
        if self.telescope:
            with contextlib.suppress(Exception):
                self.telescope.disconnect()

            self.telescope = None

        self.connect_action.setEnabled(True)
        self.disconnect_action.setEnabled(False)
        self.align_action.setEnabled(False)
        self.calibrate_action.setEnabled(False)

    def _on_align(self) -> None:
        """Handle align button click."""
        # TODO: Open alignment dialog
        pass

    def _on_calibrate(self) -> None:
        """Handle calibrate button click."""
        # TODO: Open calibration dialog
        pass

    def _on_planning(self) -> None:
        """Handle planning button click - opens planning window."""
        # TODO: Open planning window
        pass

    def _on_catalog(self) -> None:
        """Handle catalog button click - opens catalog window."""
        # TODO: Open catalog window
        pass

    def _on_checklist(self) -> None:
        """Handle checklist button click."""
        # TODO: Open checklist window
        pass

    def _on_time_slots(self) -> None:
        """Handle time slots button click."""
        # TODO: Open time slots window
        pass

    def _on_moon_impact(self) -> None:
        """Handle moon impact button click."""
        # TODO: Open moon impact window
        pass

    def _on_quick_reference(self) -> None:
        """Handle quick reference button click."""
        # TODO: Open quick reference window
        pass

    def _on_transit_times(self) -> None:
        """Handle transit times button click."""
        # TODO: Open transit times window
        pass

    def _on_timeline(self) -> None:
        """Handle timeline button click."""
        # TODO: Open timeline window
        pass

    def _on_celestial_object(self, object_name: str) -> None:
        """Handle celestial object button click."""
        # TODO: Open celestial object window for the specified object
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

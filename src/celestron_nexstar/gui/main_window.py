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
    QPushButton,
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
from celestron_nexstar.gui.themes import ColorStyle, QtMaterialTheme, ThemeMode
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

    def __init__(self, theme: QtMaterialTheme | None = None) -> None:
        """Initialize the main window."""
        super().__init__()
        self.setWindowTitle("Celestron NexStar Telescope Control")
        self.setMinimumSize(800, 600)

        # Telescope connection state
        self.telescope: NexStarTelescope | None = None

        # Initialize theme (use provided theme or create default)
        if theme is None:
            from PySide6.QtWidgets import QApplication

            self.theme = QtMaterialTheme(ThemeMode.SYSTEM, ColorStyle.BLUE, dense=True)
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

        # Create collapsible log panel at bottom
        self.log_panel = CollapsibleLogPanel()
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

        # Create Style submenu
        style_menu = view_menu.addMenu("&Style")

        # Create action group for style selection (exclusive)
        self.style_action_group = QActionGroup(self)
        self.style_action_group.setExclusive(True)

        # Style actions (matching qt-material themes)
        self.amber_action = style_menu.addAction("Amber")
        self.amber_action.setCheckable(True)
        self.amber_action.setStatusTip("Amber theme")
        self.amber_action.triggered.connect(lambda: self._set_style(ColorStyle.AMBER))
        self.style_action_group.addAction(self.amber_action)

        self.blue_action = style_menu.addAction("Blue")
        self.blue_action.setCheckable(True)
        self.blue_action.setStatusTip("Blue theme (default)")
        self.blue_action.triggered.connect(lambda: self._set_style(ColorStyle.BLUE))
        self.style_action_group.addAction(self.blue_action)

        self.cyan_action = style_menu.addAction("Cyan")
        self.cyan_action.setCheckable(True)
        self.cyan_action.setStatusTip("Cyan theme")
        self.cyan_action.triggered.connect(lambda: self._set_style(ColorStyle.CYAN))
        self.style_action_group.addAction(self.cyan_action)

        self.lightgreen_action = style_menu.addAction("Light Green")
        self.lightgreen_action.setCheckable(True)
        self.lightgreen_action.setStatusTip("Light Green theme")
        self.lightgreen_action.triggered.connect(lambda: self._set_style(ColorStyle.LIGHTGREEN))
        self.style_action_group.addAction(self.lightgreen_action)

        self.orange_action = style_menu.addAction("Orange")
        self.orange_action.setCheckable(True)
        self.orange_action.setStatusTip("Orange theme")
        self.orange_action.triggered.connect(lambda: self._set_style(ColorStyle.ORANGE))
        self.style_action_group.addAction(self.orange_action)

        self.pink_action = style_menu.addAction("Pink")
        self.pink_action.setCheckable(True)
        self.pink_action.setStatusTip("Pink theme")
        self.pink_action.triggered.connect(lambda: self._set_style(ColorStyle.PINK))
        self.style_action_group.addAction(self.pink_action)

        self.purple_action = style_menu.addAction("Purple")
        self.purple_action.setCheckable(True)
        self.purple_action.setStatusTip("Purple theme")
        self.purple_action.triggered.connect(lambda: self._set_style(ColorStyle.PURPLE))
        self.style_action_group.addAction(self.purple_action)

        self.red_action = style_menu.addAction("Red")
        self.red_action.setCheckable(True)
        self.red_action.setStatusTip("Red theme")
        self.red_action.triggered.connect(lambda: self._set_style(ColorStyle.RED))
        self.style_action_group.addAction(self.red_action)

        self.teal_action = style_menu.addAction("Teal")
        self.teal_action.setCheckable(True)
        self.teal_action.setStatusTip("Teal theme")
        self.teal_action.triggered.connect(lambda: self._set_style(ColorStyle.TEAL))
        self.style_action_group.addAction(self.teal_action)

        self.yellow_action = style_menu.addAction("Yellow")
        self.yellow_action.setCheckable(True)
        self.yellow_action.setStatusTip("Yellow theme")
        self.yellow_action.triggered.connect(lambda: self._set_style(ColorStyle.YELLOW))
        self.style_action_group.addAction(self.yellow_action)

        # Set initial checked state based on current theme and style
        self._update_theme_menu_state()
        self._update_style_menu_state()

        # Monitor system theme changes
        app = QGuiApplication.instance()
        if app and isinstance(app, QGuiApplication):
            app.paletteChanged.connect(self._on_system_theme_changed)  # type: ignore[attr-defined]

    def _create_toolbar(self) -> None:
        """Create the toolbar with telescope control buttons."""
        toolbar = QToolBar("Telescope Controls")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(22, 22))  # Standard toolbar icon size (22x22)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)  # Icon with text below
        toolbar.setObjectName("telescope_toolbar")  # Set object name for debugging
        # Disable overflow button (the ">>" button that appears when toolbar is too wide)
        toolbar.setFloatable(False)
        # Ensure buttons auto-size based on text content
        toolbar.setStyleSheet("""
            QToolBar::separator { width: 0px; }
            QToolBar::handle { width: 0px; }
            QToolBar QToolButton {
                padding: 4px 8px;
            }
        """)
        self.addToolBar(toolbar)

        # Connect button
        self.connect_action = toolbar.addAction(
            QIcon.fromTheme("network-connect", QIcon.fromTheme("network-wired")),
            "Connect",
        )
        self.connect_action.setStatusTip("Connect to telescope")
        self.connect_action.triggered.connect(self._on_connect)
        # Auto-size button based on text
        connect_btn = toolbar.widgetForAction(self.connect_action)
        if connect_btn:
            connect_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)

        # Disconnect button
        self.disconnect_action = toolbar.addAction(
            QIcon.fromTheme("network-disconnect", QIcon.fromTheme("network-offline")),
            "Disconnect",
        )
        self.disconnect_action.setStatusTip("Disconnect from telescope")
        self.disconnect_action.triggered.connect(self._on_disconnect)
        self.disconnect_action.setEnabled(False)
        disconnect_btn = toolbar.widgetForAction(self.disconnect_action)
        if disconnect_btn:
            disconnect_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)

        toolbar.addSeparator()

        # Align button
        self.align_action = toolbar.addAction(
            QIcon.fromTheme("edit-find", QIcon.fromTheme("system-search")),
            "Align",
        )
        self.align_action.setStatusTip("Align telescope")
        self.align_action.triggered.connect(self._on_align)
        self.align_action.setEnabled(False)
        align_btn = toolbar.widgetForAction(self.align_action)
        if align_btn:
            align_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)

        # Calibrate button
        self.calibrate_action = toolbar.addAction(
            QIcon.fromTheme("tools-check-spelling", QIcon.fromTheme("preferences-system")),
            "Calibrate",
        )
        self.calibrate_action.setStatusTip("Calibrate telescope")
        self.calibrate_action.triggered.connect(self._on_calibrate)
        self.calibrate_action.setEnabled(False)
        calibrate_btn = toolbar.widgetForAction(self.calibrate_action)
        if calibrate_btn:
            calibrate_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)

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

    def _set_style(self, style: ColorStyle) -> None:
        """Set the color style."""
        if self.theme.style == style:
            return  # Already using this style

        self.theme.set_style(style)
        self._update_style_menu_state()

        # Ensure theme is applied to app
        from PySide6.QtWidgets import QApplication

        qapp = QApplication.instance()
        if qapp and isinstance(qapp, QApplication):
            self.theme.apply(qapp)

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

    def _update_style_menu_state(self) -> None:
        """Update the checked state of style menu actions."""
        # Uncheck all first
        for action in self.style_action_group.actions():
            action.setChecked(False)

        # Check the current style
        style_map = {
            ColorStyle.AMBER: self.amber_action,
            ColorStyle.BLUE: self.blue_action,
            ColorStyle.CYAN: self.cyan_action,
            ColorStyle.LIGHTGREEN: self.lightgreen_action,
            ColorStyle.ORANGE: self.orange_action,
            ColorStyle.PINK: self.pink_action,
            ColorStyle.PURPLE: self.purple_action,
            ColorStyle.RED: self.red_action,
            ColorStyle.TEAL: self.teal_action,
            ColorStyle.YELLOW: self.yellow_action,
        }
        if self.theme.style in style_map:
            style_map[self.theme.style].setChecked(True)

    def _create_control_panel(self) -> QWidget:
        """Create the telescope control panel with buttons."""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Goto button (stays in control panel)
        button_layout = QHBoxLayout()

        self.goto_btn = QPushButton("Goto")
        self.goto_btn.clicked.connect(self._on_goto)
        self.goto_btn.setEnabled(False)
        button_layout.addWidget(self.goto_btn)

        layout.addLayout(button_layout)

        # Planning and Catalog buttons (open separate windows)
        secondary_button_layout = QHBoxLayout()

        self.planning_btn = QPushButton("Planning")
        self.planning_btn.clicked.connect(self._on_planning)
        secondary_button_layout.addWidget(self.planning_btn)

        self.catalog_btn = QPushButton("Catalog")
        self.catalog_btn.clicked.connect(self._on_catalog)
        secondary_button_layout.addWidget(self.catalog_btn)

        layout.addLayout(secondary_button_layout)

        # Add stretch to push buttons to top
        layout.addStretch()

        return panel

    def _create_status_bar(self) -> None:
        """Create the status bar with GPS, date/time, and telescope position."""
        status_bar = QStatusBar()
        status_bar.setSizeGripEnabled(False)  # Disable resize handle
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
        self.goto_btn.setEnabled(True)

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
        self.goto_btn.setEnabled(False)

    def _on_goto(self) -> None:
        """Handle goto button click."""
        # TODO: Open goto dialog
        pass

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

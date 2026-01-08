"""
Telescope Control Window

Fully-featured telescope control window with directional control, position monitoring,
and visible objects display.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSlider,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from celestron_nexstar.api.catalogs.catalogs import CelestialObject
from celestron_nexstar.api.core.enums import Direction, SkyBrightness, TrackingMode
from celestron_nexstar.api.core.utils import angular_separation, format_dec, format_ra
from celestron_nexstar.api.database.database import get_database
from celestron_nexstar.api.observation.optics import get_current_configuration
from celestron_nexstar.api.observation.visibility import filter_visible_objects
from celestron_nexstar.gui.dialogs.telescope_connection_dialog import TelescopeConnectionDialog
from celestron_nexstar.gui.widgets.directional_pad_widget import DirectionalPadWidget
from celestron_nexstar.gui.workers.telescope_workers import (
    ConnectTelescopeThread,
    DisconnectThread,
    GetPositionAltAzThread,
    GetPositionRADecThread,
    GetTrackingModeThread,
    IsSlewingThread,
    MoveFixedThread,
    MoveStepThread,
    SetTrackingModeThread,
    StopMotionThread,
)


if TYPE_CHECKING:
    from celestron_nexstar import NexStarTelescope

logger = logging.getLogger(__name__)


# Slew rate descriptions
SLEW_RATE_DESCRIPTIONS = {
    0: "Stop",
    1: "2x sidereal",
    2: "4x sidereal",
    3: "8x sidereal",
    4: "16x sidereal",
    5: "32x sidereal",
    6: "0.5°/sec",
    7: "1°/sec",
    8: "3°/sec",
    9: "5°/sec (max)",
}


class TelescopeControlWindow(QMainWindow):
    """
    Main telescope control window.

    Provides comprehensive telescope control with:
    - Connection management
    - 9-way directional control with variable slew rates
    - Real-time position display (RA/Dec, Alt/Az)
    - Tracking mode control
    - Slew status monitoring
    - Visible objects display with FOV filtering
    - Quick sync/goto capabilities
    """

    def __init__(self, parent: QWidget | None = None, telescope: NexStarTelescope | None = None) -> None:
        """Initialize the telescope control window."""
        super().__init__(parent)

        self.setWindowTitle("Telescope Control")
        self.setMinimumSize(1100, 900)  # Increased height for 3-panel layout

        # Telescope reference
        self.telescope = telescope

        # Command tracking for debugging and history
        from celestron_nexstar.api.telescope.command_tracker import CommandTracker

        self.command_tracker = CommandTracker(max_history=100)

        # State variables
        self._is_connected = False
        self._current_direction: Direction | None = None
        self._slew_rate = 5  # Default: 32x sidereal
        self._movement_mode = "continuous"  # or "step"
        self._selected_object: CelestialObject | None = None
        self._position_error_count = 0

        # UI widgets (will be initialized in _setup_ui)
        self.connection_status_label: QLabel | None = None
        self.connect_button: QPushButton | None = None
        self.disconnect_button: QPushButton | None = None
        self.directional_pad: DirectionalPadWidget | None = None
        self.rate_slider: QSlider | None = None
        self.rate_label: QLabel | None = None
        self.step_radio: QRadioButton | None = None
        self.continuous_radio: QRadioButton | None = None
        self.ra_label: QLabel | None = None
        self.dec_label: QLabel | None = None
        self.alt_label: QLabel | None = None
        self.az_label: QLabel | None = None
        self.tracking_combo: QComboBox | None = None
        self.slew_status_label: QLabel | None = None
        self.objects_table: QTableWidget | None = None
        self.all_visible_radio: QRadioButton | None = None
        self.fov_filter_radio: QRadioButton | None = None
        self.refresh_combo: QComboBox | None = None
        self.refresh_button: QPushButton | None = None

        # Worker threads
        self._connect_thread: ConnectTelescopeThread | None = None
        self._disconnect_thread: DisconnectThread | None = None
        self._position_ra_dec_thread: GetPositionRADecThread | None = None
        self._position_alt_az_thread: GetPositionAltAzThread | None = None
        self._move_thread: MoveFixedThread | None = None
        self._step_thread: MoveStepThread | None = None
        self._stop_thread: StopMotionThread | None = None
        self._is_slewing_thread: IsSlewingThread | None = None
        self._tracking_mode_thread: GetTrackingModeThread | None = None
        self._set_tracking_thread: SetTrackingModeThread | None = None

        # Update timers
        self.position_timer = QTimer()
        self.position_timer.timeout.connect(self._update_position)
        self.position_timer.setInterval(1000)  # 1 second

        self.slew_status_timer = QTimer()
        self.slew_status_timer.timeout.connect(self._check_slew_status)
        self.slew_status_timer.setInterval(500)  # 0.5 seconds

        self.visible_objects_timer = QTimer()
        self.visible_objects_timer.timeout.connect(self._update_visible_objects)
        self.visible_objects_timer.setInterval(30000)  # 30 seconds

        # Setup UI
        self._setup_ui()

        # Setup keyboard shortcuts
        self._setup_shortcuts()

        # Check if telescope is already connected
        if self.telescope and hasattr(self.telescope, "is_open") and self.telescope.is_open():
            self._on_connected(True)

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        # Create central widget and main layout
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Connection control bar
        main_layout.addWidget(self._create_connection_bar())

        # Command queue widget (shows pending telescope commands)
        from celestron_nexstar.gui.widgets.command_queue_widget import CommandQueueWidget

        self.command_queue = CommandQueueWidget()
        main_layout.addWidget(self.command_queue)

        # Create splitter for main content (2 panels)
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Top panel: Control and status
        top_panel = self._create_top_panel()
        splitter.addWidget(top_panel)

        # Bottom panel: Tabs with Visible Objects and Communication Log
        bottom_panel = self._create_bottom_tabs_panel()
        splitter.addWidget(bottom_panel)

        # Set initial splitter sizes (2 sections)
        splitter.setSizes([400, 350])

        main_layout.addWidget(splitter)

        self.setCentralWidget(central_widget)

    def _create_connection_bar(self) -> QWidget:
        """Create the connection status and control bar."""
        bar = QFrame()
        bar.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        layout = QHBoxLayout(bar)

        # Status indicator and label
        self.connection_status_label = QLabel("● Disconnected")
        self.connection_status_label.setStyleSheet("color: #E74C3C; font-weight: bold;")
        layout.addWidget(self.connection_status_label)

        layout.addStretch()

        # Connect button
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self._on_connect_clicked)
        layout.addWidget(self.connect_button)

        # Disconnect button
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.clicked.connect(self._on_disconnect_clicked)
        self.disconnect_button.setEnabled(False)
        layout.addWidget(self.disconnect_button)

        return bar

    def _setup_shortcuts(self) -> None:
        """Setup keyboard shortcuts for telescope control."""
        # Rate preset shortcuts
        # G = Guide rate (2x)
        guide_shortcut = QShortcut(QKeySequence("G"), self)
        guide_shortcut.activated.connect(lambda: self._on_shortcut_preset(self.rate_presets.GUIDE_RATE))

        # C = Center rate (32x)
        center_shortcut = QShortcut(QKeySequence("C"), self)
        center_shortcut.activated.connect(lambda: self._on_shortcut_preset(self.rate_presets.CENTER_RATE))

        # F = Find rate (3°/s)
        find_shortcut = QShortcut(QKeySequence("F"), self)
        find_shortcut.activated.connect(lambda: self._on_shortcut_preset(self.rate_presets.FIND_RATE))

        # Ctrl+H = Command history dialog
        history_shortcut = QShortcut(QKeySequence("Ctrl+H"), self)
        history_shortcut.activated.connect(self._on_history_shortcut)

    def _on_shortcut_preset(self, rate: int) -> None:
        """
        Handle rate preset keyboard shortcut.

        Args:
            rate: Rate value to set (2, 5, or 8)
        """
        if not self._is_connected:
            return  # Ignore if not connected

        # Trigger the preset button click (which will emit rate_changed signal)
        if rate == self.rate_presets.GUIDE_RATE:
            self.rate_presets.guide_button.click()
        elif rate == self.rate_presets.CENTER_RATE:
            self.rate_presets.center_button.click()
        elif rate == self.rate_presets.FIND_RATE:
            self.rate_presets.find_button.click()

    def _on_history_shortcut(self) -> None:
        """Handle command history keyboard shortcut (Ctrl+H)."""
        if not self.command_tracker:
            return  # No command tracker available

        from celestron_nexstar.gui.dialogs.command_history_dialog import CommandHistoryDialog

        # Open history dialog
        dialog = CommandHistoryDialog(self.command_tracker, self)
        dialog.exec()

    def _create_top_panel(self) -> QWidget:
        """Create the top panel with controls and status."""
        panel = QWidget()
        layout = QHBoxLayout(panel)
        layout.setSpacing(15)

        # Left side: Directional control
        left_group = self._create_directional_control_panel()
        layout.addWidget(left_group)

        # Right side: Position and status
        right_group = self._create_position_status_panel()
        layout.addWidget(right_group)

        layout.setStretch(0, 1)
        layout.setStretch(1, 1)

        return panel

    def _create_directional_control_panel(self) -> QWidget:
        """Create the directional control panel."""
        group = QGroupBox("Directional Control")
        layout = QVBoxLayout(group)

        # Directional pad widget
        self.directional_pad = DirectionalPadWidget()
        self.directional_pad.direction_pressed.connect(self._on_direction_pressed)
        self.directional_pad.direction_released.connect(self._on_direction_released)
        self.directional_pad.stop_pressed.connect(self._on_stop_pressed)
        self.directional_pad.set_enabled(False)  # Disabled until connected
        layout.addWidget(self.directional_pad, alignment=Qt.AlignmentFlag.AlignCenter)

        # Rate presets (Guide, Center, Find)
        from celestron_nexstar.gui.widgets.slew_rate_presets_widget import SlewRatePresetsWidget

        presets_layout = QVBoxLayout()
        presets_header = QLabel("Rate Presets:")
        presets_header.setStyleSheet("font-weight: bold;")
        presets_layout.addWidget(presets_header)

        self.rate_presets = SlewRatePresetsWidget()
        self.rate_presets.rate_changed.connect(self._on_preset_rate_selected)
        presets_layout.addWidget(self.rate_presets, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addLayout(presets_layout)

        # Slew rate control
        rate_layout = QVBoxLayout()
        rate_layout.setSpacing(5)

        rate_header = QLabel("Slew Rate:")
        rate_header.setStyleSheet("font-weight: bold;")
        rate_layout.addWidget(rate_header)

        self.rate_slider = QSlider(Qt.Orientation.Horizontal)
        self.rate_slider.setMinimum(0)
        self.rate_slider.setMaximum(9)
        self.rate_slider.setValue(5)
        self.rate_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.rate_slider.setTickInterval(1)
        self.rate_slider.valueChanged.connect(self._on_rate_changed)
        rate_layout.addWidget(self.rate_slider)

        self.rate_label = QLabel(f"Rate {self._slew_rate}: {SLEW_RATE_DESCRIPTIONS[self._slew_rate]}")
        self.rate_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rate_label.setStyleSheet("color: #4A90E2; font-weight: bold;")
        rate_layout.addWidget(self.rate_label)

        layout.addLayout(rate_layout)

        # Movement mode selection
        mode_layout = QHBoxLayout()
        mode_label = QLabel("Mode:")
        mode_layout.addWidget(mode_label)

        self.step_radio = QRadioButton("Step")
        self.step_radio.setToolTip("Single step movement (0.2 seconds)")
        mode_layout.addWidget(self.step_radio)

        self.continuous_radio = QRadioButton("Continuous")
        self.continuous_radio.setChecked(True)
        self.continuous_radio.setToolTip("Hold button for continuous movement")
        mode_layout.addWidget(self.continuous_radio)

        # Group radio buttons
        mode_group = QButtonGroup(group)
        mode_group.addButton(self.step_radio)
        mode_group.addButton(self.continuous_radio)
        self.step_radio.toggled.connect(self._on_movement_mode_changed)

        mode_layout.addStretch()
        layout.addLayout(mode_layout)

        layout.addStretch()

        return group

    def _create_position_status_panel(self) -> QWidget:
        """Create the position and status display panel."""
        group = QGroupBox("Position & Status")
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        # RA/Dec display
        ra_dec_group = QGroupBox("Equatorial Coordinates")
        ra_dec_layout = QVBoxLayout(ra_dec_group)

        self.ra_label = QLabel("RA: --h --m --s")
        self.ra_label.setStyleSheet(
            "font-family: 'Menlo', 'Monaco', 'Consolas', 'Courier New', monospace; font-size: 12pt;"
        )
        ra_dec_layout.addWidget(self.ra_label)

        self.dec_label = QLabel("Dec: --° --' --\"")
        self.dec_label.setStyleSheet(
            "font-family: 'Menlo', 'Monaco', 'Consolas', 'Courier New', monospace; font-size: 12pt;"
        )
        ra_dec_layout.addWidget(self.dec_label)

        layout.addWidget(ra_dec_group)

        # Alt/Az display
        alt_az_group = QGroupBox("Horizontal Coordinates")
        alt_az_layout = QVBoxLayout(alt_az_group)

        self.alt_label = QLabel("Alt: --.-°")
        self.alt_label.setStyleSheet(
            "font-family: 'Menlo', 'Monaco', 'Consolas', 'Courier New', monospace; font-size: 12pt;"
        )
        alt_az_layout.addWidget(self.alt_label)

        self.az_label = QLabel("Az: --.-° (--)")
        self.az_label.setStyleSheet(
            "font-family: 'Menlo', 'Monaco', 'Consolas', 'Courier New', monospace; font-size: 12pt;"
        )
        alt_az_layout.addWidget(self.az_label)

        layout.addWidget(alt_az_group)

        # Tracking mode control
        tracking_layout = QHBoxLayout()
        tracking_label = QLabel("Tracking:")
        tracking_label.setStyleSheet("font-weight: bold;")
        tracking_layout.addWidget(tracking_label)

        self.tracking_combo = QComboBox()
        self.tracking_combo.addItem("Alt-Az", TrackingMode.ALT_AZ)
        self.tracking_combo.addItem("EQ North", TrackingMode.EQ_NORTH)
        self.tracking_combo.addItem("EQ South", TrackingMode.EQ_SOUTH)
        self.tracking_combo.currentIndexChanged.connect(self._on_tracking_mode_changed)
        self.tracking_combo.setEnabled(False)
        tracking_layout.addWidget(self.tracking_combo, 1)

        layout.addLayout(tracking_layout)

        # Slew status
        slew_group = QGroupBox("Slew Status")
        slew_layout = QVBoxLayout(slew_group)

        self.slew_status_label = QLabel("Slewing: ✗ No")
        self.slew_status_label.setStyleSheet("font-size: 11pt;")
        slew_layout.addWidget(self.slew_status_label)

        layout.addWidget(slew_group)

        # Slew progress widget (shows during goto operations)
        from celestron_nexstar.gui.widgets.slew_progress_widget import SlewProgressWidget

        self.slew_progress_widget = SlewProgressWidget()
        self.slew_progress_widget.hide()  # Hidden until goto starts
        layout.addWidget(self.slew_progress_widget)

        # Telescope tools buttons
        tools_group = QGroupBox("Telescope Tools")
        tools_layout = QVBoxLayout(tools_group)
        tools_layout.setSpacing(5)

        self.goto_queue_button = QPushButton("Goto Queue / Sequence")
        self.goto_queue_button.setToolTip("Open goto queue window for automated slewing")
        self.goto_queue_button.clicked.connect(self._on_goto_queue)
        tools_layout.addWidget(self.goto_queue_button)

        self.calibrate_button = QPushButton("Calibrate Telescope")
        self.calibrate_button.setToolTip("Open calibration assistant")
        self.calibrate_button.clicked.connect(self._on_calibrate)
        self.calibrate_button.setEnabled(False)
        tools_layout.addWidget(self.calibrate_button)

        self.align_button = QPushButton("Align Telescope")
        self.align_button.setToolTip("Open alignment assistant")
        self.align_button.clicked.connect(self._on_align)
        self.align_button.setEnabled(False)
        tools_layout.addWidget(self.align_button)

        layout.addWidget(tools_group)

        layout.addStretch()

        return group

    def _create_visible_objects_panel(self) -> QWidget:
        """Create the visible objects table panel."""
        group = QGroupBox("Visible Objects")
        layout = QVBoxLayout(group)

        # Filter controls
        filter_layout = QHBoxLayout()

        filter_label = QLabel("Filter:")
        filter_label.setStyleSheet("font-weight: bold;")
        filter_layout.addWidget(filter_label)

        self.all_visible_radio = QRadioButton("All Visible")
        self.all_visible_radio.setChecked(True)
        self.all_visible_radio.setToolTip("Show all objects above horizon")
        self.all_visible_radio.toggled.connect(self._on_filter_changed)
        filter_layout.addWidget(self.all_visible_radio)

        self.fov_filter_radio = QRadioButton("In Current FOV")
        self.fov_filter_radio.setToolTip("Show only objects in telescope field of view")
        filter_layout.addWidget(self.fov_filter_radio)

        filter_layout.addStretch()

        # Auto-refresh control
        refresh_label = QLabel("Refresh:")
        filter_layout.addWidget(refresh_label)

        self.refresh_combo = QComboBox()
        self.refresh_combo.addItem("Manual", 0)
        self.refresh_combo.addItem("30 seconds", 30000)
        self.refresh_combo.addItem("1 minute", 60000)
        self.refresh_combo.addItem("5 minutes", 300000)
        self.refresh_combo.setCurrentIndex(1)  # Default: 30 seconds
        self.refresh_combo.currentIndexChanged.connect(self._on_refresh_interval_changed)
        filter_layout.addWidget(self.refresh_combo)

        # Manual refresh button
        self.refresh_button = QPushButton("Refresh Now")
        self.refresh_button.clicked.connect(self._update_visible_objects)
        self.refresh_button.setEnabled(False)
        filter_layout.addWidget(self.refresh_button)

        layout.addLayout(filter_layout)

        # Objects table
        self.objects_table = QTableWidget()
        self.objects_table.setColumnCount(6)
        self.objects_table.setHorizontalHeaderLabels(["Name", "Type", "Mag", "Alt", "RA", "Dec"])

        # Table settings
        self.objects_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.objects_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.objects_table.setAlternatingRowColors(True)
        self.objects_table.setSortingEnabled(True)
        self.objects_table.verticalHeader().setVisible(False)

        # Column sizing
        header = self.objects_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Name
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Type
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Mag
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Alt
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # RA
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Dec

        layout.addWidget(self.objects_table)

        return group

    def _create_bottom_tabs_panel(self) -> QWidget:
        """Create the bottom panel with tabs for Visible Objects and Communication Log."""
        tabs = QTabWidget()

        # Tab 1: Visible Objects
        visible_objects_tab = self._create_visible_objects_panel()
        tabs.addTab(visible_objects_tab, "Visible Objects")

        # Tab 2: Communication Log
        log_tab = self._create_communication_log_panel()
        tabs.addTab(log_tab, "Communication Log")

        return tabs

    def _create_communication_log_panel(self) -> QWidget:
        """Create the communication log panel."""
        from celestron_nexstar.gui.widgets.telescope_command_log_panel import TelescopeCommandLogPanel

        # Create log panel with command tracker (no longer collapsible, always expanded in tab)
        self.command_log_panel = TelescopeCommandLogPanel(command_tracker=self.command_tracker, parent=self)

        # Expand by default since it's in a tab
        self.command_log_panel.is_expanded = True
        # Trigger the toggle to show the log
        if hasattr(self.command_log_panel, "_toggle"):
            self.command_log_panel._toggle()

        return self.command_log_panel

    # Connection methods
    def _on_connect_clicked(self) -> None:
        """Handle connect button click."""
        # Open connection dialog
        dialog = TelescopeConnectionDialog(self)
        if dialog.exec() != TelescopeConnectionDialog.DialogCode.Accepted:
            return

        config = dialog.get_telescope_config()
        if not config:
            return

        # Create telescope if needed
        if not self.telescope:
            from celestron_nexstar import NexStarTelescope

            self.telescope = NexStarTelescope(config)
        else:
            # Update config
            self.telescope.config = config

        # Show connecting status
        if self.connection_status_label:
            self.connection_status_label.setText("● Connecting...")
            self.connection_status_label.setStyleSheet("color: #F39C12; font-weight: bold;")

        self.connect_button.setEnabled(False)

        # Start connection thread
        self._connect_thread = ConnectTelescopeThread(self.telescope)
        self._connect_thread.connection_ready.connect(self._on_connected)
        self._connect_thread.error_occurred.connect(self._on_connection_error)
        self._connect_thread.start()

    def _on_connected(self, success: bool) -> None:
        """Handle successful connection."""
        if not success:
            self._on_connection_error("Connection failed")
            return

        self._is_connected = True

        # Connect command tracker to protocol for debugging/history
        if self.telescope and hasattr(self.telescope, "protocol") and self.telescope.protocol:
            self.telescope.protocol.set_command_tracker(self.command_tracker)

        # Update UI
        if self.connection_status_label:
            conn_info = ""
            if self.telescope and self.telescope.config:
                if self.telescope.config.connection_type == "serial":
                    conn_info = f" ({self.telescope.config.port})"
                else:
                    conn_info = f" ({self.telescope.config.host}:{self.telescope.config.tcp_port})"

            self.connection_status_label.setText(f"● Connected{conn_info}")
            self.connection_status_label.setStyleSheet("color: #27AE60; font-weight: bold;")

        self.connect_button.setEnabled(False)
        self.disconnect_button.setEnabled(True)

        # Enable controls
        if self.directional_pad:
            self.directional_pad.set_enabled(True)
        if self.tracking_combo:
            self.tracking_combo.setEnabled(True)
        if self.refresh_button:
            self.refresh_button.setEnabled(True)
        if self.calibrate_button:
            self.calibrate_button.setEnabled(True)
        if self.align_button:
            self.align_button.setEnabled(True)

        # Start update timers
        self.position_timer.start()
        self.slew_status_timer.start()
        self.visible_objects_timer.start()

        # Initial updates
        self._update_position()
        self._update_visible_objects()
        self._update_tracking_mode()

    def _on_connection_error(self, error: str) -> None:
        """Handle connection error."""
        logger.error(f"Connection error: {error}")

        if self.connection_status_label:
            self.connection_status_label.setText("● Disconnected")
            self.connection_status_label.setStyleSheet("color: #E74C3C; font-weight: bold;")

        self.connect_button.setEnabled(True)

        QMessageBox.warning(
            self,
            "Connection Error",
            f"Failed to connect to telescope:\n\n{error}\n\nPlease check your connection and try again.",
        )

    def _on_disconnect_clicked(self) -> None:
        """Handle disconnect button click."""
        if not self.telescope:
            return

        # Stop timers
        self.position_timer.stop()
        self.slew_status_timer.stop()
        self.visible_objects_timer.stop()

        # Show disconnecting status
        if self.connection_status_label:
            self.connection_status_label.setText("● Disconnecting...")
            self.connection_status_label.setStyleSheet("color: #F39C12; font-weight: bold;")

        self.disconnect_button.setEnabled(False)

        # Start disconnect thread
        self._disconnect_thread = DisconnectThread(self.telescope)
        self._disconnect_thread.disconnect_complete.connect(self._on_disconnected)
        self._disconnect_thread.error_occurred.connect(lambda e: logger.error(f"Disconnect error: {e}"))
        self._disconnect_thread.start()

    def _on_disconnected(self) -> None:
        """Handle successful disconnection."""
        self._is_connected = False

        # Update UI
        if self.connection_status_label:
            self.connection_status_label.setText("● Disconnected")
            self.connection_status_label.setStyleSheet("color: #E74C3C; font-weight: bold;")

        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)

        # Disable controls
        if self.directional_pad:
            self.directional_pad.set_enabled(False)
        if self.tracking_combo:
            self.tracking_combo.setEnabled(False)
        if self.refresh_button:
            self.refresh_button.setEnabled(False)
        if self.calibrate_button:
            self.calibrate_button.setEnabled(False)
        if self.align_button:
            self.align_button.setEnabled(False)

        # Clear displays
        if self.ra_label:
            self.ra_label.setText("RA: --h --m --s")
        if self.dec_label:
            self.dec_label.setText("Dec: --° --' --\"")
        if self.alt_label:
            self.alt_label.setText("Alt: --.-°")
        if self.az_label:
            self.az_label.setText("Az: --.-° (--)")
        if self.slew_status_label:
            self.slew_status_label.setText("Slewing: ✗ No")

        # Clear objects table
        if self.objects_table:
            self.objects_table.setRowCount(0)

    # Directional movement methods
    def _on_direction_pressed(self, direction: Direction) -> None:
        """Handle directional button press."""
        if not self._is_connected or not self.telescope:
            QMessageBox.warning(self, "Not Connected", "Telescope is not connected.")
            return

        self._current_direction = direction

        if self._movement_mode == "step":
            # Single step movement
            self._perform_step_movement(direction)
        else:
            # Continuous movement
            self._start_continuous_movement(direction)

    def _on_direction_released(self, direction: Direction) -> None:
        """Handle directional button release."""
        # Only stop if in continuous mode and releasing the active direction
        if self._movement_mode == "continuous" and self._current_direction == direction:
            self._stop_movement()
            self._current_direction = None

    def _on_stop_pressed(self) -> None:
        """Handle stop button press."""
        self._stop_movement()
        self._current_direction = None

    def _perform_step_movement(self, direction: Direction) -> None:
        """Perform a single step movement."""
        if not self.telescope:
            return

        logger.info(f"Step movement: {direction.name} at rate {self._slew_rate}")

        # Start step thread
        self._step_thread = MoveStepThread(self.telescope, direction, self._slew_rate)
        self._step_thread.step_complete.connect(self._on_step_complete)
        self._step_thread.error_occurred.connect(self._on_movement_error)
        self._step_thread.start()

    def _start_continuous_movement(self, direction: Direction) -> None:
        """Start continuous movement in a direction."""
        if not self.telescope:
            return

        logger.info(f"Starting continuous movement: {direction.name} at rate {self._slew_rate}")

        # Start movement thread
        self._move_thread = MoveFixedThread(self.telescope, direction, self._slew_rate)
        self._move_thread.move_started.connect(self._on_movement_started)
        self._move_thread.error_occurred.connect(self._on_movement_error)
        self._move_thread.start()

    def _stop_movement(self) -> None:
        """Stop all telescope movement."""
        if not self.telescope:
            return

        logger.info("Stopping telescope movement")

        # Start stop thread
        self._stop_thread = StopMotionThread(self.telescope, "both")
        self._stop_thread.stopped.connect(self._on_movement_stopped)
        self._stop_thread.error_occurred.connect(lambda e: logger.error(f"Stop error: {e}"))
        self._stop_thread.start()

    def _on_step_complete(self, success: bool) -> None:
        """Handle step movement completion."""
        if success:
            logger.debug("Step movement completed")
        else:
            logger.warning("Step movement failed")

    def _on_movement_started(self, success: bool) -> None:
        """Handle movement start."""
        if success:
            logger.debug("Continuous movement started")
        else:
            logger.warning("Failed to start movement")
            self._current_direction = None

    def _on_movement_stopped(self, success: bool) -> None:
        """Handle movement stop."""
        if success:
            logger.debug("Movement stopped")
        else:
            logger.warning("Failed to stop movement")

    def _on_movement_error(self, error: str) -> None:
        """Handle movement error."""
        logger.error(f"Movement error: {error}")
        self._current_direction = None

        QMessageBox.warning(
            self, "Movement Error", f"Failed to move telescope:\n\n{error}\n\nCheck connection and try again."
        )

        # Try to stop movement
        self._stop_movement()

    def _on_rate_changed(self, value: int) -> None:
        """Handle slew rate slider change."""
        self._slew_rate = value
        if self.rate_label:
            self.rate_label.setText(f"Rate {value}: {SLEW_RATE_DESCRIPTIONS[value]}")

        # Deselect preset if slider value doesn't match any preset
        if hasattr(self, "rate_presets") and self.rate_presets:
            from celestron_nexstar.gui.widgets.slew_rate_presets_widget import SlewRatePresetsWidget

            preset_rates = [
                SlewRatePresetsWidget.GUIDE_RATE,
                SlewRatePresetsWidget.CENTER_RATE,
                SlewRatePresetsWidget.FIND_RATE,
            ]
            if value not in preset_rates:
                self.rate_presets.deselect_all()
            else:
                self.rate_presets.set_active_rate(value)

    def _on_preset_rate_selected(self, rate: int) -> None:
        """
        Handle rate preset button click.

        Args:
            rate: Preset rate value (2, 5, or 8)
        """
        # Update slider (which will trigger _on_rate_changed)
        if self.rate_slider:
            self.rate_slider.setValue(rate)

    def _on_movement_mode_changed(self) -> None:
        """Handle movement mode change."""
        if self.step_radio and self.step_radio.isChecked():
            self._movement_mode = "step"
        else:
            self._movement_mode = "continuous"

    # Position update methods
    def _update_position(self) -> None:
        """Update telescope position display."""
        if not self._is_connected or not self.telescope:
            return

        # Get RA/Dec position
        self._position_ra_dec_thread = GetPositionRADecThread(self.telescope)
        self._position_ra_dec_thread.position_ready.connect(self._on_position_ra_dec_ready)
        self._position_ra_dec_thread.error_occurred.connect(self._on_position_error)
        self._position_ra_dec_thread.start()

        # Get Alt/Az position
        self._position_alt_az_thread = GetPositionAltAzThread(self.telescope)
        self._position_alt_az_thread.position_ready.connect(self._on_position_alt_az_ready)
        self._position_alt_az_thread.error_occurred.connect(self._on_position_error)
        self._position_alt_az_thread.start()

    def _on_position_ra_dec_ready(self, coords: object) -> None:
        """Handle RA/Dec position update."""
        try:
            if self.ra_label:
                ra_str = format_ra(coords.ra_hours)
                self.ra_label.setText(f"RA: {ra_str}")

            if self.dec_label:
                dec_str = format_dec(coords.dec_degrees)
                self.dec_label.setText(f"Dec: {dec_str}")

            # Reset error count on successful update
            self._position_error_count = 0

            # Update slew progress widget if active
            if hasattr(self, "slew_progress_widget") and self.slew_progress_widget.is_active():
                self.slew_progress_widget.update_progress(coords.ra_hours, coords.dec_degrees)

        except Exception as e:
            logger.error(f"Error formatting position: {e}")

    def _on_position_alt_az_ready(self, coords: object) -> None:
        """Handle Alt/Az position update."""
        try:
            if self.alt_label:
                self.alt_label.setText(f"Alt: {coords.altitude:.2f}°")

            if self.az_label:
                # Calculate cardinal direction
                cardinal = self._get_cardinal_direction(coords.azimuth)
                self.az_label.setText(f"Az: {coords.azimuth:.2f}° ({cardinal})")

        except Exception as e:
            logger.error(f"Error formatting Alt/Az: {e}")

    def _on_position_error(self, error: str) -> None:
        """Handle position update error."""
        self._position_error_count += 1
        logger.warning(f"Position update error (count: {self._position_error_count}): {error}")

        # If multiple consecutive errors, assume disconnection
        if self._position_error_count >= 5:
            logger.error("Multiple position errors, assuming connection lost")
            QMessageBox.warning(self, "Connection Lost", "Lost connection to telescope. Please reconnect.")
            self._on_disconnected()

    def _get_cardinal_direction(self, azimuth: float) -> str:
        """Convert azimuth to cardinal direction."""
        directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        index = int((azimuth + 22.5) / 45) % 8
        return directions[index]

    # Slew status methods
    def _check_slew_status(self) -> None:
        """Check if telescope is slewing."""
        if not self._is_connected or not self.telescope:
            return

        self._is_slewing_thread = IsSlewingThread(self.telescope)
        self._is_slewing_thread.slewing_status.connect(self._on_slewing_status_ready)
        self._is_slewing_thread.error_occurred.connect(lambda e: logger.debug(f"Slew status error: {e}"))
        self._is_slewing_thread.start()

    def _on_slewing_status_ready(self, is_slewing: bool) -> None:
        """Handle slewing status update."""
        if not self.slew_status_label:
            return

        if is_slewing:
            target_info = ""
            if self._selected_object:
                target_info = f" → {self._selected_object.common_name or self._selected_object.name}"
            self.slew_status_label.setText(f"Slewing: ✓ Yes{target_info}")
            self.slew_status_label.setStyleSheet("font-size: 11pt; color: #F39C12; font-weight: bold;")
        else:
            self.slew_status_label.setText("Slewing: ✗ No")
            self.slew_status_label.setStyleSheet("font-size: 11pt; color: #27AE60;")

    # Tracking mode methods
    def _on_tracking_mode_changed(self) -> None:
        """Handle tracking mode combo box change."""
        if not self._is_connected or not self.telescope or not self.tracking_combo:
            return

        new_mode = self.tracking_combo.currentData()
        logger.info(f"Setting tracking mode to {new_mode}")

        # Set tracking mode via thread
        self._set_tracking_thread = SetTrackingModeThread(self.telescope, new_mode)
        self._set_tracking_thread.mode_set.connect(self._on_tracking_mode_set)
        self._set_tracking_thread.error_occurred.connect(self._on_tracking_mode_error)
        self._set_tracking_thread.start()

    def _on_tracking_mode_set(self, success: bool) -> None:
        """Handle tracking mode set completion."""
        if success:
            logger.info("Tracking mode updated successfully")
        else:
            logger.warning("Failed to set tracking mode")
            # Refresh current mode
            self._update_tracking_mode()

    def _on_tracking_mode_error(self, error: str) -> None:
        """Handle tracking mode error."""
        logger.error(f"Tracking mode error: {error}")
        QMessageBox.warning(self, "Tracking Mode Error", f"Failed to set tracking mode:\n\n{error}")
        # Refresh current mode
        self._update_tracking_mode()

    def _update_tracking_mode(self) -> None:
        """Update tracking mode from telescope."""
        if not self._is_connected or not self.telescope:
            return

        self._tracking_mode_thread = GetTrackingModeThread(self.telescope)
        self._tracking_mode_thread.mode_ready.connect(self._on_tracking_mode_ready)
        self._tracking_mode_thread.error_occurred.connect(lambda e: logger.debug(f"Tracking mode error: {e}"))
        self._tracking_mode_thread.start()

    def _on_tracking_mode_ready(self, mode: object) -> None:
        """Handle tracking mode update."""
        if not self.tracking_combo:
            return

        # Find and select the mode in combo box
        for i in range(self.tracking_combo.count()):
            if self.tracking_combo.itemData(i) == mode:
                # Temporarily block signals to avoid triggering change event
                self.tracking_combo.blockSignals(True)
                self.tracking_combo.setCurrentIndex(i)
                self.tracking_combo.blockSignals(False)
                break

    def _on_filter_changed(self) -> None:
        """Handle visible objects filter change."""
        if self._is_connected:
            self._update_visible_objects()

    def _on_refresh_interval_changed(self) -> None:
        """Handle refresh interval change."""
        if not self.refresh_combo:
            return

        interval = self.refresh_combo.currentData()
        if interval == 0:
            # Manual refresh
            self.visible_objects_timer.stop()
        else:
            self.visible_objects_timer.setInterval(interval)
            if self._is_connected:
                self.visible_objects_timer.start()

    # Visible objects methods
    def _update_visible_objects(self) -> None:
        """Update visible objects table."""
        if not self.objects_table:
            return

        logger.info("Updating visible objects list")

        try:
            # Get database
            db = get_database()

            # Get all objects (limit for performance)
            all_objects = db.filter_objects(limit=500)

            # Filter for visibility
            visible = filter_visible_objects(
                all_objects,
                config=None,  # Uses current optical configuration
                sky_brightness=SkyBrightness.FAIR,
                min_altitude_deg=20.0,
                observer_lat=None,  # Uses saved location
                observer_lon=None,
                dt=None,  # Uses current time
            )

            # Apply FOV filter if enabled
            if self.fov_filter_radio and self.fov_filter_radio.isChecked():
                visible = self._filter_by_fov(visible)

            # Populate table
            self._populate_objects_table(visible)

            logger.info(f"Found {len(visible)} visible objects")

        except Exception as e:
            logger.error(f"Error updating visible objects: {e}", exc_info=True)
            # Don't show error dialog, just log it

    def _filter_by_fov(self, objects: list) -> list:
        """Filter objects within current telescope FOV."""
        if not self._is_connected or not self.telescope:
            logger.warning("Cannot filter by FOV: telescope not connected")
            return []

        try:
            # Get current telescope position
            position = asyncio.run(self.telescope.get_position_ra_dec())

            # Get current FOV from optical configuration
            config = get_current_configuration()
            fov_radius = config.true_fov_deg / 2

            logger.debug(f"Filtering by FOV: {config.true_fov_deg}° (radius: {fov_radius}°)")

            # Filter objects within FOV
            filtered = []
            for obj, vis_info in objects:
                # Calculate angular separation
                sep = angular_separation(position.ra_hours, position.dec_degrees, obj.ra_hours, obj.dec_degrees)

                if sep <= fov_radius:
                    filtered.append((obj, vis_info))

            logger.debug(f"Filtered to {len(filtered)} objects in FOV")
            return filtered

        except Exception as e:
            logger.error(f"Error filtering by FOV: {e}", exc_info=True)
            # Fall back to all visible
            return objects

    def _populate_objects_table(self, objects: list) -> None:
        """Populate the objects table with visible objects."""
        if not self.objects_table:
            return

        # Clear table
        self.objects_table.setRowCount(0)
        self.objects_table.setSortingEnabled(False)  # Disable while populating

        # Populate rows
        for obj, vis_info in objects:
            row = self.objects_table.rowCount()
            self.objects_table.insertRow(row)

            # Name
            name_item = QTableWidgetItem(obj.common_name or obj.name)
            name_item.setData(Qt.ItemDataRole.UserRole, obj)  # Store object reference
            self.objects_table.setItem(row, 0, name_item)

            # Type
            type_item = QTableWidgetItem(
                obj.object_type.name if hasattr(obj.object_type, "name") else str(obj.object_type)
            )
            self.objects_table.setItem(row, 1, type_item)

            # Magnitude
            mag_item = QTableWidgetItem(f"{obj.magnitude:.1f}" if obj.magnitude is not None else "—")
            self.objects_table.setItem(row, 2, mag_item)

            # Altitude
            alt_item = QTableWidgetItem(f"{vis_info.altitude_deg:.1f}°" if vis_info.altitude_deg is not None else "—")
            self.objects_table.setItem(row, 3, alt_item)

            # RA
            ra_item = QTableWidgetItem(format_ra(obj.ra_hours))
            self.objects_table.setItem(row, 4, ra_item)

            # Dec
            dec_item = QTableWidgetItem(format_dec(obj.dec_degrees))
            self.objects_table.setItem(row, 5, dec_item)

        # Re-enable sorting
        self.objects_table.setSortingEnabled(True)

    # Telescope tools methods
    def _on_goto_queue(self) -> None:
        """Handle goto queue button click."""
        from celestron_nexstar.gui.windows.goto_queue_window import GotoQueueWindow

        # Get main window reference
        main_window = self.parent()
        if main_window is None:
            logger.warning("No main window reference, cannot open goto queue")
            return

        # Check if window already exists on main window
        if not hasattr(main_window, "_goto_queue_window") or main_window._goto_queue_window is None:
            main_window._goto_queue_window = GotoQueueWindow(main_window, telescope=self.telescope)
            main_window._goto_queue_window.destroyed.connect(lambda: setattr(main_window, "_goto_queue_window", None))
        else:
            # Update telescope reference if it changed
            main_window._goto_queue_window.telescope = self.telescope

        main_window._goto_queue_window.show()
        main_window._goto_queue_window.raise_()
        main_window._goto_queue_window.activateWindow()

    def _on_calibrate(self) -> None:
        """Handle calibrate button click."""
        from celestron_nexstar.gui.dialogs.calibration_assistant_dialog import CalibrationAssistantDialog

        dialog = CalibrationAssistantDialog(self, telescope=self.telescope)
        dialog.exec()

    def _on_align(self) -> None:
        """Handle align button click."""
        from celestron_nexstar.gui.dialogs.alignment_assistant_dialog import AlignmentAssistantDialog

        dialog = AlignmentAssistantDialog(self, telescope=self.telescope)
        dialog.exec()

    def closeEvent(self, event) -> None:  # noqa: N802
        """Handle window close event - cleanup resources."""
        logger.info("Telescope control window closing, cleaning up...")

        # Stop all timers first
        try:
            if hasattr(self, "position_timer") and self.position_timer:
                self.position_timer.stop()
            if hasattr(self, "slew_status_timer") and self.slew_status_timer:
                self.slew_status_timer.stop()
            if hasattr(self, "visible_objects_timer") and self.visible_objects_timer:
                self.visible_objects_timer.stop()
        except Exception as e:
            logger.warning(f"Error stopping timers: {e}")

        # Wait for all worker threads to finish
        threads_to_wait = [
            ("_position_ra_dec_thread", "Position RA/Dec"),
            ("_position_alt_az_thread", "Position Alt/Az"),
            ("_step_thread", "Step Movement"),
            ("_move_thread", "Continuous Movement"),
            ("_stop_thread", "Stop Movement"),
            ("_connect_thread", "Connect"),
            ("_disconnect_thread", "Disconnect"),
            ("_sync_thread", "Sync"),
            ("_goto_thread", "Goto"),
            ("_tracking_mode_thread", "Tracking Mode"),
        ]

        for thread_attr, thread_name in threads_to_wait:
            try:
                if hasattr(self, thread_attr):
                    thread = getattr(self, thread_attr)
                    if thread and thread.isRunning():
                        logger.debug(f"Waiting for {thread_name} thread to finish...")
                        thread.wait(2000)  # Wait up to 2 seconds
                        if thread.isRunning():
                            logger.warning(f"{thread_name} thread did not finish in time")
                        # Clear the reference
                        setattr(self, thread_attr, None)
            except Exception as e:
                logger.warning(f"Error waiting for {thread_name} thread: {e}")

        # If connected, disconnect and shutdown telescope
        if hasattr(self, "telescope") and self.telescope:
            if self._is_connected:
                logger.info("Disconnecting telescope on window close...")
                try:
                    # Run disconnect in the telescope's event loop with timeout
                    import concurrent.futures

                    future = concurrent.futures.Future()

                    def do_disconnect():
                        try:
                            self.telescope.run_coroutine_threadsafe(self.telescope.disconnect())
                            future.set_result(True)
                        except Exception as ex:
                            future.set_exception(ex)

                    # Run in a thread to avoid blocking
                    import threading

                    disconnect_thread = threading.Thread(target=do_disconnect, daemon=True)
                    disconnect_thread.start()
                    disconnect_thread.join(timeout=3.0)

                except Exception as e:
                    logger.warning(f"Error during disconnect: {e}")

            # Shutdown telescope event loop
            try:
                self.telescope.shutdown()
                logger.info("Telescope shutdown complete")
                self.telescope = None
            except Exception as e:
                logger.warning(f"Error during telescope shutdown: {e}")

        # Accept the close event
        event.accept()

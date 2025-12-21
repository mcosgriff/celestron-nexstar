"""
Debug log panel widget for displaying application logs with filtering and pause capability.
"""

import logging
from collections import deque
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QRegularExpression, Signal
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


if TYPE_CHECKING:
    pass


class DebugLogHandler(logging.Handler, QObject):
    """Custom logging handler that emits Qt signals for log records (thread-safe)."""

    log_signal = Signal(object)  # Emits LogRecord objects

    def __init__(self) -> None:
        """Initialize the handler."""
        logging.Handler.__init__(self)
        QObject.__init__(self)
        # Format: "HH:MM:SS [LEVEL] logger.name: message"
        self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)-8s] %(name)s: %(message)s", datefmt="%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        """Emit log record via Qt signal (thread-safe)."""
        try:
            # Emit raw LogRecord for filtering
            self.log_signal.emit(record)
        except Exception:
            # Ignore errors to avoid logging recursion
            pass


class DebugLogPanel(QWidget):
    """A panel for displaying debug logs with filtering and pause capability."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the debug log panel."""
        super().__init__(parent)

        # State management
        self.is_paused: bool = False
        self.paused_records: deque[logging.LogRecord] = deque(maxlen=1000)
        self.all_records: list[logging.LogRecord] = []
        self.enabled_levels: set[int] = {logging.WARNING, logging.ERROR}  # Default
        self.filter_text: str = ""
        self.auto_scroll: bool = True  # Auto-scroll to top when new messages arrive

        self._setup_ui()
        self._setup_logging()

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header with toggle and control buttons
        self.header = QWidget()
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(5, 2, 5, 2)

        self.toggle_btn = QPushButton("▼ Debug Log")
        self.toggle_btn.clicked.connect(self._toggle)
        header_layout.addWidget(self.toggle_btn)
        header_layout.addStretch()

        # Pause/Resume button
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setCheckable(True)
        self.pause_btn.setMinimumWidth(70)
        self.pause_btn.toggled.connect(self._toggle_pause)
        header_layout.addWidget(self.pause_btn)

        # Clear button
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setMinimumWidth(60)
        self.clear_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        self.clear_btn.clicked.connect(self._clear_log)
        header_layout.addWidget(self.clear_btn)

        layout.addWidget(self.header)

        # Filter controls widget (initially hidden)
        self.controls_widget = QWidget()
        controls_layout = QVBoxLayout(self.controls_widget)
        controls_layout.setContentsMargins(5, 5, 5, 5)
        controls_layout.setSpacing(5)

        # Log level checkboxes in horizontal layout
        level_layout = QHBoxLayout()
        level_layout.addWidget(QWidget())  # Small spacer

        self.level_checkboxes: dict[int, QCheckBox] = {}

        # Create checkboxes for each log level
        self.debug_checkbox = QCheckBox("DEBUG")
        self.debug_checkbox.setChecked(False)
        self.debug_checkbox.stateChanged.connect(self._on_level_filter_changed)
        self.level_checkboxes[logging.DEBUG] = self.debug_checkbox
        level_layout.addWidget(self.debug_checkbox)

        self.info_checkbox = QCheckBox("INFO")
        self.info_checkbox.setChecked(False)
        self.info_checkbox.stateChanged.connect(self._on_level_filter_changed)
        self.level_checkboxes[logging.INFO] = self.info_checkbox
        level_layout.addWidget(self.info_checkbox)

        self.warning_checkbox = QCheckBox("WARNING")
        self.warning_checkbox.setChecked(True)  # Default checked
        self.warning_checkbox.stateChanged.connect(self._on_level_filter_changed)
        self.level_checkboxes[logging.WARNING] = self.warning_checkbox
        level_layout.addWidget(self.warning_checkbox)

        self.error_checkbox = QCheckBox("ERROR")
        self.error_checkbox.setChecked(True)  # Default checked
        self.error_checkbox.stateChanged.connect(self._on_level_filter_changed)
        self.level_checkboxes[logging.ERROR] = self.error_checkbox
        level_layout.addWidget(self.error_checkbox)

        # Add separator
        level_layout.addWidget(QWidget())  # Small spacer

        # Auto-scroll toggle button (icon-based to match communications log style)
        self.auto_scroll_btn = QPushButton("↓")
        self.auto_scroll_btn.setCheckable(True)
        self.auto_scroll_btn.setChecked(True)  # Default enabled
        self.auto_scroll_btn.setToolTip("Auto-scroll to newest messages")
        self.auto_scroll_btn.setMaximumWidth(30)
        self.auto_scroll_btn.setMinimumWidth(30)
        self.auto_scroll_btn.toggled.connect(self._on_auto_scroll_changed)
        level_layout.addWidget(self.auto_scroll_btn)

        level_layout.addStretch()
        controls_layout.addLayout(level_layout)

        # Text filter input
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QWidget())  # Small spacer

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter text...")
        self.filter_input.textChanged.connect(self._on_text_filter_changed)
        filter_layout.addWidget(self.filter_input)

        filter_layout.addStretch()
        controls_layout.addLayout(filter_layout)

        self.controls_widget.hide()
        layout.addWidget(self.controls_widget)

        # Log text area (initially hidden)
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(1000)  # Limit to 1000 lines
        self.log_text.hide()
        layout.addWidget(self.log_text)

        # Connect scroll event to detect manual scrolling
        self.log_text.verticalScrollBar().valueChanged.connect(self._on_scroll)

        # Set initial size policy
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setMaximumHeight(30)  # Collapsed height (header only)

    def _setup_logging(self) -> None:
        """Set up logging handler for debug log panel."""
        # Create custom handler
        self.log_handler = DebugLogHandler()
        self.log_handler.setLevel(logging.DEBUG)

        # Connect signal to slot
        self.log_handler.log_signal.connect(self._on_log_record)

        # Add handler to celestron_nexstar logger (captures all app logs)
        app_logger = logging.getLogger("celestron_nexstar")
        app_logger.addHandler(self.log_handler)
        app_logger.setLevel(logging.DEBUG)

    def _on_log_record(self, record: logging.LogRecord) -> None:
        """Handle incoming log record from handler."""
        if self.is_paused:
            # Buffer the record
            self.paused_records.append(record)
        else:
            # Process immediately
            self._add_record(record)

    def _add_record(self, record: logging.LogRecord) -> None:
        """Add a log record to display and storage."""
        # Store in memory (maintain max 1000)
        self.all_records.append(record)
        if len(self.all_records) > 1000:
            self.all_records.pop(0)

        # Check filters
        if not self._should_display_record(record):
            return

        # Format the message
        msg = self.log_handler.format(record)

        # Insert at TOP (position 0) for "most recent at top"
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.log_text.setTextCursor(cursor)
        self.log_text.insertPlainText(msg + "\n")

        # Auto-scroll to top if enabled
        if self.auto_scroll:
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.log_text.setTextCursor(cursor)

        # Highlight filter text if present
        if self.filter_text:
            self._highlight_filter_text()

    def _should_display_record(self, record: logging.LogRecord) -> bool:
        """Check if record should be displayed based on filters."""
        # Check level filter
        if record.levelno not in self.enabled_levels:
            return False

        # Check text filter
        if self.filter_text:
            formatted = self.log_handler.format(record)
            if self.filter_text.lower() not in formatted.lower():
                return False

        return True

    def _toggle(self) -> None:
        """Toggle the panel expansion state."""
        is_expanded = self.log_text.isVisible()

        if not is_expanded:
            # Expand
            self.controls_widget.show()
            self.log_text.show()
            self.toggle_btn.setText("▲ Debug Log")
            self.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX
            self.setMinimumHeight(200)  # Minimum height when expanded
        else:
            # Collapse
            self.controls_widget.hide()
            self.log_text.hide()
            self.toggle_btn.setText("▼ Debug Log")
            self.setMaximumHeight(30)  # Collapsed height
            self.setMinimumHeight(30)

    def _toggle_pause(self, checked: bool) -> None:
        """Toggle pause state."""
        self.is_paused = checked

        if self.is_paused:
            # Switch to paused state
            self.pause_btn.setText("Resume")
        else:
            # Resume - process buffered records
            self.pause_btn.setText("Pause")
            self._process_paused_records()

    def _process_paused_records(self) -> None:
        """Process all paused records on resume."""
        # Process in order (oldest first)
        records = list(self.paused_records)
        self.paused_records.clear()

        for record in records:
            self._add_record(record)

    def _on_level_filter_changed(self) -> None:
        """Handle log level filter change."""
        # Update enabled levels based on checkbox states
        self.enabled_levels.clear()
        for level, checkbox in self.level_checkboxes.items():
            if checkbox.isChecked():
                self.enabled_levels.add(level)

        # Refresh display
        self._refresh_display()

    def _on_text_filter_changed(self, text: str) -> None:
        """Handle text filter change."""
        self.filter_text = text
        self._refresh_display()

    def _refresh_display(self) -> None:
        """Refresh the display by re-filtering all records."""
        self.log_text.clear()

        # Process in reverse order (most recent first) for "most recent at top"
        for record in reversed(self.all_records):
            if self._should_display_record(record):
                msg = self.log_handler.format(record)
                # Append to build from top down
                self.log_text.appendPlainText(msg)

        # Highlight filter text if present
        if self.filter_text:
            self._highlight_filter_text()

    def _highlight_filter_text(self) -> None:
        """Highlight all occurrences of the filter text in the log display."""
        if not self.filter_text:
            # Clear highlights
            self.log_text.setExtraSelections([])
            return

        # Detect theme for highlight colors
        from PySide6.QtGui import QGuiApplication, QPalette

        is_dark = False
        gui_app = QGuiApplication.instance()
        if gui_app and isinstance(gui_app, QGuiApplication):
            palette = gui_app.palette()
            window_color = palette.color(QPalette.ColorRole.Window)
            brightness = window_color.lightness()
            is_dark = brightness < 128

        # Create theme-aware highlight format
        highlight_format = QTextCharFormat()
        if is_dark:
            # Dark theme: darker yellow background, light text
            highlight_format.setBackground(QColor("#ffa726"))  # Orange/yellow
            highlight_format.setForeground(QColor("#000000"))  # Black text
        else:
            # Light theme: bright yellow background, dark text
            highlight_format.setBackground(QColor("#ffeb3b"))  # Yellow
            highlight_format.setForeground(QColor("#000000"))  # Black text

        # Find all occurrences of filter text (case-insensitive)
        extra_selections = []
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)

        # Create case-insensitive regex for search
        search_text = self.filter_text
        # Escape special regex characters
        escaped_text = QRegularExpression.escape(search_text)
        regex = QRegularExpression(escaped_text, QRegularExpression.PatternOption.CaseInsensitiveOption)

        # Search for all occurrences
        while True:
            # Find next occurrence (case-insensitive)
            cursor = self.log_text.document().find(regex, cursor)
            if cursor.isNull():
                break

            # Create selection for this occurrence
            selection = QPlainTextEdit.ExtraSelection()
            selection.cursor = cursor
            selection.format = highlight_format
            extra_selections.append(selection)

        # Apply all highlights
        self.log_text.setExtraSelections(extra_selections)

    def _clear_log(self) -> None:
        """Clear the log text and stored records."""
        self.log_text.clear()
        self.all_records.clear()
        self.paused_records.clear()

    def _on_auto_scroll_changed(self, checked: bool) -> None:
        """Handle auto-scroll toggle button state change."""
        self.auto_scroll = checked
        if self.auto_scroll:
            # Scroll to top when re-enabled
            cursor = self.log_text.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.log_text.setTextCursor(cursor)

    def _on_scroll(self, value: int) -> None:
        """Detect manual scrolling and disable auto-scroll if user scrolls away from top."""
        # Only disable auto-scroll if user manually scrolled away from top
        # Check if we're at the top (value should be 0 or very close)
        scrollbar = self.log_text.verticalScrollBar()
        at_top = scrollbar.value() == scrollbar.minimum()

        if not at_top and self.auto_scroll:
            # User scrolled away from top, disable auto-scroll
            self.auto_scroll = False
            self.auto_scroll_btn.setChecked(False)
        elif at_top and not self.auto_scroll:
            # User scrolled back to top, re-enable auto-scroll
            self.auto_scroll = True
            self.auto_scroll_btn.setChecked(True)

    def apply_theme(self, theme: object) -> None:
        """Apply theme to the debug log panel."""
        # Get monospace font from application property
        from PySide6.QtGui import QGuiApplication, QPalette
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        monospace_font = app.property("monospace_font") if app and app.property("monospace_font") else None
        font_family = f"'{monospace_font}'" if monospace_font else "'Courier New'"

        # Detect theme for log panel styling
        is_dark = False
        gui_app = QGuiApplication.instance()
        if gui_app and isinstance(gui_app, QGuiApplication):
            palette = gui_app.palette()
            window_color = palette.color(QPalette.ColorRole.Window)
            brightness = window_color.lightness()
            is_dark = brightness < 128

        # Theme-aware log panel styling
        bg_color = "#ffffff" if not is_dark else "#1e1e1e"
        text_color = "#000000" if not is_dark else "#d4d4d4"
        self.log_text.setStyleSheet(
            f"""
            QPlainTextEdit {{
                background-color: {bg_color};
                color: {text_color};
                font-family: {font_family};
                font-size: 10pt;
                border: none;
            }}
        """
        )

    def closeEvent(self, event: object) -> None:  # noqa: N802
        """Clean up logging handler when widget is closed."""
        # Remove handler from logger
        app_logger = logging.getLogger("celestron_nexstar")
        app_logger.removeHandler(self.log_handler)
        super().closeEvent(event)  # type: ignore[arg-type]

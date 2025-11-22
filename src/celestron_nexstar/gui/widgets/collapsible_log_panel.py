"""
Collapsible log panel widget for displaying telescope communication logs.
"""

import logging

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class QtLogHandler(logging.Handler):
    """Custom logging handler that writes to a QPlainTextEdit widget."""

    def __init__(self, text_widget: QPlainTextEdit) -> None:
        """Initialize the handler with a text widget."""
        super().__init__()
        self.text_widget = text_widget
        self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record to the text widget."""
        try:
            msg = self.format(record)
            # Append to the text widget (thread-safe via Qt signals)
            self.text_widget.appendPlainText(msg)

            # Auto-scroll to bottom
            cursor = self.text_widget.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.text_widget.setTextCursor(cursor)
        except Exception:
            # Ignore errors in logging handler to avoid recursion
            pass


class CollapsibleLogPanel(QWidget):
    """A collapsible panel for displaying communication logs."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the collapsible log panel."""
        super().__init__(parent)
        self.is_expanded = False
        self._setup_ui()
        self._setup_logging()

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header with toggle button
        self.header = QWidget()
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(5, 2, 5, 2)

        self.toggle_btn = QPushButton("▼ Communication Log")
        self.toggle_btn.clicked.connect(self._toggle)
        header_layout.addWidget(self.toggle_btn)
        header_layout.addStretch()

        # Clear button - ensure it's wide enough to show full text
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setMinimumWidth(60)
        self.clear_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        self.clear_btn.setObjectName("clear_log_button")
        self.clear_btn.clicked.connect(self._clear_log)
        header_layout.addWidget(self.clear_btn)

        layout.addWidget(self.header)

        # Log text area (initially hidden)
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(1000)  # Limit to 1000 lines to prevent memory issues
        self.log_text.hide()
        layout.addWidget(self.log_text)

        # Set initial size policy
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setMaximumHeight(30)  # Collapsed height (header only)

    def _setup_logging(self) -> None:
        """Set up logging handler for telescope communication."""
        # Create custom handler for the log panel
        self.log_handler = QtLogHandler(self.log_text)

        # Set level to capture DEBUG and above for telescope protocol
        self.log_handler.setLevel(logging.DEBUG)

        # Add handler to telescope protocol logger
        protocol_logger = logging.getLogger("celestron_nexstar.api.telescope.protocol")
        protocol_logger.addHandler(self.log_handler)
        protocol_logger.setLevel(logging.DEBUG)

        # Also capture telescope module logs
        telescope_logger = logging.getLogger("celestron_nexstar.api.telescope")
        telescope_logger.addHandler(self.log_handler)
        telescope_logger.setLevel(logging.DEBUG)

    def _toggle(self) -> None:
        """Toggle the panel expansion state."""
        self.is_expanded = not self.is_expanded

        if self.is_expanded:
            self.log_text.show()
            self.toggle_btn.setText("▲ Communication Log")
            self.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX
            self.setMinimumHeight(150)  # Minimum height when expanded
        else:
            self.log_text.hide()
            self.toggle_btn.setText("▼ Communication Log")
            self.setMaximumHeight(30)  # Collapsed height
            self.setMinimumHeight(30)

    def _clear_log(self) -> None:
        """Clear the log text."""
        self.log_text.clear()

    def apply_theme(self, theme: object) -> None:
        """Apply theme to the log panel (qt-material handles most styling)."""
        # Log panel styling is handled by qt-material, but we keep dark background for readability
        self.log_text.setStyleSheet(
            """
            QPlainTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-family: 'Courier New', monospace;
                font-size: 10pt;
                border: none;
            }
        """
        )

    def closeEvent(self, event: object) -> None:  # noqa: N802
        """Clean up logging handler when widget is closed."""
        # Remove handler from loggers
        protocol_logger = logging.getLogger("celestron_nexstar.api.telescope.protocol")
        telescope_logger = logging.getLogger("celestron_nexstar.api.telescope")
        protocol_logger.removeHandler(self.log_handler)
        telescope_logger.removeHandler(self.log_handler)
        super().closeEvent(event)  # type: ignore[arg-type]

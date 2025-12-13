"""
Custom title bar widget for client-side window decorations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

if TYPE_CHECKING:
    from PySide6.QtWidgets import QMainWindow


class CustomTitleBar(QWidget):
    """Custom title bar for client-side decorations with minimize/maximize/close controls."""

    def __init__(self, parent: QMainWindow, title: str = "Application") -> None:
        """
        Initialize the custom title bar.

        Args:
            parent: The parent QMainWindow
            title: The window title to display
        """
        print(f"CustomTitleBar.__init__ called with title: {title}")
        super().__init__(parent)
        self.parent_window = parent

        # Force visibility and size
        self.setAutoFillBackground(True)
        self.setFixedHeight(40)
        self.setMinimumHeight(40)
        self.setVisible(True)

        # Set a VERY OBVIOUS style immediately
        self.setStyleSheet("""
            CustomTitleBar {
                background-color: #ff0000;
                border: 5px solid #00ff00;
                min-height: 40px;
                max-height: 40px;
            }
        """)

        self.show()

        print(f"CustomTitleBar initialized, height set to 40, visible: {self.isVisible()}")

        # Enable mouse tracking for dragging
        self.setMouseTracking(True)

        # For window dragging
        self.drag_position: QPoint | None = None

        # Create layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 5, 0)
        layout.setSpacing(0)

        # Title label
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(self.title_label)
        layout.addStretch()

        # Window control buttons
        self.minimize_btn = QPushButton("−")
        self.maximize_btn = QPushButton("□")
        self.close_btn = QPushButton("✕")

        # Style the buttons
        button_style = """
            QPushButton {
                border: none;
                border-radius: 0px;
                padding: 0px;
                font-size: 16px;
                font-weight: bold;
                min-width: 46px;
                max-width: 46px;
                min-height: 40px;
                max-height: 40px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.2);
            }
        """

        close_button_style = """
            QPushButton {
                border: none;
                border-radius: 0px;
                padding: 0px;
                font-size: 16px;
                font-weight: bold;
                min-width: 46px;
                max-width: 46px;
                min-height: 40px;
                max-height: 40px;
            }
            QPushButton:hover {
                background-color: #e81123;
                color: white;
            }
            QPushButton:pressed {
                background-color: #f1707a;
                color: white;
            }
        """

        self.minimize_btn.setStyleSheet(button_style)
        self.maximize_btn.setStyleSheet(button_style)
        self.close_btn.setStyleSheet(close_button_style)

        # Add buttons to layout
        layout.addWidget(self.minimize_btn)
        layout.addWidget(self.maximize_btn)
        layout.addWidget(self.close_btn)

        # Connect button signals
        self.minimize_btn.clicked.connect(parent.showMinimized)
        self.maximize_btn.clicked.connect(self._toggle_maximize)
        self.close_btn.clicked.connect(parent.close)

        # Apply theme-aware styling
        self._apply_theme_style()

    def _apply_theme_style(self) -> None:
        """Apply theme-aware styling to the title bar."""
        from PySide6.QtGui import QGuiApplication, QPalette

        app = QGuiApplication.instance()
        if app and isinstance(app, QGuiApplication):
            palette = app.palette()
            window_color = palette.color(QPalette.ColorRole.Window)
            text_color = palette.color(QPalette.ColorRole.WindowText)
            brightness = window_color.lightness()

            # Determine if dark theme
            is_dark = brightness < 128

            # Set title bar background color (slightly different from window)
            if is_dark:
                bg_color = f"rgb({min(window_color.red() + 10, 255)}, {min(window_color.green() + 10, 255)}, {min(window_color.blue() + 10, 255)})"
            else:
                bg_color = f"rgb({max(window_color.red() - 10, 0)}, {max(window_color.green() - 10, 0)}, {max(window_color.blue() - 10, 0)})"

            # DEBUG: Use bright red background to make title bar visible
            self.setStyleSheet(f"""
                CustomTitleBar {{
                    background-color: #ff0000;
                    border-bottom: 5px solid #00ff00;
                    min-height: 40px;
                    max-height: 40px;
                }}
            """)

            self.title_label.setStyleSheet(f"""
                QLabel {{
                    color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()});
                    font-weight: bold;
                    font-size: 13px;
                }}
            """)

    def set_title(self, title: str) -> None:
        """
        Update the window title.

        Args:
            title: The new title text
        """
        self.title_label.setText(title)

    def _toggle_maximize(self) -> None:
        """Toggle between maximized and normal window state."""
        if self.parent_window.isMaximized():
            self.parent_window.showNormal()
            self.maximize_btn.setText("□")
        else:
            self.parent_window.showMaximized()
            self.maximize_btn.setText("❐")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """
        Handle mouse press events for window dragging.

        Args:
            event: The mouse event
        """
        if event.button() == Qt.MouseButton.LeftButton:
            # Don't drag if clicking on buttons
            if self.childAt(event.pos()) in [self.minimize_btn, self.maximize_btn, self.close_btn]:
                event.ignore()
                return

            # Store the position for dragging - use pos() instead of frameGeometry()
            self.drag_position = event.globalPosition().toPoint() - self.parent_window.pos()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """
        Handle mouse move events for window dragging.

        Args:
            event: The mouse event
        """
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_position is not None:
            # Move the window
            self.parent_window.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """
        Handle mouse release events.

        Args:
            event: The mouse event
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = None
            event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """
        Handle double-click events to toggle maximize.

        Args:
            event: The mouse event
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximize()
            event.accept()

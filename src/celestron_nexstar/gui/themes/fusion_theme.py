"""
Qt Fusion theme management for the GUI application.

Uses Qt's built-in Fusion style with light/dark theme support.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication


class ThemeMode(str, Enum):
    """Theme mode enumeration."""

    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"  # Follow OS system theme


class FusionTheme:
    """
    Qt Fusion theme manager using Qt's built-in Fusion style.

    Provides light/dark theme switching using QPalette.
    """

    def __init__(self, mode: ThemeMode = ThemeMode.SYSTEM) -> None:
        """Initialize theme with specified mode."""
        self.mode = mode
        self._app: QApplication | None = None

    def apply(self, app: QApplication) -> None:
        """Apply the theme to the application."""
        from PySide6.QtGui import QPalette
        from PySide6.QtWidgets import QStyleFactory

        self._app = app

        # Set Fusion style
        app.setStyle(QStyleFactory.create("Fusion"))

        # Determine actual theme mode
        actual_mode = self._detect_system_theme() if self.mode == ThemeMode.SYSTEM else self.mode

        # Create and apply palette based on theme mode
        palette = QPalette()
        if actual_mode == ThemeMode.DARK:
            from PySide6.QtGui import QColor

            # Dark theme palette
            palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
            palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
            palette.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
            palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
            palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(0, 0, 0))
            palette.setColor(QPalette.ColorRole.ToolTipText, QColor(255, 255, 255))
            palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
            palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
            palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
            palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
            palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
            palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
            palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))
        else:  # LIGHT mode
            # Use default light palette (Fusion style default)
            pass

        app.setPalette(palette)

    def _detect_system_theme(self) -> ThemeMode:
        """Detect the system theme preference."""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication, QPalette

        app = QGuiApplication.instance()
        if app and isinstance(app, QGuiApplication):
            # Qt 6.5+ has colorScheme() method
            try:
                style_hints = app.styleHints()  # type: ignore[attr-defined]
                color_scheme = style_hints.colorScheme()  # type: ignore[attr-defined]
                if color_scheme == Qt.ColorScheme.Dark:  # type: ignore[attr-defined]
                    return ThemeMode.DARK
                elif color_scheme == Qt.ColorScheme.Light:  # type: ignore[attr-defined]
                    return ThemeMode.LIGHT
            except (AttributeError, TypeError):
                # Fallback for older Qt versions: check palette brightness
                palette: QPalette = app.palette()  # type: ignore[attr-defined]
                window_color = palette.color(QPalette.ColorRole.Window)
                # If window background is dark, assume dark theme
                brightness = window_color.lightness()
                if brightness < 128:
                    return ThemeMode.DARK

        # Default to light if detection fails
        return ThemeMode.LIGHT

    def set_mode(self, mode: ThemeMode) -> None:
        """Set the theme mode."""
        self.mode = mode
        if self._app:
            self.apply(self._app)

    def get_app(self) -> QApplication | None:
        """Get the QApplication instance."""
        return self._app

"""
Qt Material theme management for the GUI application.

Uses the qt-material package for Material Design styling.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, ClassVar


if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication


class ThemeMode(str, Enum):
    """Theme mode enumeration."""

    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"  # Follow OS system theme


class ColorStyle(str, Enum):
    """Material Design color style enumeration based on qt-material themes."""

    AMBER = "amber"  # light_amber.xml / dark_amber.xml
    BLUE = "blue"  # light_blue.xml / dark_blue.xml
    CYAN = "cyan"  # light_cyan.xml / dark_cyan.xml
    LIGHTGREEN = "lightgreen"  # light_lightgreen.xml / dark_lightgreen.xml
    ORANGE = "orange"  # light_orange.xml (no dark version)
    PINK = "pink"  # light_pink.xml / dark_pink.xml
    PURPLE = "purple"  # light_purple.xml / dark_purple.xml
    RED = "red"  # light_red.xml / dark_red.xml
    TEAL = "teal"  # light_teal.xml / dark_teal.xml
    YELLOW = "yellow"  # light_yellow.xml / dark_yellow.xml


class QtMaterialTheme:
    """
    Qt Material theme manager using qt-material package.

    Provides theme switching and management using qt-material stylesheets.
    """

    # Map color styles to qt-material theme files
    THEME_MAP: ClassVar[dict[ColorStyle, dict[str, str]]] = {
        ColorStyle.AMBER: {"light": "light_amber.xml", "dark": "dark_amber.xml"},
        ColorStyle.BLUE: {"light": "light_blue.xml", "dark": "dark_blue.xml"},
        ColorStyle.CYAN: {"light": "light_cyan.xml", "dark": "dark_cyan.xml"},
        ColorStyle.LIGHTGREEN: {"light": "light_lightgreen.xml", "dark": "dark_lightgreen.xml"},
        ColorStyle.ORANGE: {"light": "light_orange.xml", "dark": "light_orange.xml"},  # No dark version, use light
        ColorStyle.PINK: {"light": "light_pink.xml", "dark": "dark_pink.xml"},
        ColorStyle.PURPLE: {"light": "light_purple.xml", "dark": "dark_purple.xml"},
        ColorStyle.RED: {"light": "light_red.xml", "dark": "dark_red.xml"},
        ColorStyle.TEAL: {"light": "light_teal.xml", "dark": "dark_teal.xml"},
        ColorStyle.YELLOW: {"light": "light_yellow.xml", "dark": "dark_yellow.xml"},
    }

    def __init__(
        self,
        mode: ThemeMode = ThemeMode.LIGHT,
        style: ColorStyle = ColorStyle.BLUE,
        dense: bool = True,
    ) -> None:
        """Initialize theme with specified mode, color style, and density."""
        self.mode = mode
        self.style = style
        self.dense = dense
        self._app: QApplication | None = None

    def apply(self, app: QApplication) -> None:
        """Apply the theme to the application."""
        from qt_material import apply_stylesheet  # type: ignore[import-untyped]

        self._app = app

        # Determine actual theme mode
        actual_mode_enum = self._detect_system_theme() if self.mode == ThemeMode.SYSTEM else self.mode

        # Get theme file name (convert enum to string for dict lookup)
        actual_mode_str = actual_mode_enum.value  # "light" or "dark"
        theme_file = self.THEME_MAP[self.style][actual_mode_str]

        # Apply stylesheet with dense mode
        # density_scale is passed through extra parameter
        # Values: "0" = normal, "1" = dense, "2" = very dense
        density_scale = "1" if self.dense else "0"
        apply_stylesheet(
            app,
            theme=theme_file,
            invert_secondary=(actual_mode_enum == ThemeMode.LIGHT),
            extra={"density_scale": density_scale},
        )

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

    def set_style(self, style: ColorStyle) -> None:
        """Set the color style."""
        self.style = style
        if self._app:
            self.apply(self._app)

    def set_dense(self, dense: bool) -> None:
        """Set dense mode."""
        self.dense = dense
        if self._app:
            self.apply(self._app)

    def get_app(self) -> QApplication | None:
        """Get the QApplication instance."""
        return self._app

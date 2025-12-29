"""
Slew Rate Presets Widget

Provides quick-access buttons for common slew rates (Guide, Center, Find).
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget


class SlewRatePresetsWidget(QWidget):
    """
    Slew rate preset buttons for quick telescope speed selection.

    Provides three preset buttons:
    - Guide: Rate 2 (4x sidereal) - Fine centering and guiding
    - Center: Rate 5 (32x sidereal) - Standard positioning
    - Find: Rate 8 (3°/sec) - Fast object acquisition

    Signals:
        rate_changed: Emitted when a preset button is clicked (emits rate value 2, 5, or 8)
    """

    rate_changed = Signal(int)  # Emits rate value (2, 5, or 8)

    # Preset rate mappings
    GUIDE_RATE = 2  # 4x sidereal
    CENTER_RATE = 5  # 32x sidereal
    FIND_RATE = 8  # 3°/sec

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the slew rate presets widget."""
        super().__init__(parent)

        # Store currently selected preset (None if no preset active)
        self._selected_preset: int | None = None

        # Create buttons
        self.guide_button: QPushButton
        self.center_button: QPushButton
        self.find_button: QPushButton

        self._setup_ui()
        self._create_button_styles()

    def _setup_ui(self) -> None:
        """Set up the UI layout."""
        layout = QHBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create preset buttons
        self.guide_button = QPushButton("Guide\n2x")
        self.guide_button.setToolTip("Guide rate (2x sidereal)\nFine centering and guiding")
        self.guide_button.setMinimumWidth(80)
        self.guide_button.clicked.connect(lambda: self._on_preset_clicked(self.GUIDE_RATE))

        self.center_button = QPushButton("Center\n32x")
        self.center_button.setToolTip("Center rate (32x sidereal)\nStandard positioning")
        self.center_button.setMinimumWidth(80)
        self.center_button.clicked.connect(lambda: self._on_preset_clicked(self.CENTER_RATE))

        self.find_button = QPushButton("Find\n3°/s")
        self.find_button.setToolTip("Find rate (3°/sec)\nFast object acquisition")
        self.find_button.setMinimumWidth(80)
        self.find_button.clicked.connect(lambda: self._on_preset_clicked(self.FIND_RATE))

        # Add buttons to layout
        layout.addWidget(self.guide_button)
        layout.addWidget(self.center_button)
        layout.addWidget(self.find_button)

        self.setLayout(layout)

    def _on_preset_clicked(self, rate: int) -> None:
        """Handle preset button click."""
        self._selected_preset = rate
        self._update_button_highlights()
        self.rate_changed.emit(rate)

    def _update_button_highlights(self) -> None:
        """Update button styling to show active preset."""
        # Reset all buttons to normal style
        self._create_button_styles()

        # Add highlight border to selected preset
        if self._selected_preset is not None:
            selected_style = """
                QPushButton {{
                    border: 3px solid #FFD700;
                    box-shadow: 0 0 10px #FFD700;
                }}
            """

            if self._selected_preset == self.GUIDE_RATE:
                current_style = self.guide_button.styleSheet()
                self.guide_button.setStyleSheet(current_style + selected_style)
            elif self._selected_preset == self.CENTER_RATE:
                current_style = self.center_button.styleSheet()
                self.center_button.setStyleSheet(current_style + selected_style)
            elif self._selected_preset == self.FIND_RATE:
                current_style = self.find_button.styleSheet()
                self.find_button.setStyleSheet(current_style + selected_style)

    def set_active_rate(self, rate: int) -> None:
        """
        Set the active rate (updates button highlights without emitting signal).

        Args:
            rate: Current rate value (2, 5, 8, or None to deselect all)
        """
        if rate in [self.GUIDE_RATE, self.CENTER_RATE, self.FIND_RATE]:
            self._selected_preset = rate
        else:
            self._selected_preset = None

        self._update_button_highlights()

    def deselect_all(self) -> None:
        """Deselect all preset buttons (called when slider is manually adjusted)."""
        self._selected_preset = None
        self._update_button_highlights()

    def get_selected_rate(self) -> int | None:
        """
        Get the currently selected preset rate.

        Returns:
            Selected rate value (2, 5, or 8) or None if no preset is selected
        """
        return self._selected_preset

    def apply_theme(self, theme: object) -> None:
        """
        Apply theme to the preset buttons.

        Adapts button colors based on dark/light theme.
        """
        from PySide6.QtGui import QGuiApplication, QPalette

        # Detect theme
        is_dark = False
        gui_app = QGuiApplication.instance()
        if gui_app and isinstance(gui_app, QGuiApplication):
            palette = gui_app.palette()
            window_color = palette.color(QPalette.ColorRole.Window)
            brightness = window_color.lightness()
            is_dark = brightness < 128

        # Recreate button styles with theme-aware colors
        self._create_button_styles(is_dark)
        self._update_button_highlights()

    def _create_button_styles(self, is_dark: bool = False) -> None:
        """
        Create button styles with theme-aware colors.

        Args:
            is_dark: Whether we're in dark mode
        """
        # Guide button (blue) - adjust for theme
        guide_bg = "#3498DB" if not is_dark else "#2E86C1"
        guide_hover = "#2E86C1" if not is_dark else "#2874A6"
        guide_pressed = "#2874A6" if not is_dark else "#21618C"

        guide_style = f"""
            QPushButton {{
                background-color: {guide_bg};
                color: white;
                border: 2px solid {guide_bg};
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                min-width: 80px;
            }}
            QPushButton:hover {{
                background-color: {guide_hover};
            }}
            QPushButton:pressed {{
                background-color: {guide_pressed};
            }}
            QPushButton:disabled {{
                background-color: #CCCCCC;
                color: #666666;
                border-color: #999999;
            }}
        """
        self.guide_button.setStyleSheet(guide_style)

        # Center button (green)
        center_bg = "#27AE60" if not is_dark else "#229954"
        center_hover = "#229954" if not is_dark else "#1E8449"
        center_pressed = "#1E8449" if not is_dark else "#186A3B"

        center_style = f"""
            QPushButton {{
                background-color: {center_bg};
                color: white;
                border: 2px solid {center_bg};
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                min-width: 80px;
            }}
            QPushButton:hover {{
                background-color: {center_hover};
            }}
            QPushButton:pressed {{
                background-color: {center_pressed};
            }}
            QPushButton:disabled {{
                background-color: #CCCCCC;
                color: #666666;
                border-color: #999999;
            }}
        """
        self.center_button.setStyleSheet(center_style)

        # Find button (orange)
        find_bg = "#E67E22" if not is_dark else "#CA6F1E"
        find_hover = "#CA6F1E" if not is_dark else "#AF601A"
        find_pressed = "#AF601A" if not is_dark else "#935116"

        find_style = f"""
            QPushButton {{
                background-color: {find_bg};
                color: white;
                border: 2px solid {find_bg};
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                min-width: 80px;
            }}
            QPushButton:hover {{
                background-color: {find_hover};
            }}
            QPushButton:pressed {{
                background-color: {find_pressed};
            }}
            QPushButton:disabled {{
                background-color: #CCCCCC;
                color: #666666;
                border-color: #999999;
            }}
        """
        self.find_button.setStyleSheet(find_style)

"""
Directional Pad Widget

9-way directional control pad for telescope slewing with visual feedback.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QPushButton, QWidget

from celestron_nexstar.api.core.enums import Direction


class DirectionalPadWidget(QWidget):
    """
    9-way directional control pad for telescope slewing.

    Provides 8 directional buttons (UP, DOWN, LEFT, RIGHT, and 4 diagonals)
    plus a center STOP button. Supports both click (step) and press-hold
    (continuous) operations.

    Signals:
        direction_pressed: Emitted when a direction button is pressed
        direction_released: Emitted when a direction button is released
        stop_pressed: Emitted when the STOP button is pressed
    """

    direction_pressed = Signal(object)  # type: ignore[type-arg,misc]  # Emits Direction enum
    direction_released = Signal(object)  # type: ignore[type-arg,misc]  # Emits Direction enum
    stop_pressed = Signal()  # type: ignore[type-arg,misc]

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the directional pad widget."""
        super().__init__(parent)

        # Button size
        self._button_size = 80

        # Create buttons dictionary
        self.buttons: dict[Direction, QPushButton] = {}
        self.stop_button: QPushButton | None = None

        self._setup_ui()
        self._apply_styling()

    def _setup_ui(self) -> None:
        """Set up the UI layout."""
        layout = QGridLayout(self)
        layout.setSpacing(5)
        layout.setContentsMargins(10, 10, 10, 10)

        # Create direction buttons
        # Row 0: UP_LEFT, UP, UP_RIGHT
        self._create_direction_button(Direction.UP_LEFT, "↖", 0, 0, layout)
        self._create_direction_button(Direction.UP, "↑", 0, 1, layout)
        self._create_direction_button(Direction.UP_RIGHT, "↗", 0, 2, layout)

        # Row 1: LEFT, STOP, RIGHT
        self._create_direction_button(Direction.LEFT, "←", 1, 0, layout)
        self._create_stop_button(1, 1, layout)
        self._create_direction_button(Direction.RIGHT, "→", 1, 2, layout)

        # Row 2: DOWN_LEFT, DOWN, DOWN_RIGHT
        self._create_direction_button(Direction.DOWN_LEFT, "↙", 2, 0, layout)
        self._create_direction_button(Direction.DOWN, "↓", 2, 1, layout)
        self._create_direction_button(Direction.DOWN_RIGHT, "↘", 2, 2, layout)

        self.setLayout(layout)

    def _create_direction_button(
        self, direction: Direction, text: str, row: int, col: int, layout: QGridLayout
    ) -> None:
        """Create a directional button."""
        button = QPushButton(text, self)
        button.setMinimumSize(self._button_size, self._button_size)
        button.setMaximumSize(self._button_size, self._button_size)

        # Connect press and release events
        button.pressed.connect(lambda d=direction: self._on_direction_pressed(d))
        button.released.connect(lambda d=direction: self._on_direction_released(d))

        # Set tooltip
        button.setToolTip(f"Move {direction.name.replace('_', ' ').title()}")

        self.buttons[direction] = button
        layout.addWidget(button, row, col)

    def _create_stop_button(self, row: int, col: int, layout: QGridLayout) -> None:
        """Create the center STOP button."""
        button = QPushButton("STOP", self)
        button.setMinimumSize(self._button_size, self._button_size)
        button.setMaximumSize(self._button_size, self._button_size)

        # Connect click event
        button.clicked.connect(self._on_stop_pressed)

        # Set tooltip
        button.setToolTip("Stop all telescope movement")

        # Store reference
        self.stop_button = button
        layout.addWidget(button, row, col)

    def _apply_styling(self) -> None:
        """Apply custom styling to buttons."""
        # Direction button style
        direction_style = """
            QPushButton {
                font-size: 24px;
                font-weight: bold;
                background-color: #4A90E2;
                color: white;
                border: 2px solid #357ABD;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #5FA3F5;
            }
            QPushButton:pressed {
                background-color: #357ABD;
            }
            QPushButton:disabled {
                background-color: #CCCCCC;
                color: #666666;
                border-color: #999999;
            }
        """

        # Apply to all direction buttons
        for button in self.buttons.values():
            button.setStyleSheet(direction_style)

        # STOP button style (red)
        if self.stop_button:
            stop_style = """
                QPushButton {
                    font-size: 16px;
                    font-weight: bold;
                    background-color: #E74C3C;
                    color: white;
                    border: 2px solid #C0392B;
                    border-radius: 8px;
                }
                QPushButton:hover {
                    background-color: #FF5E4D;
                }
                QPushButton:pressed {
                    background-color: #C0392B;
                }
                QPushButton:disabled {
                    background-color: #CCCCCC;
                    color: #666666;
                    border-color: #999999;
                }
            """
            self.stop_button.setStyleSheet(stop_style)

    def _on_direction_pressed(self, direction: Direction) -> None:
        """Handle direction button press."""
        self.direction_pressed.emit(direction)

    def _on_direction_released(self, direction: Direction) -> None:
        """Handle direction button release."""
        self.direction_released.emit(direction)

    def _on_stop_pressed(self) -> None:
        """Handle STOP button press."""
        self.stop_pressed.emit()

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable all buttons."""
        for button in self.buttons.values():
            button.setEnabled(enabled)
        if self.stop_button:
            # STOP button should always be enabled for emergency stop
            self.stop_button.setEnabled(True)

    def set_direction_enabled(self, direction: Direction, enabled: bool) -> None:
        """Enable or disable a specific direction button."""
        if direction in self.buttons:
            self.buttons[direction].setEnabled(enabled)

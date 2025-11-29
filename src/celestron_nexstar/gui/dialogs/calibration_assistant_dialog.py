"""
Calibration Assistant Dialog

Step-by-step wizard for telescope backlash calibration with visual guides.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QProgressBar,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


if TYPE_CHECKING:
    from celestron_nexstar import NexStarTelescope

logger = logging.getLogger(__name__)


class CalibrationAssistantDialog(QDialog):
    """Step-by-step calibration wizard dialog."""

    def __init__(self, parent: QWidget | None = None, telescope: NexStarTelescope | None = None) -> None:
        """Initialize the calibration assistant dialog."""
        super().__init__(parent)
        self.setWindowTitle("Calibration Assistant")
        self.setMinimumWidth(700)
        self.setMinimumHeight(500)

        self.telescope = telescope
        self.current_step = 0
        self.selected_axis: str | None = None  # "azimuth", "altitude", "both"

        # Main layout
        main_layout = QVBoxLayout(self)

        # Step indicator
        self.step_label = QLabel("Step 1 of 4: Select Axis")
        step_font = QFont()
        step_font.setBold(True)
        step_font.setPointSize(12)
        self.step_label.setFont(step_font)
        main_layout.addWidget(self.step_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 4)
        self.progress_bar.setValue(1)
        main_layout.addWidget(self.progress_bar)

        # Content area (scrollable)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        scroll_area.setWidget(self.content_widget)
        main_layout.addWidget(scroll_area, stretch=1)

        # Button box
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Next")
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).clicked.connect(self._on_next_clicked)
        self.button_box.rejected.connect(self.reject)
        main_layout.addWidget(self.button_box)

        # Initialize first step
        self._show_axis_selection()

    def _clear_content(self) -> None:
        """Clear the content area."""
        while self.content_layout.count():
            child = self.content_layout.takeAt(0)
            widget = child.widget()
            if widget:
                widget.deleteLater()

    def _show_axis_selection(self) -> None:
        """Show axis selection step."""
        self.current_step = 1
        self._clear_content()
        self.step_label.setText("Step 1 of 4: Select Axis to Calibrate")
        self.progress_bar.setValue(1)

        # Info
        info_label = QLabel(
            "<h3>Backlash Calibration</h3>"
            "<p>Backlash is the play or slack in the mount's gears that can cause "
            "inaccurate pointing and tracking. This wizard will guide you through "
            "calibrating the anti-backlash settings.</p>"
            "<p>Select which axis you want to calibrate:</p>"
        )
        info_label.setWordWrap(True)
        self.content_layout.addWidget(info_label)

        # Axis selection
        self.azimuth_radio = QRadioButton("Azimuth (East/West)")
        self.azimuth_radio.setChecked(True)
        self.azimuth_radio.toggled.connect(lambda checked: self._select_axis("azimuth" if checked else None))
        self.content_layout.addWidget(self.azimuth_radio)

        self.altitude_radio = QRadioButton("Altitude (Up/Down)")
        self.altitude_radio.toggled.connect(lambda checked: self._select_axis("altitude" if checked else None))
        self.content_layout.addWidget(self.altitude_radio)

        self.both_radio = QRadioButton("Both Axes")
        self.both_radio.toggled.connect(lambda checked: self._select_axis("both" if checked else None))
        self.content_layout.addWidget(self.both_radio)

        self.content_layout.addStretch()

        # Default selection
        self.selected_axis = "azimuth"

    def _select_axis(self, axis: str | None) -> None:
        """Select calibration axis."""
        if axis:
            self.selected_axis = axis

    def _on_next_clicked(self) -> None:
        """Handle Next button click."""
        if self.current_step == 1:
            # Axis selected, show instructions
            self._show_instructions()
        elif self.current_step == 2:
            # Instructions shown, show setup step
            self._show_setup()
        elif self.current_step == 3:
            # Setup complete, show testing step
            self._show_testing()
        elif self.current_step == 4:
            # Testing complete, show completion
            self._show_completion()

    def _show_instructions(self) -> None:
        """Show calibration instructions."""
        self.current_step = 2
        self._clear_content()
        self.step_label.setText("Step 2 of 4: Instructions")
        self.progress_bar.setValue(2)

        axis_name = (
            "Azimuth"
            if self.selected_axis == "azimuth"
            else "Altitude"
            if self.selected_axis == "altitude"
            else "Both Axes"
        )
        direction = (
            "eastward"
            if self.selected_axis == "azimuth"
            else "upward"
            if self.selected_axis == "altitude"
            else "eastward/upward"
        )
        opposite = (
            "west/down" if self.selected_axis == "both" else ("west" if self.selected_axis == "azimuth" else "down")
        )

        instructions_text = (
            f"<h3>Calibrating {axis_name}</h3>"
            "<h4>Procedure:</h4>"
            "<ol>"
            "<li><b>Set initial anti-backlash value to 99</b> in the hand control:<br>"
            "   Menu > Scope Setup > Anti-Backlash > [Axis] Positive/Negative</li>"
            "<li><b>Slew the mount {direction}</b> at rate 3 or higher for at least 10 arc-minutes</li>"
            "<li><b>Release the button</b> and observe the field movement:<br>"
            "   • If field jumps {opposite}: Value too high (overshoot)<br>"
            "   • If field drifts {direction}: Value too low (not enough correction)<br>"
            "   • If field stays steady: Value is correct!</li>"
            "<li><b>Adjust the value</b> and repeat until no overshoot occurs</li>"
            "<li><b>Set the opposite direction</b> (Negative) to the same value</li>"
            "</ol>"
            "<p><b>Note:</b> You must adjust these settings in the hand control menu. "
            "This assistant provides guidance only.</p>"
        ).format(direction=direction, opposite=opposite)

        instructions_label = QLabel(instructions_text)
        instructions_label.setWordWrap(True)
        self.content_layout.addWidget(instructions_label)

        self.content_layout.addStretch()

    def _show_setup(self) -> None:
        """Show setup step."""
        self.current_step = 3
        self._clear_content()
        self.step_label.setText("Step 3 of 4: Setup")
        self.progress_bar.setValue(3)

        axis_name = (
            "Azimuth"
            if self.selected_axis == "azimuth"
            else "Altitude"
            if self.selected_axis == "altitude"
            else "Both Axes"
        )

        setup_text = (
            f"<h3>Setup for {axis_name} Calibration</h3>"
            "<h4>Before you begin:</h4>"
            "<ul>"
            "<li>Ensure your telescope is properly balanced</li>"
            "<li>Make sure you have a clear view of the sky</li>"
            "<li>Have the hand control ready</li>"
            "<li>Choose a bright star or object to use as a reference point</li>"
            "</ul>"
            "<h4>In the hand control:</h4>"
            "<ol>"
            "<li>Navigate to: Menu > Scope Setup > Anti-Backlash</li>"
            "<li>Set the <b>Positive</b> direction to <b>99</b></li>"
            "<li>Set the <b>Negative</b> direction to <b>99</b> (we'll adjust this later)</li>"
            "</ol>"
            "<p>Click 'Next' when you've completed the setup in the hand control.</p>"
        )

        setup_label = QLabel(setup_text)
        setup_label.setWordWrap(True)
        self.content_layout.addWidget(setup_label)

        self.content_layout.addStretch()

    def _show_testing(self) -> None:
        """Show testing step."""
        self.current_step = 4
        self._clear_content()
        self.step_label.setText("Step 4 of 4: Testing and Adjustment")
        self.progress_bar.setValue(4)

        axis_name = (
            "Azimuth"
            if self.selected_axis == "azimuth"
            else "Altitude"
            if self.selected_axis == "altitude"
            else "Both Axes"
        )
        direction = (
            "eastward"
            if self.selected_axis == "azimuth"
            else "upward"
            if self.selected_axis == "altitude"
            else "eastward/upward"
        )
        opposite = (
            "west/down" if self.selected_axis == "both" else ("west" if self.selected_axis == "azimuth" else "down")
        )

        testing_text = (
            f"<h3>Testing {axis_name} Anti-Backlash</h3>"
            "<h4>Testing Procedure:</h4>"
            "<ol>"
            "<li>Center a bright star in your eyepiece</li>"
            f"<li>Use the hand control to slew <b>{direction}</b> at rate 3 or higher</li>"
            "<li>Slew for at least 10 arc-minutes (watch the star move across the field)</li>"
            "<li><b>Release the button</b> and immediately observe what happens:</li>"
            "</ol>"
            "<h4>What to look for:</h4>"
            "<ul>"
            f"<li><b style='color: red;'>Field jumps {opposite}:</b> Value too high (overshoot) - reduce the value</li>"
            f"<li><b style='color: orange;'>Field drifts {direction}:</b> Value too low - increase the value</li>"
            "<li><b style='color: green;'>Field stays steady:</b> Value is correct! ✓</li>"
            "</ul>"
            "<h4>Adjustment:</h4>"
            "<ul>"
            "<li>If overshoot: Reduce the Positive value by 5-10 and test again</li>"
            "<li>If drift: Increase the Positive value by 5-10 and test again</li>"
            "<li>Repeat until the field stays steady when you release the button</li>"
            "<li>Once Positive is correct, set Negative to the same value</li>"
            "</ul>"
            "<p><b>Tip:</b> Use the highest magnification eyepiece you have for the most accurate results.</p>"
        )

        testing_label = QLabel(testing_text)
        testing_label.setWordWrap(True)
        self.content_layout.addWidget(testing_label)

        self.content_layout.addStretch()

        # Update button
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Finish")

    def _show_completion(self) -> None:
        """Show completion step."""
        completion_text = (
            "<h2>Calibration Complete!</h2>"
            "<p>You've completed the backlash calibration procedure.</p>"
            "<h4>Next Steps:</h4>"
            "<ul>"
            "<li>Test GoTo accuracy by performing a goto to a known object</li>"
            "<li>Monitor tracking accuracy over time</li>"
            "<li>Re-calibrate if you add or remove accessories (changes balance)</li>"
            "<li>Re-calibrate if you notice tracking or pointing issues</li>"
            "</ul>"
            "<h4>Tips:</h4>"
            "<ul>"
            "<li>Optimal values are typically around 50 for Alt-Az mounts</li>"
            "<li>Values may need adjustment if mount balance changes</li>"
            "<li>If you can't find a perfect value, choose one that slightly overshoots rather than drifts</li>"
            "</ul>"
        )

        completion_label = QLabel(completion_text)
        completion_label.setWordWrap(True)
        self._clear_content()
        self.content_layout.addWidget(completion_label)

        self.content_layout.addStretch()

        # Update button
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Close")
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).clicked.disconnect()
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).clicked.connect(self.accept)

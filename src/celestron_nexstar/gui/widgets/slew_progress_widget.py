"""
Slew Progress Widget

Displays progress bar with velocity and ETA during telescope goto operations.
"""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget

from celestron_nexstar.api.core.utils import angular_separation


class SlewProgressWidget(QWidget):
    """
    Progress indicator for telescope goto operations.

    Displays:
    - Progress bar (0-100%)
    - Current velocity (degrees/second)
    - Estimated time to arrival (seconds)
    - Target object information

    Auto-hides when not active.
    """

    # Update interval in milliseconds
    UPDATE_INTERVAL_MS = 200

    # Number of samples for velocity averaging (smooth out jitter)
    VELOCITY_SAMPLES = 5

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the slew progress widget."""
        super().__init__(parent)

        # Progress state
        self._target_ra: float | None = None  # Target RA in hours
        self._target_dec: float | None = None  # Target Dec in degrees
        self._target_name: str | None = None  # Target object name
        self._initial_separation: float | None = None  # Initial distance to target (degrees)
        self._start_time: datetime | None = None  # When goto started
        self._is_estimating: bool = False  # True during first few seconds (collecting data)

        # Velocity calculation (for smoothing)
        self._position_history: deque[tuple[datetime, float, float]] = deque(
            maxlen=self.VELOCITY_SAMPLES
        )  # (timestamp, ra, dec)

        # UI elements
        self.progress_bar: QProgressBar
        self.info_label: QLabel

        # Update timer
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._on_update_timeout)
        self.update_timer.setInterval(self.UPDATE_INTERVAL_MS)

        self._setup_ui()
        self._apply_styling()

        # Start hidden
        self.hide()

    def _setup_ui(self) -> None:
        """Set up the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(5)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        layout.addWidget(self.progress_bar)

        # Info label (velocity, ETA, target)
        self.info_label = QLabel("Initializing...")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        self.setLayout(layout)

    def _apply_styling(self, is_dark: bool = False) -> None:
        """
        Apply custom styling.

        Args:
            is_dark: Whether we're in dark mode
        """
        # Theme-aware colors
        border_color = "#4A90E2" if not is_dark else "#3A7BC2"
        chunk_color = "#27AE60" if not is_dark else "#229954"

        self.setStyleSheet(
            f"""
            QProgressBar {{
                border: 2px solid {border_color};
                border-radius: 5px;
                text-align: center;
                height: 25px;
            }}
            QProgressBar::chunk {{
                background-color: {chunk_color};
                border-radius: 3px;
            }}
            QLabel {{
                color: palette(text);
                font-size: 11px;
            }}
        """
        )

    def start_goto(
        self,
        target_ra: float,
        target_dec: float,
        target_name: str | None = None,
    ) -> None:
        """
        Start tracking goto progress.

        Args:
            target_ra: Target right ascension in hours
            target_dec: Target declination in degrees
            target_name: Optional target object name
        """
        self._target_ra = target_ra
        self._target_dec = target_dec
        self._target_name = target_name or "Target"
        self._initial_separation = None  # Will be set on first update
        self._start_time = datetime.now(UTC)
        self._is_estimating = True  # First few seconds are for estimation
        self._position_history.clear()

        # Reset UI
        self.progress_bar.setValue(0)
        self.info_label.setText("Starting goto...")

        # Show widget and start updates
        self.show()
        self.update_timer.start()

    def update_progress(self, current_ra: float, current_dec: float) -> None:
        """
        Update progress based on current telescope position.

        Args:
            current_ra: Current right ascension in hours
            current_dec: Current declination in degrees
        """
        if self._target_ra is None or self._target_dec is None:
            return

        # Calculate current separation to target
        current_separation = angular_separation(current_ra, current_dec, self._target_ra, self._target_dec)

        # Set initial separation on first update
        if self._initial_separation is None:
            self._initial_separation = current_separation
            if self._initial_separation < 0.01:  # Very close, already at target
                self._complete_goto()
                return

        # Record position for velocity calculation
        self._position_history.append((datetime.now(UTC), current_ra, current_dec))

        # Calculate progress (0-100%)
        if self._initial_separation and self._initial_separation > 0:
            progress_fraction = 1.0 - (current_separation / self._initial_separation)
            progress_pct = max(0, min(100, int(progress_fraction * 100)))
        else:
            progress_pct = 0

        # Update progress bar
        self.progress_bar.setValue(progress_pct)

        # Check if we've arrived (within 0.1 degrees)
        if current_separation < 0.1:
            self._complete_goto()
            return

        # Calculate velocity and ETA (after collecting enough samples)
        if len(self._position_history) >= 2:
            velocity = self._calculate_velocity()
            eta = self._calculate_eta(current_separation, velocity)

            # Exit estimating mode after 2 seconds
            if self._is_estimating and (datetime.now(UTC) - self._start_time).total_seconds() > 2:
                self._is_estimating = False

            # Update info label
            if self._is_estimating:
                self.info_label.setText(f"Estimating... Target: {self._target_name}")
            else:
                vel_str = f"{velocity:.2f}°/s" if velocity > 0 else "N/A"
                eta_str = f"{eta:.0f}s" if eta > 0 else "N/A"
                self.info_label.setText(f"Velocity: {vel_str}  |  ETA: {eta_str}  |  Target: {self._target_name}")

    def _calculate_velocity(self) -> float:
        """
        Calculate current slew velocity in degrees/second.

        Uses rolling average over recent position samples to smooth out jitter.

        Returns:
            Velocity in degrees/second
        """
        if len(self._position_history) < 2:
            return 0.0

        # Get oldest and newest samples
        oldest = self._position_history[0]
        newest = self._position_history[-1]

        # Calculate distance traveled
        distance = angular_separation(oldest[1], oldest[2], newest[1], newest[2])

        # Calculate time elapsed
        time_delta = (newest[0] - oldest[0]).total_seconds()

        if time_delta > 0:
            return distance / time_delta
        return 0.0

    def _calculate_eta(self, remaining_distance: float, velocity: float) -> float:
        """
        Calculate estimated time to arrival.

        Args:
            remaining_distance: Distance to target in degrees
            velocity: Current velocity in degrees/second

        Returns:
            ETA in seconds
        """
        if velocity > 0:
            return remaining_distance / velocity
        return 0.0

    def _complete_goto(self) -> None:
        """Mark goto as completed."""
        self.progress_bar.setValue(100)
        self.info_label.setText(f"Arrived at {self._target_name}")

        # Hide after 2 seconds
        QTimer.singleShot(2000, self.stop)

    def _on_update_timeout(self) -> None:
        """Handle update timer timeout (used for animations/checks)."""
        # Currently just a placeholder - actual updates come from external calls to update_progress()
        pass

    def stop(self) -> None:
        """Stop tracking and hide widget."""
        self.update_timer.stop()
        self._target_ra = None
        self._target_dec = None
        self._target_name = None
        self._initial_separation = None
        self._start_time = None
        self._is_estimating = False
        self._position_history.clear()
        self.hide()

    def is_active(self) -> bool:
        """
        Check if goto is currently being tracked.

        Returns:
            True if tracking an active goto
        """
        return self._target_ra is not None and self.isVisible()

    def apply_theme(self, theme: object) -> None:
        """
        Apply theme to the progress widget.

        Adapts colors based on dark/light theme.
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

        # Reapply styling with theme colors
        self._apply_styling(is_dark)

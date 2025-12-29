"""
Command Queue Widget

Displays pending telescope commands with visual status indicators.
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class CommandState(Enum):
    """Command execution states."""

    QUEUED = "queued"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


class CommandBadge(QLabel):
    """
    Individual command badge widget.

    Shows command name/ID with color-coded background based on state.
    """

    def __init__(self, command: str, parent: QWidget | None = None, is_dark: bool = False) -> None:
        """
        Initialize command badge.

        Args:
            command: Command string to display
            parent: Parent widget
            is_dark: Whether we're in dark mode
        """
        super().__init__(parent)
        self.command = command
        self.state = CommandState.QUEUED
        self.is_dark = is_dark

        # Format command for display (truncate if long)
        display_text = command if len(command) <= 10 else command[:7] + "..."
        self.setText(f"[{display_text}]")

        self.setFixedHeight(25)
        self.setStyleSheet(self._get_style(CommandState.QUEUED))

    def set_state(self, state: CommandState) -> None:
        """
        Update badge state and styling.

        Args:
            state: New command state
        """
        self.state = state
        self.setStyleSheet(self._get_style(state))

        # Update text for executing state (add spinner)
        if state == CommandState.EXECUTING:
            self.setText(f"[{self.command}] ⟳")
        elif state == CommandState.COMPLETED:
            self.setText(f"[{self.command}] ✓")
        elif state == CommandState.FAILED:
            self.setText(f"[{self.command}] ✗")
        else:
            self.setText(f"[{self.command}]")

    def _get_style(self, state: CommandState) -> str:
        """
        Get stylesheet for given state.

        Args:
            state: Command state

        Returns:
            Qt stylesheet string
        """
        # Theme-aware colors
        queued_bg = "#95A5A6" if not self.is_dark else "#7F8C8D"
        executing_bg = "#F39C12" if not self.is_dark else "#D68910"
        completed_bg = "#27AE60" if not self.is_dark else "#229954"
        failed_bg = "#E74C3C" if not self.is_dark else "#C0392B"

        styles = {
            CommandState.QUEUED: f"""
                QLabel {{
                    background-color: {queued_bg};
                    color: white;
                    padding: 4px 8px;
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: bold;
                }}
            """,
            CommandState.EXECUTING: f"""
                QLabel {{
                    background-color: {executing_bg};
                    color: white;
                    padding: 4px 8px;
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: bold;
                }}
            """,
            CommandState.COMPLETED: f"""
                QLabel {{
                    background-color: {completed_bg};
                    color: white;
                    padding: 4px 8px;
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: bold;
                }}
            """,
            CommandState.FAILED: f"""
                QLabel {{
                    background-color: {failed_bg};
                    color: white;
                    padding: 4px 8px;
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: bold;
                }}
            """,
        }
        return styles.get(state, styles[CommandState.QUEUED])


class CommandQueueWidget(QWidget):
    """
    Displays pending telescope commands in a horizontal queue.

    Commands are shown as color-coded badges:
    - Gray: Queued (waiting)
    - Yellow/Orange: Executing (in progress)
    - Green: Completed (success)
    - Red: Failed (error)

    Completed/failed badges auto-remove after 2 seconds.
    """

    # Auto-remove delay for completed/failed commands (milliseconds)
    AUTO_REMOVE_DELAY_MS = 2000

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the command queue widget."""
        super().__init__(parent)

        # Track command badges
        self._badges: dict[str, CommandBadge] = {}  # command -> badge

        # Track removal timers
        self._removal_timers: dict[str, QTimer] = {}  # command -> timer

        # Track theme state
        self._is_dark = False

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI layout."""
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.layout.setSpacing(5)

        # Add label
        label = QLabel("Command Queue:")
        label.setStyleSheet("font-weight: bold; font-size: 11px;")
        self.layout.addWidget(label)

        # Stretch to push badges to the left
        self.layout.addStretch()

        self.setLayout(self.layout)

        # Start with minimal height
        self.setMaximumHeight(35)

    def add_command(self, command: str) -> None:
        """
        Add a command to the queue.

        Args:
            command: Command string (e.g., "E", "J", "GoTo")
        """
        # Cancel any pending removal timer
        if command in self._removal_timers:
            self._removal_timers[command].stop()
            del self._removal_timers[command]

        # Create or update badge
        if command not in self._badges:
            badge = CommandBadge(command, self, self._is_dark)
            self._badges[command] = badge

            # Insert before stretch (second-to-last position)
            insert_index = self.layout.count() - 1
            self.layout.insertWidget(insert_index, badge)
        else:
            # Reset existing badge to queued state
            self._badges[command].set_state(CommandState.QUEUED)

    def set_executing(self, command: str) -> None:
        """
        Mark command as currently executing.

        Args:
            command: Command string
        """
        if command in self._badges:
            self._badges[command].set_state(CommandState.EXECUTING)

    def set_completed(self, command: str) -> None:
        """
        Mark command as completed successfully.

        Auto-removes after AUTO_REMOVE_DELAY_MS milliseconds.

        Args:
            command: Command string
        """
        if command in self._badges:
            self._badges[command].set_state(CommandState.COMPLETED)
            self._schedule_removal(command)

    def set_failed(self, command: str, persist: bool = False) -> None:
        """
        Mark command as failed.

        Args:
            command: Command string
            persist: If True, failed badge persists until cleared manually
        """
        if command in self._badges:
            self._badges[command].set_state(CommandState.FAILED)

            if not persist:
                self._schedule_removal(command)

    def _schedule_removal(self, command: str) -> None:
        """
        Schedule auto-removal of a command badge.

        Args:
            command: Command string
        """
        # Cancel any existing timer
        if command in self._removal_timers:
            self._removal_timers[command].stop()

        # Create new timer
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self.remove_command(command))
        timer.start(self.AUTO_REMOVE_DELAY_MS)

        self._removal_timers[command] = timer

    def remove_command(self, command: str) -> None:
        """
        Remove a command from the queue.

        Args:
            command: Command string
        """
        if command in self._badges:
            badge = self._badges[command]
            self.layout.removeWidget(badge)
            badge.deleteLater()
            del self._badges[command]

        if command in self._removal_timers:
            self._removal_timers[command].stop()
            del self._removal_timers[command]

    def clear_all(self) -> None:
        """Clear all commands from the queue."""
        # Stop all timers
        for timer in self._removal_timers.values():
            timer.stop()
        self._removal_timers.clear()

        # Remove all badges
        for badge in self._badges.values():
            self.layout.removeWidget(badge)
            badge.deleteLater()
        self._badges.clear()

    def get_queue_size(self) -> int:
        """
        Get number of commands in queue.

        Returns:
            Number of command badges currently displayed
        """
        return len(self._badges)

    def apply_theme(self, theme: object) -> None:
        """
        Apply theme to the command queue widget.

        Updates all existing badges with new theme colors.
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

        # Update theme state
        self._is_dark = is_dark

        # Update all existing badges
        for badge in self._badges.values():
            badge.is_dark = is_dark
            # Refresh badge style by setting its current state
            badge.set_state(badge.state)

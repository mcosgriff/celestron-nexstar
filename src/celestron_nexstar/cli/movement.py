"""
Movement Controller for Interactive Telescope Control

This module provides the MovementController class for real-time telescope
movement control using arrow keys with features including:
- Arrow key directional control (up/down/left/right)
- Variable slew rate adjustment (0-9)
- Visual feedback for movement state
- Emergency stop functionality
"""


class MovementController:
    """Controller for interactive telescope movement using arrow keys."""

    def __init__(self, get_port_func: callable) -> None:
        """Initialize the movement controller.

        Args:
            get_port_func: Function to get the telescope port (returns str | None)
        """
        self.get_port = get_port_func
        self.slew_rate = 5  # Default rate 0-9
        self.active_direction: str | None = None  # Current movement direction
        self.moving = False

    def start_move(self, direction: str) -> None:
        """Start moving in a direction.

        Args:
            direction: Direction to move ('up', 'down', 'left', 'right')
        """
        if self.moving and self.active_direction == direction:
            return  # Already moving in this direction

        port = self.get_port()
        if not port:
            return

        try:
            from celestron_nexstar import NexStarTelescope

            with NexStarTelescope(str(port)) as telescope:
                telescope.move_fixed(direction, self.slew_rate)
                self.moving = True
                self.active_direction = direction
        except Exception:
            pass  # Silently fail to not disrupt UI

    def stop_move(self) -> None:
        """Stop all movement."""
        if not self.moving:
            return

        port = self.get_port()
        if not port:
            return

        try:
            from celestron_nexstar import NexStarTelescope

            with NexStarTelescope(str(port)) as telescope:
                telescope.stop_motion("both")
                self.moving = False
                self.active_direction = None
        except Exception:
            pass  # Silently fail

    def increase_rate(self) -> None:
        """Increase slew rate (max 9)."""
        if self.slew_rate < 9:
            self.slew_rate += 1

    def decrease_rate(self) -> None:
        """Decrease slew rate (min 0)."""
        if self.slew_rate > 0:
            self.slew_rate -= 1

    def get_rate(self) -> int:
        """Get current slew rate.

        Returns:
            Current slew rate (0-9)
        """
        return self.slew_rate

    def is_moving(self) -> bool:
        """Check if telescope is currently moving.

        Returns:
            True if moving, False otherwise
        """
        return self.moving

    def get_direction(self) -> str | None:
        """Get current movement direction.

        Returns:
            Current direction or None if not moving
        """
        return self.active_direction

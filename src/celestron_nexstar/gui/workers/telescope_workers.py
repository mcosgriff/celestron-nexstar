"""
Telescope Worker Threads

QThread workers for async telescope operations to prevent UI blocking.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QThread, Signal


if TYPE_CHECKING:
    from celestron_nexstar import NexStarTelescope

logger = logging.getLogger(__name__)


class GetPositionRADecThread(QThread):
    """Worker thread to get telescope RA/Dec position."""

    position_ready = Signal(object)  # type: ignore[type-arg,misc]  # Emits EquatorialCoordinates
    error_occurred = Signal(str)  # type: ignore[type-arg,misc]  # Emits error message

    def __init__(self, telescope: NexStarTelescope) -> None:
        """Initialize the position thread."""
        super().__init__()
        self.telescope = telescope

    def run(self) -> None:
        """Get telescope position in background thread."""
        try:
            coords = self.telescope.run_coroutine_threadsafe(self.telescope.get_position_ra_dec())
            self.position_ready.emit(coords)
        except Exception as e:
            logger.error(f"Error getting telescope position: {e}", exc_info=True)
            self.error_occurred.emit(str(e))


class GetPositionAltAzThread(QThread):
    """Worker thread to get telescope Alt/Az position."""

    position_ready = Signal(object)  # type: ignore[type-arg,misc]  # Emits HorizontalCoordinates
    error_occurred = Signal(str)  # type: ignore[type-arg,misc]  # Emits error message

    def __init__(self, telescope: NexStarTelescope) -> None:
        """Initialize the position thread."""
        super().__init__()
        self.telescope = telescope

    def run(self) -> None:
        """Get telescope position in background thread."""
        try:
            position = self.telescope.run_coroutine_threadsafe(self.telescope.get_position_alt_az())
            self.position_ready.emit(position)
        except Exception as e:
            logger.error(f"Error getting telescope Alt/Az position: {e}", exc_info=True)
            self.error_occurred.emit(str(e))


class GetLocationThread(QThread):
    """Worker thread to get telescope GPS location."""

    location_ready = Signal(object)  # type: ignore[type-arg,misc]  # Emits GeographicLocation
    error_occurred = Signal(str)  # type: ignore[type-arg,misc]  # Emits error message

    def __init__(self, telescope: NexStarTelescope) -> None:
        """Initialize the location thread."""
        super().__init__()
        self.telescope = telescope

    def run(self) -> None:
        """Get telescope location in background thread."""
        try:
            location = self.telescope.run_coroutine_threadsafe(self.telescope.get_location())
            self.location_ready.emit(location)
        except Exception as e:
            logger.error(f"Error getting telescope location: {e}", exc_info=True)
            self.error_occurred.emit(str(e))


class SyncRADecThread(QThread):
    """Worker thread to sync telescope to RA/Dec coordinates."""

    sync_complete = Signal(bool)  # type: ignore[type-arg,misc]  # Emits success status
    error_occurred = Signal(str)  # type: ignore[type-arg,misc]  # Emits error message

    def __init__(self, telescope: NexStarTelescope, ra_hours: float, dec_degrees: float) -> None:
        """Initialize the sync thread."""
        super().__init__()
        self.telescope = telescope
        self.ra_hours = ra_hours
        self.dec_degrees = dec_degrees

    def run(self) -> None:
        """Sync telescope in background thread."""
        try:
            success = self.telescope.run_coroutine_threadsafe(
                self.telescope.sync_ra_dec(self.ra_hours, self.dec_degrees)
            )
            self.sync_complete.emit(success)
        except Exception as e:
            logger.error(f"Error syncing telescope: {e}", exc_info=True)
            self.error_occurred.emit(str(e))
            self.sync_complete.emit(False)


class GotoRADecThread(QThread):
    """Worker thread to goto RA/Dec coordinates."""

    goto_complete = Signal(bool)  # type: ignore[type-arg,misc]  # Emits success status
    error_occurred = Signal(str)  # type: ignore[type-arg,misc]  # Emits error message

    def __init__(self, telescope: NexStarTelescope, ra_hours: float, dec_degrees: float) -> None:
        """Initialize the goto thread."""
        super().__init__()
        self.telescope = telescope
        self.ra_hours = ra_hours
        self.dec_degrees = dec_degrees

    def run(self) -> None:
        """Goto coordinates in background thread."""
        try:
            success = self.telescope.run_coroutine_threadsafe(
                self.telescope.goto_ra_dec(self.ra_hours, self.dec_degrees)
            )
            self.goto_complete.emit(success)
        except Exception as e:
            logger.error(f"Error going to coordinates: {e}", exc_info=True)
            self.error_occurred.emit(str(e))
            self.goto_complete.emit(False)


class DisconnectThread(QThread):
    """Worker thread to disconnect telescope."""

    disconnect_complete = Signal()  # type: ignore[type-arg,misc]
    error_occurred = Signal(str)  # type: ignore[type-arg,misc]  # Emits error message

    def __init__(self, telescope: NexStarTelescope) -> None:
        """Initialize the disconnect thread."""
        super().__init__()
        self.telescope = telescope

    def run(self) -> None:
        """Disconnect telescope in background thread."""
        try:
            # First disconnect from the telescope
            self.telescope.run_coroutine_threadsafe(self.telescope.disconnect())
            # Then shutdown the event loop (must be done from outside the loop)
            self.telescope.shutdown()
            self.disconnect_complete.emit()
        except Exception as e:
            logger.error(f"Error disconnecting telescope: {e}", exc_info=True)
            self.error_occurred.emit(str(e))


class ConnectTelescopeThread(QThread):
    """Worker thread to connect to telescope."""

    connection_ready = Signal(bool)  # type: ignore[type-arg,misc]  # Emits success status
    error_occurred = Signal(str)  # type: ignore[type-arg,misc]  # Emits error message

    def __init__(self, telescope: NexStarTelescope) -> None:
        """Initialize the connect thread."""
        super().__init__()
        self.telescope = telescope

    def run(self) -> None:
        """Connect to telescope in background thread."""
        try:
            success = self.telescope.run_coroutine_threadsafe(self.telescope.connect())
            self.connection_ready.emit(success)
        except Exception as e:
            logger.error(f"Error connecting to telescope: {e}", exc_info=True)
            self.error_occurred.emit(str(e))
            self.connection_ready.emit(False)


class GetTrackingModeThread(QThread):
    """Worker thread to get current tracking mode."""

    mode_ready = Signal(object)  # type: ignore[type-arg,misc]  # Emits TrackingMode
    error_occurred = Signal(str)  # type: ignore[type-arg,misc]  # Emits error message

    def __init__(self, telescope: NexStarTelescope) -> None:
        """Initialize the tracking mode thread."""
        super().__init__()
        self.telescope = telescope

    def run(self) -> None:
        """Get tracking mode in background thread."""
        try:
            mode = self.telescope.run_coroutine_threadsafe(self.telescope.get_tracking_mode())
            self.mode_ready.emit(mode)
        except Exception as e:
            logger.error(f"Error getting tracking mode: {e}", exc_info=True)
            self.error_occurred.emit(str(e))


class SetTrackingModeThread(QThread):
    """Worker thread to set tracking mode."""

    mode_set = Signal(bool)  # type: ignore[type-arg,misc]  # Emits success status
    error_occurred = Signal(str)  # type: ignore[type-arg,misc]  # Emits error message

    def __init__(self, telescope: NexStarTelescope, mode: object) -> None:
        """Initialize the set tracking mode thread."""
        super().__init__()
        self.telescope = telescope
        self.mode = mode

    def run(self) -> None:
        """Set tracking mode in background thread."""
        try:
            success = self.telescope.run_coroutine_threadsafe(self.telescope.set_tracking_mode(self.mode))
            self.mode_set.emit(success)
        except Exception as e:
            logger.error(f"Error setting tracking mode: {e}", exc_info=True)
            self.error_occurred.emit(str(e))
            self.mode_set.emit(False)


class MoveFixedThread(QThread):
    """Worker thread for continuous directional movement."""

    move_started = Signal(bool)  # type: ignore[type-arg,misc]  # Emits success status
    error_occurred = Signal(str)  # type: ignore[type-arg,misc]  # Emits error message

    def __init__(self, telescope: NexStarTelescope, direction: object, rate: int) -> None:
        """Initialize the move fixed thread."""
        super().__init__()
        self.telescope = telescope
        self.direction = direction
        self.rate = rate

    def run(self) -> None:
        """Start continuous movement in background thread."""
        try:
            success = self.telescope.run_coroutine_threadsafe(
                self.telescope.move_fixed(self.direction, self.rate)
            )
            self.move_started.emit(success)
        except Exception as e:
            logger.error(f"Error moving telescope: {e}", exc_info=True)
            self.error_occurred.emit(str(e))
            self.move_started.emit(False)


class MoveStepThread(QThread):
    """Worker thread for single step movement."""

    step_complete = Signal(bool)  # type: ignore[type-arg,misc]  # Emits success status
    error_occurred = Signal(str)  # type: ignore[type-arg,misc]  # Emits error message

    def __init__(self, telescope: NexStarTelescope, direction: object, rate: int) -> None:
        """Initialize the move step thread."""
        super().__init__()
        self.telescope = telescope
        self.direction = direction
        self.rate = rate

    def run(self) -> None:
        """Execute step movement in background thread."""
        try:
            success = self.telescope.run_coroutine_threadsafe(
                self.telescope.move_step(self.direction, self.rate)
            )
            self.step_complete.emit(success)
        except Exception as e:
            logger.error(f"Error stepping telescope: {e}", exc_info=True)
            self.error_occurred.emit(str(e))
            self.step_complete.emit(False)


class StopMotionThread(QThread):
    """Worker thread to stop telescope motion."""

    stopped = Signal(bool)  # type: ignore[type-arg,misc]  # Emits success status
    error_occurred = Signal(str)  # type: ignore[type-arg,misc]  # Emits error message

    def __init__(self, telescope: NexStarTelescope, axis: str = "both") -> None:
        """Initialize the stop motion thread."""
        super().__init__()
        self.telescope = telescope
        self.axis = axis

    def run(self) -> None:
        """Stop telescope motion in background thread."""
        try:
            success = self.telescope.run_coroutine_threadsafe(self.telescope.stop_motion(self.axis))
            self.stopped.emit(success)
        except Exception as e:
            logger.error(f"Error stopping motion: {e}", exc_info=True)
            self.error_occurred.emit(str(e))
            self.stopped.emit(False)


class IsSlewingThread(QThread):
    """Worker thread to check if telescope is slewing."""

    slewing_status = Signal(bool)  # type: ignore[type-arg,misc]  # Emits slewing status
    error_occurred = Signal(str)  # type: ignore[type-arg,misc]  # Emits error message

    def __init__(self, telescope: NexStarTelescope) -> None:
        """Initialize the is slewing thread."""
        super().__init__()
        self.telescope = telescope

    def run(self) -> None:
        """Check slewing status in background thread."""
        try:
            is_slewing = self.telescope.run_coroutine_threadsafe(self.telescope.is_slewing())
            self.slewing_status.emit(is_slewing)
        except Exception as e:
            logger.error(f"Error checking slew status: {e}", exc_info=True)
            self.error_occurred.emit(str(e))
            self.slewing_status.emit(False)

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
            coords = asyncio.run(self.telescope.get_position_ra_dec())
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
            position = asyncio.run(self.telescope.get_position_alt_az())
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
            location = asyncio.run(self.telescope.get_location())
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
            success = asyncio.run(self.telescope.sync_ra_dec(self.ra_hours, self.dec_degrees))
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
            success = asyncio.run(self.telescope.goto_ra_dec(self.ra_hours, self.dec_degrees))
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
            asyncio.run(self.telescope.disconnect())
            self.disconnect_complete.emit()
        except Exception as e:
            logger.error(f"Error disconnecting telescope: {e}", exc_info=True)
            self.error_occurred.emit(str(e))

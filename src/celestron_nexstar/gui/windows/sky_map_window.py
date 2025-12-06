"""
Sky Map Window

Window for displaying the interactive sky map.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget

from celestron_nexstar.gui.widgets.sky_map_widget import SkyMapWidget


if TYPE_CHECKING:
    from celestron_nexstar import NexStarTelescope


class SkyMapWindow(QMainWindow):
    """Window for displaying the interactive sky map."""

    def __init__(
        self,
        parent: QWidget | None = None,
        telescope: NexStarTelescope | None = None,
    ) -> None:
        """Initialize the sky map window."""
        super().__init__(parent)
        self.setWindowTitle("Interactive Sky Map")
        self.setMinimumSize(800, 800)

        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create sky map widget
        self.sky_map = SkyMapWidget(self, telescope=telescope)
        layout.addWidget(self.sky_map)

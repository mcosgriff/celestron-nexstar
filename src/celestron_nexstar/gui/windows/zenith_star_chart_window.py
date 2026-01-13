"""
Zenith Star Chart Window

Window for displaying the full-sky zenith star chart.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget

from celestron_nexstar.gui.widgets.zenith_star_chart_widget import ZenithStarChartWidget


if TYPE_CHECKING:
    from celestron_nexstar import NexStarTelescope


class ZenithStarChartWindow(QMainWindow):
    """Window for displaying the full-sky zenith star chart."""

    def __init__(
        self,
        parent: QWidget | None = None,
        telescope: NexStarTelescope | None = None,
    ) -> None:
        """Initialize the zenith star chart window."""
        super().__init__(parent)
        self.setWindowTitle("Zenith Star Chart - Full Sky View")
        self.setMinimumSize(800, 850)

        # Create a central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create a zenith star chart widget
        self.star_chart = ZenithStarChartWidget(self, telescope=telescope)
        layout.addWidget(self.star_chart)

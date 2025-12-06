"""
GUI Windows

Subwindows for the main application.
"""

from celestron_nexstar.gui.windows.catalog_window import CatalogSearchWindow
from celestron_nexstar.gui.windows.goto_queue_window import GotoQueueWindow
from celestron_nexstar.gui.windows.optic_plot_window import OpticPlotWindow
from celestron_nexstar.gui.windows.sky_map_window import SkyMapWindow
from celestron_nexstar.gui.windows.zenith_star_chart_window import ZenithStarChartWindow


__all__ = [
    "CatalogSearchWindow",
    "GotoQueueWindow",
    "OpticPlotWindow",
    "SkyMapWindow",
    "ZenithStarChartWindow",
]

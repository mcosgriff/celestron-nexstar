"""GUI widgets for the telescope control application."""

from celestron_nexstar.gui.widgets.command_queue_widget import CommandQueueWidget
from celestron_nexstar.gui.widgets.sky_map_widget import SkyMapWidget
from celestron_nexstar.gui.widgets.slew_progress_widget import SlewProgressWidget
from celestron_nexstar.gui.widgets.slew_rate_presets_widget import SlewRatePresetsWidget
from celestron_nexstar.gui.widgets.telescope_command_log_panel import TelescopeCommandLogPanel


__all__ = [
    "CommandQueueWidget",
    "SkyMapWidget",
    "SlewProgressWidget",
    "SlewRatePresetsWidget",
    "TelescopeCommandLogPanel",
]

"""
Data management utilities for external data sources.
"""

from celestron_nexstar.api.data.starplot_config import (
    configure_starplot_cache,
    get_starplot_data_directory,
)


__all__ = ["configure_starplot_cache", "get_starplot_data_directory"]

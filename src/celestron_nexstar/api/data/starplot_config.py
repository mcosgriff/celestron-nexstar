"""
Configuration for starplot to use our standard cache directory.

This module configures starplot to store its data files in our standard cache location
(~/.cache/celestron-nexstar/starplot-data/) for offline use and consistency with other
data storage in the application.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path


logger = logging.getLogger(__name__)

__all__ = ["configure_starplot_cache", "get_starplot_data_directory"]


def get_starplot_data_directory() -> Path:
    """
    Get the directory where starplot data should be stored.

    Uses our standard cache location: ~/.cache/celestron-nexstar/starplot-data/

    Returns:
        Path to starplot data directory
    """
    cache_dir = Path.home() / ".cache" / "celestron-nexstar" / "starplot-data"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def configure_starplot_cache() -> None:
    """
    Configure starplot to use our standard cache directory for offline data storage.

    This sets the STARPLOT_DOWNLOAD_PATH environment variable to point to our cache
    directory, ensuring that starplot's downloaded data (like the full Big Sky catalog)
    is stored in a consistent location with our other cached data.

    This should be called early in the application startup, before starplot is imported.
    """
    if "STARPLOT_DOWNLOAD_PATH" not in os.environ:
        data_dir = get_starplot_data_directory()
        os.environ["STARPLOT_DOWNLOAD_PATH"] = str(data_dir)
        logger.debug(f"Configured starplot to use cache directory: {data_dir}")
    else:
        logger.debug(f"starplot download path already set to: {os.environ['STARPLOT_DOWNLOAD_PATH']}")

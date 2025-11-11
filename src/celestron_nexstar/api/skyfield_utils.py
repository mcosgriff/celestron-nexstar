"""
Skyfield Utilities

Centralized configuration for Skyfield ephemeris file location.
Provides a shared Loader instance that uses ~/.skyfield by default.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from skyfield.api import Loader


def get_skyfield_directory() -> Path:
    """
    Get the Skyfield cache directory.

    Checks SKYFIELD_DIR environment variable first, then defaults to ~/.skyfield

    Returns:
        Path to Skyfield cache directory
    """
    env_dir = os.environ.get("SKYFIELD_DIR")
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    return Path.home() / ".skyfield"


# Module-level loader instance - created lazily on first access
_loader: Loader | None = None


def get_skyfield_loader() -> Loader:
    """
    Get a shared Skyfield Loader instance configured to use ~/.skyfield.

    The loader is created once and reused for all subsequent calls.
    This ensures all ephemeris files are stored in the same location.

    Returns:
        Configured Loader instance
    """
    global _loader
    if _loader is None:
        from skyfield.api import Loader

        skyfield_dir = get_skyfield_directory()
        skyfield_dir.mkdir(parents=True, exist_ok=True)
        _loader = Loader(str(skyfield_dir.resolve()))
    return _loader


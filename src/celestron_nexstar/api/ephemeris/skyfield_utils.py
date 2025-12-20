"""
Skyfield Utilities

Centralized configuration for Skyfield ephemeris file location.
Provides a shared Loader instance that uses ~/.skyfield by default.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from skyfield.api import Loader
    from skyfield.timelib import Timescale


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
_timescale: Timescale | None = None


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


def get_skyfield_timescale() -> Timescale:
    """
    Get a shared Skyfield Timescale instance.

    Skyfield's Loader.timescale() reads bundled data (e.g., iers.npz). In long-running GUI
    sessions, repeatedly calling Loader.timescale() can contribute to excessive file handle usage.
    We create it once and reuse it.
    """
    global _timescale
    if _timescale is None:
        loader = get_skyfield_loader()
        _timescale = loader.timescale()
    return _timescale


@lru_cache(maxsize=16)
def get_skyfield_ephemeris(bsp_file: str) -> Any:
    """
    Load and cache a Skyfield ephemeris kernel (BSP file).

    Note: this delegates to Skyfield's Loader, which may download missing files to the configured
    Skyfield directory. Callers that must avoid downloads should pre-check file existence.
    """
    loader = get_skyfield_loader()
    return loader(bsp_file)

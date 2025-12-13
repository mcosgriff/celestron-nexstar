"""
User Config

Small set of user-editable application settings that aren't tied to a specific
domain (location/optics/etc). These settings are stored in:

  ~/.config/celestron-nexstar/user_config.json

The GUI settings dialog edits this file. Settings take effect on restart unless
otherwise noted.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UserConfig:
    """User-editable app configuration."""

    # Database performance toggle:
    # If True, the catalog database is copied into a shared in-memory SQLite DB.
    # Takes effect on restart (initialization of the DB singleton).
    use_memory_db: bool = False


def get_user_config_path() -> Path:
    """Return the path to the user config JSON file, ensuring its directory exists."""
    config_dir = Path.home() / ".config" / "celestron-nexstar"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "user_config.json"


def load_user_config() -> UserConfig:
    """Load user config from disk, returning defaults when missing/invalid."""
    path = get_user_config_path()
    if not path.exists():
        return UserConfig()

    try:
        with path.open("r") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return UserConfig()

        use_memory_db = bool(raw.get("use_memory_db", False))
        return UserConfig(use_memory_db=use_memory_db)
    except Exception as e:
        logger.warning(f"Failed to load user config from {path}: {e}")
        return UserConfig()


def save_user_config(config: UserConfig) -> None:
    """Persist user config to disk."""
    path = get_user_config_path()
    with path.open("w") as f:
        json.dump(asdict(config), f, indent=2)

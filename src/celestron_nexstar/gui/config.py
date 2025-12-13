"""
GUI configuration management.
"""

import json
import logging
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class WindowDecorationType(Enum):
    """Window decoration style options."""

    SERVER_SIDE = "server_side"  # Native/system window decorations
    CLIENT_SIDE = "client_side"  # Custom title bar


class GUIConfig:
    """GUI configuration settings."""

    def __init__(self) -> None:
        """Initialize GUI configuration with defaults."""
        self.window_decoration: WindowDecorationType = WindowDecorationType.SERVER_SIDE

    @classmethod
    def load(cls) -> "GUIConfig":
        """
        Load GUI configuration from file.

        Returns:
            GUIConfig instance with loaded or default settings
        """
        config = cls()
        config_path = get_gui_config_path()

        if config_path.exists():
            try:
                with config_path.open("r") as f:
                    data = json.load(f)
                    # Load window decoration preference
                    if "window_decoration" in data:
                        try:
                            config.window_decoration = WindowDecorationType(data["window_decoration"])
                        except ValueError:
                            logger.warning(
                                f"Invalid window_decoration value: {data['window_decoration']}, using default"
                            )
            except Exception as e:
                logger.error(f"Error loading GUI config: {e}", exc_info=True)

        return config

    def save(self) -> None:
        """Save GUI configuration to file."""
        config_path = get_gui_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)

        data: dict[str, Any] = {"window_decoration": self.window_decoration.value}

        try:
            with config_path.open("w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving GUI config: {e}", exc_info=True)


def get_gui_config_path() -> Path:
    """
    Get the path to the GUI configuration file.

    Returns:
        Path to gui_config.json
    """
    return Path.home() / ".config" / "celestron-nexstar" / "gui_config.json"


def get_gui_config() -> GUIConfig:
    """
    Get the current GUI configuration.

    Returns:
        GUIConfig instance
    """
    return GUIConfig.load()

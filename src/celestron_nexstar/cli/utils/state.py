"""
CLI State Management

Manages telescope connection state across CLI commands.
"""

import contextlib
from typing import Any

from celestron_nexstar import NexStarTelescope, TelescopeConfig


# Global telescope instance
_telescope: NexStarTelescope | None = None
_cli_state: dict[str, Any] = {}


def get_telescope() -> NexStarTelescope | None:
    """Get the current telescope instance."""
    return _telescope


def set_telescope(telescope: NexStarTelescope) -> None:
    """Set the telescope instance."""
    global _telescope
    _telescope = telescope


def clear_telescope() -> None:
    """Clear the telescope instance."""
    global _telescope
    if _telescope is not None:
        with contextlib.suppress(Exception):
            _telescope.disconnect()
    _telescope = None


def ensure_connected(port: str | None = None) -> NexStarTelescope:
    """
    Ensure telescope is connected, creating connection if needed.

    Args:
        port: Serial port to connect to (required if not already connected)

    Returns:
        Connected telescope instance

    Raises:
        RuntimeError: If not connected and no port specified
    """
    global _telescope

    if _telescope is not None:
        return _telescope

    if port is None:
        raise RuntimeError(
            "Not connected to telescope. Please specify a port with --port or set NEXSTAR_PORT environment variable."
        )

    # Create and connect telescope
    config = TelescopeConfig(port=port)
    _telescope = NexStarTelescope(config)
    _telescope.connect()

    return _telescope


def get_cli_state() -> dict[str, Any]:
    """Get CLI state dictionary."""
    return _cli_state


def set_cli_state(key: str, value: Any) -> None:
    """Set CLI state value."""
    _cli_state[key] = value


def get_cli_state_value(key: str, default: Any = None) -> Any:
    """Get CLI state value with default."""
    return _cli_state.get(key, default)

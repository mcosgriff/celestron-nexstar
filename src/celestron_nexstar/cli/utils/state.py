"""
CLI State Management

Manages telescope connection state across CLI commands.
"""

import asyncio
import contextlib
from typing import Any

import typer
from rich.console import Console
from rich.prompt import Prompt

from celestron_nexstar import NexStarTelescope, TelescopeConfig
from celestron_nexstar.cli.utils.output import print_error, print_info


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
            # Try to disconnect synchronously if possible
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If loop is running, schedule disconnect
                    # Store task reference to avoid garbage collection
                    _disconnect_task = asyncio.create_task(_telescope.disconnect())  # noqa: RUF006
                    # Task will run in background, we don't wait for it
                else:
                    loop.run_until_complete(_telescope.disconnect())
            except RuntimeError:
                # No event loop, create one
                asyncio.run(_telescope.disconnect())
    _telescope = None


def ensure_connected() -> NexStarTelescope:
    """
    Ensure telescope is connected, creating connection if needed.

    If telescope exists but is not connected, attempts to reconnect using saved config.
    If no telescope exists, prompts user to choose connection type (serial or TCP/IP).

    Returns:
        Connected telescope instance

    Raises:
        typer.Exit: If connection fails or user cancels
    """
    global _telescope
    console = Console()

    # Check if telescope exists and is connected
    if _telescope is not None:
        # Try to reconnect if not open
        if not _telescope.protocol.is_open():
            print_info("Telescope connection lost. Attempting to reconnect...")
            try:
                asyncio.run(_telescope.connect())
                print_info("Reconnected successfully")
                return _telescope
            except Exception as e:
                print_error(f"Failed to reconnect: {e}")
                # Clear the broken connection
                clear_telescope()
        else:
            return _telescope

    # No telescope exists - prompt user for connection type
    print_info("Telescope not connected. Please choose connection type:")
    connection_type = Prompt.ask(
        "Connection type",
        choices=["serial", "tcp"],
        default="serial",
        console=console,
    )

    if connection_type == "tcp":
        # TCP/IP connection
        host = Prompt.ask("TCP/IP host", default="192.168.4.1", console=console)
        tcp_port_str = Prompt.ask("TCP/IP port", default="4030", console=console)
        try:
            tcp_port = int(tcp_port_str)
        except ValueError:
            print_error(f"Invalid port number: {tcp_port_str}")
            raise typer.Exit(code=1) from None

        config = TelescopeConfig(connection_type="tcp", host=host, tcp_port=tcp_port)
        connection_desc = f"{host}:{tcp_port}"
    else:
        # Serial connection
        port = Prompt.ask("Serial port", default="/dev/ttyUSB0", console=console)
        baudrate_str = Prompt.ask("Baud rate", default="9600", console=console)
        try:
            baudrate = int(baudrate_str)
        except ValueError:
            print_error(f"Invalid baud rate: {baudrate_str}")
            raise typer.Exit(code=1) from None

        config = TelescopeConfig(port=port, baudrate=baudrate)
        connection_desc = port

    # Create and connect telescope
    try:
        with console.status(f"[bold blue]Connecting to telescope on {connection_desc}...", spinner="dots"):
            _telescope = NexStarTelescope(config)
            asyncio.run(_telescope.connect())
        print_info(f"Connected to telescope on {connection_desc}")
        return _telescope
    except Exception as e:
        print_error(f"Failed to connect: {e}")
        _telescope = None
        raise typer.Exit(code=1) from e


def get_cli_state() -> dict[str, Any]:
    """Get CLI state dictionary."""
    return _cli_state


def set_cli_state(key: str, value: Any) -> None:
    """Set CLI state value."""
    _cli_state[key] = value


def get_cli_state_value(key: str, default: Any = None) -> Any:
    """Get CLI state value with default."""
    return _cli_state.get(key, default)


def run_async(coro: Any) -> Any:
    """
    Run an async coroutine from a sync context.

    This is a helper function for CLI commands that need to call async telescope methods.

    Args:
        coro: The coroutine to run

    Returns:
        The result of the coroutine
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is running, we can't use run_until_complete
            # This shouldn't happen in CLI context, but handle it gracefully
            raise RuntimeError("Cannot run async code from within an async context in CLI")
        return loop.run_until_complete(coro)
    except RuntimeError:
        # No event loop, create one
        return asyncio.run(coro)

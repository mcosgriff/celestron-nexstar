"""
Connection Commands

Commands for managing telescope connection.
"""

from typing import Literal

import typer
from click import Context
from rich.console import Console
from typer.core import TyperGroup

from celestron_nexstar import NexStarTelescope, TelescopeConfig
from celestron_nexstar.cli.utils.output import print_error, print_json, print_success, print_telescope_info
from celestron_nexstar.cli.utils.state import clear_telescope, get_telescope, set_telescope


class SortedCommandsGroup(TyperGroup):
    """Custom Typer group that sorts commands alphabetically within each help panel."""

    def list_commands(self, ctx: Context) -> list[str]:
        """Return commands sorted alphabetically."""
        commands = super().list_commands(ctx)
        return sorted(commands)


app = typer.Typer(help="Telescope connection commands", cls=SortedCommandsGroup)
console = Console()


@app.command(rich_help_panel="Connection")
def connect(
    port: str | None = typer.Argument(
        None, help="Serial port (e.g., /dev/ttyUSB0, COM3) or TCP address (e.g., 192.168.4.1:4030)"
    ),
    baudrate: int = typer.Option(9600, help="Baud rate (serial only)"),
    timeout: float = typer.Option(2.0, help="Connection timeout in seconds"),
    tcp: bool = typer.Option(False, "--tcp", help="Use TCP/IP connection (SkyPortal WiFi Adapter)"),
    host: str = typer.Option("192.168.4.1", "--host", help="TCP/IP host address (default: 192.168.4.1)"),
    tcp_port: int = typer.Option(4030, "--tcp-port", help="TCP/IP port (default: 4030)"),
) -> None:
    """
    Connect to the telescope and verify communication.

    Supports both serial and TCP/IP connections (e.g., via Celestron SkyPortal WiFi Adapter).

    Examples:
        # Serial connection
        nexstar connect /dev/ttyUSB0
        nexstar connect COM3 --baudrate 19200

        # TCP/IP connection (SkyPortal WiFi Adapter)
        nexstar connect --tcp
        nexstar connect --tcp --host 192.168.4.1 --tcp-port 4030
    """
    try:
        # Determine connection type
        if tcp:
            connection_type: Literal["serial", "tcp"] = "tcp"
            connection_desc = f"{host}:{tcp_port}"
            config = TelescopeConfig(
                connection_type=connection_type,
                host=host,
                tcp_port=tcp_port,
                timeout=timeout,
            )
        else:
            if port is None:
                print_error("Serial port required when not using --tcp")
                raise typer.Exit(code=1) from None
            connection_type = "serial"
            connection_desc = port
            config = TelescopeConfig(port=port, baudrate=baudrate, timeout=timeout)

        with console.status(f"[bold blue]Connecting to telescope on {connection_desc}...", spinner="dots"):
            telescope = NexStarTelescope(config)
            telescope.connect()
            set_telescope(telescope)

        print_success(f"Connected to telescope on {connection_desc}")

        # Get and display telescope info
        try:
            info = telescope.get_info()
            print_telescope_info(info.model, info.firmware_major, info.firmware_minor)
        except Exception:
            # Connection succeeded but info failed - not critical
            pass

    except Exception as e:
        print_error(f"Failed to connect: {e}")
        raise typer.Exit(code=1) from e


@app.command(rich_help_panel="Connection")
def disconnect() -> None:
    """
    Disconnect from the telescope.

    Example:
        nexstar disconnect
    """
    telescope = get_telescope()

    if telescope is None:
        print_error("Not connected to telescope")
        raise typer.Exit(code=1) from None

    try:
        clear_telescope()
        print_success("Disconnected from telescope")
    except Exception as e:
        print_error(f"Error during disconnect: {e}")
        raise typer.Exit(code=1) from e


@app.command(rich_help_panel="Testing")
def test(
    port: str | None = typer.Argument(None, help="Serial port to test (not used with --tcp)"),
    char: str = typer.Option("x", help="Character for echo test (single char)"),
    tcp: bool = typer.Option(False, "--tcp", help="Use TCP/IP connection (SkyPortal WiFi Adapter)"),
    host: str = typer.Option("192.168.4.1", "--host", help="TCP/IP host address (default: 192.168.4.1)"),
    tcp_port: int = typer.Option(4030, "--tcp-port", help="TCP/IP port (default: 4030)"),
) -> None:
    """
    Test connection with echo command.

    This sends a character to the telescope and verifies it echoes back,
    confirming basic communication is working.

    Examples:
        # Serial connection
        nexstar test /dev/ttyUSB0
        nexstar test COM3 --char A

        # TCP/IP connection
        nexstar test --tcp
        nexstar test --tcp --host 192.168.4.1 --tcp-port 4030
    """
    if len(char) != 1:
        print_error("Echo character must be a single character")
        raise typer.Exit(code=1) from None

    try:
        # Determine connection type
        if tcp:
            connection_desc = f"{host}:{tcp_port}"
            config = TelescopeConfig(connection_type="tcp", host=host, tcp_port=tcp_port)
        else:
            if port is None:
                print_error("Serial port required when not using --tcp")
                raise typer.Exit(code=1) from None
            connection_desc = port
            config = TelescopeConfig(port=port)

        with console.status(f"[bold blue]Testing connection on {connection_desc}...", spinner="dots"):
            telescope = NexStarTelescope(config)
            telescope.connect()

            # Run echo test
            success = telescope.echo_test(char)

        if success:
            print_success(f"Echo test passed on {connection_desc}")
        else:
            print_error(f"Echo test failed on {connection_desc}")
            raise typer.Exit(code=1) from None

        # Clean up
        telescope.disconnect()

    except Exception as e:
        print_error(f"Connection test failed: {e}")
        raise typer.Exit(code=1) from e


@app.command(rich_help_panel="Status")
def info(
    port: str | None = typer.Option(None, "--port", "-p", help="Serial port (if not already connected)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    tcp: bool = typer.Option(False, "--tcp", help="Use TCP/IP connection (SkyPortal WiFi Adapter)"),
    host: str = typer.Option("192.168.4.1", "--host", help="TCP/IP host address (default: 192.168.4.1)"),
    tcp_port: int = typer.Option(4030, "--tcp-port", help="TCP/IP port (default: 4030)"),
) -> None:
    """
    Get telescope information (model, firmware version).

    Examples:
        # Serial connection
        nexstar info --port /dev/ttyUSB0
        nexstar connect /dev/ttyUSB0
        nexstar info

        # TCP/IP connection
        nexstar info --tcp
        nexstar info --tcp --host 192.168.4.1 --tcp-port 4030

        # JSON output
        nexstar info --json
    """
    telescope = get_telescope()
    temp_connection = False

    try:
        # If not connected, create temporary connection
        if telescope is None:
            if tcp:
                config = TelescopeConfig(connection_type="tcp", host=host, tcp_port=tcp_port)
            elif port is None:
                print_error("Not connected. Please specify --port or --tcp, or connect first.")
                raise typer.Exit(code=1) from None
            else:
                config = TelescopeConfig(port=port)

            telescope = NexStarTelescope(config)
            telescope.connect()
            temp_connection = True

        # Get telescope info
        info = telescope.get_info()

        if json_output:
            print_json(
                {
                    "model": info.model,
                    "model_name": f"NexStar {info.model}SE",
                    "firmware": {"major": info.firmware_major, "minor": info.firmware_minor},
                    "firmware_string": f"{info.firmware_major}.{info.firmware_minor:02d}",
                }
            )
        else:
            print_telescope_info(info.model, info.firmware_major, info.firmware_minor)

    except Exception as e:
        print_error(f"Failed to get telescope info: {e}")
        raise typer.Exit(code=1) from None

    finally:
        # Clean up temporary connection
        if temp_connection and telescope is not None:
            telescope.disconnect()

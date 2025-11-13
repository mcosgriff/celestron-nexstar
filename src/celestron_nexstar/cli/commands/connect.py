"""
Connection Commands

Commands for managing telescope connection.
"""

import typer
from click import Context
from rich.console import Console
from typer.core import TyperGroup

from celestron_nexstar import NexStarTelescope, TelescopeConfig

from ..utils.output import print_error, print_json, print_success, print_telescope_info
from ..utils.state import clear_telescope, get_telescope, set_telescope


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
    port: str = typer.Argument(..., help="Serial port (e.g., /dev/ttyUSB0, COM3)"),
    baudrate: int = typer.Option(9600, help="Baud rate"),
    timeout: float = typer.Option(2.0, help="Connection timeout in seconds"),
) -> None:
    """
    Connect to the telescope and verify communication.

    Example:
        nexstar connect /dev/ttyUSB0
        nexstar connect COM3 --baudrate 19200
    """
    try:
        with console.status(f"[bold blue]Connecting to telescope on {port}...", spinner="dots"):
            config = TelescopeConfig(port=port, baudrate=baudrate, timeout=timeout)
            telescope = NexStarTelescope(config)
            telescope.connect()
            set_telescope(telescope)

        print_success(f"Connected to telescope on {port}")

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
    port: str = typer.Argument(..., help="Serial port to test"),
    char: str = typer.Option("x", help="Character for echo test (single char)"),
) -> None:
    """
    Test connection with echo command.

    This sends a character to the telescope and verifies it echoes back,
    confirming basic communication is working.

    Example:
        nexstar test /dev/ttyUSB0
        nexstar test COM3 --char A
    """
    if len(char) != 1:
        print_error("Echo character must be a single character")
        raise typer.Exit(code=1) from None

    try:
        with console.status(f"[bold blue]Testing connection on {port}...", spinner="dots"):
            config = TelescopeConfig(port=port)
            telescope = NexStarTelescope(config)
            telescope.connect()

            # Run echo test
            success = telescope.echo_test(char)

        if success:
            print_success(f"Echo test passed on {port}")
        else:
            print_error(f"Echo test failed on {port}")
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
) -> None:
    """
    Get telescope information (model, firmware version).

    Example:
        nexstar info --port /dev/ttyUSB0
        nexstar connect /dev/ttyUSB0
        nexstar info
        nexstar info --json
    """
    telescope = get_telescope()
    temp_connection = False

    try:
        # If not connected, create temporary connection
        if telescope is None:
            if port is None:
                print_error("Not connected. Please specify --port or connect first.")
                raise typer.Exit(code=1) from None

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

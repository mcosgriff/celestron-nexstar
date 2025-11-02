"""
Celestron NexStar CLI - Main Application

This is the main entry point for the Celestron NexStar command-line interface.
"""

import typer
from rich.console import Console

# Import and register subcommands
from .commands import align, catalog, connect, ephemeris, goto, location, move, optics, position, time, track


# Create main app
app = typer.Typer(
    name="nexstar",
    help="Celestron NexStar Telescope Control CLI",
    add_completion=True,
    rich_markup_mode="rich",
)

# Console for rich output
console = Console()

# Global state for CLI
state: dict[str, str | None | bool] = {
    "port": None,
    "profile": None,
    "verbose": False,
}


@app.callback()
def main(
    port: str | None = typer.Option(
        None,
        "--port",
        "-p",
        help="Serial port for telescope connection",
        envvar="NEXSTAR_PORT",
    ),
    profile: str | None = typer.Option(
        None,
        "--profile",
        help="Configuration profile to use",
        envvar="NEXSTAR_PROFILE",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose output",
    ),
) -> None:
    """
    Celestron NexStar Telescope Control CLI

    Control your Celestron NexStar telescope from the command line.

    [bold green]Examples:[/bold green]

        nexstar connect /dev/ttyUSB0
        nexstar position
        nexstar goto --ra 12.5 --dec 45.0

    [bold blue]Environment Variables:[/bold blue]

        NEXSTAR_PORT    - Default serial port
        NEXSTAR_PROFILE - Default configuration profile
    """
    state["port"] = port
    state["profile"] = profile
    state["verbose"] = verbose

    if verbose:
        console.print("[dim]Verbose mode enabled[/dim]")
        if port:
            console.print(f"[dim]Using port: {port}[/dim]")
        if profile:
            console.print(f"[dim]Using profile: {profile}[/dim]")


@app.command()
def version() -> None:
    """Show the CLI version."""
    from celestron_nexstar.cli import __version__

    console.print(f"[bold]Celestron NexStar CLI[/bold] version [cyan]{__version__}[/cyan]")


# Register command groups - Phase 2 (Core)
app.add_typer(connect.app, name="connect", help="Connection commands (deprecated - use subcommands)")
app.add_typer(position.app, name="position", help="Position query commands")
app.add_typer(goto.app, name="goto", help="Slew (goto) commands")
app.add_typer(move.app, name="move", help="Manual movement commands")
app.add_typer(track.app, name="track", help="Tracking control commands")
app.add_typer(align.app, name="align", help="Alignment commands")

# Register command groups - Phase 3 (Advanced)
app.add_typer(location.app, name="location", help="Observer location commands")
app.add_typer(time.app, name="time", help="Time and date commands")
app.add_typer(catalog.app, name="catalog", help="Celestial object catalogs")
app.add_typer(optics.app, name="optics", help="Telescope and eyepiece configuration")
app.add_typer(ephemeris.app, name="ephemeris", help="Ephemeris file management")


# Also add connect commands directly to main app for convenience
@app.command("conn")
def conn(
    port: str = typer.Argument(..., help="Serial port (e.g., /dev/ttyUSB0, COM3)"),
    baudrate: int = typer.Option(9600, help="Baud rate"),
    timeout: float = typer.Option(2.0, help="Connection timeout in seconds"),
) -> None:
    """Quick connect to telescope (shorthand for 'connect connect')."""
    connect.connect(port, baudrate, timeout)


@app.command("disc")
def disc() -> None:
    """Quick disconnect from telescope (shorthand for 'connect disconnect')."""
    connect.disconnect()


if __name__ == "__main__":
    app()

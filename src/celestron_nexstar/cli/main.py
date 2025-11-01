"""
Celestron NexStar CLI - Main Application

This is the main entry point for the Celestron NexStar command-line interface.
"""

import typer
from rich.console import Console


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


# Import and register subcommands (to be created in Phase 2)
# from .commands import connect, position, goto, track, align, config, monitor, interactive


if __name__ == "__main__":
    app()

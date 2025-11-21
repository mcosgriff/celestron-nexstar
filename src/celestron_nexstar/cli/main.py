"""
Celestron NexStar CLI - Main Application

This is the main entry point for the Celestron NexStar command-line interface.
"""

import typer
from click import Context
from dotenv import load_dotenv
from rich.console import Console
from typer.core import TyperGroup

from celestron_nexstar.cli.commands import glossary

# Import and register subcommands
from celestron_nexstar.cli.commands.astronomy import (
    aurora,
    binoculars,
    comets,
    eclipse,
    events,
    iss,
    meteors,
    milky_way,
    naked_eye,
    occultations,
    planets,
    satellites,
    space_weather,
    variables,
    zodiacal,
)
from celestron_nexstar.cli.commands.dashboard import dashboard
from celestron_nexstar.cli.commands.data import catalog, data, ephemeris
from celestron_nexstar.cli.commands.location import location, weather
from celestron_nexstar.cli.commands.observation import multi_night, telescope
from celestron_nexstar.cli.commands.optics import optics
from celestron_nexstar.cli.commands.telescope import align, connect, goto, mount, move, position, time, track
from celestron_nexstar.cli.commands.vacation import vacation


class SortedCommandsGroup(TyperGroup):
    """Custom Typer group that sorts commands alphabetically within each help panel."""

    def list_commands(self, ctx: Context) -> list[str]:
        """Return commands sorted alphabetically."""
        commands = super().list_commands(ctx)
        return sorted(commands)


# Create main app
app = typer.Typer(
    name="nexstar",
    help="Celestron NexStar Telescope Control CLI",
    add_completion=True,
    rich_markup_mode="rich",
    cls=SortedCommandsGroup,
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

    load_dotenv()

    if verbose:
        console.print("[dim]Verbose mode enabled[/dim]")
        if port:
            console.print(f"[dim]Using port: {port}[/dim]")
        if profile:
            console.print(f"[dim]Using profile: {profile}[/dim]")


@app.command(rich_help_panel="Utilities")
def version() -> None:
    """Show the CLI version."""
    from celestron_nexstar.cli import __version__

    console.print(f"[bold]Celestron NexStar CLI[/bold] version [cyan]{__version__}[/cyan]")


@app.command("config", rich_help_panel="Configuration")
def show_all_config(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """
    Show all current configuration values.

    Displays optical configuration (telescope and eyepiece) and observer location
    in a single unified view.

    Example:
        nexstar config
        nexstar config --json
    """
    from pathlib import Path

    from rich.table import Table

    from celestron_nexstar.api.location.observer import get_observer_location
    from celestron_nexstar.api.observation.optics import get_current_configuration
    from celestron_nexstar.cli.utils.output import print_error, print_info, print_json

    try:
        # Get all configuration
        optical_config = get_current_configuration()
        observer_location = get_observer_location()

        # Get config file paths
        config_dir = Path.home() / ".config" / "celestron-nexstar"
        optical_config_path = config_dir / "optical_config.json"
        location_config_path = config_dir / "observer_location.json"

        if json_output:
            # JSON output
            lat_dir = "N" if observer_location.latitude >= 0 else "S"
            lon_dir = "E" if observer_location.longitude >= 0 else "W"

            print_json(
                {
                    "optical": {
                        "telescope": {
                            "model": optical_config.telescope.model.value,
                            "display_name": optical_config.telescope.display_name,
                            "aperture_mm": optical_config.telescope.aperture_mm,
                            "aperture_inches": round(optical_config.telescope.aperture_inches, 1),
                            "focal_length_mm": optical_config.telescope.focal_length_mm,
                            "focal_ratio": optical_config.telescope.focal_ratio,
                            "effective_aperture_mm": round(optical_config.telescope.effective_aperture_mm, 1),
                        },
                        "eyepiece": {
                            "name": optical_config.eyepiece.name,
                            "focal_length_mm": optical_config.eyepiece.focal_length_mm,
                            "apparent_fov_deg": optical_config.eyepiece.apparent_fov_deg,
                        },
                        "performance": {
                            "magnification": round(optical_config.magnification, 1),
                            "exit_pupil_mm": round(optical_config.exit_pupil_mm, 2),
                            "true_fov_deg": round(optical_config.true_fov_deg, 2),
                        },
                    },
                    "location": {
                        "name": observer_location.name,
                        "latitude": observer_location.latitude,
                        "longitude": observer_location.longitude,
                        "elevation": observer_location.elevation,
                        "latitude_formatted": f"{abs(observer_location.latitude):.4f}°{lat_dir}",
                        "longitude_formatted": f"{abs(observer_location.longitude):.4f}°{lon_dir}",
                    },
                    "config_files": {
                        "directory": str(config_dir),
                        "optical_config": str(optical_config_path),
                        "location_config": str(location_config_path),
                    },
                }
            )
        else:
            # Pretty table output
            console.print("\n[bold cyan]Current Configuration[/bold cyan]\n")

            # Optical Configuration
            optics_table = Table(
                title="[bold]Optical Configuration[/bold]",
                show_header=True,
                header_style="bold magenta",
                expand=False,
            )
            optics_table.add_column("Setting", style="cyan")
            optics_table.add_column("Value", style="green")

            optics_table.add_row("Telescope", optical_config.telescope.display_name)
            optics_table.add_row(
                "Aperture",
                f'{optical_config.telescope.aperture_mm}mm ({optical_config.telescope.aperture_inches:.1f}")',
            )
            optics_table.add_row("Focal Length", f"{optical_config.telescope.focal_length_mm}mm")
            optics_table.add_row("Focal Ratio", f"f/{optical_config.telescope.focal_ratio}")
            optics_table.add_row(
                "Eyepiece", optical_config.eyepiece.name or f"{optical_config.eyepiece.focal_length_mm}mm"
            )
            optics_table.add_row("Eyepiece Focal Length", f"{optical_config.eyepiece.focal_length_mm}mm")
            optics_table.add_row("Apparent FOV", f"{optical_config.eyepiece.apparent_fov_deg}°")
            optics_table.add_row("Magnification", f"{optical_config.magnification:.0f}x")
            optics_table.add_row("Exit Pupil", f"{optical_config.exit_pupil_mm:.1f}mm")
            optics_table.add_row(
                "True FOV", f"{optical_config.true_fov_deg:.2f}° ({optical_config.true_fov_arcmin:.1f}')"
            )

            console.print(optics_table)
            console.print()

            # Observer Location
            location_table = Table(
                title="[bold]Observer Location[/bold]",
                show_header=True,
                header_style="bold magenta",
                expand=False,
            )
            location_table.add_column("Setting", style="cyan")
            location_table.add_column("Value", style="green")

            if observer_location.name:
                location_table.add_row("Location Name", observer_location.name)

            lat_dir = "N" if observer_location.latitude >= 0 else "S"
            lon_dir = "E" if observer_location.longitude >= 0 else "W"
            location_table.add_row("Latitude", f"{abs(observer_location.latitude):.4f}°{lat_dir}")
            location_table.add_row("Longitude", f"{abs(observer_location.longitude):.4f}°{lon_dir}")

            if observer_location.elevation:
                location_table.add_row("Elevation", f"{observer_location.elevation:.0f} m above sea level")

            console.print(location_table)
            console.print()

            # Config File Paths
            paths_table = Table(
                title="[bold]Configuration Files[/bold]",
                show_header=True,
                header_style="bold magenta",
                expand=False,
            )
            paths_table.add_column("File", style="cyan")
            paths_table.add_column("Path", style="dim")

            paths_table.add_row("Config Directory", str(config_dir))
            paths_table.add_row(
                "Optical Config",
                str(optical_config_path)
                + (" [green]✓[/green]" if optical_config_path.exists() else " [dim](not saved)[/dim]"),
            )
            paths_table.add_row(
                "Location Config",
                str(location_config_path)
                + (" [green]✓[/green]" if location_config_path.exists() else " [dim](not saved)[/dim]"),
            )

            console.print(paths_table)
            console.print()

            print_info("Use 'nexstar optics show' for detailed optical specs")
            print_info("Use 'nexstar location get-observer' for detailed location info")

    except Exception as e:
        print_error(f"Failed to show configuration: {e}")
        raise typer.Exit(code=1) from e


# Register command groups organized by category

# Telescope Control
app.add_typer(
    connect.app,
    name="connect",
    help="Connection commands",
    rich_help_panel="Telescope Control",
)
app.add_typer(
    position.app,
    name="position",
    help="Position query commands",
    rich_help_panel="Telescope Control",
)
app.add_typer(
    goto.app,
    name="goto",
    help="Slew (goto) commands",
    rich_help_panel="Telescope Control",
)
app.add_typer(
    move.app,
    name="move",
    help="Manual movement commands",
    rich_help_panel="Telescope Control",
)
app.add_typer(
    track.app,
    name="track",
    help="Tracking control commands",
    rich_help_panel="Telescope Control",
)
app.add_typer(
    align.app,
    name="align",
    help="Alignment commands",
    rich_help_panel="Telescope Control",
)
app.add_typer(
    mount.app,
    name="mount",
    help="Mount settings and backlash control",
    rich_help_panel="Telescope Control",
)

# Planning & Observation
app.add_typer(
    telescope.app,
    name="telescope",
    help="Telescope viewing commands",
    rich_help_panel="Planning & Observation",
)
app.add_typer(
    multi_night.app,
    name="multi-night",
    help="Multi-night planning and comparison (uses telescope configuration)",
    rich_help_panel="Planning & Observation",
)
app.add_typer(
    binoculars.app,
    name="binoculars",
    help="Binocular viewing (ISS, constellations, asterisms)",
    rich_help_panel="Planning & Observation",
)
app.add_typer(
    naked_eye.app,
    name="naked-eye",
    help="Naked-eye stargazing (no equipment needed)",
    rich_help_panel="Planning & Observation",
)
# Celestial Events
app.add_typer(
    aurora.app,
    name="aurora",
    help="Aurora borealis (Northern Lights) visibility",
    rich_help_panel="Celestial Events",
)
app.add_typer(
    milky_way.app,
    name="milky-way",
    help="Milky Way visibility",
    rich_help_panel="Celestial Events",
)
app.add_typer(
    space_weather.app,
    name="space-weather",
    help="Space weather conditions and alerts (NOAA SWPC)",
    rich_help_panel="Celestial Events",
)
app.add_typer(
    eclipse.app,
    name="eclipse",
    help="Lunar and solar eclipse predictions",
    rich_help_panel="Celestial Events",
)
app.add_typer(
    planets.app,
    name="planets",
    help="Planetary events (conjunctions, oppositions)",
    rich_help_panel="Celestial Events",
)
app.add_typer(
    meteors.app,
    name="meteors",
    help="Enhanced meteor shower predictions with moon phase",
    rich_help_panel="Celestial Events",
)
app.add_typer(
    comets.app,
    name="comets",
    help="Bright comet tracking and visibility",
    rich_help_panel="Celestial Events",
)
app.add_typer(
    iss.app,
    name="iss",
    help="International Space Station pass predictions",
    rich_help_panel="Celestial Events",
)
app.add_typer(
    satellites.app,
    name="satellites",
    help="Bright satellite passes and flares",
    rich_help_panel="Celestial Events",
)
app.add_typer(
    zodiacal.app,
    name="zodiacal",
    help="Zodiacal light and gegenschein viewing",
    rich_help_panel="Celestial Events",
)
app.add_typer(
    variables.app,
    name="variables",
    help="Variable star events (eclipses, maxima, minima)",
    rich_help_panel="Celestial Events",
)
app.add_typer(
    occultations.app,
    name="occultations",
    help="Asteroid occultation predictions",
    rich_help_panel="Celestial Events",
)
app.add_typer(
    catalog.app,
    name="catalog",
    help="Celestial object catalogs",
    rich_help_panel="Planning & Observation",
)
app.add_typer(
    vacation.app,
    name="vacation",
    help="Vacation planning for telescope viewing",
    rich_help_panel="Planning & Observation",
)
app.add_typer(
    events.app,
    name="events",
    help="Space events calendar and viewing recommendations",
    rich_help_panel="Planning & Observation",
)

# Configuration
app.add_typer(
    location.app,
    name="location",
    help="Observer location commands",
    rich_help_panel="Configuration",
)
app.add_typer(
    time.app,
    name="time",
    help="Time and date commands",
    rich_help_panel="Configuration",
)
app.add_typer(
    optics.app,
    name="optics",
    help="Telescope and eyepiece configuration",
    rich_help_panel="Configuration",
)
app.add_typer(
    ephemeris.app,
    name="ephemeris",
    help="Ephemeris file management",
    rich_help_panel="Configuration",
)
app.add_typer(
    weather.app,
    name="weather",
    help="Current weather conditions",
    rich_help_panel="Configuration",
)

# Data & Management
app.add_typer(
    data.app,
    name="data",
    help="Data import and management",
    rich_help_panel="Data & Management",
)
app.add_typer(
    dashboard.app,
    name="dashboard",
    help="Full-screen dashboard",
    rich_help_panel="Data & Management",
)
app.add_typer(
    glossary.app,
    name="glossary",
    help="Astronomical terms glossary",
    rich_help_panel="Utilities",
)


# Also add connect commands directly to main app for convenience
@app.command("conn", rich_help_panel="Utilities")
def conn(
    port: str = typer.Argument(..., help="Serial port (e.g., /dev/ttyUSB0, COM3)"),
    baudrate: int = typer.Option(9600, help="Baud rate"),
    timeout: float = typer.Option(2.0, help="Connection timeout in seconds"),
) -> None:
    """Quick connect to telescope (shorthand for 'connect connect')."""
    connect.connect(port, baudrate, timeout)


@app.command("disc", rich_help_panel="Utilities")
def disc() -> None:
    """Quick disconnect from telescope (shorthand for 'connect disconnect')."""
    connect.disconnect()


@app.command(rich_help_panel="Utilities")
def shell() -> None:
    """
    Enter interactive shell mode with autocomplete.

    In interactive mode, you can run commands without the 'nexstar' prefix.

    [bold green]Examples:[/bold green]

        nexstar> position get
        nexstar> goto radec --ra 5.5 --dec 22.5
        nexstar> catalog search "andromeda"
        nexstar> exit

    [bold blue]Features:[/bold blue]

        - Tab completion for commands and subcommands
        - Status bar with time, weather, GPS, and telescope position
        - Ctrl+C to cancel current input
        - Type 'exit' or 'quit' to leave shell
        - Type 'help' to see available commands
    """
    from celestron_nexstar.cli.shell_app import ShellApp, create_status_cache

    # Create status cache
    status_cache = create_status_cache()

    # Create and run the Textual shell app
    shell_app = ShellApp(app, status_cache)
    shell_app.run()


if __name__ == "__main__":
    app()

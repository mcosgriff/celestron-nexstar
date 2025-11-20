"""
Goto Commands

Commands for slewing telescope to target coordinates.
"""

import asyncio
import time

import typer
from click import Context
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.prompt import Confirm
from rich.text import Text
from typer.core import TyperGroup

from celestron_nexstar.api.catalogs.catalogs import get_object_by_name
from celestron_nexstar.api.observation.visibility import assess_visibility
from celestron_nexstar.cli.utils.output import (
    calculate_panel_width,
    console,
    format_dec,
    format_ra,
    print_error,
    print_info,
    print_success,
)
from celestron_nexstar.cli.utils.selection import select_object
from celestron_nexstar.cli.utils.state import ensure_connected


class SortedCommandsGroup(TyperGroup):
    """Custom Typer group that sorts commands alphabetically within each help panel."""

    def list_commands(self, ctx: Context) -> list[str]:
        """Return commands sorted alphabetically."""
        commands = super().list_commands(ctx)
        return sorted(commands)


app = typer.Typer(help="Telescope slew (goto) commands", cls=SortedCommandsGroup)


@app.command(rich_help_panel="Slew to Coordinates")
def radec(
    ra: float = typer.Option(..., "--ra", help="Right Ascension in hours (0-24)"),
    dec: float = typer.Option(..., "--dec", help="Declination in degrees (-90 to +90)"),
    wait: bool = typer.Option(True, help="Wait for slew to complete"),
    progress: bool = typer.Option(True, help="Show progress indicator"),
) -> None:
    """
    Slew telescope to RA/Dec coordinates.

    Example:
        nexstar goto radec --ra 12.5 --dec 45.0
        nexstar goto radec --ra 2.5303 --dec 89.2641  # Polaris
        nexstar goto radec --ra 10.68 --dec 41.27 --no-wait
    """
    # Validate coordinates
    if not 0 <= ra <= 24:
        print_error("RA must be between 0 and 24 hours")
        raise typer.Exit(code=1) from None
    if not -90 <= dec <= 90:
        print_error("Dec must be between -90 and +90 degrees")
        raise typer.Exit(code=1) from None

    try:
        telescope = ensure_connected()

        print_info(f"Slewing to RA {ra:.4f}h, Dec {dec:+.4f}°")

        # Start slew
        success = telescope.goto_ra_dec(ra, dec)
        if not success:
            print_error("Failed to initiate slew")
            raise typer.Exit(code=1) from None

        if wait:
            if progress:
                # Show progress with spinner
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TimeElapsedColumn(),
                    console=console,
                ) as prog:
                    task = prog.add_task("Slewing to target...", total=None)

                    while telescope.is_slewing():
                        time.sleep(0.5)
                        prog.update(task)

                print_success(f"Arrived at RA {ra:.4f}h, Dec {dec:+.4f}°")
            else:
                # Wait without progress bar
                while telescope.is_slewing():
                    time.sleep(0.5)
                print_success("Slew complete")
        else:
            print_success("Slew initiated")

    except Exception as e:
        print_error(f"Slew failed: {e}")
        raise typer.Exit(code=1) from e


@app.command(rich_help_panel="Slew to Coordinates")
def altaz(
    az: float = typer.Option(..., "--az", help="Azimuth in degrees (0-360)"),
    alt: float = typer.Option(..., "--alt", help="Altitude in degrees (-90 to +90)"),
    wait: bool = typer.Option(True, help="Wait for slew to complete"),
    progress: bool = typer.Option(True, help="Show progress indicator"),
) -> None:
    """
    Slew telescope to Alt/Az coordinates.

    Example:
        nexstar goto altaz --az 180 --alt 45
        nexstar goto altaz --az 0 --alt 90  # Zenith
        nexstar goto altaz --az 270 --alt 30 --no-wait
    """
    # Validate coordinates
    if not 0 <= az <= 360:
        print_error("Azimuth must be between 0 and 360 degrees")
        raise typer.Exit(code=1)
    if not -90 <= alt <= 90:
        print_error("Altitude must be between -90 and +90 degrees")
        raise typer.Exit(code=1)

    try:
        telescope = ensure_connected()

        print_info(f"Slewing to Az {az:.2f}°, Alt {alt:+.2f}°")

        # Start slew
        success = telescope.goto_alt_az(az, alt)
        if not success:
            print_error("Failed to initiate slew")
            raise typer.Exit(code=1)

        if wait:
            if progress:
                # Show progress with spinner
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TimeElapsedColumn(),
                    console=console,
                ) as prog:
                    task = prog.add_task("Slewing to target...", total=None)

                    while telescope.is_slewing():
                        time.sleep(0.5)
                        prog.update(task)

                print_success(f"Arrived at Az {az:.2f}°, Alt {alt:+.2f}°")
            else:
                # Wait without progress bar
                while telescope.is_slewing():
                    time.sleep(0.5)
                print_success("Slew complete")
        else:
            print_success("Slew initiated")

    except Exception as e:
        print_error(f"Slew failed: {e}")
        raise typer.Exit(code=1) from e


@app.command(rich_help_panel="Control")
def cancel() -> None:
    """
    Cancel current goto operation.

    Example:
        nexstar goto cancel
    """
    try:
        telescope = ensure_connected()

        if not telescope.is_slewing():
            print_info("Telescope is not currently slewing")
            return

        success = telescope.cancel_goto()
        if success:
            print_success("Slew cancelled")
        else:
            print_error("Failed to cancel slew")
            raise typer.Exit(code=1)

    except Exception as e:
        print_error(f"Cancel failed: {e}")
        raise typer.Exit(code=1) from e


@app.command(rich_help_panel="Slew to Object")
def by_name(
    object_name: str = typer.Argument(..., help="Object name (e.g., IO, M31, Polaris, Jupiter)"),
    wait: bool = typer.Option(True, help="Wait for slew to complete"),
    progress: bool = typer.Option(True, help="Show progress indicator"),
) -> None:
    """
    Slew telescope to a named celestial object.

    Looks up the object by name, displays details for confirmation, then slews to it.
    Uses fuzzy matching - if multiple objects match, you'll be prompted to choose.

    Example:
        nexstar goto by_name IO
        nexstar goto by_name M31
        nexstar goto by_name Polaris
        nexstar goto by_name Jupiter --no-wait
    """
    try:
        # Look up object
        matches = asyncio.run(get_object_by_name(object_name))

        if not matches:
            print_error(f"No objects found matching '{object_name}'")
            print_info("Try 'nexstar catalog search <query>' to find objects")
            raise typer.Exit(code=1) from None

        # If multiple matches, let user select
        obj = select_object(matches, object_name)
        if obj is None:
            raise typer.Exit(code=1) from None

        # Update position for dynamic objects (planets, moons) to ensure current coordinates
        obj = obj.with_current_position()

        # Assess visibility
        visibility_info = assess_visibility(obj)

        # Display object details for confirmation
        display_name = obj.common_name or obj.name
        info_text = Text()

        # Name and common name
        info_text.append(f"{obj.name}", style="bold cyan")
        if obj.common_name and obj.common_name != obj.name:
            info_text.append(f" ({obj.common_name})", style="cyan")
        info_text.append("\n\n")

        # Coordinates
        info_text.append("Coordinates:\n", style="bold yellow")
        info_text.append(f"  RA:  {format_ra(obj.ra_hours)}\n", style="green")
        info_text.append(f"  Dec: {format_dec(obj.dec_degrees)}\n", style="green")
        info_text.append("\n")

        # Metadata
        info_text.append("Properties:\n", style="bold yellow")
        info_text.append(f"  Type:     {obj.object_type}\n", style="white")
        if obj.magnitude:
            info_text.append(f"  Magnitude: {obj.magnitude:.2f}\n", style="white")
        info_text.append(f"  Catalog:  {obj.catalog}\n", style="white")

        # Visibility information
        info_text.append("\n")
        info_text.append("Visibility:\n", style="bold yellow")
        if visibility_info.is_visible:
            info_text.append("  Status: ", style="white")
            info_text.append("✓ Visible\n", style="bold green")
        else:
            info_text.append("  Status: ", style="white")
            info_text.append("✗ Not Visible\n", style="bold red")

        if visibility_info.altitude_deg is not None:
            info_text.append(f"  Altitude: {visibility_info.altitude_deg:.1f}°\n", style="white")
        if visibility_info.azimuth_deg is not None:
            # Convert azimuth to cardinal direction
            az = visibility_info.azimuth_deg
            match az:
                case a if a < 22.5 or a >= 337.5:
                    direction = "N"
                case a if a < 67.5:
                    direction = "NE"
                case a if a < 112.5:
                    direction = "E"
                case a if a < 157.5:
                    direction = "SE"
                case a if a < 202.5:
                    direction = "S"
                case a if a < 247.5:
                    direction = "SW"
                case a if a < 292.5:
                    direction = "W"
                case _:
                    direction = "NW"
            info_text.append(f"  Azimuth: {visibility_info.azimuth_deg:.1f}° ({direction})\n", style="white")

        # Description (if available)
        if obj.description:
            info_text.append("\n")
            info_text.append("Description:\n", style="bold yellow")
            info_text.append(f"  {obj.description}\n", style="white")

        panel = Panel.fit(
            info_text,
            title=f"[bold]Slew to {display_name}?[/bold]",
            border_style="cyan",
            width=calculate_panel_width(info_text, console),
        )
        console.print(panel)
        console.print()

        # Prompt for confirmation
        if not Confirm.ask(f"[cyan]Slew telescope to {display_name}?[/cyan]", default=True):
            print_info("Slew cancelled")
            return

        # Get telescope connection
        telescope = ensure_connected()

        print_info(f"Slewing to {display_name} (RA {obj.ra_hours:.4f}h, Dec {obj.dec_degrees:+.4f}°)")

        # Start slew
        success = telescope.goto_ra_dec(obj.ra_hours, obj.dec_degrees)
        if not success:
            print_error("Failed to initiate slew")
            raise typer.Exit(code=1) from None

        if wait:
            if progress:
                # Show progress with spinner
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TimeElapsedColumn(),
                    console=console,
                ) as prog:
                    task = prog.add_task(f"Slewing to {display_name}...", total=None)

                    while telescope.is_slewing():
                        time.sleep(0.5)
                        prog.update(task)

                print_success(f"Arrived at {display_name}")
            else:
                # Wait without progress bar
                while telescope.is_slewing():
                    time.sleep(0.5)
                print_success("Slew complete")
        else:
            print_success("Slew initiated")

    except Exception as e:
        print_error(f"Slew failed: {e}")
        raise typer.Exit(code=1) from e


@app.command(rich_help_panel="Status")
def status() -> None:
    """
    Check if telescope is currently slewing.

    Example:
        nexstar goto status
    """
    try:
        telescope = ensure_connected()
        is_slewing = telescope.is_slewing()

        if is_slewing:
            console.print("[yellow]Telescope is slewing[/yellow]")
        else:
            console.print("[green]Telescope is stationary[/green]")

    except Exception as e:
        print_error(f"Failed to get status: {e}")
        raise typer.Exit(code=1) from e

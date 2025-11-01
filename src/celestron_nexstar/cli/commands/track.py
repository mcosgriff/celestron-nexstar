"""
Track Commands

Commands for controlling telescope tracking.
"""

from typing import Literal

import typer

from celestron_nexstar import TrackingMode
from ..utils.output import (
    print_error,
    print_success,
    print_info,
    print_json,
    format_tracking_mode,
    console,
)
from ..utils.state import ensure_connected


app = typer.Typer(help="Tracking control commands")


@app.command()
def start(
    port: str | None = typer.Option(None, "--port", "-p", help="Serial port"),
    mode: Literal["alt-az", "eq-north", "eq-south"] = typer.Option(
        "alt-az", help="Tracking mode: alt-az, eq-north, eq-south"
    ),
) -> None:
    """
    Start telescope tracking in specified mode.

    Tracking modes:
        alt-az    - Altitude-Azimuth tracking (for alt-az mounts)
        eq-north  - Equatorial tracking for Northern Hemisphere
        eq-south  - Equatorial tracking for Southern Hemisphere

    Example:
        nexstar track start
        nexstar track start --mode eq-north
        nexstar track start --mode alt-az
    """
    # Map string to TrackingMode enum
    mode_map = {"alt-az": TrackingMode.ALT_AZ, "eq-north": TrackingMode.EQ_NORTH, "eq-south": TrackingMode.EQ_SOUTH}

    tracking_mode = mode_map[mode]

    try:
        telescope = ensure_connected(port)

        success = telescope.set_tracking_mode(tracking_mode)
        if success:
            print_success(f"Tracking started in {format_tracking_mode(tracking_mode.name)} mode")
        else:
            print_error("Failed to start tracking")
            raise typer.Exit(code=1)

    except Exception as e:
        print_error(f"Failed to set tracking mode: {e}")
        raise typer.Exit(code=1)


@app.command()
def stop(
    port: str | None = typer.Option(None, "--port", "-p", help="Serial port"),
) -> None:
    """
    Stop telescope tracking.

    Example:
        nexstar track stop
    """
    try:
        telescope = ensure_connected(port)

        success = telescope.set_tracking_mode(TrackingMode.OFF)
        if success:
            print_success("Tracking stopped")
        else:
            print_error("Failed to stop tracking")
            raise typer.Exit(code=1)

    except Exception as e:
        print_error(f"Failed to stop tracking: {e}")
        raise typer.Exit(code=1)


@app.command()
def status(
    port: str | None = typer.Option(None, "--port", "-p", help="Serial port"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """
    Get current tracking mode.

    Example:
        nexstar track status
        nexstar track status --json
    """
    try:
        telescope = ensure_connected(port)

        mode = telescope.get_tracking_mode()

        if json_output:
            print_json({"mode": mode.name, "mode_value": mode.value, "mode_display": format_tracking_mode(mode.name)})
        else:
            formatted_mode = format_tracking_mode(mode.name)
            if mode == TrackingMode.OFF:
                console.print(f"[yellow]Tracking: {formatted_mode}[/yellow]")
            else:
                console.print(f"[green]Tracking: {formatted_mode}[/green]")

    except Exception as e:
        print_error(f"Failed to get tracking mode: {e}")
        raise typer.Exit(code=1)

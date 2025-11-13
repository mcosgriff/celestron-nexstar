"""
Move Commands

Commands for manual telescope movement.
"""

import time
from typing import Literal

import typer
from click import Context
from typer.core import TyperGroup

from ..utils.output import print_error, print_info, print_success
from ..utils.state import ensure_connected


class SortedCommandsGroup(TyperGroup):
    """Custom Typer group that sorts commands alphabetically within each help panel."""

    def list_commands(self, ctx: Context) -> list[str]:
        """Return commands sorted alphabetically."""
        commands = super().list_commands(ctx)
        return sorted(commands)


app = typer.Typer(help="Manual movement commands", cls=SortedCommandsGroup)


@app.command(rich_help_panel="Movement")
def fixed(
    port: str | None = typer.Option(None, "--port", "-p", help="Serial port"),
    direction: Literal["up", "down", "left", "right"] = typer.Argument(..., help="Direction to move"),
    rate: int = typer.Option(5, min=0, max=9, help="Movement rate (0-9, 0=slowest, 9=fastest)"),
    duration: float | None = typer.Option(None, help="Duration in seconds (if specified, auto-stops)"),
) -> None:
    """
    Move telescope in specified direction at fixed rate.

    If duration is specified, the telescope will move for that duration
    then automatically stop. Otherwise, you must manually stop it.

    Example:
        nexstar move fixed up --rate 5 --duration 2.0
        nexstar move fixed right --rate 7
        nexstar move fixed down --rate 3 --duration 1.5
    """
    if not 0 <= rate <= 9:
        print_error("Rate must be between 0 and 9")
        raise typer.Exit(code=1) from None

    try:
        telescope = ensure_connected(port)

        # Start movement
        success = telescope.move_fixed(direction, rate)
        if not success:
            print_error(f"Failed to start movement {direction}")
            raise typer.Exit(code=1) from None

        print_info(f"Moving {direction} at rate {rate}")

        # If duration specified, wait and then stop
        if duration is not None:
            time.sleep(duration)

            # Determine axis from direction
            axis = "alt" if direction in ["up", "down"] else "az"
            telescope.stop_motion(axis)

            print_success(f"Moved {direction} for {duration:.1f} seconds")
        else:
            print_info("Movement started (use 'nexstar move stop' to stop)")

    except Exception as e:
        print_error(f"Move failed: {e}")
        raise typer.Exit(code=1) from e


@app.command(rich_help_panel="Movement")
def stop(
    port: str | None = typer.Option(None, "--port", "-p", help="Serial port"),
    axis: Literal["az", "alt", "both"] = typer.Option("both", help="Axis to stop"),
) -> None:
    """
    Stop telescope motion on specified axis.

    Example:
        nexstar move stop
        nexstar move stop --axis az
        nexstar move stop --axis alt
    """
    try:
        telescope = ensure_connected(port)

        success = telescope.stop_motion(axis)
        if success:
            if axis == "both":
                print_success("Stopped all motion")
            else:
                print_success(f"Stopped {axis.upper()} axis")
        else:
            print_error(f"Failed to stop motion on {axis}")
            raise typer.Exit(code=1) from None

    except Exception as e:
        print_error(f"Stop failed: {e}")
        raise typer.Exit(code=1) from e

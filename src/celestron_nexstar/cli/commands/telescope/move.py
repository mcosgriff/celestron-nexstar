"""
Move Commands

Commands for manual telescope movement.
"""

from typing import Literal

import typer
from click import Context
from typer.core import TyperGroup

from celestron_nexstar.api.core.enums import Direction
from celestron_nexstar.cli.utils.output import print_error, print_info, print_success
from celestron_nexstar.cli.utils.state import ensure_connected, run_async


class SortedCommandsGroup(TyperGroup):
    """Custom Typer group that sorts commands alphabetically within each help panel."""

    def list_commands(self, ctx: Context) -> list[str]:
        """Return commands sorted alphabetically."""
        commands = super().list_commands(ctx)
        return sorted(commands)


app = typer.Typer(help="Manual movement commands", cls=SortedCommandsGroup)


@app.command(rich_help_panel="Movement")
def fixed(
    direction: Direction = typer.Argument(
        ..., help="Direction to move (up, down, left, right, up-left, up-right, down-left, down-right)"
    ),
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
        nexstar move fixed up-right --rate 5 --duration 1.0
    """
    if not 0 <= rate <= 9:
        print_error("Rate must be between 0 and 9")
        raise typer.Exit(code=1) from None

    try:
        import asyncio

        telescope = ensure_connected()

        # If duration specified, use move_for_time
        if duration is not None:
            # Run async function - this is a sync entry point, so asyncio.run() is safe
            success = asyncio.run(telescope.move_for_time(direction, duration, rate))
            if success:
                print_success(f"Moved {direction} for {duration:.1f} seconds at rate {rate}")
            else:
                print_error(f"Failed to move {direction}")
                raise typer.Exit(code=1) from None
        else:
            # Start continuous movement
            success = run_async(telescope.move_fixed(direction, rate))
            if not success:
                print_error(f"Failed to start movement {direction}")
                raise typer.Exit(code=1) from None

            print_info(f"Moving {direction} at rate {rate} (use 'nexstar move stop' to stop)")

    except Exception as e:
        print_error(f"Move failed: {e}")
        raise typer.Exit(code=1) from e


@app.command(rich_help_panel="Movement")
def step(
    direction: Direction = typer.Argument(
        ..., help="Direction to move (up, down, left, right, up-left, up-right, down-left, down-right)"
    ),
    rate: int = typer.Option(4, min=0, max=9, help="Movement rate (0-9, 0=slowest, 9=fastest)"),
) -> None:
    """
    Move telescope one step in the specified direction.

    This mimics a single button press on the NexStar hand controller.
    The step size depends on the rate - faster rates result in larger steps.

    Example:
        nexstar move step up --rate 5
        nexstar move step right --rate 7
        nexstar move step up-right --rate 4
    """
    if not 0 <= rate <= 9:
        print_error("Rate must be between 0 and 9")
        raise typer.Exit(code=1) from None

    try:
        import asyncio

        telescope = ensure_connected()

        # Run async function - this is a sync entry point, so asyncio.run() is safe
        success = asyncio.run(telescope.move_step(direction, rate))
        if success:
            print_success(f"Moved one step {direction} at rate {rate}")
        else:
            print_error(f"Failed to move step {direction}")
            raise typer.Exit(code=1) from None

    except Exception as e:
        print_error(f"Step move failed: {e}")
        raise typer.Exit(code=1) from e


@app.command(rich_help_panel="Movement")
def stop(
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
        telescope = ensure_connected()

        success = run_async(telescope.stop_motion(axis))
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

"""
Goto Commands

Commands for slewing telescope to target coordinates.
"""

import time

import typer
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from ..utils.output import console, print_error, print_info, print_success
from ..utils.state import ensure_connected


app = typer.Typer(help="Telescope slew (goto) commands")


@app.command()
def radec(
    port: str | None = typer.Option(None, "--port", "-p", help="Serial port"),
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
        telescope = ensure_connected(port)

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


@app.command()
def altaz(
    port: str | None = typer.Option(None, "--port", "-p", help="Serial port"),
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
        telescope = ensure_connected(port)

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


@app.command()
def cancel(
    port: str | None = typer.Option(None, "--port", "-p", help="Serial port"),
) -> None:
    """
    Cancel current goto operation.

    Example:
        nexstar goto cancel
    """
    try:
        telescope = ensure_connected(port)

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


@app.command()
def status(
    port: str | None = typer.Option(None, "--port", "-p", help="Serial port"),
) -> None:
    """
    Check if telescope is currently slewing.

    Example:
        nexstar goto status
    """
    try:
        telescope = ensure_connected(port)
        is_slewing = telescope.is_slewing()

        if is_slewing:
            console.print("[yellow]Telescope is slewing[/yellow]")
        else:
            console.print("[green]Telescope is stationary[/green]")

    except Exception as e:
        print_error(f"Failed to get status: {e}")
        raise typer.Exit(code=1) from e

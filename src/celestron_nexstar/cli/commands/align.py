"""
Align Commands

Commands for telescope alignment and sync.
"""

import typer

from ..utils.output import print_error, print_success, print_info
from ..utils.state import ensure_connected


app = typer.Typer(help="Alignment commands")


@app.command()
def sync(
    port: str | None = typer.Option(None, "--port", "-p", help="Serial port"),
    ra: float = typer.Option(..., "--ra", help="Right Ascension in hours (0-24)"),
    dec: float = typer.Option(..., "--dec", help="Declination in degrees (-90 to +90)"),
) -> None:
    """
    Sync telescope position to specified RA/Dec coordinates.

    This tells the telescope that it is currently pointing at the
    specified coordinates, which is used for alignment. First manually
    center a known star, then sync to its coordinates.

    Example:
        # After manually centering Polaris:
        nexstar align sync --ra 2.5303 --dec 89.2641

        # After centering Vega:
        nexstar align sync --ra 18.6156 --dec 38.7836
    """
    # Validate coordinates
    if not 0 <= ra <= 24:
        print_error("RA must be between 0 and 24 hours")
        raise typer.Exit(code=1)
    if not -90 <= dec <= 90:
        print_error("Dec must be between -90 and +90 degrees")
        raise typer.Exit(code=1)

    try:
        telescope = ensure_connected(port)

        print_info(f"Syncing to RA {ra:.4f}h, Dec {dec:+.4f}°")

        success = telescope.sync_ra_dec(ra, dec)
        if success:
            print_success(f"Synced to RA {ra:.4f}h, Dec {dec:+.4f}°")
            print_info("Alignment updated. You may want to sync on additional stars for better accuracy.")
        else:
            print_error("Failed to sync position")
            raise typer.Exit(code=1)

    except Exception as e:
        print_error(f"Sync failed: {e}")
        raise typer.Exit(code=1)

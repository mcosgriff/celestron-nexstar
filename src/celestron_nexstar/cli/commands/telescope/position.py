"""
Position Commands

Commands for querying telescope position.
"""

import time
from typing import Literal

import typer
from click import Context
from rich.live import Live
from rich.table import Table
from typer.core import TyperGroup

from celestron_nexstar.cli.utils.output import (
    console,
    format_dec,
    format_ra,
    print_error,
    print_json,
    print_position_table,
)
from celestron_nexstar.cli.utils.state import ensure_connected


class SortedCommandsGroup(TyperGroup):
    """Custom Typer group that sorts commands alphabetically within each help panel."""

    def list_commands(self, ctx: Context) -> list[str]:
        """Return commands sorted alphabetically."""
        commands = super().list_commands(ctx)
        return sorted(commands)


app = typer.Typer(help="Position query commands", cls=SortedCommandsGroup)


@app.command("get", rich_help_panel="Query")
def get_position(
    port: str | None = typer.Option(None, "--port", "-p", help="Serial port"),
    format_output: Literal["pretty", "json", "csv", "dms", "hms"] = typer.Option(
        "pretty", "--format", "-f", help="Output format"
    ),
    watch: bool = typer.Option(False, "--watch", "-w", help="Continuously update position"),
    interval: float = typer.Option(1.0, help="Update interval for watch mode (seconds)"),
) -> None:
    """
    Get current telescope position (RA/Dec and Alt/Az).

    Example:
        nexstar position get
        nexstar position get --format json
        nexstar position get --watch --interval 2.0
    """
    try:
        telescope = ensure_connected()

        if watch:
            # Watch mode - continuously update
            try:
                with Live(console=console, refresh_per_second=4) as live:
                    while True:
                        # Get both coordinate systems
                        radec = telescope.get_position_ra_dec()
                        altaz = telescope.get_position_alt_az()

                        # Create table for live display
                        table = Table(title="Telescope Position (Live)", show_header=True, header_style="bold magenta")
                        table.add_column("Coordinate System", style="cyan")
                        table.add_column("Value", style="green")

                        table.add_row("Right Ascension", format_ra(radec.ra_hours))
                        table.add_row("Declination", format_dec(radec.dec_degrees))
                        table.add_row("Azimuth", f"{altaz.azimuth:.4f}°")
                        table.add_row("Altitude", f"{altaz.altitude:.4f}°")

                        live.update(table)
                        time.sleep(interval)

            except KeyboardInterrupt:
                console.print("\n[yellow]Stopped watching position[/yellow]")
                return

        else:
            # Single position query
            radec = telescope.get_position_ra_dec()
            altaz = telescope.get_position_alt_az()

            if format_output == "json":
                print_json(
                    {
                        "equatorial": {
                            "ra_hours": radec.ra_hours,
                            "dec_degrees": radec.dec_degrees,
                            "ra_formatted": format_ra(radec.ra_hours),
                            "dec_formatted": format_dec(radec.dec_degrees),
                        },
                        "horizontal": {"azimuth": altaz.azimuth, "altitude": altaz.altitude},
                    }
                )
            elif format_output == "csv":
                console.print(f"{radec.ra_hours},{radec.dec_degrees},{altaz.azimuth},{altaz.altitude}")
            elif format_output == "dms":
                console.print(f"RA: {format_ra(radec.ra_hours)}")
                console.print(f"Dec: {format_dec(radec.dec_degrees)}")
                console.print(f"Az: {altaz.azimuth:.4f}°, Alt: {altaz.altitude:.4f}°")
            elif format_output == "hms":
                console.print(f"RA: {format_ra(radec.ra_hours)}")
                console.print(f"Dec: {format_dec(radec.dec_degrees)}")
            else:  # pretty
                print_position_table(
                    ra_hours=radec.ra_hours,
                    dec_degrees=radec.dec_degrees,
                    azimuth=altaz.azimuth,
                    altitude=altaz.altitude,
                )

    except Exception as e:
        print_error(f"Failed to get position: {e}")
        raise typer.Exit(code=1) from e


@app.command(rich_help_panel="Query")
def radec(
    port: str | None = typer.Option(None, "--port", "-p", help="Serial port"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """
    Get RA/Dec position only.

    Example:
        nexstar position radec
        nexstar position radec --json
    """
    try:
        telescope = ensure_connected()
        coords = telescope.get_position_ra_dec()

        if json_output:
            print_json(
                {
                    "ra_hours": coords.ra_hours,
                    "dec_degrees": coords.dec_degrees,
                    "ra_formatted": format_ra(coords.ra_hours),
                    "dec_formatted": format_dec(coords.dec_degrees),
                }
            )
        else:
            print_position_table(ra_hours=coords.ra_hours, dec_degrees=coords.dec_degrees)

    except Exception as e:
        print_error(f"Failed to get RA/Dec: {e}")
        raise typer.Exit(code=1) from e


@app.command(rich_help_panel="Query")
def altaz(
    port: str | None = typer.Option(None, "--port", "-p", help="Serial port"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """
    Get Alt/Az position only.

    Example:
        nexstar position altaz
        nexstar position altaz --json
    """
    try:
        telescope = ensure_connected()
        coords = telescope.get_position_alt_az()

        if json_output:
            print_json({"azimuth": coords.azimuth, "altitude": coords.altitude})
        else:
            print_position_table(azimuth=coords.azimuth, altitude=coords.altitude)

    except Exception as e:
        print_error(f"Failed to get Alt/Az: {e}")
        raise typer.Exit(code=1) from e

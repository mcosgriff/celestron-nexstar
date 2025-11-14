"""
Comet Tracking Commands

Find bright comets visible from your location.
"""

import asyncio
from datetime import datetime
from pathlib import Path

import typer
from click import Context
from rich.console import Console
from rich.table import Table
from typer.core import TyperGroup

from celestron_nexstar.api.astronomy.comets import CometVisibility, get_upcoming_comets, get_visible_comets
from celestron_nexstar.api.database.models import get_db_session
from celestron_nexstar.api.location.observer import ObserverLocation, get_observer_location
from celestron_nexstar.cli.utils.export import FileConsole, create_file_console, export_to_text


class SortedCommandsGroup(TyperGroup):
    """Custom Typer group that sorts commands alphabetically within each help panel."""

    def list_commands(self, ctx: Context) -> list[str]:
        """Return commands sorted alphabetically."""
        commands = super().list_commands(ctx)
        return sorted(commands)


app = typer.Typer(help="Comet tracking commands", cls=SortedCommandsGroup)
console = Console()


def _generate_export_filename(command: str = "comets") -> Path:
    """Generate export filename for comet commands."""
    from celestron_nexstar.api.location.observer import get_observer_location

    location = get_observer_location()

    if location.name:
        location_short = location.name.lower().replace(" ", "_").replace(",", "").replace(".", "")
        location_short = location_short.replace("_(default)", "").replace("_observatory", "")
        location_short = location_short[:20]
    else:
        location_short = "unknown"

    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"nexstar_comets_{location_short}_{date_str}_{command}.txt"
    return Path(filename)


@app.command("visible")
def show_visible(
    months: int = typer.Option(12, "--months", "-m", help="Number of months ahead to search (default: 12)"),
    max_magnitude: float = typer.Option(8.0, "--max-mag", help="Maximum magnitude to include (default: 8.0)"),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Find bright comets visible from your location."""
    location = get_observer_location()
    if not location:
        console.print(
            "[red]Error: No observer location set. Use 'nexstar location set' to configure your location.[/red]"
        )
        raise typer.Exit(1)

    async def _get_comets() -> list[CometVisibility]:
        async with get_db_session() as db_session:
            return await get_visible_comets(db_session, location, months_ahead=months, max_magnitude=max_magnitude)

    comets = asyncio.run(_get_comets())

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("visible")
        file_console = create_file_console()
        _show_comets_content(file_console, location, comets, months)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_comets_content(console, location, comets, months)


@app.command("next")
def show_next(
    months: int = typer.Option(24, "--months", "-m", help="Number of months ahead to search (default: 24)"),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Find upcoming bright comets."""
    location = get_observer_location()
    if not location:
        console.print(
            "[red]Error: No observer location set. Use 'nexstar location set' to configure your location.[/red]"
        )
        raise typer.Exit(1)

    async def _get_comets() -> list[CometVisibility]:
        async with get_db_session() as db_session:
            return await get_upcoming_comets(db_session, location, months_ahead=months)

    comets = asyncio.run(_get_comets())

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("next")
        file_console = create_file_console()
        _show_comets_content(file_console, location, comets, months)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_comets_content(console, location, comets, months)


def _show_comets_content(
    output_console: Console | FileConsole, location: ObserverLocation, comets: list[CometVisibility], months: int
) -> None:
    """Display comet information."""
    from zoneinfo import ZoneInfo

    from timezonefinder import TimezoneFinder

    location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

    output_console.print(f"\n[bold cyan]Comet Visibility for {location_name}[/bold cyan]")
    output_console.print(f"[dim]Searching next {months} months[/dim]\n")

    if not comets:
        output_console.print("[yellow]No bright comets found in the forecast period.[/yellow]\n")
        output_console.print("[dim]Comet visibility is highly variable. Check regularly for new discoveries.[/dim]\n")
        return

    # Get timezone for formatting
    try:
        _tz_finder = TimezoneFinder()
        tz_name = _tz_finder.timezone_at(lat=location.latitude, lng=location.longitude)
        tz = ZoneInfo(tz_name) if tz_name else None
    except Exception:
        tz = None

    # Display comets in a table
    table = Table(show_header=True, header_style="bold")
    table.add_column("Date", style="cyan")
    table.add_column("Comet")
    table.add_column("Magnitude", justify="right")
    table.add_column("Visible", justify="center")
    table.add_column("Altitude", justify="right")

    for vis in comets:
        # Format date
        if tz:
            date_local = vis.date.astimezone(tz)
            date_str = date_local.strftime("%Y-%m-%d")
        else:
            date_str = vis.date.strftime("%Y-%m-%d UTC")

        # Format comet name
        comet_str = vis.comet.name

        # Format magnitude with color
        if vis.magnitude < 3.0:
            mag_str = f"[bold bright_green]{vis.magnitude:.1f}[/bold bright_green]"
        elif vis.magnitude < 6.0:
            mag_str = f"[green]{vis.magnitude:.1f}[/green]"
        elif vis.magnitude < 8.0:
            mag_str = f"[yellow]{vis.magnitude:.1f}[/yellow]"
        else:
            mag_str = f"[dim]{vis.magnitude:.1f}[/dim]"

        # Format visibility
        visible_str = "[green]✓ Yes[/green]" if vis.is_visible else "[dim]✗ No[/dim]"

        # Format altitude
        alt_str = f"{vis.altitude:.0f}°"

        table.add_row(date_str, comet_str, mag_str, visible_str, alt_str)

    output_console.print(table)

    # Show details
    output_console.print("\n[bold]Comet Details:[/bold]")
    for vis in comets[:10]:  # Show first 10
        if tz:
            date_local = vis.date.astimezone(tz)
            peak_local = vis.comet.peak_date.astimezone(tz)
            date_str = date_local.strftime("%B %d, %Y")
            peak_str = peak_local.strftime("%B %d, %Y")
        else:
            date_str = vis.date.strftime("%B %d, %Y UTC")
            peak_str = vis.comet.peak_date.strftime("%B %d, %Y UTC")

        output_console.print(f"\n  [bold]{vis.comet.name}[/bold] ({vis.comet.designation})")
        output_console.print(f"    Peak: {peak_str} at magnitude {vis.comet.peak_magnitude:.1f}")
        output_console.print(f"    {date_str}: Magnitude {vis.magnitude:.1f} at {vis.altitude:.0f}° altitude")
        if vis.comet.is_periodic and vis.comet.period_years:
            output_console.print(f"    Periodic: {vis.comet.period_years:.0f}-year orbit")
        output_console.print(f"    {vis.comet.notes}")
        output_console.print(f"    {vis.notes}")

    output_console.print("\n[bold]Viewing Tips:[/bold]")
    output_console.print("  • [green]Magnitude < 6.0: Potentially visible to naked eye under dark skies[/green]")
    output_console.print("  • [yellow]Magnitude 6.0-8.0: Visible with binoculars[/yellow]")
    output_console.print("  • [dim]Magnitude > 8.0: Requires telescope[/dim]")
    output_console.print("  • [green]Comets are best viewed away from city lights[/green]")
    output_console.print("  • [dim]Comet brightness can change unpredictably due to outbursts[/dim]")
    output_console.print("\n[dim]💡 Tip: Comet visibility is highly variable - check regularly for updates![/dim]\n")


if __name__ == "__main__":
    app()

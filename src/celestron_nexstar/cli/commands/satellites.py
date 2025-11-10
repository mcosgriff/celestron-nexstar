"""
Satellite Tracking Commands

Find bright satellite passes and flares.
"""

from datetime import UTC, datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from ...api.satellite_flares import get_bright_satellite_passes, get_starlink_passes
from ...api.observer import get_observer_location
from ...cli.utils.export import create_file_console, export_to_text

app = typer.Typer(help="Satellite tracking commands")
console = Console()


def _generate_export_filename(command: str = "satellites") -> Path:
    """Generate export filename for satellite commands."""
    from datetime import datetime
    from ...api.observer import get_observer_location

    location = get_observer_location()

    if location.name:
        location_short = location.name.lower().replace(" ", "_").replace(",", "").replace(".", "")
        location_short = location_short.replace("_(default)", "").replace("_observatory", "")
        location_short = location_short[:20]
    else:
        location_short = "unknown"

    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"nexstar_satellites_{location_short}_{date_str}_{command}.txt"
    return Path(filename)


@app.command("bright")
def show_bright(
    days: int = typer.Option(7, "--days", "-d", help="Number of days ahead to search (default: 7)"),
    min_magnitude: float = typer.Option(3.0, "--min-mag", help="Maximum magnitude to include (default: 3.0)"),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Find bright satellite passes (Hubble, Tiangong, etc.)."""
    location = get_observer_location()
    if not location:
        console.print("[red]Error: No observer location set. Use 'nexstar location set' to configure your location.[/red]")
        raise typer.Exit(1)

    passes = get_bright_satellite_passes(location, days=days, min_magnitude=min_magnitude)

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("bright")
        file_console = create_file_console()
        _show_passes_content(file_console, location, passes, days)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_passes_content(console, location, passes, days)


@app.command("starlink")
def show_starlink(
    days: int = typer.Option(7, "--days", "-d", help="Number of days ahead to search (default: 7)"),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Find Starlink train passes (simplified)."""
    location = get_observer_location()
    if not location:
        console.print("[red]Error: No observer location set. Use 'nexstar location set' to configure your location.[/red]")
        raise typer.Exit(1)

    passes = get_starlink_passes(location, days=days)

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("starlink")
        file_console = create_file_console()
        _show_passes_content(file_console, location, passes, days)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    if not passes:
        console.print("\n[yellow]Starlink tracking requires fetching TLE for many satellites.[/yellow]")
        console.print("[dim]Full implementation coming soon. Use 'nexstar satellites bright' for other bright satellites.[/dim]\n")
    else:
        _show_passes_content(console, location, passes, days)


def _show_passes_content(output_console: Console, location, passes: list, days: int) -> None:
    """Display satellite pass information."""
    from zoneinfo import ZoneInfo
    from timezonefinder import TimezoneFinder

    location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

    output_console.print(f"\n[bold cyan]Bright Satellite Passes for {location_name}[/bold cyan]")
    output_console.print(f"[dim]Searching next {days} days[/dim]\n")

    if not passes:
        output_console.print("[yellow]No bright satellite passes found in the forecast period.[/yellow]\n")
        return

    # Get timezone for formatting
    try:
        _tz_finder = TimezoneFinder()
        tz_name = _tz_finder.timezone_at(lat=location.latitude, lng=location.longitude)
        tz = ZoneInfo(tz_name) if tz_name else None
    except Exception:
        tz = None

    # Display passes in a table
    table = Table(expand=True, show_header=True, header_style="bold")
    table.add_column("Date", style="cyan", width=18)
    table.add_column("Satellite", width=25)
    table.add_column("Max Time", style="cyan", width=18)
    table.add_column("Altitude", justify="right", width=10)
    table.add_column("Magnitude", justify="right", width=12)

    for pass_obj in passes:
        # Format date
        if tz:
            date_local = pass_obj.rise_time.astimezone(tz)
            max_local = pass_obj.max_time.astimezone(tz)
            date_str = date_local.strftime("%Y-%m-%d")
            max_str = max_local.strftime("%I:%M %p")
        else:
            date_str = pass_obj.rise_time.strftime("%Y-%m-%d UTC")
            max_str = pass_obj.max_time.strftime("%I:%M %p UTC")

        # Format magnitude with color
        if pass_obj.magnitude < -1.0:
            mag_str = f"[bold bright_green]{pass_obj.magnitude:.1f}[/bold bright_green]"
        elif pass_obj.magnitude < 1.0:
            mag_str = f"[green]{pass_obj.magnitude:.1f}[/green]"
        elif pass_obj.magnitude < 3.0:
            mag_str = f"[yellow]{pass_obj.magnitude:.1f}[/yellow]"
        else:
            mag_str = f"[dim]{pass_obj.magnitude:.1f}[/dim]"

        # Format altitude
        alt_str = f"{pass_obj.max_altitude_deg:.0f}°"

        table.add_row(date_str, pass_obj.name, max_str, alt_str, mag_str)

    output_console.print(table)

    # Show details
    output_console.print("\n[bold]Pass Details:[/bold]")
    for pass_obj in passes[:10]:  # Show first 10
        if tz:
            rise_local = pass_obj.rise_time.astimezone(tz)
            max_local = pass_obj.max_time.astimezone(tz)
            set_local = pass_obj.set_time.astimezone(tz)
            rise_str = rise_local.strftime("%I:%M %p")
            max_str = max_local.strftime("%I:%M %p")
            set_str = set_local.strftime("%I:%M %p")
        else:
            rise_str = pass_obj.rise_time.strftime("%I:%M %p UTC")
            max_str = pass_obj.max_time.strftime("%I:%M %p UTC")
            set_str = pass_obj.set_time.strftime("%I:%M %p UTC")

        duration = (pass_obj.set_time - pass_obj.rise_time).total_seconds() / 60.0

        output_console.print(f"\n  [bold]{pass_obj.name}[/bold]")
        output_console.print(f"    Rise: {rise_str} → Max: {max_str} ({pass_obj.max_altitude_deg:.0f}°) → Set: {set_str}")
        output_console.print(f"    Duration: {duration:.0f} minutes, Magnitude: {pass_obj.magnitude:.1f}")
        output_console.print(f"    {pass_obj.notes}")

    output_console.print("\n[bold]Viewing Tips:[/bold]")
    output_console.print("  • [green]Bright satellites are visible to naked eye[/green]")
    output_console.print("  • [yellow]Look for steady moving 'stars' crossing the sky[/yellow]")
    output_console.print("  • [dim]Satellites move steadily (unlike aircraft which blink)[/dim]")
    output_console.print("  • [green]Best viewing when sky is dark and satellite is sunlit[/green]")
    output_console.print("\n[dim]💡 Tip: Use 'nexstar iss passes' for International Space Station passes![/dim]\n")


if __name__ == "__main__":
    app()


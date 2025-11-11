"""
ISS Pass Prediction Commands

Find International Space Station passes visible from your location.
"""

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from ...api.compass import azimuth_to_compass_8point
from ...api.iss_tracking import ISSPass, get_iss_passes_cached
from ...api.models import get_db_session
from ...api.observer import ObserverLocation, get_observer_location
from ...cli.utils.export import FileConsole, create_file_console, export_to_text


app = typer.Typer(help="International Space Station pass predictions")
console = Console()


def _generate_export_filename(command: str = "iss") -> Path:
    """Generate export filename for ISS commands."""
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
    filename = f"nexstar_iss_{location_short}_{date_str}_{command}.txt"
    return Path(filename)


def _format_local_time(dt: datetime, lat: float, lon: float) -> str:
    """Format datetime in local timezone."""
    from zoneinfo import ZoneInfo

    from timezonefinder import TimezoneFinder

    try:
        tz_finder = TimezoneFinder()
        tz_name = tz_finder.timezone_at(lat=lat, lng=lon)
        if tz_name:
            tz = ZoneInfo(tz_name)
            local_dt = dt.astimezone(tz)
            return local_dt.strftime("%I:%M %p")
    except Exception:
        pass

    return dt.strftime("%H:%M UTC")


@app.command("passes")
def show_passes(
    days: int = typer.Option(7, "--days", "-d", help="Number of days ahead to search (default: 7)"),
    min_altitude: float = typer.Option(10.0, "--min-alt", help="Minimum peak altitude in degrees (default: 10.0)"),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Find ISS passes visible from your location."""
    location = get_observer_location()
    if not location:
        console.print(
            "[red]Error: No observer location set. Use 'nexstar location set' to configure your location.[/red]"
        )
        raise typer.Exit(1)

    now = datetime.now(UTC)

    with get_db_session() as db:
        iss_passes = asyncio.run(
            get_iss_passes_cached(
                location.latitude,
                location.longitude,
                start_time=now,
                days=days,
                min_altitude_deg=min_altitude,
                db_session=db,
            )
        )

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("passes")
        file_console = create_file_console()
        _show_passes_content(file_console, location, iss_passes, days, min_altitude)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_passes_content(console, location, iss_passes, days, min_altitude)


def _show_passes_content(
    output_console: Console | FileConsole,
    location: ObserverLocation,
    iss_passes: list[ISSPass],
    days: int,
    min_altitude: float,
) -> None:
    """Display ISS pass information."""
    location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

    output_console.print(f"\n[bold cyan]ISS Visible Passes for {location_name}[/bold cyan]")
    output_console.print(f"[dim]Searching next {days} days (minimum altitude: {min_altitude:.0f}°)[/dim]\n")

    if not iss_passes:
        output_console.print("[yellow]No visible ISS passes found in the forecast period.[/yellow]\n")
        return

    # Filter to visible passes only
    visible_passes = [p for p in iss_passes if p.is_visible]

    if not visible_passes:
        output_console.print("[yellow]No visible ISS passes (all passes are in Earth's shadow).[/yellow]\n")
        return

    # Display passes in a table
    table = Table(show_header=True, header_style="bold")
    table.add_column("Date", style="cyan")
    table.add_column("Rise Time", style="green")
    table.add_column("Max Alt", justify="right")
    table.add_column("Path", style="dim")
    table.add_column("Duration", justify="right")
    table.add_column("Quality")

    for iss_pass in visible_passes[:20]:  # Show first 20
        rise_time_str = _format_local_time(iss_pass.rise_time, location.latitude, location.longitude)
        date_str = iss_pass.rise_time.strftime("%a %b %d")

        # Format path
        path_str = f"{azimuth_to_compass_8point(iss_pass.rise_azimuth_deg)} → {azimuth_to_compass_8point(iss_pass.max_azimuth_deg)} ({iss_pass.max_altitude_deg:.0f}°) → {azimuth_to_compass_8point(iss_pass.set_azimuth_deg)}"

        duration_min = iss_pass.duration_seconds // 60
        duration_str = f"{duration_min}m {iss_pass.duration_seconds % 60}s"

        quality = iss_pass.quality_rating

        table.add_row(
            date_str,
            rise_time_str,
            f"{iss_pass.max_altitude_deg:.0f}°",
            path_str,
            duration_str,
            quality,
        )

    output_console.print(table)

    # Show details for best passes
    excellent_passes = [p for p in visible_passes if p.max_altitude_deg >= 50]
    if excellent_passes:
        output_console.print("\n[bold]Excellent Passes (≥50° altitude):[/bold]")
        for iss_pass in excellent_passes[:5]:  # Show first 5
            rise_time_str = _format_local_time(iss_pass.rise_time, location.latitude, location.longitude)
            max_time_str = _format_local_time(iss_pass.max_time, location.latitude, location.longitude)
            set_time_str = _format_local_time(iss_pass.set_time, location.latitude, location.longitude)

            output_console.print(f"\n  [bold]{iss_pass.rise_time.strftime('%B %d, %Y')}[/bold]")
            duration_min = iss_pass.duration_seconds // 60
            quality = iss_pass.quality_rating

            output_console.print(
                f"    Rise: {rise_time_str} from {azimuth_to_compass_8point(iss_pass.rise_azimuth_deg)}"
            )
            output_console.print(
                f"    Max: {max_time_str} at {iss_pass.max_altitude_deg:.0f}° ({azimuth_to_compass_8point(iss_pass.max_azimuth_deg)})"
            )
            output_console.print(f"    Set: {set_time_str} to {azimuth_to_compass_8point(iss_pass.set_azimuth_deg)}")
            output_console.print(
                f"    Duration: {duration_min}m {iss_pass.duration_seconds % 60}s | Quality: {quality}"
            )

    output_console.print("\n[bold]Viewing Tips:[/bold]")
    output_console.print("  • [green]ISS is visible to naked eye - no equipment needed![/green]")
    output_console.print("  • [yellow]Look for a bright, steady-moving 'star' crossing the sky[/yellow]")
    output_console.print("  • [dim]ISS moves faster than aircraft and doesn't blink[/dim]")
    output_console.print("  • [green]Best viewing when sky is dark and ISS is sunlit[/green]")
    output_console.print("  • [dim]Use binoculars for enhanced viewing of solar panels[/dim]")
    output_console.print("\n[dim]💡 Tip: ISS is the third brightest object in the sky (after Sun and Moon)![/dim]\n")


if __name__ == "__main__":
    app()

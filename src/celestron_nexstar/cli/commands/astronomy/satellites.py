"""
Satellite Tracking Commands

Find bright satellite passes and flares.
"""

from datetime import datetime
from pathlib import Path

import typer
from click import Context
from rich.console import Console
from rich.table import Table
from typer.core import TyperGroup

from celestron_nexstar.api.events.satellite_flares import (
    SatellitePass,
    get_bright_satellite_passes,
    get_starlink_passes,
    get_stations_passes,
    get_visual_passes,
)
from celestron_nexstar.api.location.observer import ObserverLocation, get_observer_location
from celestron_nexstar.cli.utils.export import FileConsole, create_file_console, export_to_text


class SortedCommandsGroup(TyperGroup):
    """Custom Typer group that sorts commands alphabetically within each help panel."""

    def list_commands(self, ctx: Context) -> list[str]:
        """Return commands sorted alphabetically."""
        commands = super().list_commands(ctx)
        return sorted(commands)


app = typer.Typer(help="Satellite tracking commands", cls=SortedCommandsGroup)
console = Console()


def _generate_export_filename(command: str = "satellites") -> Path:
    """Generate export filename for satellite commands."""
    from celestron_nexstar.api.location.observer import get_observer_location

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
        console.print(
            "[red]Error: No observer location set. Use 'nexstar location set' to configure your location.[/red]"
        )
        raise typer.Exit(1)

    passes = get_bright_satellite_passes(location, days=days, min_magnitude=min_magnitude)

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("bright")
        file_console = create_file_console()
        _show_bright_passes_content(file_console, location, passes, days)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_bright_passes_content(console, location, passes, days)


@app.command("starlink")
def show_starlink(
    days: int = typer.Option(7, "--days", "-d", help="Number of days ahead to search (default: 7)"),
    min_altitude: float = typer.Option(10.0, "--min-alt", help="Minimum peak altitude in degrees (default: 10.0)"),
    max_passes: int = typer.Option(50, "--max-passes", help="Maximum number of passes to return (default: 50)"),
    all_passes: bool = typer.Option(
        False, "--all", "-a", help="Show all passes including non-visible ones (default: only visible)"
    ),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Find Starlink train passes."""
    location = get_observer_location()
    if not location:
        console.print(
            "[red]Error: No observer location set. Use 'nexstar location set' to configure your location.[/red]"
        )
        raise typer.Exit(1)

    # Get database session for caching TLE data
    import asyncio

    async def _get_passes() -> list[SatellitePass]:
        # get_starlink_passes is sync and expects a sync Session, so pass None to let it create its own
        return get_starlink_passes(
            location, days=days, min_altitude_deg=min_altitude, max_passes=max_passes, db_session=None
        )

    passes = asyncio.run(_get_passes())

    # Filter to visible passes only unless --all flag is set
    visible_passes = [p for p in passes if p.is_visible] if not all_passes else passes

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("starlink")
        file_console = create_file_console()
        _show_starlink_passes_content(
            file_console, location, visible_passes, days, all_passes=all_passes, total_passes=passes
        )
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    if not visible_passes:
        if passes:
            console.print("\n[yellow]No visible Starlink passes found in the forecast period.[/yellow]")
            console.print(f"[dim]Found {len(passes)} total pass(es), but none are visible.[/dim]")
            console.print("[dim]Use --all flag to see all passes including non-visible ones.[/dim]\n")
        else:
            console.print("\n[yellow]No Starlink passes found in the forecast period.[/yellow]")
            console.print("[dim]Try increasing the search window with --days option.[/dim]\n")
    else:
        _show_starlink_passes_content(
            console, location, visible_passes, days, all_passes=all_passes, total_passes=passes
        )


def _show_bright_passes_content(
    output_console: Console | FileConsole, location: ObserverLocation, passes: list[SatellitePass], days: int
) -> None:
    """Display bright satellite pass information grouped by satellite."""
    from collections import defaultdict
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

    # Group passes by satellite name
    passes_by_satellite: dict[str, list[SatellitePass]] = defaultdict(list)
    for pass_obj in passes:
        passes_by_satellite[pass_obj.name].append(pass_obj)

    # Sort satellites by name
    sorted_satellites = sorted(passes_by_satellite.keys())

    # Display a table for each satellite
    for satellite_name in sorted_satellites:
        satellite_passes = passes_by_satellite[satellite_name]
        # Sort passes by rise time
        satellite_passes.sort(key=lambda p: p.rise_time)

        output_console.print(f"\n[bold yellow]{satellite_name}[/bold yellow]")
        output_console.print(f"[dim]{len(satellite_passes)} pass(es) found[/dim]\n")

        # Create table for this satellite
        table = Table(show_header=True, header_style="bold", show_lines=False)
        table.add_column("Date", style="cyan", width=12)
        table.add_column("Rise", style="cyan", width=10)
        table.add_column("Max", style="cyan", width=10)
        table.add_column("Set", style="cyan", width=10)
        table.add_column("Max Alt", justify="right", width=8)
        table.add_column("Mag", justify="right", width=6)
        table.add_column("Duration", justify="right", width=10)

        for pass_obj in satellite_passes:
            # Format dates and times
            if tz:
                rise_local = pass_obj.rise_time.astimezone(tz)
                max_local = pass_obj.max_time.astimezone(tz)
                set_local = pass_obj.set_time.astimezone(tz)
                date_str = rise_local.strftime("%Y-%m-%d")
                rise_str = rise_local.strftime("%I:%M %p")
                max_str = max_local.strftime("%I:%M %p")
                set_str = set_local.strftime("%I:%M %p")
            else:
                date_str = pass_obj.rise_time.strftime("%Y-%m-%d")
                rise_str = pass_obj.rise_time.strftime("%I:%M %p")
                max_str = pass_obj.max_time.strftime("%I:%M %p")
                set_str = pass_obj.set_time.strftime("%I:%M %p")

            # Format magnitude with color
            if pass_obj.magnitude < -1.0:
                mag_str = f"[bold bright_green]{pass_obj.magnitude:.2f}[/bold bright_green]"
            elif pass_obj.magnitude < 1.0:
                mag_str = f"[green]{pass_obj.magnitude:.2f}[/green]"
            elif pass_obj.magnitude < 3.0:
                mag_str = f"[yellow]{pass_obj.magnitude:.2f}[/yellow]"
            else:
                mag_str = f"[dim]{pass_obj.magnitude:.2f}[/dim]"

            # Format altitude
            alt_str = f"{pass_obj.max_altitude_deg:.0f}°"

            # Format duration
            duration_min = (pass_obj.set_time - pass_obj.rise_time).total_seconds() / 60.0
            duration_str = f"{duration_min:.0f}m"

            table.add_row(date_str, rise_str, max_str, set_str, alt_str, mag_str, duration_str)

        output_console.print(table)

    # Summary
    total_passes = len(passes)
    total_satellites = len(sorted_satellites)
    output_console.print("\n[bold]Summary:[/bold]")
    output_console.print(f"  [dim]Total satellites:[/dim] {total_satellites}")
    output_console.print(f"  [dim]Total passes:[/dim] {total_passes}")

    output_console.print("\n[bold]Viewing Tips:[/bold]")
    output_console.print("  • [green]Bright satellites are visible to naked eye[/green]")
    output_console.print("  • [yellow]Look for steady moving 'stars' crossing the sky[/yellow]")
    output_console.print("  • [dim]Satellites move steadily (unlike aircraft which blink)[/dim]")
    output_console.print("  • [green]Best viewing when sky is dark and satellite is sunlit[/green]")
    output_console.print("\n[dim]💡 Tip: Use 'nexstar iss passes' for International Space Station passes![/dim]\n")


def _show_starlink_passes_content(
    output_console: Console | FileConsole,
    location: ObserverLocation,
    passes: list[SatellitePass],
    days: int,
    all_passes: bool = False,
    total_passes: list[SatellitePass] | None = None,
) -> None:
    """Display Starlink satellite pass information grouped by satellite."""
    from collections import defaultdict
    from zoneinfo import ZoneInfo

    from timezonefinder import TimezoneFinder

    location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

    output_console.print(f"\n[bold cyan]Starlink Satellite Passes for {location_name}[/bold cyan]")
    output_console.print(f"[dim]Searching next {days} days[/dim]\n")

    if not passes:
        output_console.print("[yellow]No Starlink passes found in the forecast period.[/yellow]\n")
        return

    # Calculate visible count
    if total_passes is None:
        total_passes = passes
    visible_count = sum(1 for p in total_passes if p.is_visible)

    # Get timezone for formatting
    try:
        _tz_finder = TimezoneFinder()
        tz_name = _tz_finder.timezone_at(lat=location.latitude, lng=location.longitude)
        tz = ZoneInfo(tz_name) if tz_name else None
    except Exception:
        tz = None

    # Group passes by satellite name
    passes_by_satellite: dict[str, list[SatellitePass]] = defaultdict(list)
    for pass_obj in passes:
        passes_by_satellite[pass_obj.name].append(pass_obj)

    # Sort satellites by name
    sorted_satellites = sorted(passes_by_satellite.keys())

    # Display a table for each satellite
    for satellite_name in sorted_satellites:
        satellite_passes = passes_by_satellite[satellite_name]
        # Sort passes by rise time
        satellite_passes.sort(key=lambda p: p.rise_time)

        output_console.print(f"\n[bold yellow]{satellite_name}[/bold yellow]")
        # Count visible passes for this satellite
        satellite_visible_count = sum(1 for p in satellite_passes if p.is_visible)
        if all_passes and satellite_visible_count < len(satellite_passes):
            output_console.print(
                f"[dim]{len(satellite_passes)} pass(es) found, {satellite_visible_count} visible[/dim]\n"
            )
        else:
            output_console.print(f"[dim]{len(satellite_passes)} pass(es) found[/dim]\n")

        # Create table for this satellite
        table = Table(show_header=True, header_style="bold", show_lines=False)
        table.add_column("Date", style="cyan", width=12)
        table.add_column("Rise", style="cyan", width=10)
        table.add_column("Max", style="cyan", width=10)
        table.add_column("Set", style="cyan", width=10)
        table.add_column("Max Alt", justify="right", width=8)
        table.add_column("Mag", justify="right", width=6)
        table.add_column("Duration", justify="right", width=10)
        table.add_column("Visible", width=8)

        for pass_obj in satellite_passes:
            # Format dates and times
            if tz:
                rise_local = pass_obj.rise_time.astimezone(tz)
                max_local = pass_obj.max_time.astimezone(tz)
                set_local = pass_obj.set_time.astimezone(tz)
                date_str = rise_local.strftime("%Y-%m-%d")
                rise_str = rise_local.strftime("%I:%M %p")
                max_str = max_local.strftime("%I:%M %p")
                set_str = set_local.strftime("%I:%M %p")
            else:
                date_str = pass_obj.rise_time.strftime("%Y-%m-%d")
                rise_str = pass_obj.rise_time.strftime("%I:%M %p")
                max_str = pass_obj.max_time.strftime("%I:%M %p")
                set_str = pass_obj.set_time.strftime("%I:%M %p")

            # Format magnitude with color
            if pass_obj.magnitude < -1.0:
                mag_str = f"[bold bright_green]{pass_obj.magnitude:.2f}[/bold bright_green]"
            elif pass_obj.magnitude < 1.0:
                mag_str = f"[green]{pass_obj.magnitude:.2f}[/green]"
            elif pass_obj.magnitude < 3.0:
                mag_str = f"[yellow]{pass_obj.magnitude:.2f}[/yellow]"
            elif pass_obj.magnitude < 6.0:
                mag_str = f"[dim]{pass_obj.magnitude:.2f}[/dim]"
            else:
                mag_str = f"[dim red]{pass_obj.magnitude:.2f}[/dim red]"

            # Format altitude
            alt_str = f"{pass_obj.max_altitude_deg:.0f}°"

            # Format duration
            duration_min = (pass_obj.set_time - pass_obj.rise_time).total_seconds() / 60.0
            duration_str = f"{duration_min:.0f}m"

            # Format visibility
            visible_str = "[green]Yes[/green]" if pass_obj.is_visible else "[dim red]No[/dim red]"

            table.add_row(date_str, rise_str, max_str, set_str, alt_str, mag_str, duration_str, visible_str)

        output_console.print(table)

    # Summary
    displayed_passes = len(passes)
    total_satellites = len(sorted_satellites)
    # total_passes is guaranteed to be not None after line 280
    total_count = len(total_passes)
    output_console.print("\n[bold]Summary:[/bold]")
    output_console.print(f"  [dim]Total satellites:[/dim] {total_satellites}")
    if total_count > visible_count:
        output_console.print(f"  [dim]Total passes:[/dim] {total_count} pass(es) found, {visible_count} visible")
    else:
        output_console.print(f"  [dim]Total passes:[/dim] {displayed_passes}")

    output_console.print("\n[bold]Viewing Tips:[/bold]")
    output_console.print("  • [green]Starlink satellites are visible when sunlit[/green]")
    output_console.print("  • [yellow]Look for steady moving 'stars' crossing the sky[/yellow]")
    output_console.print("  • [dim]Satellites move steadily (unlike aircraft which blink)[/dim]")
    output_console.print("  • [green]Best viewing when sky is dark and satellite is sunlit[/green]")
    output_console.print("  • [dim]Starlink trains may appear as a line of satellites[/dim]")
    output_console.print("\n[dim]💡 Tip: Use 'nexstar satellites bright' for other bright satellites![/dim]\n")


@app.command("stations")
def show_stations(
    days: int = typer.Option(7, "--days", "-d", help="Number of days ahead to search (default: 7)"),
    min_altitude: float = typer.Option(10.0, "--min-alt", help="Minimum peak altitude in degrees (default: 10.0)"),
    max_passes: int = typer.Option(50, "--max-passes", help="Maximum number of passes to return (default: 50)"),
    all_passes: bool = typer.Option(
        False, "--all", "-a", help="Show all passes including non-visible ones (default: only visible)"
    ),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Find space station passes (ISS, Tiangong, etc.)."""
    location = get_observer_location()
    if not location:
        console.print(
            "[red]Error: No observer location set. Use 'nexstar location set' to configure your location.[/red]"
        )
        raise typer.Exit(1)

    # Get database session for caching TLE data
    import asyncio

    async def _get_passes() -> list[SatellitePass]:
        # get_stations_passes is sync and expects a sync Session, so pass None to let it create its own
        return get_stations_passes(
            location, days=days, min_altitude_deg=min_altitude, max_passes=max_passes, db_session=None
        )

    passes = asyncio.run(_get_passes())

    # Filter to visible passes only unless --all flag is set
    visible_passes = [p for p in passes if p.is_visible] if not all_passes else passes

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("stations")
        file_console = create_file_console()
        _show_starlink_passes_content(
            file_console, location, visible_passes, days, all_passes=all_passes, total_passes=passes
        )
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    if not visible_passes:
        if passes:
            console.print("\n[yellow]No visible space station passes found in the forecast period.[/yellow]")
            console.print(f"[dim]Found {len(passes)} total pass(es), but none are visible.[/dim]")
            console.print("[dim]Use --all flag to see all passes including non-visible ones.[/dim]\n")
        else:
            console.print("\n[yellow]No space station passes found in the forecast period.[/yellow]")
            console.print("[dim]Try increasing the search window with --days option.[/dim]\n")
    else:
        _show_starlink_passes_content(
            console, location, visible_passes, days, all_passes=all_passes, total_passes=passes
        )


@app.command("visual")
def show_visual(
    days: int = typer.Option(7, "--days", "-d", help="Number of days ahead to search (default: 7)"),
    min_altitude: float = typer.Option(10.0, "--min-alt", help="Minimum peak altitude in degrees (default: 10.0)"),
    max_passes: int = typer.Option(100, "--max-passes", help="Maximum number of passes to return (default: 100)"),
    all_passes: bool = typer.Option(
        False, "--all", "-a", help="Show all passes including non-visible ones (default: only visible)"
    ),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Find visually observable satellite passes."""
    location = get_observer_location()
    if not location:
        console.print(
            "[red]Error: No observer location set. Use 'nexstar location set' to configure your location.[/red]"
        )
        raise typer.Exit(1)

    # Get database session for caching TLE data
    import asyncio

    async def _get_passes() -> list[SatellitePass]:
        # get_visual_passes is now async, so await it directly
        return await get_visual_passes(
            location, days=days, min_altitude_deg=min_altitude, max_passes=max_passes, db_session=None
        )

    passes = asyncio.run(_get_passes())

    # Filter to visible passes only unless --all flag is set
    visible_passes = [p for p in passes if p.is_visible] if not all_passes else passes

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("visual")
        file_console = create_file_console()
        _show_starlink_passes_content(
            file_console, location, visible_passes, days, all_passes=all_passes, total_passes=passes
        )
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    if not visible_passes:
        if passes:
            console.print("\n[yellow]No visible satellite passes found in the forecast period.[/yellow]")
            console.print(f"[dim]Found {len(passes)} total pass(es), but none are visible.[/dim]")
            console.print("[dim]Use --all flag to see all passes including non-visible ones.[/dim]\n")
        else:
            console.print("\n[yellow]No visual satellite passes found in the forecast period.[/yellow]")
            console.print("[dim]Try increasing the search window with --days option.[/dim]\n")
    else:
        _show_starlink_passes_content(
            console, location, visible_passes, days, all_passes=all_passes, total_passes=passes
        )


if __name__ == "__main__":
    app()

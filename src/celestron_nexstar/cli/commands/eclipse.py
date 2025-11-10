"""
Eclipse Prediction Commands

Find upcoming lunar and solar eclipses visible from your location.
"""

from datetime import UTC, datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from ...api.eclipses import get_next_lunar_eclipse, get_next_solar_eclipse, get_upcoming_eclipses
from ...api.observer import get_observer_location
from ...cli.utils.export import create_file_console, export_to_text

app = typer.Typer(help="Eclipse prediction commands")
console = Console()


def _generate_export_filename(command: str = "eclipse") -> Path:
    """Generate export filename for eclipse commands."""
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
    filename = f"nexstar_eclipse_{location_short}_{date_str}_{command}.txt"
    return Path(filename)


def _format_eclipse_type(eclipse_type: str) -> str:
    """Format eclipse type with color."""
    colors = {
        "lunar_total": "[bold bright_green]Total Lunar[/bold bright_green]",
        "lunar_partial": "[green]Partial Lunar[/green]",
        "lunar_penumbral": "[dim]Penumbral Lunar[/dim]",
        "solar_total": "[bold bright_red]Total Solar[/bold bright_red]",
        "solar_partial": "[yellow]Partial Solar[/yellow]",
        "solar_annular": "[bold yellow]Annular Solar[/bold yellow]",
    }
    return colors.get(eclipse_type, eclipse_type)


@app.command("next")
def show_next(
    years: int = typer.Option(5, "--years", "-y", help="Number of years ahead to search (default: 5)"),
    eclipse_type: str | None = typer.Option(None, "--type", help="Filter by type: lunar or solar"),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Find next eclipses visible from your location."""
    location = get_observer_location()
    if not location:
        console.print("[red]Error: No observer location set. Use 'nexstar location set' to configure your location.[/red]")
        raise typer.Exit(1)

    # Get eclipses
    eclipses = get_upcoming_eclipses(location, years_ahead=years, eclipse_type=eclipse_type)

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("next")
        file_console = create_file_console()
        _show_eclipses_content(file_console, location, eclipses, years)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_eclipses_content(console, location, eclipses, years)


@app.command("lunar")
def show_lunar(
    years: int = typer.Option(5, "--years", "-y", help="Number of years ahead to search (default: 5)"),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Find next lunar eclipses visible from your location."""
    location = get_observer_location()
    if not location:
        console.print("[red]Error: No observer location set. Use 'nexstar location set' to configure your location.[/red]")
        raise typer.Exit(1)

    eclipses = get_next_lunar_eclipse(location, years_ahead=years)

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("lunar")
        file_console = create_file_console()
        _show_eclipses_content(file_console, location, eclipses, years)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_eclipses_content(console, location, eclipses, years)


@app.command("solar")
def show_solar(
    years: int = typer.Option(10, "--years", "-y", help="Number of years ahead to search (default: 10)"),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Find next solar eclipses visible from your location."""
    location = get_observer_location()
    if not location:
        console.print("[red]Error: No observer location set. Use 'nexstar location set' to configure your location.[/red]")
        raise typer.Exit(1)

    eclipses = get_next_solar_eclipse(location, years_ahead=years)

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("solar")
        file_console = create_file_console()
        _show_eclipses_content(file_console, location, eclipses, years)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_eclipses_content(console, location, eclipses, years)


def _show_eclipses_content(output_console: Console, location, eclipses: list, years: int) -> None:
    """Display eclipse information."""
    from zoneinfo import ZoneInfo
    from timezonefinder import TimezoneFinder

    from ...api.observer import ObserverLocation

    _tz_finder = TimezoneFinder()

    location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

    output_console.print(f"\n[bold cyan]Upcoming Eclipses for {location_name}[/bold cyan]")
    output_console.print(f"[dim]Searching next {years} years[/dim]\n")

    if not eclipses:
        output_console.print("[yellow]No eclipses found in the forecast period.[/yellow]\n")
        return

    # Get timezone for formatting
    try:
        tz_name = _tz_finder.timezone_at(lat=location.latitude, lng=location.longitude)
        tz = ZoneInfo(tz_name) if tz_name else None
    except Exception:
        tz = None

    # Display eclipses in a table
    table = Table(expand=True, show_header=True, header_style="bold")
    table.add_column("Date", style="cyan", width=18)
    table.add_column("Type", width=20)
    table.add_column("Maximum Time", style="cyan", width=18)
    table.add_column("Visible", justify="center", width=10)
    table.add_column("Altitude", justify="right", width=10)
    table.add_column("Magnitude", justify="right", width=10)

    for eclipse in eclipses:
        # Format date
        if tz:
            date_local = eclipse.date.astimezone(tz)
            date_str = date_local.strftime("%Y-%m-%d")
            max_local = eclipse.maximum_time.astimezone(tz)
            max_str = max_local.strftime("%I:%M %p")
        else:
            date_str = eclipse.date.strftime("%Y-%m-%d UTC")
            max_str = eclipse.maximum_time.strftime("%I:%M %p UTC")

        # Format type
        type_str = _format_eclipse_type(eclipse.eclipse_type)

        # Format visibility
        if eclipse.is_visible:
            visible_str = "[green]✓ Yes[/green]"
        else:
            visible_str = "[dim]✗ No[/dim]"

        # Format altitude
        alt_str = f"{eclipse.altitude_at_maximum:.0f}°"

        # Format magnitude
        mag_str = f"{eclipse.magnitude:.2f}"

        table.add_row(date_str, type_str, max_str, visible_str, alt_str, mag_str)

    output_console.print(table)

    # Show details for visible eclipses
    visible_eclipses = [e for e in eclipses if e.is_visible]
    if visible_eclipses:
        output_console.print("\n[bold]Visible Eclipses Details:[/bold]")
        for eclipse in visible_eclipses[:5]:  # Show first 5
            if tz:
                date_local = eclipse.date.astimezone(tz)
                max_local = eclipse.maximum_time.astimezone(tz)
                date_str = date_local.strftime("%B %d, %Y")
                max_str = max_local.strftime("%I:%M %p")
                if eclipse.visibility_start:
                    start_local = eclipse.visibility_start.astimezone(tz)
                    start_str = start_local.strftime("%I:%M %p")
                else:
                    start_str = "—"
                if eclipse.visibility_end:
                    end_local = eclipse.visibility_end.astimezone(tz)
                    end_str = end_local.strftime("%I:%M %p")
                else:
                    end_str = "—"
            else:
                date_str = eclipse.date.strftime("%B %d, %Y UTC")
                max_str = eclipse.maximum_time.strftime("%I:%M %p UTC")
                start_str = eclipse.visibility_start.strftime("%I:%M %p UTC") if eclipse.visibility_start else "—"
                end_str = eclipse.visibility_end.strftime("%I:%M %p UTC") if eclipse.visibility_end else "—"

            output_console.print(f"\n  [bold]{_format_eclipse_type(eclipse.eclipse_type)}[/bold] - {date_str}")
            output_console.print(f"    Maximum: {max_str} at {eclipse.altitude_at_maximum:.0f}° altitude")
            if eclipse.visibility_start and eclipse.visibility_end:
                output_console.print(f"    Duration: {start_str} to {end_str} ({eclipse.duration_minutes:.0f} minutes)")
            output_console.print(f"    {eclipse.notes}")

    output_console.print("\n[bold]Viewing Tips:[/bold]")
    output_console.print("  • [green]Lunar eclipses are safe to view with naked eye or binoculars[/green]")
    output_console.print("  • [red]⚠ Solar eclipses require special eye protection - NEVER look directly at the sun[/red]")
    output_console.print("  • [yellow]For solar eclipses, use ISO 12312-2 certified eclipse glasses[/yellow]")
    output_console.print("  • [green]Check weather forecast for cloud cover during eclipse times[/green]")
    output_console.print("\n[dim]💡 Tip: Eclipses are rare events - plan ahead for the best viewing experience![/dim]\n")


if __name__ == "__main__":
    app()


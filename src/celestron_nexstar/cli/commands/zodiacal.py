"""
Zodiacal Light and Gegenschein Commands

Find best viewing times for zodiacal light and gegenschein.
"""

from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from ...api.observer import ObserverLocation, get_observer_location
from ...api.zodiacal_light import ZodiacalLightWindow, get_gegenschein_windows, get_zodiacal_light_windows
from ...cli.utils.export import FileConsole, create_file_console, export_to_text


app = typer.Typer(help="Zodiacal light and gegenschein viewing")
console = Console()


def _generate_export_filename(command: str = "zodiacal") -> Path:
    """Generate export filename for zodiacal commands."""
    from ...api.observer import get_observer_location

    location = get_observer_location()

    if location.name:
        location_short = location.name.lower().replace(" ", "_").replace(",", "").replace(".", "")
        location_short = location_short.replace("_(default)", "").replace("_observatory", "")
        location_short = location_short[:20]
    else:
        location_short = "unknown"

    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"nexstar_zodiacal_{location_short}_{date_str}_{command}.txt"
    return Path(filename)


@app.command("zodiacal-light")
def show_zodiacal_light(
    months: int = typer.Option(6, "--months", "-m", help="Number of months ahead to search (default: 6)"),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Find best viewing times for zodiacal light."""
    location = get_observer_location()
    if not location:
        console.print(
            "[red]Error: No observer location set. Use 'nexstar location set' to configure your location.[/red]"
        )
        raise typer.Exit(1)

    windows = get_zodiacal_light_windows(location, months_ahead=months)

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("zodiacal-light")
        file_console = create_file_console()
        _show_windows_content(file_console, location, windows, "Zodiacal Light", months)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_windows_content(console, location, windows, "Zodiacal Light", months)


@app.command("gegenschein")
def show_gegenschein(
    months: int = typer.Option(6, "--months", "-m", help="Number of months ahead to search (default: 6)"),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Find best viewing times for gegenschein."""
    location = get_observer_location()
    if not location:
        console.print(
            "[red]Error: No observer location set. Use 'nexstar location set' to configure your location.[/red]"
        )
        raise typer.Exit(1)

    windows = get_gegenschein_windows(location, months_ahead=months)

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("gegenschein")
        file_console = create_file_console()
        _show_windows_content(file_console, location, windows, "Gegenschein", months)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_windows_content(console, location, windows, "Gegenschein", months)


def _show_windows_content(
    output_console: Console | FileConsole,
    location: ObserverLocation,
    windows: list[ZodiacalLightWindow],
    phenomenon: str,
    months: int,
) -> None:
    """Display viewing window information."""
    from zoneinfo import ZoneInfo

    from timezonefinder import TimezoneFinder

    location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

    output_console.print(f"\n[bold cyan]{phenomenon} Viewing Windows for {location_name}[/bold cyan]")
    output_console.print(f"[dim]Searching next {months} months[/dim]\n")

    if not windows:
        output_console.print(
            f"[yellow]No {phenomenon.lower()} viewing windows found in the forecast period.[/yellow]\n"
        )
        return

    # Get timezone for formatting
    try:
        _tz_finder = TimezoneFinder()
        tz_name = _tz_finder.timezone_at(lat=location.latitude, lng=location.longitude)
        tz = ZoneInfo(tz_name) if tz_name else None
    except Exception:
        tz = None

    # Display windows in a table
    table = Table(expand=True, show_header=True, header_style="bold")
    table.add_column("Date", style="cyan", width=18)
    table.add_column("Type", width=12)
    table.add_column("Window", width=25)
    table.add_column("Quality", width=12)

    for window in windows[:30]:  # Show first 30
        # Format date
        if tz:
            date_local = window.date.astimezone(tz)
            start_local = window.start_time.astimezone(tz)
            end_local = window.end_time.astimezone(tz)
            date_str = date_local.strftime("%Y-%m-%d")
            window_str = f"{start_local.strftime('%I:%M %p')} - {end_local.strftime('%I:%M %p')}"
        else:
            date_str = window.date.strftime("%Y-%m-%d UTC")
            window_str = f"{window.start_time.strftime('%H:%M')} - {window.end_time.strftime('%H:%M')} UTC"

        # Format type
        type_str = window.window_type.capitalize()

        # Format quality with color
        quality_colors = {
            "excellent": "[bold bright_green]Excellent[/bold bright_green]",
            "good": "[green]Good[/green]",
            "fair": "[yellow]Fair[/yellow]",
            "poor": "[red]Poor[/red]",
        }
        quality_str = quality_colors.get(window.viewing_quality, window.viewing_quality)

        table.add_row(date_str, type_str, window_str, quality_str)

    output_console.print(table)

    # Show details
    output_console.print("\n[bold]Viewing Details:[/bold]")
    for window in windows[:10]:  # Show first 10
        if tz:
            date_local = window.date.astimezone(tz)
            start_local = window.start_time.astimezone(tz)
            end_local = window.end_time.astimezone(tz)
            date_str = date_local.strftime("%B %d, %Y")
            window_str = f"{start_local.strftime('%I:%M %p')} to {end_local.strftime('%I:%M %p')}"
        else:
            date_str = window.date.strftime("%B %d, %Y UTC")
            window_str = f"{window.start_time.strftime('%H:%M')} to {window.end_time.strftime('%H:%M')} UTC"

        output_console.print(f"\n  [bold]{date_str}[/bold] - {window.window_type.capitalize()}")
        output_console.print(f"    Window: {window_str}")
        output_console.print(f"    Quality: {window.viewing_quality.capitalize()} - {window.notes}")

    output_console.print("\n[bold]Viewing Tips:[/bold]")
    if phenomenon == "Zodiacal Light":
        output_console.print(
            "  • [green]Best seen 60-90 minutes after sunset (spring) or before sunrise (autumn)[/green]"
        )
        output_console.print("  • [yellow]Requires dark skies (Bortle 3 or better)[/yellow]")
        output_console.print("  • [dim]Look for a faint triangular glow along the ecliptic[/dim]")
        output_console.print("  • [green]Best when moon is below horizon[/green]")
    else:  # Gegenschein
        output_console.print("  • [green]Best seen around midnight when anti-sun point is highest[/green]")
        output_console.print("  • [yellow]Requires very dark skies (Bortle 2 or better)[/yellow]")
        output_console.print("  • [dim]Look for a faint oval glow opposite the sun[/dim]")
        output_console.print("  • [green]Best in autumn/winter months[/green]")
    output_console.print("\n[dim]💡 Tip: These phenomena are subtle - allow your eyes to fully dark-adapt![/dim]\n")


if __name__ == "__main__":
    app()

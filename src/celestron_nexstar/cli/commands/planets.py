"""
Planetary Events Commands

Find planetary conjunctions, oppositions, and other events.
"""

from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from ...api.observer import ObserverLocation, get_observer_location
from ...api.planetary_events import (
    PlanetaryEvent,
    get_planetary_conjunctions,
    get_planetary_oppositions,
)
from ...cli.utils.export import FileConsole, create_file_console, export_to_text


app = typer.Typer(help="Planetary events commands")
console = Console()


def _generate_export_filename(command: str = "planets") -> Path:
    """Generate export filename for planetary events commands."""
    from ...api.observer import get_observer_location

    location = get_observer_location()

    if location.name:
        location_short = location.name.lower().replace(" ", "_").replace(",", "").replace(".", "")
        location_short = location_short.replace("_(default)", "").replace("_observatory", "")
        location_short = location_short[:20]
    else:
        location_short = "unknown"

    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"nexstar_planets_{location_short}_{date_str}_{command}.txt"
    return Path(filename)


@app.command("conjunctions")
def show_conjunctions(
    months: int = typer.Option(12, "--months", "-m", help="Number of months ahead to search (default: 12)"),
    max_separation: float = typer.Option(
        5.0, "--max-separation", help="Maximum angular separation in degrees (default: 5.0)"
    ),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Find planetary conjunctions (planets appearing close together)."""
    location = get_observer_location()
    if not location:
        console.print(
            "[red]Error: No observer location set. Use 'nexstar location set' to configure your location.[/red]"
        )
        raise typer.Exit(1)

    conjunctions = get_planetary_conjunctions(location, max_separation=max_separation, months_ahead=months)

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("conjunctions")
        file_console = create_file_console()
        _show_conjunctions_content(file_console, location, conjunctions, months)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_conjunctions_content(console, location, conjunctions, months)


@app.command("oppositions")
def show_oppositions(
    years: int = typer.Option(5, "--years", "-y", help="Number of years ahead to search (default: 5)"),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Find planetary oppositions (best viewing times for outer planets)."""
    location = get_observer_location()
    if not location:
        console.print(
            "[red]Error: No observer location set. Use 'nexstar location set' to configure your location.[/red]"
        )
        raise typer.Exit(1)

    oppositions = get_planetary_oppositions(location, years_ahead=years)

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("oppositions")
        file_console = create_file_console()
        _show_oppositions_content(file_console, location, oppositions, years)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_oppositions_content(console, location, oppositions, years)


def _show_conjunctions_content(
    output_console: Console | FileConsole, location: ObserverLocation, conjunctions: list[PlanetaryEvent], months: int
) -> None:
    """Display conjunction information."""
    from zoneinfo import ZoneInfo

    from timezonefinder import TimezoneFinder

    location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

    output_console.print(f"\n[bold cyan]Planetary Conjunctions for {location_name}[/bold cyan]")
    output_console.print(f"[dim]Searching next {months} months[/dim]\n")

    if not conjunctions:
        output_console.print("[yellow]No conjunctions found in the forecast period.[/yellow]\n")
        return

    # Get timezone for formatting
    try:
        _tz_finder = TimezoneFinder()
        tz_name = _tz_finder.timezone_at(lat=location.latitude, lng=location.longitude)
        tz = ZoneInfo(tz_name) if tz_name else None
    except Exception:
        tz = None

    # Display conjunctions in a table
    table = Table(show_header=True, header_style="bold")
    table.add_column("Date", style="cyan")
    table.add_column("Planets")
    table.add_column("Separation", justify="right")
    table.add_column("Visible", justify="center")
    table.add_column("Altitude", justify="right")

    for event in conjunctions[:20]:  # Show first 20
        # Format date
        if tz:
            date_local = event.date.astimezone(tz)
            date_str = date_local.strftime("%Y-%m-%d %I:%M %p")
        else:
            date_str = event.date.strftime("%Y-%m-%d %H:%M UTC")

        # Format planets
        planet2_str = event.planet2.capitalize() if event.planet2 else "N/A"
        planets_str = f"{event.planet1.capitalize()} - {planet2_str}"

        # Format separation
        sep_str = f"{event.separation_degrees:.2f}°"

        # Format visibility
        visible_str = "[green]✓ Yes[/green]" if event.is_visible else "[dim]✗ No[/dim]"

        # Format altitude
        alt_str = f"{event.altitude_at_event:.0f}°"

        table.add_row(date_str, planets_str, sep_str, visible_str, alt_str)

    output_console.print(table)

    # Show details for visible conjunctions
    visible_conjunctions = [e for e in conjunctions if e.is_visible]
    if visible_conjunctions:
        output_console.print("\n[bold]Visible Conjunctions Details:[/bold]")
        for event in visible_conjunctions[:5]:  # Show first 5
            if tz:
                date_local = event.date.astimezone(tz)
                date_str = date_local.strftime("%B %d, %Y at %I:%M %p")
            else:
                date_str = event.date.strftime("%B %d, %Y at %H:%M UTC")

            planet2_str = event.planet2.capitalize() if event.planet2 else "N/A"
            output_console.print(f"\n  [bold]{event.planet1.capitalize()} - {planet2_str}[/bold] - {date_str}")
            output_console.print(
                f"    Separation: {event.separation_degrees:.2f}° at {event.altitude_at_event:.0f}° altitude"
            )
            output_console.print(f"    {event.notes}")

    output_console.print("\n[bold]Viewing Tips:[/bold]")
    output_console.print("  • Conjunctions are best viewed with binoculars or telescope")
    output_console.print("  • Look for planets appearing close together in the sky")
    output_console.print("  • Some conjunctions may be visible to the naked eye")
    output_console.print("\n[dim]💡 Tip: Conjunctions are great photo opportunities![/dim]\n")


def _show_oppositions_content(
    output_console: Console | FileConsole, location: ObserverLocation, oppositions: list[PlanetaryEvent], years: int
) -> None:
    """Display opposition information."""
    from zoneinfo import ZoneInfo

    from timezonefinder import TimezoneFinder

    location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

    output_console.print(f"\n[bold cyan]Planetary Oppositions for {location_name}[/bold cyan]")
    output_console.print(f"[dim]Searching next {years} years[/dim]\n")

    if not oppositions:
        output_console.print("[yellow]No oppositions found in the forecast period.[/yellow]\n")
        return

    # Get timezone for formatting
    try:
        _tz_finder = TimezoneFinder()
        tz_name = _tz_finder.timezone_at(lat=location.latitude, lng=location.longitude)
        tz = ZoneInfo(tz_name) if tz_name else None
    except Exception:
        tz = None

    # Display oppositions in a table
    table = Table(show_header=True, header_style="bold")
    table.add_column("Date", style="cyan")
    table.add_column("Planet")
    table.add_column("Elongation", justify="right")
    table.add_column("Visible", justify="center")
    table.add_column("Altitude", justify="right")

    for event in oppositions:
        # Format date
        if tz:
            date_local = event.date.astimezone(tz)
            date_str = date_local.strftime("%Y-%m-%d %I:%M %p")
        else:
            date_str = event.date.strftime("%Y-%m-%d %H:%M UTC")

        # Format planet
        planet_str = event.planet1.capitalize()

        # Format elongation (should be close to 180°)
        elong_str = f"{event.separation_degrees:.1f}°"

        # Format visibility
        visible_str = "[green]✓ Yes[/green]" if event.is_visible else "[dim]✗ No[/dim]"

        # Format altitude
        alt_str = f"{event.altitude_at_event:.0f}°"

        table.add_row(date_str, planet_str, elong_str, visible_str, alt_str)

    output_console.print(table)

    # Show details
    output_console.print("\n[bold]Opposition Details:[/bold]")
    for event in oppositions[:10]:  # Show first 10
        if tz:
            date_local = event.date.astimezone(tz)
            date_str = date_local.strftime("%B %d, %Y at %I:%M %p")
        else:
            date_str = event.date.strftime("%B %d, %Y at %H:%M UTC")

        output_console.print(f"\n  [bold]{event.planet1.capitalize()}[/bold] - {date_str}")
        output_console.print(
            f"    Elongation: {event.separation_degrees:.1f}° at {event.altitude_at_event:.0f}° altitude"
        )
        output_console.print(f"    {event.notes}")

    output_console.print("\n[bold]Viewing Tips:[/bold]")
    output_console.print("  • [green]Opposition is the best time to observe outer planets[/green]")
    output_console.print("  • Planet is closest to Earth and brightest")
    output_console.print("  • Planet is visible all night (rises at sunset, sets at sunrise)")
    output_console.print("  • Best viewing with telescope for detail")
    output_console.print("\n[dim]💡 Tip: Plan your observing sessions around oppositions![/dim]\n")


if __name__ == "__main__":
    app()

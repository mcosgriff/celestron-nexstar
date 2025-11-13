"""
Variable Star Events Commands

Find variable star events (eclipses, maxima, minima).
"""

from datetime import datetime
from pathlib import Path

import typer
from click import Context
from rich.console import Console
from rich.table import Table
from typer.core import TyperGroup

from ...api.observer import ObserverLocation, get_observer_location
from ...api.variable_stars import VariableStarEvent, get_variable_star_events
from ...cli.utils.export import FileConsole, create_file_console, export_to_text


class SortedCommandsGroup(TyperGroup):
    """Custom Typer group that sorts commands alphabetically within each help panel."""

    def list_commands(self, ctx: Context) -> list[str]:
        """Return commands sorted alphabetically."""
        commands = super().list_commands(ctx)
        return sorted(commands)


app = typer.Typer(help="Variable star events", cls=SortedCommandsGroup)
console = Console()


def _generate_export_filename(command: str = "variables") -> Path:
    """Generate export filename for variable star commands."""
    from ...api.observer import get_observer_location

    location = get_observer_location()

    if location.name:
        location_short = location.name.lower().replace(" ", "_").replace(",", "").replace(".", "")
        location_short = location_short.replace("_(default)", "").replace("_observatory", "")
        location_short = location_short[:20]
    else:
        location_short = "unknown"

    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"nexstar_variables_{location_short}_{date_str}_{command}.txt"
    return Path(filename)


@app.command("events")
def show_events(
    months: int = typer.Option(6, "--months", "-m", help="Number of months ahead to search (default: 6)"),
    event_type: str | None = typer.Option(None, "--type", help="Filter by event type: minimum or maximum"),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Find variable star events (minima, maxima, eclipses)."""
    location = get_observer_location()
    if not location:
        console.print(
            "[red]Error: No observer location set. Use 'nexstar location set' to configure your location.[/red]"
        )
        raise typer.Exit(1)

    events = get_variable_star_events(location, months_ahead=months, event_type=event_type)

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("events")
        file_console = create_file_console()
        _show_events_content(file_console, location, events, months)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_events_content(console, location, events, months)


def _show_events_content(
    output_console: Console | FileConsole, location: ObserverLocation, events: list[VariableStarEvent], months: int
) -> None:
    """Display variable star event information."""
    from zoneinfo import ZoneInfo

    from timezonefinder import TimezoneFinder

    location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

    output_console.print(f"\n[bold cyan]Variable Star Events for {location_name}[/bold cyan]")
    output_console.print(f"[dim]Searching next {months} months[/dim]\n")

    if not events:
        output_console.print("[yellow]No variable star events found in the forecast period.[/yellow]\n")
        return

    # Get timezone for formatting
    try:
        _tz_finder = TimezoneFinder()
        tz_name = _tz_finder.timezone_at(lat=location.latitude, lng=location.longitude)
        tz = ZoneInfo(tz_name) if tz_name else None
    except Exception:
        tz = None

    # Display events in a table
    table = Table(show_header=True, header_style="bold")
    table.add_column("Date", style="cyan")
    table.add_column("Star")
    table.add_column("Event")
    table.add_column("Magnitude", justify="right")
    table.add_column("Type")

    for event in events:
        # Format date
        if tz:
            date_local = event.date.astimezone(tz)
            date_str = date_local.strftime("%Y-%m-%d %I:%M %p")
        else:
            date_str = event.date.strftime("%Y-%m-%d %H:%M UTC")

        # Format event type with color
        if event.event_type == "minimum":
            event_str = "[bold bright_green]Minimum[/bold bright_green]"
        elif event.event_type == "maximum":
            event_str = "[yellow]Maximum[/yellow]"
        else:
            event_str = event.event_type.capitalize()

        # Format magnitude
        mag_str = f"{event.magnitude:.1f}"

        # Format variable type
        type_str = event.star.variable_type.replace("_", " ").title()

        table.add_row(date_str, event.star.name, event_str, mag_str, type_str)

    output_console.print(table)

    # Show details
    output_console.print("\n[bold]Event Details:[/bold]")
    for event in events[:15]:  # Show first 15
        if tz:
            date_local = event.date.astimezone(tz)
            date_str = date_local.strftime("%B %d, %Y at %I:%M %p")
        else:
            date_str = event.date.strftime("%B %d, %Y at %H:%M UTC")

        output_console.print(f"\n  [bold]{event.star.name}[/bold] ({event.star.designation})")
        output_console.print(f"    {date_str}")
        output_console.print(f"    Event: {event.event_type.capitalize()} - Magnitude {event.magnitude:.1f}")
        output_console.print(
            f"    Type: {event.star.variable_type.replace('_', ' ').title()} (Period: {event.star.period_days:.2f} days)"
        )
        output_console.print(f"    {event.star.notes}")
        output_console.print(f"    {event.notes}")

    output_console.print("\n[bold]Viewing Tips:[/bold]")
    output_console.print("  • [green]Eclipsing binaries show rapid brightness changes[/green]")
    output_console.print("  • [yellow]Cepheids vary smoothly over their period[/yellow]")
    output_console.print("  • [dim]Compare brightness to nearby comparison stars[/dim]")
    output_console.print("  • [green]Use binoculars or telescope for dimmer variables[/green]")
    output_console.print("\n[dim]💡 Tip: Algol (β Persei) is a great target - visible to naked eye![/dim]\n")


if __name__ == "__main__":
    app()

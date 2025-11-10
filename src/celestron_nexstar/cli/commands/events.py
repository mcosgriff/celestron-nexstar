"""
Space Events Commands

Show upcoming space events and find best viewing locations.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from ...api.observer import ObserverLocation, geocode_location, get_observer_location
from ...api.space_events import (
    SpaceEventType,
    find_best_viewing_location,
    get_upcoming_events,
    is_event_visible_from_location,
)
from ...cli.utils.export import create_file_console, export_to_text

app = typer.Typer(help="Space events calendar and viewing recommendations")
console = Console()


def _generate_export_filename(command: str = "events", location: str | None = None, date_suffix: str = "") -> Path:
    """Generate export filename for events commands."""
    from datetime import datetime
    import re

    date_str = datetime.now().strftime("%Y-%m-%d")

    parts = [f"nexstar_events_{date_str}", command]

    if location:
        sanitized = re.sub(r'[^\w\s-]', '', location)
        sanitized = re.sub(r'[-\s]+', '-', sanitized)
        sanitized = sanitized[:30]
        if sanitized:
            parts.append(sanitized)

    if date_suffix:
        parts.append(date_suffix.lstrip("_"))

    filename = "_".join(parts) + ".txt"
    return Path(filename)


@app.command("upcoming")
def show_upcoming_events(
    days_ahead: int = typer.Option(90, "--days", "-d", help="Days ahead to show events (default: 90, ignored if --date is used)"),
    date: str | None = typer.Option(None, "--date", help="Find events within ±7 days of this date (YYYY-MM-DD format)"),
    event_type: str | None = typer.Option(None, "--type", "-t", help="Filter by event type (meteor_shower, eclipse, etc.)"),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file"),
    export_path: str | None = typer.Option(None, "--export-path", help="Custom export file path"),
) -> None:
    """Show upcoming space events from the calendar."""
    from datetime import UTC, timedelta

    if date:
        # Parse the date and find events within ±7 days
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d")
            # Make it timezone-aware (use UTC midnight)
            target_date = target_date.replace(tzinfo=UTC)
            start_date = target_date - timedelta(days=7)
            end_date = target_date + timedelta(days=7)
        except ValueError:
            console.print(f"[red]Error: Invalid date format '{date}'. Use YYYY-MM-DD format (e.g., 2025-12-14)[/red]")
            raise typer.Exit(1)
    else:
        # Use days_ahead from today
        start_date = datetime.now(UTC)
        end_date = start_date + timedelta(days=days_ahead)

    event_types = None
    if event_type:
        try:
            event_types = [SpaceEventType(event_type)]
        except ValueError:
            console.print(f"[red]Error: Invalid event type '{event_type}'[/red]")
            console.print(f"[dim]Valid types: {', '.join([e.value for e in SpaceEventType])}[/dim]")
            raise typer.Exit(1)

    events = get_upcoming_events(start_date=start_date, end_date=end_date, event_types=event_types)

    if export:
        if date:
            date_suffix = f"{date}_±7days"
        else:
            date_suffix = f"{days_ahead}days"
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("upcoming", None, date_suffix)
        file_console = create_file_console()
        _show_events_content(file_console, events, days_ahead, date)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_events_content(console, events, days_ahead, date)


@app.command("viewing")
def show_viewing_recommendations(
    event_name: str = typer.Argument(..., help="Name of the event (partial match OK)"),
    location: str | None = typer.Option(None, "--location", "-l", help="Location to check (default: your saved location)"),
    max_distance: float = typer.Option(500.0, "--max-distance", help="Maximum distance to search for better locations (miles)"),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file"),
    export_path: str | None = typer.Option(None, "--export-path", help="Custom export file path"),
) -> None:
    """
    Find the best viewing location for a specific space event.
    
    Compares your current location with event requirements and suggests
    nearby dark sky sites or other locations if needed.
    """
    from datetime import UTC, timedelta

    # Get events
    start_date = datetime.now(UTC)
    end_date = start_date + timedelta(days=730)  # 2 years
    all_events = get_upcoming_events(start_date=start_date, end_date=end_date)

    # Find matching event
    matching_events = [e for e in all_events if event_name.lower() in e.name.lower()]

    if not matching_events:
        console.print(f"[red]Error: No event found matching '{event_name}'[/red]")
        console.print(f"[dim]Use 'nexstar events upcoming' to see available events[/dim]")
        raise typer.Exit(1)

    if len(matching_events) > 1:
        console.print(f"[yellow]Multiple events found matching '{event_name}':[/yellow]")
        for e in matching_events:
            console.print(f"  • {e.name} ({e.date.strftime('%Y-%m-%d')})")
        console.print(f"[dim]Please be more specific[/dim]")
        raise typer.Exit(1)

    event = matching_events[0]

    # Get location
    if location:
        try:
            observer_location = geocode_location(location)
        except Exception as e:
            console.print(f"[red]Error: Could not geocode location '{location}': {e}[/red]")
            raise typer.Exit(1)
    else:
        try:
            observer_location = get_observer_location()
        except Exception as e:
            console.print(f"[red]Error: Could not get your location: {e}[/red]")
            console.print(f"[dim]Set your location with 'nexstar location set' or use --location[/dim]")
            raise typer.Exit(1)

    # Find best viewing location
    max_distance_km = max_distance * 1.60934
    best_location, recommendation = find_best_viewing_location(event, observer_location, max_distance_km)

    if export:
        location_name = observer_location.name or f"{observer_location.latitude:.1f}N-{observer_location.longitude:.1f}E"
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("viewing", location_name)
        file_console = create_file_console()
        _show_viewing_recommendation_content(file_console, event, observer_location, recommendation, best_location)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_viewing_recommendation_content(console, event, observer_location, recommendation, best_location)


def _show_events_content(output_console: Console, events: list, days_ahead: int, date: str | None = None) -> None:
    """Display space events."""
    from datetime import UTC

    if date:
        output_console.print(f"\n[bold cyan]Space Events (within ±7 days of {date})[/bold cyan]\n")
    else:
        output_console.print(f"\n[bold cyan]Upcoming Space Events (next {days_ahead} days)[/bold cyan]\n")

    if not events:
        output_console.print("[dim]No events found in this time period[/dim]\n")
        return

    table = Table(expand=True, show_header=True, header_style="bold")
    table.add_column("Date", width=12)
    table.add_column("Event", style="bold", width=30)
    table.add_column("Type", width=20)
    table.add_column("Description", style="dim")

    for event in events:
        date_str = event.date.strftime("%Y-%m-%d")
        type_str = event.event_type.value.replace("_", " ").title()
        desc = event.description[:60] + "..." if len(event.description) > 60 else event.description

        table.add_row(date_str, event.name, type_str, desc)

    output_console.print(table)

    output_console.print(f"\n[dim]💡 Tip: Use 'nexstar events viewing <event-name>' to find best viewing location[/dim]\n")


def _show_viewing_recommendation_content(
    output_console: Console,
    event,
    location: ObserverLocation,
    recommendation: str,
    best_location: ObserverLocation | None,
) -> None:
    """Display viewing recommendations for an event."""
    from ...api.light_pollution import get_light_pollution_data

    location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

    output_console.print(f"\n[bold cyan]Viewing Recommendations for {event.name}[/bold cyan]\n")
    output_console.print(f"[bold]Event Date:[/bold] {event.date.strftime('%Y-%m-%d')}")
    output_console.print(f"[bold]Event Type:[/bold] {event.event_type.value.replace('_', ' ').title()}\n")

    output_console.print(f"[bold]Your Location:[/bold] {location_name}\n")

    # Check visibility
    is_visible = is_event_visible_from_location(event, location)
    if is_visible:
        output_console.print("[green]✓ Event is visible from your location[/green]\n")
    else:
        output_console.print("[red]✗ Event is NOT visible from your location[/red]\n")
        output_console.print("[yellow]You may need to travel to a different region to view this event.[/yellow]\n")

    # Show requirements
    req = event.viewing_requirements
    output_console.print("[bold]Viewing Requirements:[/bold]")
    if req.equipment_needed:
        output_console.print(f"  • Equipment: {req.equipment_needed.replace('_', ' ').title()}")
    if req.dark_sky_required:
        output_console.print("  • Dark sky required: Yes")
    if req.min_bortle_class:
        output_console.print(f"  • Minimum Bortle class: {req.min_bortle_class}")
    if req.notes:
        output_console.print(f"  • Notes: {req.notes}")

    # Show current location conditions
    light_data = get_light_pollution_data(location.latitude, location.longitude)
    output_console.print(f"\n[bold]Your Current Sky Conditions:[/bold]")
    output_console.print(f"  • Bortle Class: {light_data.bortle_class.value}")
    output_console.print(f"  • SQM Value: {light_data.sqm_value:.2f} mag/arcsec²")

    # Show recommendation
    output_console.print(f"\n[bold]Recommendation:[/bold]")
    output_console.print(f"  {recommendation}\n")

    if event.url:
        output_console.print(f"[dim]Source: {event.url}[/dim]\n")


if __name__ == "__main__":
    app()


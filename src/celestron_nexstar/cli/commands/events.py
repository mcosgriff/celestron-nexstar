"""
Space Events Commands

Show upcoming space events and find best viewing locations.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

import typer
from rich.console import Console
from rich.table import Table

from ...api.observer import ObserverLocation, geocode_location, get_observer_location
from ...api.space_events import (
    SpaceEvent,
    SpaceEventType,
    find_best_viewing_location,
    get_upcoming_events,
    is_event_visible_from_location,
)
from ...cli.utils.export import FileConsole, create_file_console, export_to_text
from ...cli.utils.selection import select_from_list


app = typer.Typer(help="Space events calendar and viewing recommendations")
console = Console()


def _generate_export_filename(command: str = "events", location: str | None = None, date_suffix: str = "") -> Path:
    """Generate export filename for events commands."""
    import re
    from datetime import datetime

    date_str = datetime.now().strftime("%Y-%m-%d")

    parts = [f"nexstar_events_{date_str}", command]

    if location:
        sanitized = re.sub(r"[^\w\s-]", "", location)
        sanitized = re.sub(r"[-\s]+", "-", sanitized)
        sanitized = sanitized[:30]
        if sanitized:
            parts.append(sanitized)

    if date_suffix:
        parts.append(date_suffix.lstrip("_"))

    filename = "_".join(parts) + ".txt"
    return Path(filename)


@app.command("upcoming")
def show_upcoming_events(
    days_ahead: int = typer.Option(
        90, "--days", "-d", help="Days ahead to show events (default: 90, ignored if --date is used)"
    ),
    date: str | None = typer.Option(None, "--date", help="Find events around this date (YYYY-MM-DD format)"),
    range_days: int = typer.Option(
        7, "--range", "-r", help="Days before and after --date to search (default: 7, only used with --date)"
    ),
    event_type: str | None = typer.Option(
        None,
        "--type",
        "-t",
        help="Filter by event type (meteor_shower, eclipse, etc.) or 'all' for all types. If not provided, will prompt interactively.",
    ),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file"),
    export_path: str | None = typer.Option(None, "--export-path", help="Custom export file path"),
) -> None:
    """Show upcoming space events from the calendar."""
    from datetime import UTC, timedelta

    if date:
        # Parse the date and find events within ±range_days
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d")
            # Make it timezone-aware (use UTC midnight)
            target_date = target_date.replace(tzinfo=UTC)
            start_date = target_date - timedelta(days=range_days)
            end_date = target_date + timedelta(days=range_days)
        except ValueError as e:
            console.print(f"[red]Error: Invalid date format '{date}'. Use YYYY-MM-DD format (e.g., 2025-12-14)[/red]")
            raise typer.Exit(1) from e
    else:
        # Use days_ahead from today
        start_date = datetime.now(UTC)
        end_date = start_date + timedelta(days=days_ahead)

    # Interactive selection if event_type not provided
    if event_type is None:
        selected_type = _select_event_type_interactive()
        event_types = None if selected_type is None or selected_type == "all" else [SpaceEventType(selected_type)]
    elif event_type.lower() == "all":
        # Explicit "all" option
        event_types = None
    else:
        try:
            event_types = [SpaceEventType(event_type)]
        except ValueError as e:
            console.print(f"[red]Error: Invalid event type '{event_type}'[/red]")
            console.print(f"[dim]Valid types: {', '.join([e.value for e in SpaceEventType])}, 'all'[/dim]")
            raise typer.Exit(1) from e

    events = get_upcoming_events(start_date=start_date, end_date=end_date, event_types=event_types)

    if export:
        date_suffix = f"{date}_±{range_days}days" if date else f"{days_ahead}days"
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("upcoming", None, date_suffix)
        file_console = create_file_console()
        _show_events_content(file_console, events, days_ahead, date, range_days)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_events_content(console, events, days_ahead, date, range_days)


@app.command("viewing")
def show_viewing_recommendations(
    event_name: str = typer.Argument(..., help="Name of the event (partial match OK)"),
    location: str | None = typer.Option(
        None, "--location", "-l", help="Location to check (default: your saved location)"
    ),
    max_distance: float = typer.Option(
        500.0, "--max-distance", help="Maximum distance to search for better locations (miles)"
    ),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file"),
    export_path: str | None = typer.Option(None, "--export-path", help="Custom export file path"),
) -> None:
    """
    Find the best viewing location for a specific space event.

    Compares your current location with event requirements and suggests
    nearby dark sky sites or other locations if needed.
    """
    from datetime import UTC, timedelta

    # Get events - search a wide range (past and future) to find events by name
    now = datetime.now(UTC)
    start_date = now - timedelta(days=365)  # 1 year in the past
    end_date = now + timedelta(days=730)  # 2 years in the future
    all_events = get_upcoming_events(start_date=start_date, end_date=end_date)

    # Find matching event (case-insensitive, partial match)
    event_name_lower = event_name.lower()
    matching_events = [
        e for e in all_events if event_name_lower in e.name.lower() or e.name.lower() in event_name_lower
    ]

    # If no matches found, try a broader search (all events, regardless of date)
    if not matching_events:
        # Get all events from hardcoded lists as fallback
        from ...api.space_events import SPACE_EVENTS_2025, SPACE_EVENTS_2026

        all_events_fallback = SPACE_EVENTS_2025 + SPACE_EVENTS_2026
        matching_events = [
            e for e in all_events_fallback if event_name_lower in e.name.lower() or e.name.lower() in event_name_lower
        ]

    if not matching_events:
        console.print(f"[red]Error: No event found matching '{event_name}'[/red]")
        console.print("[dim]Use 'nexstar events upcoming' to see available events[/dim]")
        raise typer.Exit(1)

    if len(matching_events) > 1:
        console.print(f"[yellow]Multiple events found matching '{event_name}':[/yellow]")
        for e in matching_events:
            console.print(f"  • {e.name} ({e.date.strftime('%Y-%m-%d')})")
        console.print("[dim]Please be more specific[/dim]")
        raise typer.Exit(1)

    event = matching_events[0]

    # Get location
    if location:
        try:
            observer_location = asyncio.run(geocode_location(location))
        except Exception as e:
            console.print(f"[red]Error: Could not geocode location '{location}': {e}[/red]")
            raise typer.Exit(1) from e
    else:
        try:
            observer_location = get_observer_location()
        except Exception as e:
            console.print(f"[red]Error: Could not get your location: {e}[/red]")
            console.print("[dim]Set your location with 'nexstar location set' or use --location[/dim]")
            raise typer.Exit(1) from e

    # Find best viewing location
    max_distance_km = max_distance * 1.60934
    best_location, recommendation = find_best_viewing_location(event, observer_location, max_distance_km)

    if export:
        location_name = (
            observer_location.name or f"{observer_location.latitude:.1f}N-{observer_location.longitude:.1f}E"
        )
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("viewing", location_name)
        file_console = create_file_console()
        _show_viewing_recommendation_content(file_console, event, observer_location, recommendation, best_location)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_viewing_recommendation_content(console, event, observer_location, recommendation, best_location)


def _show_events_content(
    output_console: Console | FileConsole,
    events: list[SpaceEvent],
    days_ahead: int,
    date: str | None = None,
    range_days: int = 7,
) -> None:
    """Display space events."""

    if date:
        output_console.print(f"\n[bold cyan]Space Events (within ±{range_days} days of {date})[/bold cyan]\n")
    else:
        output_console.print(f"\n[bold cyan]Upcoming Space Events (next {days_ahead} days)[/bold cyan]\n")

    if not events:
        output_console.print("[dim]No events found in this time period[/dim]\n")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Date")
    table.add_column("Event", style="bold")
    table.add_column("Type")
    table.add_column("Description", style="dim")

    for event in events:
        date_str = event.date.strftime("%Y-%m-%d")
        type_str = event.event_type.value.replace("_", " ").title()
        desc = event.description[:60] + "..." if len(event.description) > 60 else event.description

        table.add_row(date_str, event.name, type_str, desc)

    output_console.print(table)

    output_console.print(
        "\n[dim]💡 Tip: Use 'nexstar events viewing <event-name>' to find best viewing location[/dim]\n"
    )


def _select_event_type_interactive() -> str | None:
    """Interactively select an event type."""
    # Create list with "all" option first, then event types
    all_option = "all"
    event_types = list(SpaceEventType)
    all_items: list[str | SpaceEventType] = [all_option, *event_types]

    # Event type descriptions
    descriptions = {
        SpaceEventType.METEOR_SHOWER: "Meteor shower events",
        SpaceEventType.PLANETARY_OPPOSITION: "Planetary oppositions",
        SpaceEventType.PLANETARY_ELONGATION: "Planetary elongations",
        SpaceEventType.PLANETARY_BRIGHTNESS: "Planetary brightness peaks",
        SpaceEventType.LUNAR_ECLIPSE: "Lunar eclipses",
        SpaceEventType.SOLAR_ECLIPSE: "Solar eclipses",
        SpaceEventType.SPACE_MISSION: "Space mission events",
        SpaceEventType.ASTEROID_FLYBY: "Asteroid flyby events",
        SpaceEventType.SOLSTICE: "Solstices",
        SpaceEventType.EQUINOX: "Equinoxes",
        SpaceEventType.OTHER: "Other space events",
    }

    def display_event_type(item: str | SpaceEventType) -> tuple[str, ...]:
        if isinstance(item, str):
            if item == "all":
                return ("All Event Types", "Show all events regardless of type")
            # Should not happen, but handle it
            return (item, "Event type")
        else:
            # item is SpaceEventType (mypy type narrowing issue)
            display_name = item.value.replace("_", " ").title()  # type: ignore[unreachable]
            description = descriptions.get(item, "Event type")
            return (display_name, description)

    selected = select_from_list(
        all_items,
        title="Select Event Type (or 'q' to cancel)",
        display_func=display_event_type,
        headers=["Event Type", "Description"],
    )

    if selected is None:
        return None
    if isinstance(selected, str) and selected == "all":
        return "all"
    if isinstance(selected, SpaceEventType):
        return selected.value
    # Should not reach here, but handle it
    return None


def _show_viewing_recommendation_content(
    output_console: Console | FileConsole,
    event: SpaceEvent,
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
    light_data = asyncio.run(get_light_pollution_data(location.latitude, location.longitude))
    output_console.print("\n[bold]Your Current Sky Conditions:[/bold]")
    output_console.print(f"  • Bortle Class: {light_data.bortle_class.value}")
    output_console.print(f"  • SQM Value: {light_data.sqm_value:.2f} mag/arcsec²")

    # Show recommendation
    output_console.print("\n[bold]Recommendation:[/bold]")
    output_console.print(f"  {recommendation}\n")

    if event.url:
        output_console.print(f"[dim]Source: {event.url}[/dim]\n")


if __name__ == "__main__":
    app()

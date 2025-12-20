"""
Asteroid Visibility Commands

Find bright asteroids visible from your location.
"""

from datetime import datetime
from pathlib import Path

import typer
from click import Context
from rich.console import Console
from rich.table import Table
from typer.core import TyperGroup

from celestron_nexstar.api.astronomy.asteroids import (
    AsteroidVisibility,
    get_upcoming_oppositions,
    get_visible_asteroids,
)
from celestron_nexstar.api.database.models import get_db_session
from celestron_nexstar.api.location.observer import ObserverLocation, get_observer_location
from celestron_nexstar.cli.utils.export import FileConsole, create_file_console, export_to_text


class SortedCommandsGroup(TyperGroup):
    """Custom Typer group that sorts commands alphabetically within each help panel."""

    def list_commands(self, ctx: Context) -> list[str]:
        """Return commands sorted alphabetically."""
        commands = super().list_commands(ctx)
        return sorted(commands)


app = typer.Typer(help="Asteroid visibility commands", cls=SortedCommandsGroup)
console = Console()


def _generate_export_filename(command: str = "asteroids") -> Path:
    """Generate export filename for asteroid commands."""
    location = get_observer_location()

    if location.name:
        location_short = location.name.lower().replace(" ", "_").replace(",", "").replace(".", "")
        location_short = location_short.replace("_(default)", "").replace("_observatory", "")
        location_short = location_short[:20]
    else:
        location_short = "unknown"

    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"nexstar_asteroids_{location_short}_{date_str}_{command}.txt"
    return Path(filename)


def _format_asteroid_type(asteroid_type: str) -> str:
    """Format asteroid type with color."""
    colors = {
        "main_belt": "[dim]Belt[/dim]",
        "neo": "[bold red]NEO[/bold red]",
        "dwarf_planet": "[magenta]Dwarf[/magenta]",
        "trojan": "[yellow]Trojan[/yellow]",
        "centaur": "[cyan]Centaur[/cyan]",
        "tno": "[cyan]TNO[/cyan]",
    }
    return colors.get(asteroid_type, asteroid_type)


@app.command("visible")
def show_visible(
    max_magnitude: float = typer.Option(12.0, "--max-mag", "-m", help="Maximum magnitude to include (default: 12.0)"),
    min_altitude: float = typer.Option(0.0, "--min-alt", "-a", help="Minimum altitude above horizon (default: 0)"),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Show asteroids currently visible from your location."""
    location = get_observer_location()
    if not location:
        console.print(
            "[red]Error: No observer location set. Use 'nexstar location set' to configure your location.[/red]"
        )
        raise typer.Exit(1)

    with get_db_session() as db_session:
        visible = get_visible_asteroids(db_session, location, max_magnitude=max_magnitude, min_altitude=min_altitude)

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("visible")
        file_console = create_file_console()
        _show_visible_content(file_console, location, visible, max_magnitude)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_visible_content(console, location, visible, max_magnitude)


@app.command("oppositions")
def show_oppositions(
    months: int = typer.Option(12, "--months", "-m", help="Number of months ahead to search (default: 12)"),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Find upcoming asteroid oppositions."""
    location = get_observer_location()
    if not location:
        console.print(
            "[red]Error: No observer location set. Use 'nexstar location set' to configure your location.[/red]"
        )
        raise typer.Exit(1)

    with get_db_session() as db_session:
        oppositions = get_upcoming_oppositions(db_session, location, months_ahead=months)

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("oppositions")
        file_console = create_file_console()
        _show_oppositions_content(file_console, location, oppositions, months)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_oppositions_content(console, location, oppositions, months)


def _show_visible_content(
    output_console: Console | FileConsole,
    location: ObserverLocation,
    visible: list[AsteroidVisibility],
    max_magnitude: float,
) -> None:
    """Display visible asteroids."""
    location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

    output_console.print(f"\n[bold orange1]Asteroid Visibility for {location_name}[/bold orange1]")
    output_console.print(f"[dim]Maximum magnitude: {max_magnitude}[/dim]\n")

    if not visible:
        output_console.print("[yellow]No asteroids found matching criteria.[/yellow]\n")
        output_console.print("[dim]Try increasing --max-mag or seeding more asteroids.[/dim]\n")
        return

    # Summary
    above_horizon = [v for v in visible if v.altitude > 0]
    output_console.print(
        f"Found [green]{len(visible)}[/green] asteroids, [green]{len(above_horizon)}[/green] above horizon\n"
    )

    # Table
    table = Table(show_header=True, header_style="bold")
    table.add_column("Name", style="cyan")
    table.add_column("Type")
    table.add_column("Mag", justify="right")
    table.add_column("Alt", justify="right")
    table.add_column("Elong", justify="right")
    table.add_column("Status")

    for vis in visible[:25]:  # Top 25
        name = vis.asteroid.name or vis.asteroid.designation
        if len(name) > 18:
            name = name[:18] + "..."

        type_str = _format_asteroid_type(vis.asteroid.asteroid_type)

        # Magnitude
        if vis.magnitude < 6:
            mag_str = f"[bold bright_green]{vis.magnitude:.1f}[/bold bright_green]"
        elif vis.magnitude < 9:
            mag_str = f"[yellow]{vis.magnitude:.1f}[/yellow]"
        else:
            mag_str = f"[dim]{vis.magnitude:.1f}[/dim]"

        # Altitude
        alt_str = f"{vis.altitude:.0f}°" if vis.altitude >= 0 else f"[dim]{vis.altitude:.0f}°[/dim]"

        # Elongation
        elong = vis.elongation_deg or 0
        if elong > 150:
            elong_str = f"[green]{elong:.0f}°[/green]"
        elif elong < 30:
            elong_str = f"[red]{elong:.0f}°[/red]"
        else:
            elong_str = f"{elong:.0f}°"

        # Status
        if vis.is_visible and elong > 150:
            status = "[bold green]★ Opposition[/bold green]"
        elif vis.is_visible:
            status = "[green]✓ Visible[/green]"
        else:
            status = "[dim]✗ Below horizon[/dim]"

        table.add_row(name, type_str, mag_str, alt_str, elong_str, status)

    output_console.print(table)

    # Details for visible
    visible_above = [v for v in visible if v.is_visible][:5]
    if visible_above:
        output_console.print("\n[bold]Top Visible Asteroids:[/bold]")

        for vis in visible_above:
            output_console.print(f"\n  [bold]{vis.asteroid.display_name}[/bold]")
            output_console.print(f"    Type: {vis.asteroid.asteroid_type.replace('_', ' ').title()}")

            if vis.ra_hours is not None and vis.dec_degrees is not None:
                ra_h = int(vis.ra_hours)
                ra_m = int((vis.ra_hours - ra_h) * 60)
                dec_sign = "+" if vis.dec_degrees >= 0 else ""
                output_console.print(f"    Position: RA {ra_h}h {ra_m}m, Dec {dec_sign}{vis.dec_degrees:.1f}°")

            output_console.print(f"    Altitude: {vis.altitude:.1f}°, Azimuth: {vis.azimuth:.1f}°")
            output_console.print(f"    Magnitude: {vis.magnitude:.2f}, Elongation: {vis.elongation_deg:.0f}°")

            if vis.helio_distance_au and vis.geo_distance_au:
                output_console.print(
                    f"    Distance: {vis.helio_distance_au:.2f} AU from Sun, {vis.geo_distance_au:.2f} AU from Earth"
                )

            if vis.asteroid.diameter_km:
                output_console.print(f"    Diameter: {vis.asteroid.diameter_km:.1f} km")

            if vis.notes:
                output_console.print(f"    [dim]{vis.notes}[/dim]")

    output_console.print("\n[bold]Viewing Tips:[/bold]")
    output_console.print("  • [green]Elongation > 150° indicates opposition (brightest)[/green]")
    output_console.print("  • [yellow]Magnitude < 8: visible in binoculars[/yellow]")
    output_console.print("  • [dim]Track asteroids over multiple nights to see motion[/dim]")
    output_console.print("  • [dim]Vesta can reach naked-eye visibility at opposition[/dim]")
    output_console.print("")


def _show_oppositions_content(
    output_console: Console | FileConsole,
    location: ObserverLocation,
    oppositions: list[AsteroidVisibility],
    months: int,
) -> None:
    """Display upcoming asteroid oppositions."""
    from zoneinfo import ZoneInfo

    from timezonefinder import TimezoneFinder

    location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

    output_console.print("\n[bold orange1]Upcoming Asteroid Oppositions[/bold orange1]")
    output_console.print(f"[dim]{location_name} • Next {months} months[/dim]\n")

    if not oppositions:
        output_console.print("[yellow]No bright asteroid oppositions found in this period.[/yellow]\n")
        return

    # Get timezone
    try:
        tz_finder = TimezoneFinder()
        tz_name = tz_finder.timezone_at(lat=location.latitude, lng=location.longitude)
        tz = ZoneInfo(tz_name) if tz_name else None
    except Exception:
        tz = None

    # Table
    table = Table(show_header=True, header_style="bold")
    table.add_column("Date", style="cyan")
    table.add_column("Asteroid")
    table.add_column("Type")
    table.add_column("Mag", justify="right")
    table.add_column("Elong", justify="right")

    for vis in oppositions:
        if tz:
            date_local = vis.date.astimezone(tz)
            date_str = date_local.strftime("%Y-%m-%d")
        else:
            date_str = vis.date.strftime("%Y-%m-%d")

        name = vis.asteroid.name or vis.asteroid.designation
        type_str = _format_asteroid_type(vis.asteroid.asteroid_type)

        if vis.magnitude < 6:
            mag_str = f"[bold bright_green]{vis.magnitude:.1f}[/bold bright_green]"
        elif vis.magnitude < 9:
            mag_str = f"[yellow]{vis.magnitude:.1f}[/yellow]"
        else:
            mag_str = f"[dim]{vis.magnitude:.1f}[/dim]"

        elong_str = f"[green]{vis.elongation_deg:.0f}°[/green]"

        table.add_row(date_str, name, type_str, mag_str, elong_str)

    output_console.print(table)

    output_console.print("\n[bold]Opposition Details:[/bold]")
    for vis in oppositions[:5]:
        if tz:
            date_local = vis.date.astimezone(tz)
            date_str = date_local.strftime("%B %d, %Y")
        else:
            date_str = vis.date.strftime("%B %d, %Y")

        output_console.print(f"\n  [bold]{vis.asteroid.display_name}[/bold] - {date_str}")
        output_console.print(f"    Peak magnitude: {vis.magnitude:.2f}")
        output_console.print(f"    Elongation: {vis.elongation_deg:.0f}° (near opposition)")

        if vis.asteroid.diameter_km:
            output_console.print(f"    Diameter: {vis.asteroid.diameter_km:.1f} km")

        if vis.asteroid.notes:
            output_console.print(f"    [dim]{vis.asteroid.notes}[/dim]")

    output_console.print("\n[dim]💡 Opposition = asteroid opposite the Sun = closest and brightest[/dim]\n")


if __name__ == "__main__":
    app()

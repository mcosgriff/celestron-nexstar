"""
Vacation Planning Commands

Plan telescope viewing for vacation destinations.
"""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from ...api.light_pollution import BortleClass
from ...api.observer import ObserverLocation, geocode_location
from ...api.vacation_planning import find_dark_sites_near, get_vacation_viewing_info
from ...cli.utils.export import create_file_console, export_to_text

app = typer.Typer(help="Vacation planning for telescope viewing")
console = Console()


def _generate_export_filename(command: str = "vacation") -> Path:
    """Generate export filename for vacation commands."""
    from datetime import datetime

    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"nexstar_vacation_{date_str}_{command}.txt"
    return Path(filename)


@app.command("view")
def show_viewing_info(
    location: str = typer.Argument(..., help="Vacation location (city, address, or coordinates)"),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Show what's visible from a vacation location."""
    try:
        # Geocode location
        vacation_location = geocode_location(location)
    except Exception as e:
        console.print(f"[red]Error: Could not geocode location '{location}': {e}[/red]")
        raise typer.Exit(1)

    viewing_info = get_vacation_viewing_info(vacation_location)

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("view")
        file_console = create_file_console()
        _show_viewing_info_content(file_console, vacation_location, viewing_info)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_viewing_info_content(console, vacation_location, viewing_info)


@app.command("dark-sites")
def show_dark_sites(
    location: str = typer.Argument(..., help="Vacation location (city, address, or coordinates)"),
    max_distance: float = typer.Option(200.0, "--max-distance", help="Maximum distance in km (default: 200)"),
    min_bortle: int = typer.Option(4, "--min-bortle", help="Minimum Bortle class (1-9, default: 4)"),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Find dark sky viewing sites near a vacation location."""
    try:
        # Geocode location
        vacation_location = geocode_location(location)
    except Exception as e:
        console.print(f"[red]Error: Could not geocode location '{location}': {e}[/red]")
        raise typer.Exit(1)

    # Validate min_bortle
    if not 1 <= min_bortle <= 9:
        console.print("[red]Error: min-bortle must be between 1 and 9[/red]")
        raise typer.Exit(1)

    min_bortle_class = BortleClass(min_bortle)
    dark_sites = find_dark_sites_near(vacation_location, max_distance_km=max_distance, min_bortle=min_bortle_class)

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("dark-sites")
        file_console = create_file_console()
        _show_dark_sites_content(file_console, vacation_location, dark_sites, max_distance)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_dark_sites_content(console, vacation_location, dark_sites, max_distance)


def _show_viewing_info_content(output_console: Console, location: ObserverLocation, viewing_info) -> None:
    """Display vacation viewing information."""
    location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

    output_console.print(f"\n[bold cyan]Viewing Conditions for {location_name}[/bold cyan]\n")

    # Sky quality table
    table = Table(show_header=True, header_style="bold")
    table.add_column("Metric", style="cyan", width=25)
    table.add_column("Value", style="green")

    # Format Bortle class with color
    bortle_colors = {
        BortleClass.CLASS_1: "[bold bright_green]Class 1 - Excellent[/bold bright_green]",
        BortleClass.CLASS_2: "[bright_green]Class 2 - Excellent[/bright_green]",
        BortleClass.CLASS_3: "[green]Class 3 - Rural[/green]",
        BortleClass.CLASS_4: "[yellow]Class 4 - Rural/Suburban[/yellow]",
        BortleClass.CLASS_5: "[yellow]Class 5 - Suburban[/yellow]",
        BortleClass.CLASS_6: "[red]Class 6 - Bright Suburban[/red]",
        BortleClass.CLASS_7: "[red]Class 7 - Suburban/Urban[/red]",
        BortleClass.CLASS_8: "[bold red]Class 8 - City[/bold red]",
        BortleClass.CLASS_9: "[bold red]Class 9 - Inner City[/bold red]",
    }
    bortle_str = bortle_colors.get(viewing_info.bortle_class, str(viewing_info.bortle_class.value))

    table.add_row("Bortle Scale", bortle_str)
    table.add_row("SQM Value", f"{viewing_info.sqm_value:.2f} mag/arcsec²")
    table.add_row("Naked Eye Limiting Mag", f"{viewing_info.naked_eye_limiting_magnitude:.1f}")
    table.add_row("Milky Way Visible", "[green]Yes[/green]" if viewing_info.milky_way_visible else "[red]No[/red]")

    output_console.print(table)

    output_console.print(f"\n[bold]Description:[/bold]")
    output_console.print(f"  {viewing_info.description}")

    if viewing_info.recommendations:
        output_console.print(f"\n[bold]Recommendations:[/bold]")
        for rec in viewing_info.recommendations:
            output_console.print(f"  • {rec}")

    output_console.print("\n[bold]Next Steps:[/bold]")
    output_console.print("  • Use 'nexstar vacation dark-sites' to find nearby dark sky locations")
    output_console.print("  • Use 'nexstar telescope tonight' with this location for detailed viewing")
    output_console.print("\n[dim]💡 Tip: Consider visiting a nearby dark sky site for the best viewing experience![/dim]\n")


def _show_dark_sites_content(output_console: Console, location: ObserverLocation, dark_sites: list, max_distance: float) -> None:
    """Display dark sky sites information."""
    location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

    output_console.print(f"\n[bold cyan]Dark Sky Sites Near {location_name}[/bold cyan]")
    output_console.print(f"[dim]Searching within {max_distance:.0f} km[/dim]\n")

    if not dark_sites:
        output_console.print("[yellow]No dark sky sites found within the search radius.[/yellow]")
        output_console.print("[dim]Try increasing --max-distance or check for International Dark Sky Parks in the area.[/dim]\n")
        return

    # Display sites in a table
    table = Table(expand=True, show_header=True, header_style="bold")
    table.add_column("Site Name", style="bold", width=30)
    table.add_column("Distance", justify="right", width=12)
    table.add_column("Bortle", width=15)
    table.add_column("SQM", justify="right", width=10)
    table.add_column("Description", style="dim")

    for site in dark_sites:
        # Format Bortle class
        bortle_colors = {
            BortleClass.CLASS_1: "[bold bright_green]Class 1[/bold bright_green]",
            BortleClass.CLASS_2: "[bright_green]Class 2[/bright_green]",
            BortleClass.CLASS_3: "[green]Class 3[/green]",
            BortleClass.CLASS_4: "[yellow]Class 4[/yellow]",
        }
        bortle_str = bortle_colors.get(site.bortle_class, f"Class {site.bortle_class.value}")

        # Format distance
        if site.distance_km < 1:
            distance_str = f"{site.distance_km * 1000:.0f} m"
        else:
            distance_str = f"{site.distance_km:.1f} km"

        table.add_row(site.name, distance_str, bortle_str, f"{site.sqm_value:.2f}", site.description)

    output_console.print(table)

    # Show details
    output_console.print("\n[bold]Site Details:[/bold]")
    for site in dark_sites[:10]:  # Show first 10
        output_console.print(f"\n  [bold]{site.name}[/bold]")
        output_console.print(f"    Distance: {site.distance_km:.1f} km")
        output_console.print(f"    Location: {site.latitude:.4f}°N, {site.longitude:.4f}°E")
        output_console.print(f"    Bortle Class: {site.bortle_class.value} (SQM: {site.sqm_value:.2f})")
        output_console.print(f"    {site.description}")
        if site.notes:
            output_console.print(f"    [dim]{site.notes}[/dim]")

    output_console.print("\n[bold]Planning Tips:[/bold]")
    output_console.print("  • [green]Check park hours and access requirements[/green]")
    output_console.print("  • [yellow]Some sites require permits or reservations[/yellow]")
    output_console.print("  • [dim]Bring red flashlights and follow dark sky etiquette[/dim]")
    output_console.print("  • [green]Check weather forecasts before traveling[/green]")
    output_console.print("\n[dim]💡 Tip: Use 'nexstar vacation view' to check viewing conditions at these sites![/dim]\n")


if __name__ == "__main__":
    app()


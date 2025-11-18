"""
Milky Way Visibility Commands

Check if the Milky Way is visible from your location based on
dark sky conditions, moon phase, weather, and galactic center position.
"""

from datetime import datetime
from pathlib import Path

import typer
from click import Context
from rich.console import Console
from rich.table import Table
from typer.core import TyperGroup

from celestron_nexstar.api.events.milky_way import (
    MilkyWayForecast,
    MilkyWayOpportunity,
    check_milky_way_visibility,
    get_milky_way_visibility_windows,
    get_next_milky_way_opportunity,
)
from celestron_nexstar.api.location.observer import ObserverLocation, get_observer_location
from celestron_nexstar.cli.utils.export import FileConsole, create_file_console, export_to_text


class SortedCommandsGroup(TyperGroup):
    """Custom Typer group that sorts commands alphabetically within each help panel."""

    def list_commands(self, ctx: Context) -> list[str]:
        """Return commands sorted alphabetically."""
        commands = super().list_commands(ctx)
        return sorted(commands)


app = typer.Typer(help="Milky Way visibility commands", cls=SortedCommandsGroup)
console = Console()


def _generate_export_filename(command: str = "milky-way", location: ObserverLocation | None = None) -> Path:
    """Generate export filename for Milky Way commands."""
    from celestron_nexstar.api.location.observer import get_observer_location

    if location is None:
        try:
            location = get_observer_location()
        except Exception:
            location = None

    # Get location name (shortened, sanitized)
    if location and location.name:
        location_short = location.name.lower().replace(" ", "_").replace(",", "").replace(".", "")
        # Remove common suffixes and limit length
        location_short = location_short.replace("_(default)", "").replace("_observatory", "")
        location_short = location_short[:20]  # Limit length
    else:
        location_short = "unknown"

    # Get date
    date_str = datetime.now().strftime("%Y-%m-%d")

    filename = f"nexstar_milky_way_{location_short}_{date_str}_{command}.txt"
    return Path(filename)


def _format_visibility_level(level: str) -> str:
    """Format visibility level with color."""
    colors = {
        "excellent": "[bold bright_green]Excellent[/bold bright_green]",
        "good": "[bold green]Good[/bold green]",
        "fair": "[bold yellow]Fair[/bold yellow]",
        "poor": "[yellow]Poor[/yellow]",
        "none": "[dim]None[/dim]",
    }
    return colors.get(level, level)


@app.command("tonight")
def show_tonight(
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Check if the Milky Way is visible tonight from your location."""
    location = get_observer_location()
    if not location:
        console.print(
            "[red]Error: No observer location set. Use 'nexstar location set' to configure your location.[/red]"
        )
        raise typer.Exit(1)

    # Check Milky Way visibility
    forecast = check_milky_way_visibility(location)

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("tonight", location)
        file_console = create_file_console()
        _show_milky_way_content(file_console, location, forecast)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_milky_way_content(console, location, forecast)


def _show_milky_way_content(
    output_console: Console | FileConsole, location: ObserverLocation, forecast: MilkyWayForecast | None
) -> None:
    """Display Milky Way visibility information."""

    location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

    output_console.print(f"\n[bold cyan]Milky Way Visibility for {location_name}[/bold cyan]")
    output_console.print("[dim]Milky Way visibility based on dark sky conditions, moon phase, and weather[/dim]\n")

    if forecast is None:
        output_console.print("[yellow]⚠ Unable to calculate Milky Way visibility[/yellow]")
        output_console.print("[dim]This may be due to missing location or calculation errors.[/dim]")
        output_console.print("[dim]Try again in a few minutes.[/dim]\n")
        return

    # Main status
    if forecast.is_visible:
        output_console.print("[bold bright_green]✓ Milky Way is VISIBLE tonight![/bold bright_green]\n")
    else:
        output_console.print("[dim]○ Milky Way is not visible tonight[/dim]\n")

    # Detailed information table
    table = Table(show_header=True, header_style="bold")
    table.add_column("Parameter", style="cyan")
    table.add_column("Value", style="white")

    # Visibility Score
    score_pct = forecast.visibility_score * 100.0

    # Visibility Level
    vis_level_str = _format_visibility_level(forecast.visibility_level)
    # Add calculation note
    level_calc = {
        "excellent": " (score ≥ 70%)",
        "good": " (score ≥ 50%)",
        "fair": " (score ≥ 30%)",
        "poor": " (score ≥ 10%)",
        "none": " (score < 10%)",
    }
    vis_level_str += f"[dim]{level_calc.get(forecast.visibility_level, '')}[/dim]"
    table.add_row("Visibility Level", vis_level_str)
    if score_pct >= 70:
        score_color = "[bold bright_green]"
        score_desc = " (Excellent conditions)"
    elif score_pct >= 50:
        score_color = "[green]"
        score_desc = " (Good conditions)"
    elif score_pct >= 30:
        score_color = "[yellow]"
        score_desc = " (Fair conditions)"
    else:
        score_color = "[red]"
        score_desc = " (Poor conditions)"
    table.add_row("Visibility Score", f"{score_color}{score_pct:.1f}%{score_desc}[/{score_color.strip('[]')}]")

    # Light pollution (Bortle class)
    if forecast.bortle_class is not None:
        bortle_colors = {
            1: "[bold bright_green]Class 1 - Excellent[/bold bright_green]",
            2: "[bright_green]Class 2 - Excellent[/bright_green]",
            3: "[green]Class 3 - Rural[/green]",
            4: "[yellow]Class 4 - Rural/Suburban[/yellow]",
            5: "[yellow]Class 5 - Suburban[/yellow]",
            6: "[red]Class 6 - Bright Suburban[/red]",
            7: "[red]Class 7 - Suburban/Urban[/red]",
            8: "[bold red]Class 8 - City[/bold red]",
            9: "[bold red]Class 9 - Inner City[/bold red]",
        }
        bortle_str = bortle_colors.get(forecast.bortle_class, f"Class {forecast.bortle_class}")
        if forecast.sqm_value is not None:
            bortle_str += f" (SQM: {forecast.sqm_value:.2f})"
        table.add_row("Light Pollution (Bortle)", bortle_str)
    else:
        table.add_row("Light Pollution (Bortle)", "[dim]Unknown[/dim]")

    # Darkness
    if forecast.is_dark:
        table.add_row("Darkness", "[green]✓ Dark enough (after sunset, before sunrise)[/green]")
    else:
        table.add_row("Darkness", "[yellow]✗ Too bright (need darkness for Milky Way viewing)[/yellow]")

    # Moon phase and position
    if forecast.moon_illumination is not None:
        moon_pct = forecast.moon_illumination * 100
        moon_status_parts = []

        if moon_pct < 1:
            moon_status_parts.append("[green]New Moon - ideal[/green]")
        elif moon_pct < 30:
            moon_status_parts.append("[green]Crescent - good[/green]")
        elif moon_pct < 70:
            moon_status_parts.append("[yellow]Quarter - moderate[/yellow]")
        else:
            moon_status_parts.append("[red]Bright moon - poor[/red]")

        # Add moon altitude information
        if forecast.moon_altitude is not None:
            if forecast.moon_altitude < 0:
                moon_status_parts.append("(below horizon - no impact)")
            elif forecast.moon_altitude < 10:
                moon_status_parts.append(f"(low: {forecast.moon_altitude:.0f}° - minimal impact)")
            elif forecast.moon_altitude < 30:
                moon_status_parts.append(f"(moderate: {forecast.moon_altitude:.0f}° - some impact)")
            else:
                moon_status_parts.append(f"(high: {forecast.moon_altitude:.0f}° - significant impact)")

        moon_display = f"{moon_pct:.0f}% illuminated " + " ".join(moon_status_parts)
        table.add_row("Moon Phase", moon_display)

        # Add moonrise/moonset times if available
        if forecast.moonrise_time or forecast.moonset_time:
            moon_times = []
            if forecast.moonset_time:
                moonset_str = forecast.moonset_time.strftime("%I:%M %p")
                moon_times.append(f"Sets: {moonset_str}")
            if forecast.moonrise_time:
                moonrise_str = forecast.moonrise_time.strftime("%I:%M %p")
                moon_times.append(f"Rises: {moonrise_str}")
            if moon_times:
                table.add_row("Moon Times", ", ".join(moon_times))
    else:
        table.add_row("Moon Phase", "[dim]Unknown[/dim]")

    # Cloud cover
    if forecast.cloud_cover_percent is not None:
        if forecast.cloud_cover_percent < 20:
            table.add_row("Cloud Cover", f"[green]{forecast.cloud_cover_percent:.0f}% (Clear skies)[/green]")
        elif forecast.cloud_cover_percent < 50:
            table.add_row("Cloud Cover", f"[yellow]{forecast.cloud_cover_percent:.0f}% (Partly cloudy)[/yellow]")
        else:
            table.add_row("Cloud Cover", f"[red]{forecast.cloud_cover_percent:.0f}% (Cloudy - blocks view)[/red]")
    else:
        table.add_row("Cloud Cover", "[dim]Unknown[/dim]")

    # Galactic center
    if forecast.galactic_center_altitude is not None:
        if forecast.galactic_center_visible:
            if forecast.galactic_center_altitude >= 30:
                gc_str = f"[green]{forecast.galactic_center_altitude:.1f}° (Excellent altitude)[/green]"
            else:
                gc_str = f"[green]{forecast.galactic_center_altitude:.1f}° (Visible)[/green]"
        else:
            gc_str = f"[yellow]{forecast.galactic_center_altitude:.1f}° (Below horizon)[/yellow]"
        table.add_row("Galactic Center Altitude", gc_str)
    else:
        table.add_row("Galactic Center Altitude", "[dim]Unknown[/dim]")

    # Peak viewing window
    if forecast.peak_viewing_start and forecast.peak_viewing_end:
        start_str = forecast.peak_viewing_start.strftime("%I:%M %p")
        end_str = forecast.peak_viewing_end.strftime("%I:%M %p")
        table.add_row("Peak Viewing Window", f"[green]{start_str} - {end_str}[/green]")

    output_console.print(table)

    # Viewing tips
    output_console.print("\n[bold]Viewing Tips:[/bold]")
    if forecast.is_visible:
        output_console.print("  • [green]Look toward the southern horizon (Northern Hemisphere)[/green]")
        output_console.print("  • [green]Best viewed with naked eye or binoculars[/green]")
        output_console.print("  • [green]Allow 20-30 minutes for dark adaptation[/green]")
        output_console.print("  • [green]The Milky Way appears as a faint band of light across the sky[/green]")
        if forecast.cloud_cover_percent and forecast.cloud_cover_percent > 50:
            output_console.print("  • [yellow]⚠ Heavy cloud cover may block the view - check weather forecast[/yellow]")
        if forecast.moon_illumination and forecast.moon_illumination > 0.3:
            if forecast.moon_altitude is not None and forecast.moon_altitude < 0:
                output_console.print("  • [green]✓ Moon is below horizon - no interference[/green]")
            else:
                output_console.print("  • [yellow]⚠ Bright moon may reduce visibility of faint Milky Way[/yellow]")
                if forecast.moonset_time:
                    from zoneinfo import ZoneInfo

                    from timezonefinder import TimezoneFinder

                    try:
                        _tz_finder = TimezoneFinder()
                        tz_name = _tz_finder.timezone_at(lat=location.latitude, lng=location.longitude)
                        tz = ZoneInfo(tz_name) if tz_name else None
                        if tz:
                            moonset_local = forecast.moonset_time.astimezone(tz)
                            moonset_str = moonset_local.strftime("%I:%M %p")
                            output_console.print(
                                f"  • [dim]Moon sets at {moonset_str} - better viewing after that time[/dim]"
                            )
                    except Exception:
                        pass
        if forecast.bortle_class and forecast.bortle_class > 4:
            output_console.print(
                "  • [yellow]⚠ Light pollution may limit visibility - consider darker location[/yellow]"
            )
    else:
        if forecast.bortle_class and forecast.bortle_class > 4:
            output_console.print(
                f"  • [dim]Light pollution (Bortle Class {forecast.bortle_class}) is too high for Milky Way viewing[/dim]"
            )
            output_console.print("  • [dim]Need Bortle Class 4 or better (ideally 1-3) for good visibility[/dim]")
        if not forecast.is_dark:
            output_console.print("  • [dim]Wait until after sunset for darkness[/dim]")
        if forecast.cloud_cover_percent and forecast.cloud_cover_percent > 50:
            output_console.print("  • [dim]Heavy cloud cover is blocking visibility[/dim]")
        if forecast.moon_illumination and forecast.moon_illumination > 0.3:
            if forecast.moon_altitude is not None and forecast.moon_altitude < 0:
                output_console.print("  • [green]✓ Moon is below horizon - no interference from moon[/green]")
            else:
                output_console.print("  • [dim]Bright moon is washing out the faint Milky Way[/dim]")
                output_console.print("  • [dim]Best viewing is during New Moon or crescent phase[/dim]")
                if forecast.moonset_time:
                    from zoneinfo import ZoneInfo

                    from timezonefinder import TimezoneFinder

                    try:
                        _tz_finder = TimezoneFinder()
                        tz_name = _tz_finder.timezone_at(lat=location.latitude, lng=location.longitude)
                        tz = ZoneInfo(tz_name) if tz_name else None
                        if tz:
                            moonset_local = forecast.moonset_time.astimezone(tz)
                            moonset_str = moonset_local.strftime("%I:%M %p")
                            output_console.print(
                                f"  • [dim]Moon sets at {moonset_str} - better viewing after that time[/dim]"
                            )
                    except Exception:
                        pass
        if forecast.galactic_center_altitude is not None and not forecast.galactic_center_visible:
            output_console.print("  • [dim]Galactic center is below the horizon[/dim]")
            output_console.print("  • [dim]In Northern Hemisphere, best viewing is during summer months[/dim]")

    output_console.print(
        "\n[dim]💡 Tip: Milky Way visibility depends heavily on dark skies. Even Bortle Class 4 locations may show only faint traces.[/dim]"
    )
    output_console.print(
        "[dim]💡 Tip: Summer months (June-August) offer the best views of the galactic center in the Northern Hemisphere.[/dim]"
    )
    output_console.print("[dim]💡 Tip: Use 'nexstar location light-pollution' to find darker locations near you.[/dim]")
    output_console.print("\n[bold]Visibility Level Calculation:[/bold]")
    output_console.print("  • [dim]Excellent: score ≥ 70%[/dim]")
    output_console.print("  • [dim]Good: score ≥ 50%[/dim]")
    output_console.print("  • [dim]Fair: score ≥ 30%[/dim]")
    output_console.print("  • [dim]Poor: score ≥ 10%[/dim]")
    output_console.print("  • [dim]None: score < 10%[/dim]")
    output_console.print(
        "  • [dim]Use 'nexstar milky-way how' for detailed explanation of the scoring algorithm[/dim]\n"
    )


@app.command("when")
def show_when(
    location: str | None = typer.Argument(None, help="Location (city, address, or ZIP code) to check"),
    days: int = typer.Option(7, "--days", "-d", help="Number of days to check (default: 7, max: 14)"),
    latitude: float | None = typer.Option(None, "--lat", help="Latitude in degrees (-90 to +90)"),
    longitude: float | None = typer.Option(None, "--lon", help="Longitude in degrees (-180 to +180)"),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Find when the Milky Way will be visible from a location in the next few days.

    You can specify location by:
    1. City/address/ZIP code (geocoded automatically)
    2. Explicit lat/lon coordinates (--lat and --lon)
    3. If no location provided, you'll be prompted to enter one

    Examples:
        nexstar milky-way when "New York, NY"
        nexstar milky-way when --lat 40.7128 --lon -74.0060
        nexstar milky-way when  # Will prompt for location
    """
    import asyncio
    import sys

    from rich.prompt import Prompt

    from celestron_nexstar.api.location.observer import geocode_location

    observer_location: ObserverLocation | None = None

    # Option 1: Geocode from city/address/ZIP
    if location:
        try:
            console.print(f"[dim]Geocoding location: {location}...[/dim]")
            observer_location = asyncio.run(geocode_location(location))
            console.print(f"[green]✓[/green] Found: {observer_location.name}\n")
        except Exception as e:
            console.print(f"[red]Error: Could not geocode location '{location}': {e}[/red]")
            raise typer.Exit(1) from e

    # Option 2: Use explicit coordinates
    elif latitude is not None and longitude is not None:
        if not -90 <= latitude <= 90:
            console.print("[red]Error: Latitude must be between -90 and +90 degrees[/red]")
            raise typer.Exit(1)
        if not -180 <= longitude <= 180:
            console.print("[red]Error: Longitude must be between -180 and +180 degrees[/red]")
            raise typer.Exit(1)

        observer_location = ObserverLocation(latitude=latitude, longitude=longitude, elevation=0.0, name=None)

    # Option 3: Try to get saved location
    else:
        try:
            observer_location = get_observer_location()
        except Exception:
            observer_location = None

        # Option 4: Prompt user if no location available
        if not observer_location:
            # Check if we're in an interactive terminal
            if sys.stdin.isatty():
                console.print("\n[cyan]Location Required[/cyan]")
                console.print(
                    "[dim]Enter a location to check Milky Way visibility. You can provide:\n"
                    "  • City name (e.g., 'New York, NY')\n"
                    "  • Address (e.g., '123 Main St, Boston, MA')\n"
                    "  • ZIP code (e.g., '90210')\n"
                    "  • Coordinates (e.g., '40.7128, -74.0060')\n[/dim]"
                )

                location_input = Prompt.ask("Enter location", default="", console=console)

                if not location_input:
                    console.print("[red]Error: No location provided[/red]")
                    raise typer.Exit(1)

                # Try to parse as coordinates first (lat, lon)
                try:
                    # Check if input looks like coordinates (contains comma and numbers)
                    parts = location_input.split(",")
                    if len(parts) == 2:
                        try:
                            lat = float(parts[0].strip())
                            lon = float(parts[1].strip())
                            if -90 <= lat <= 90 and -180 <= lon <= 180:
                                observer_location = ObserverLocation(
                                    latitude=lat, longitude=lon, elevation=0.0, name=None
                                )
                                console.print(f"[green]✓[/green] Using coordinates: {lat:.4f}°, {lon:.4f}°\n")
                            else:
                                raise ValueError("Coordinates out of range")
                        except ValueError:
                            # Not coordinates, treat as address
                            pass
                except Exception:
                    pass

                # If not coordinates, geocode as address
                if not observer_location:
                    try:
                        console.print(f"[dim]Geocoding: {location_input}...[/dim]")
                        observer_location = asyncio.run(geocode_location(location_input))
                        console.print(f"[green]✓[/green] Found: {observer_location.name}\n")
                    except Exception as e:
                        console.print(f"[red]Error: Could not geocode location '{location_input}': {e}[/red]")
                        raise typer.Exit(1) from e
            else:
                # Non-interactive environment
                console.print("[red]Error: No observer location set and not in interactive mode.[/red]")
                console.print(
                    "[dim]Set your location with 'nexstar location set-observer' or provide --location, --lat, --lon[/dim]"
                )
                raise typer.Exit(1)

    if not observer_location:
        console.print("[red]Error: No observer location available.[/red]")
        raise typer.Exit(1)

    # Limit days to 14
    days = min(days, 14)

    # Get visibility windows (this may take a moment as it fetches weather data)
    console.print(f"[dim]Analyzing visibility windows for the next {days} days...[/dim]")
    windows = get_milky_way_visibility_windows(observer_location, days=days)

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("when", observer_location)
        file_console = create_file_console()
        _show_when_content(file_console, observer_location, windows, days)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_when_content(console, observer_location, windows, days)


def _show_when_content(
    output_console: Console | FileConsole,
    location: ObserverLocation,
    windows: list[tuple[datetime, datetime, float, str]],
    days: int,
) -> None:
    """Display Milky Way visibility windows."""
    from zoneinfo import ZoneInfo

    from timezonefinder import TimezoneFinder

    _tz_finder = TimezoneFinder()

    location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

    output_console.print(f"\n[bold cyan]Milky Way Visibility Windows for {location_name}[/bold cyan]")
    output_console.print(f"[dim]Forecast for the next {days} days based on dark sky conditions and moon phase[/dim]\n")

    if not windows:
        output_console.print("[yellow]No Milky Way visibility windows found in the forecast period.[/yellow]")
        output_console.print(
            "[dim]Conditions may not be favorable due to light pollution, moon phase, or weather.[/dim]\n"
        )
        output_console.print(
            "[dim]💡 Tip: Milky Way requires dark skies (Bortle Class 4 or better) and dark moon.[/dim]"
        )
        output_console.print("[dim]💡 Tip: Try 'nexstar milky-way next' to find upcoming opportunities.[/dim]\n")
        return

    # Get timezone for formatting
    try:
        tz_name = _tz_finder.timezone_at(lat=location.latitude, lng=location.longitude)
        tz = ZoneInfo(tz_name) if tz_name else None
    except Exception:
        tz = None

    # Display windows in a table
    table = Table(show_header=True, header_style="bold")
    table.add_column("Start Time", style="cyan")
    table.add_column("End Time", style="cyan")
    table.add_column("Duration", justify="right")
    table.add_column("Max Score", justify="right")
    table.add_column("Visibility")

    for start_time, end_time, max_score, visibility_level in windows:
        # Format times in local timezone
        if tz:
            start_local = start_time.astimezone(tz)
            end_local = end_time.astimezone(tz)
            start_str = start_local.strftime("%Y-%m-%d %H:%M")
            end_str = end_local.strftime("%Y-%m-%d %H:%M")
        else:
            start_str = start_time.strftime("%Y-%m-%d %H:%M UTC")
            end_str = end_time.strftime("%Y-%m-%d %H:%M UTC")

        # Calculate duration
        duration = end_time - start_time
        hours = duration.total_seconds() / 3600
        if hours < 24:
            duration_str = f"{hours:.1f}h"
        else:
            days_duration = hours / 24
            duration_str = f"{days_duration:.1f}d"

        # Format score with color
        score_pct = max_score * 100.0
        if score_pct >= 70:
            score_str = f"[bold bright_green]{score_pct:.0f}%[/bold bright_green]"
        elif score_pct >= 50:
            score_str = f"[green]{score_pct:.0f}%[/green]"
        elif score_pct >= 30:
            score_str = f"[yellow]{score_pct:.0f}%[/yellow]"
        else:
            score_str = f"[dim]{score_pct:.0f}%[/dim]"

        # Format visibility level with calculation
        vis_str = _format_visibility_level(visibility_level)
        # Add calculation note
        level_calc = {
            "excellent": " (≥70%)",
            "good": " (≥50%)",
            "fair": " (≥30%)",
            "poor": " (≥10%)",
            "none": " (<10%)",
        }
        vis_str += f"[dim]{level_calc.get(visibility_level, '')}[/dim]"

        table.add_row(start_str, end_str, duration_str, score_str, vis_str)

    output_console.print(table)

    output_console.print("\n[bold]Viewing Tips:[/bold]")
    output_console.print("  • [green]Look toward the southern horizon (Northern Hemisphere)[/green]")
    output_console.print("  • [green]Best viewed with naked eye or binoculars[/green]")
    output_console.print("  • [green]Allow 20-30 minutes for dark adaptation[/green]")
    output_console.print("  • [green]Check weather forecast for cloud cover during these times[/green]")
    output_console.print(
        "  • [yellow]⚠ Forecasts are predictions and may change - check 'nexstar milky-way tonight' for current conditions[/yellow]"
    )
    output_console.print(
        "\n[dim]💡 Tip: Milky Way visibility depends heavily on dark skies and moon phase. Even Bortle Class 4 locations may show only faint traces.[/dim]"
    )
    output_console.print("\n[bold]Visibility Level Calculation:[/bold]")
    output_console.print("  • [dim]Excellent: score ≥ 70%[/dim]")
    output_console.print("  • [dim]Good: score ≥ 50%[/dim]")
    output_console.print("  • [dim]Fair: score ≥ 30%[/dim]")
    output_console.print("  • [dim]Poor: score ≥ 10%[/dim]")
    output_console.print("  • [dim]None: score < 10%[/dim]")
    output_console.print(
        "  • [dim]Use 'nexstar milky-way how' for detailed explanation of the scoring algorithm[/dim]\n"
    )


@app.command("next")
def show_next(
    location: str | None = typer.Argument(None, help="Location (city, address, or ZIP code) to check"),
    months: int = typer.Option(12, "--months", "-m", help="Number of months ahead to search (default: 12)"),
    min_score: float = typer.Option(
        0.5, "--min-score", help="Minimum visibility score threshold (0.0-1.0, default: 0.5)"
    ),
    limit: int = typer.Option(10, "--limit", "-l", help="Maximum number of opportunities to show (default: 10)"),
    latitude: float | None = typer.Option(None, "--lat", help="Latitude in degrees (-90 to +90)"),
    longitude: float | None = typer.Option(None, "--lon", help="Longitude in degrees (-180 to +180)"),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Find the next best Milky Way viewing opportunities using moon phase and seasonal patterns.

    You can specify location by:
    1. City/address/ZIP code (geocoded automatically)
    2. Explicit lat/lon coordinates (--lat and --lon)
    3. If no location provided, you'll be prompted to enter one

    Examples:
        nexstar milky-way next "New York, NY"
        nexstar milky-way next --lat 40.7128 --lon -74.0060
        nexstar milky-way next  # Will prompt for location
    """
    import asyncio
    import sys

    from rich.prompt import Prompt

    from celestron_nexstar.api.location.observer import geocode_location

    observer_location: ObserverLocation | None = None

    # Option 1: Geocode from city/address/ZIP
    if location:
        try:
            console.print(f"[dim]Geocoding location: {location}...[/dim]")
            observer_location = asyncio.run(geocode_location(location))
            console.print(f"[green]✓[/green] Found: {observer_location.name}\n")
        except Exception as e:
            console.print(f"[red]Error: Could not geocode location '{location}': {e}[/red]")
            raise typer.Exit(1) from e

    # Option 2: Use explicit coordinates
    elif latitude is not None and longitude is not None:
        if not -90 <= latitude <= 90:
            console.print("[red]Error: Latitude must be between -90 and +90 degrees[/red]")
            raise typer.Exit(1)
        if not -180 <= longitude <= 180:
            console.print("[red]Error: Longitude must be between -180 and +180 degrees[/red]")
            raise typer.Exit(1)

        observer_location = ObserverLocation(latitude=latitude, longitude=longitude, elevation=0.0, name=None)

    # Option 3: Try to get saved location
    else:
        try:
            observer_location = get_observer_location()
        except Exception:
            observer_location = None

        # Option 4: Prompt user if no location available
        if not observer_location:
            # Check if we're in an interactive terminal
            if sys.stdin.isatty():
                console.print("\n[cyan]Location Required[/cyan]")
                console.print(
                    "[dim]Enter a location to find Milky Way viewing opportunities. You can provide:\n"
                    "  • City name (e.g., 'New York, NY')\n"
                    "  • Address (e.g., '123 Main St, Boston, MA')\n"
                    "  • ZIP code (e.g., '90210')\n"
                    "  • Coordinates (e.g., '40.7128, -74.0060')\n[/dim]"
                )

                location_input = Prompt.ask("Enter location", default="", console=console)

                if not location_input:
                    console.print("[red]Error: No location provided[/red]")
                    raise typer.Exit(1)

                # Try to parse as coordinates first (lat, lon)
                try:
                    # Check if input looks like coordinates (contains comma and numbers)
                    parts = location_input.split(",")
                    if len(parts) == 2:
                        try:
                            lat = float(parts[0].strip())
                            lon = float(parts[1].strip())
                            if -90 <= lat <= 90 and -180 <= lon <= 180:
                                observer_location = ObserverLocation(
                                    latitude=lat, longitude=lon, elevation=0.0, name=None
                                )
                                console.print(f"[green]✓[/green] Using coordinates: {lat:.4f}°, {lon:.4f}°\n")
                            else:
                                raise ValueError("Coordinates out of range")
                        except ValueError:
                            # Not coordinates, treat as address
                            pass
                except Exception:
                    pass

                # If not coordinates, geocode as address
                if not observer_location:
                    try:
                        console.print(f"[dim]Geocoding: {location_input}...[/dim]")
                        observer_location = asyncio.run(geocode_location(location_input))
                        console.print(f"[green]✓[/green] Found: {observer_location.name}\n")
                    except Exception as e:
                        console.print(f"[red]Error: Could not geocode location '{location_input}': {e}[/red]")
                        raise typer.Exit(1) from e
            else:
                # Non-interactive environment
                console.print("[red]Error: No observer location set and not in interactive mode.[/red]")
                console.print(
                    "[dim]Set your location with 'nexstar location set-observer' or provide --location, --lat, --lon[/dim]"
                )
                raise typer.Exit(1)

    if not observer_location:
        console.print("[red]Error: No observer location available.[/red]")
        raise typer.Exit(1)

    # Get opportunities
    console.print(f"[dim]Analyzing opportunities for the next {months} months...[/dim]")
    console.print(f"[dim]Checking historical cloud cover data for {observer_location.name or 'location'}...[/dim]")
    opportunities, month_data_source = get_next_milky_way_opportunity(
        observer_location, months_ahead=months, min_score=min_score
    )

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("next", observer_location)
        file_console = create_file_console()
        _show_next_content(file_console, observer_location, opportunities, limit, months, month_data_source)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_next_content(console, observer_location, opportunities, limit, months, month_data_source)


def _show_next_content(
    output_console: Console | FileConsole,
    location: ObserverLocation,
    opportunities: list[MilkyWayOpportunity],
    limit: int,
    months: int,
    month_data_source: dict[int, bool],
) -> None:
    """Display next Milky Way opportunities with scores."""

    location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

    output_console.print(f"\n[bold cyan]Next Milky Way Viewing Opportunities for {location_name}[/bold cyan]")
    output_console.print("[dim]Forecast based on moon phase cycles and seasonal patterns[/dim]")
    output_console.print(f"[dim]Searching next {months} months, showing top {limit} opportunities[/dim]\n")

    if not opportunities:
        output_console.print("[yellow]No Milky Way opportunities found above the score threshold.[/yellow]")
        output_console.print(
            "[dim]This may be due to high light pollution or unfavorable conditions in the forecast period.[/dim]"
        )
        output_console.print("[dim]Try lowering --min-score or increasing --months to see more opportunities.[/dim]\n")
        return

    # Display opportunities table
    table = Table(show_header=True, header_style="bold")
    table.add_column("Month", style="cyan")
    table.add_column("Season")
    table.add_column("Expected Score", justify="right")
    table.add_column("Moon Phase", justify="right")
    table.add_column("Galactic Center", justify="right")
    table.add_column("Confidence")
    table.add_column("Notes", style="dim")

    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    for opp in opportunities[:limit]:
        month_str = f"{month_names[opp.month - 1]} {opp.start_date.year}"

        # Format expected score with color and range if available
        score_pct = opp.expected_visibility_score * 100.0
        if opp.min_visibility_score is not None and opp.max_visibility_score is not None:
            min_pct = opp.min_visibility_score * 100.0
            max_pct = opp.max_visibility_score * 100.0
            # Show range: min-max (expected)
            if score_pct >= 70:
                score_display = f"[bold bright_green]{min_pct:.0f}-{max_pct:.0f}%[/bold bright_green]"
            elif score_pct >= 50:
                score_display = f"[green]{min_pct:.0f}-{max_pct:.0f}%[/green]"
            elif score_pct >= 30:
                score_display = f"[yellow]{min_pct:.0f}-{max_pct:.0f}%[/yellow]"
            else:
                score_display = f"[dim]{min_pct:.0f}-{max_pct:.0f}%[/dim]"
        else:
            # Fallback to single score
            if score_pct >= 70:
                score_display = f"[bold bright_green]{score_pct:.0f}%[/bold bright_green]"
            elif score_pct >= 50:
                score_display = f"[green]{score_pct:.0f}%[/green]"
            elif score_pct >= 30:
                score_display = f"[yellow]{score_pct:.0f}%[/yellow]"
            else:
                score_display = f"[dim]{score_pct:.0f}%[/dim]"

        # Format moon phase factor
        moon_pct = opp.moon_phase_factor * 100.0
        if moon_pct >= 80:
            moon_display = f"[green]{moon_pct:.0f}%[/green]"
        elif moon_pct >= 50:
            moon_display = f"[yellow]{moon_pct:.0f}%[/yellow]"
        else:
            moon_display = f"[red]{moon_pct:.0f}%[/red]"

        # Format galactic center factor
        gc_pct = opp.galactic_center_factor * 100.0
        if gc_pct >= 80:
            gc_display = f"[green]{gc_pct:.0f}%[/green]"
        elif gc_pct >= 50:
            gc_display = f"[yellow]{gc_pct:.0f}%[/yellow]"
        else:
            gc_display = f"[dim]{gc_pct:.0f}%[/dim]"

        # Format confidence
        conf_colors = {
            "high": "[green]High[/green]",
            "medium": "[yellow]Medium[/yellow]",
            "low": "[dim]Low[/dim]",
        }
        conf_display = conf_colors.get(opp.confidence, opp.confidence)

        # Truncate notes if too long
        notes_display = opp.notes[:60] + "..." if len(opp.notes) > 60 else opp.notes

        table.add_row(month_str, opp.season, score_display, moon_display, gc_display, conf_display, notes_display)

    output_console.print(table)

    output_console.print("\n[bold]Understanding the Scores:[/bold]")
    output_console.print("  • [dim]Expected Score shows overall visibility quality (0-100%)[/dim]")
    output_console.print(
        "  • [dim]Score ranges (e.g., 45-55%) show best-case to worst-case based on cloud cover estimates[/dim]"
    )
    output_console.print(
        "  • [dim]Narrower ranges (e.g., 45-55%) indicate higher confidence than wider ranges (e.g., 30-70%)[/dim]"
    )
    output_console.print("  • [dim]Moon Phase shows how dark the moon will be (higher is better)[/dim]")
    output_console.print("  • [dim]Galactic Center shows how well-positioned the galactic center will be[/dim]")
    output_console.print(
        "  • [dim]Based on moon phase cycles, seasonal patterns, and climatological cloud cover estimates[/dim]"
    )
    output_console.print(
        "  • [green]✓ Opportunities within 14 days use actual weather forecasts for higher accuracy[/green]"
    )
    output_console.print(
        "  • [dim]Longer-term opportunities use historical data (p40-p60 percentile range for tighter predictions)[/dim]"
    )
    output_console.print("\n[bold]Cloud Cover Data Source:[/bold]")

    # Group months by data source
    historical_months: list[int] = []
    seasonal_months: list[int] = []
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    for month, used_historical in sorted(month_data_source.items()):
        if used_historical:
            historical_months.append(month)
        else:
            seasonal_months.append(month)

    if historical_months:
        month_strs = [month_names[m - 1] for m in historical_months]
        output_console.print(f"  • [green]✓ Historical data used for:[/green] [dim]{', '.join(month_strs)}[/dim]")
        output_console.print("    [dim]   Location-specific statistics from Open-Meteo (2000-present)[/dim]")
        output_console.print("    [dim]   Using p40-p60 percentile range (tighter, more confident predictions)[/dim]")

    if seasonal_months:
        month_strs = [month_names[m - 1] for m in seasonal_months]
        output_console.print(f"  • [yellow]⚠ Seasonal estimates used for:[/yellow] [dim]{', '.join(month_strs)}[/dim]")
        output_console.print("    [dim]   General seasonal cloud cover patterns (historical data not available)[/dim]")

    if not month_data_source:
        output_console.print("  • [dim]No cloud cover data available for analyzed months[/dim]")

    output_console.print("  • [dim]Historical data is checked first and cached in the database for future use[/dim]")
    output_console.print(
        "  • [dim]Use 'nexstar weather historical' to view historical cloud cover data for your location[/dim]"
    )
    output_console.print("\n[bold]Visibility Level Calculation:[/bold]")
    output_console.print("  • [dim]Excellent: score ≥ 70%[/dim]")
    output_console.print("  • [dim]Good: score ≥ 50%[/dim]")
    output_console.print("  • [dim]Fair: score ≥ 30%[/dim]")
    output_console.print("  • [dim]Poor: score ≥ 10%[/dim]")
    output_console.print("  • [dim]None: score < 10%[/dim]")

    output_console.print("\n[bold]Planning Tips:[/bold]")
    output_console.print("  • [green]Book travel during high-score months for best chances[/green]")
    output_console.print("  • [green]Monitor 'nexstar milky-way when' as dates approach for specific forecasts[/green]")
    output_console.print(
        "  • [green]Check 'nexstar milky-way tonight' during your visit for real-time conditions[/green]"
    )
    output_console.print(
        "  • [yellow]⚠ Even high-score months don't guarantee visibility - weather and timing matter[/yellow]"
    )
    output_console.print(
        "\n[dim]💡 Tip: Use --min-score to filter results (e.g., --min-score 0.6 for 60%+ expected score)[/dim]\n"
    )


@app.command("how")
def show_how(
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Explain how Milky Way visibility is determined."""
    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("how")
        file_console = create_file_console()
        _show_how_content(file_console)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_how_content(console)


def _show_how_content(output_console: Console | FileConsole) -> None:
    """Display information about how Milky Way visibility is determined."""
    output_console.print("\n[bold cyan]How Milky Way Visibility is Determined[/bold cyan]\n")

    output_console.print(
        "[dim]Milky Way visibility is calculated using a multiplicative scoring model that considers "
        "four key factors. The algorithm starts with a perfect score of 1.0 and multiplies by factors "
        "for each condition, resulting in a final visibility score from 0.0 to 1.0 (0% to 100%).[/dim]\n"
    )

    # Algorithm overview
    output_console.print("[bold]Algorithm Overview[/bold]")
    output_console.print("  • Start with score = 1.0 (100%)")
    output_console.print("  • Multiply by factor for each condition")
    output_console.print("  • Final score determines visibility level")
    output_console.print("  • Milky Way is visible if score > 0.3 (30%) and it's dark\n")

    # Factor 1: Light Pollution
    output_console.print("[bold]1. Light Pollution (Bortle Class) - [yellow]Most Important[/yellow][/bold]")
    table1 = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table1.add_column("Bortle Class", style="cyan")
    table1.add_column("Description", style="white")
    table1.add_column("Factor", justify="right", style="green")
    table1.add_column("Impact", style="dim")

    table1.add_row("1-3", "Excellent dark sky", "1.0", "No reduction")
    table1.add_row("4", "Rural/Suburban transition", "0.7", "30% reduction")
    table1.add_row("5", "Suburban", "0.4", "60% reduction")
    table1.add_row("6+", "Bright suburban to city", "0.1", "90% reduction")

    output_console.print(table1)
    output_console.print(
        "  [dim]💡 Light pollution is the most critical factor. Even Bortle Class 4 locations may only show faint traces of the Milky Way.[/dim]\n"
    )

    # Factor 2: Moon Phase and Altitude
    output_console.print("[bold]2. Moon Phase and Altitude - [yellow]Very Important[/yellow][/bold]")
    table2 = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table2.add_column("Moon Phase", style="cyan")
    table2.add_column("Illumination", style="white")
    table2.add_column("Factor", justify="right", style="green")
    table2.add_column("Impact", style="dim")

    table2.add_row("New Moon", "< 1%", "1.0", "No reduction (ideal)")
    table2.add_row("Crescent", "< 30%", "0.8", "20% reduction (good)")
    table2.add_row("Quarter", "30-70%", "0.5", "50% reduction (moderate)")
    table2.add_row("Gibbous/Full", "> 70%", "0.2", "80% reduction (poor)")
    table2.add_row("Below Horizon", "Any phase", "1.0", "No impact (moon not visible)")

    output_console.print(table2)
    output_console.print(
        "  [dim]💡 A bright moon washes out the faint Milky Way. New Moon or crescent phases are essential for good visibility.[/dim]"
    )
    output_console.print(
        "  [dim]💡 If the moon is below the horizon, it doesn't affect visibility regardless of phase.[/dim]"
    )
    output_console.print(
        "  [dim]💡 Moon altitude also matters - a low moon (<10°) has less impact than a high moon (>30°).[/dim]\n"
    )

    # Factor 3: Cloud Cover
    output_console.print("[bold]3. Cloud Cover - [yellow]Important[/yellow][/bold]")
    table3 = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table3.add_column("Sky Condition", style="cyan")
    table3.add_column("Cloud Cover", style="white")
    table3.add_column("Factor", justify="right", style="green")
    table3.add_column("Impact", style="dim")

    table3.add_row("Clear", "< 20%", "1.0", "No reduction")
    table3.add_row("Partly Cloudy", "20-50%", "0.7", "30% reduction")
    table3.add_row("Cloudy", "> 50%", "0.3", "70% reduction")

    output_console.print(table3)
    output_console.print(
        "  [dim]💡 Clouds block the view of the Milky Way. Clear skies are essential for visibility.[/dim]\n"
    )

    # Factor 4: Galactic Center Altitude
    output_console.print("[bold]4. Galactic Center Altitude - [yellow]Moderate Importance[/yellow][/bold]")
    table4 = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table4.add_column("Altitude", style="cyan")
    table4.add_column("Description", style="white")
    table4.add_column("Factor", justify="right", style="green")
    table4.add_column("Impact", style="dim")

    table4.add_row("≥ 30°", "High altitude", "1.0", "No reduction (excellent)")
    table4.add_row("10-30°", "Moderate altitude", "0.8", "20% reduction (good)")
    table4.add_row("< 10°", "Low altitude", "0.5", "50% reduction (fair)")

    output_console.print(table4)
    output_console.print(
        "  [dim]💡 The galactic center (in Sagittarius) is the brightest part of the Milky Way. "
        "Higher altitude means less atmospheric interference and better visibility.[/dim]\n"
    )

    # Missing Data Handling
    output_console.print("[bold]Missing Data Handling[/bold]")
    output_console.print("  If data is unavailable for any factor, the algorithm uses conservative fallback values:\n")
    table_missing = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table_missing.add_column("Factor", style="cyan")
    table_missing.add_column("Fallback Factor", justify="right", style="green")
    table_missing.add_column("Assumption", style="dim")

    table_missing.add_row("Light Pollution", "0.5", "Moderate light pollution assumed")
    table_missing.add_row("Moon Phase", "0.6", "Moderate moon brightness assumed")
    table_missing.add_row("Cloud Cover", "0.9", "Mostly clear skies assumed")
    table_missing.add_row("Galactic Center Altitude", "0.8", "Moderate altitude assumed")

    output_console.print(table_missing)
    output_console.print(
        "  [dim]💡 These fallback values are conservative estimates. When actual data is available, "
        "it will be used instead of these assumptions.[/dim]\n"
    )

    # Visibility Threshold
    output_console.print("[bold]Visibility Threshold[/bold]")
    output_console.print("  • Milky Way is considered [green]visible[/green] if:")
    output_console.print("    - Visibility score > 0.3 (30%)")
    output_console.print("    - AND it's dark (after sunset, before sunrise)")
    output_console.print()

    # Visibility Levels
    output_console.print("[bold]Visibility Levels[/bold]")
    table5 = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table5.add_column("Level", style="cyan")
    table5.add_column("Score Range", style="white")
    table5.add_column("Description", style="dim")

    table5.add_row("[bold bright_green]Excellent[/bold bright_green]", "≥ 70%", "Outstanding viewing conditions")
    table5.add_row("[bold green]Good[/bold green]", "≥ 50%", "Good viewing conditions")
    table5.add_row("[bold yellow]Fair[/bold yellow]", "≥ 30%", "Fair viewing conditions (visible)")
    table5.add_row("[yellow]Poor[/yellow]", "≥ 10%", "Poor viewing conditions (barely visible)")
    table5.add_row("[dim]None[/dim]", "< 10%", "Not visible")

    output_console.print(table5)
    output_console.print()

    # Example Calculation
    output_console.print("[bold]Example Calculation[/bold]")
    output_console.print("  Scenario: Bortle Class 4, 15% moon (crescent), 10% clouds, galactic center at 25°")
    output_console.print()
    output_console.print("  Step 1: Start with score = [green]1.0[/green] (100%)")
    output_console.print("  Step 2: Apply Bortle Class 4 factor → 1.0 x 0.7 = [green]0.7[/green] (70%)")
    output_console.print("  Step 3: Apply crescent moon factor → 0.7 x 0.8 = [green]0.56[/green] (56%)")
    output_console.print("  Step 4: Apply clear skies factor → 0.56 x 1.0 = [green]0.56[/green] (56%)")
    output_console.print("  Step 5: Apply galactic center altitude factor → 0.56 x 0.8 = [green]0.448[/green] (44.8%)")
    output_console.print()
    output_console.print("  Final Score: [bold green]0.448 (44.8%)[/bold green]")
    output_console.print("  Visibility Level: [bold green]Good[/bold green]")
    output_console.print("  Visible: [bold green]Yes[/bold green] (score > 0.3 and dark)\n")

    # Important Notes
    output_console.print("[bold]Important Notes[/bold]")
    output_console.print(
        "  • [yellow]Multiplicative Model:[/yellow] The algorithm uses multiplication, so poor conditions "
        "in one factor can significantly reduce the overall score."
    )
    output_console.print(
        "  • [yellow]Light Pollution is Critical:[/yellow] Even with perfect moon phase and clear skies, "
        "high light pollution (Bortle 6+) makes the Milky Way nearly invisible."
    )
    output_console.print(
        "  • [yellow]Moon Phase Matters:[/yellow] A bright moon can wash out the faint Milky Way, even "
        "in dark sky locations."
    )
    output_console.print(
        "  • [yellow]Conservative Threshold:[/yellow] The 0.3 (30%) threshold is conservative. "
        "Even at Bortle Class 4, the Milky Way may only show faint traces."
    )
    output_console.print(
        "  • [yellow]Seasonal Variation:[/yellow] In the Northern Hemisphere, summer months (June-August) "
        "offer the best views of the galactic center, which is the brightest part of the Milky Way."
    )
    output_console.print()

    # Data Sources
    output_console.print("[bold]Data Sources[/bold]")
    output_console.print("  • Light Pollution: Bortle class from light pollution database")
    output_console.print("  • Moon Phase: Calculated using astronomical algorithms")
    output_console.print("  • Cloud Cover: Weather forecast data")
    output_console.print("  • Galactic Center: Position calculated from coordinates (RA: 17.76h, Dec: -29.01°)")
    output_console.print("  • Darkness: Calculated from sunset/sunrise times\n")

    output_console.print(
        "[dim]💡 For more information, see: https://www.celestron.com/blogs/knowledgebase/the-ultimate-guide-to-viewing-the-milky-way[/dim]\n"
    )


if __name__ == "__main__":
    app()

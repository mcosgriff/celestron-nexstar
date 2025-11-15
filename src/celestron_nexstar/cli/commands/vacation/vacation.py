"""
Vacation Planning Commands

Plan telescope viewing for vacation destinations.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import typer
from click import Context
from rich.console import Console
from rich.table import Table
from typer.core import TyperGroup

from celestron_nexstar.api.astronomy.comets import get_visible_comets
from celestron_nexstar.api.astronomy.eclipses import get_next_lunar_eclipse, get_next_solar_eclipse
from celestron_nexstar.api.astronomy.meteor_shower_predictions import get_enhanced_meteor_predictions
from celestron_nexstar.api.astronomy.planetary_events import get_planetary_conjunctions, get_planetary_oppositions
from celestron_nexstar.api.astronomy.solar_system import get_moon_info, get_sun_info
from celestron_nexstar.api.database.models import get_db_session
from celestron_nexstar.api.events.aurora import check_aurora_visibility
from celestron_nexstar.api.events.iss_tracking import get_iss_passes
from celestron_nexstar.api.events.space_events import get_upcoming_events
from celestron_nexstar.api.events.vacation_planning import (
    DarkSkySite,
    VacationViewingInfo,
    find_dark_sites_near,
    get_vacation_viewing_info,
)
from celestron_nexstar.api.location.light_pollution import BortleClass
from celestron_nexstar.api.location.observer import ObserverLocation, geocode_location
from celestron_nexstar.api.location.weather import fetch_hourly_weather_forecast
from celestron_nexstar.cli.utils.export import FileConsole, create_file_console, export_to_text


class SortedCommandsGroup(TyperGroup):
    """Custom Typer group that sorts commands alphabetically within each help panel."""

    def list_commands(self, ctx: Context) -> list[str]:
        """Return commands sorted alphabetically."""
        commands = super().list_commands(ctx)
        return sorted(commands)


app = typer.Typer(help="Vacation planning for telescope viewing", cls=SortedCommandsGroup)
console = Console()


def _generate_export_filename(
    command: str = "vacation", location: str | None = None, days: int | None = None, date_suffix: str = ""
) -> Path:
    """Generate export filename for vacation commands."""
    import re
    from datetime import datetime

    date_str = datetime.now().strftime("%Y-%m-%d")

    parts = [f"nexstar_vacation_{date_str}", command]

    if location:
        # Sanitize location for filename (remove special chars, limit length)
        sanitized = re.sub(r"[^\w\s-]", "", location)
        sanitized = re.sub(r"[-\s]+", "-", sanitized)
        sanitized = sanitized[:30]  # Limit length
        if sanitized:
            parts.append(sanitized)

    if days is not None:
        parts.append(f"{days}days")

    if date_suffix:
        parts.append(date_suffix.lstrip("_"))

    filename = "_".join(parts) + ".txt"
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
        vacation_location = asyncio.run(geocode_location(location))
    except Exception as e:
        console.print(f"[red]Error: Could not geocode location '{location}': {e}[/red]")
        raise typer.Exit(1) from e

    viewing_info = get_vacation_viewing_info(vacation_location)

    if export:
        location_name = (
            vacation_location.name or f"{vacation_location.latitude:.1f}N-{vacation_location.longitude:.1f}E"
        )
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("view", location_name)
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
    max_distance: float = typer.Option(200.0, "--max-distance", help="Maximum distance in miles (default: 200)"),
    min_bortle: int = typer.Option(4, "--min-bortle", help="Minimum Bortle class (1-9, default: 4)"),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Find dark sky viewing sites near a vacation location."""
    try:
        # Geocode location
        vacation_location = asyncio.run(geocode_location(location))
    except Exception as e:
        console.print(f"[red]Error: Could not geocode location '{location}': {e}[/red]")
        raise typer.Exit(1) from e

    # Validate min_bortle
    if not 1 <= min_bortle <= 9:
        console.print("[red]Error: min-bortle must be between 1 and 9[/red]")
        raise typer.Exit(1)

    # Convert miles to kilometers for internal calculation
    max_distance_km = max_distance * 1.60934

    min_bortle_class = BortleClass(min_bortle)
    dark_sites = find_dark_sites_near(vacation_location, max_distance_km=max_distance_km, min_bortle=min_bortle_class)

    if export:
        location_name = (
            vacation_location.name or f"{vacation_location.latitude:.1f}N-{vacation_location.longitude:.1f}E"
        )
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("dark-sites", location_name)
        file_console = create_file_console()
        _show_dark_sites_content(file_console, vacation_location, dark_sites, max_distance)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_dark_sites_content(console, vacation_location, dark_sites, max_distance)


def _show_viewing_info_content(
    output_console: Console | FileConsole, location: ObserverLocation, viewing_info: VacationViewingInfo
) -> None:
    """Display vacation viewing information."""
    location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

    output_console.print(f"\n[bold cyan]Viewing Conditions for {location_name}[/bold cyan]\n")

    # Sky quality table
    table = Table(show_header=True, header_style="bold")
    table.add_column("Metric", style="cyan")
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
    table.add_row("Naked Eye Limiting Mag", f"{viewing_info.naked_eye_limiting_magnitude:.2f}")
    table.add_row("Milky Way Visible", "[green]Yes[/green]" if viewing_info.milky_way_visible else "[red]No[/red]")

    output_console.print(table)

    output_console.print("\n[bold]Description:[/bold]")
    output_console.print(f"  {viewing_info.description}")

    if viewing_info.recommendations:
        output_console.print("\n[bold]Recommendations:[/bold]")
        for rec in viewing_info.recommendations:
            output_console.print(f"  • {rec}")

    output_console.print("\n[bold]Next Steps:[/bold]")
    output_console.print("  • Use 'nexstar vacation dark-sites' to find nearby dark sky locations")
    output_console.print("  • Use 'nexstar telescope tonight' with this location for detailed viewing")
    output_console.print(
        "\n[dim]💡 Tip: Consider visiting a nearby dark sky site for the best viewing experience![/dim]\n"
    )


def _show_dark_sites_content(
    output_console: Console | FileConsole,
    location: ObserverLocation,
    dark_sites: list[DarkSkySite],
    max_distance_miles: float,
) -> None:
    """Display dark sky sites information."""
    location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

    output_console.print(f"\n[bold cyan]Dark Sky Sites Near {location_name}[/bold cyan]")
    output_console.print(f"[dim]Searching within {max_distance_miles:.0f} miles[/dim]\n")

    if not dark_sites:
        output_console.print("[yellow]No dark sky sites found within the search radius.[/yellow]")
        output_console.print(
            "[dim]Try increasing --max-distance or check for International Dark Sky Parks in the area.[/dim]\n"
        )
        return

    # Display sites in a table
    table = Table(show_header=True, header_style="bold")
    table.add_column("Site Name", style="bold")
    table.add_column("Distance", justify="right")
    table.add_column("Bortle")
    table.add_column("SQM", justify="right")
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

        # Format distance in miles
        distance_miles = site.distance_km / 1.60934
        distance_str = f"{site.distance_km * 1000:.0f} m" if distance_miles < 1 else f"{distance_miles:.1f} mi"

        table.add_row(site.name, distance_str, bortle_str, f"{site.sqm_value:.2f}", site.description)

    output_console.print(table)

    # Show details
    output_console.print("\n[bold]Site Details:[/bold]")
    for site in dark_sites[:10]:  # Show first 10
        distance_miles = site.distance_km / 1.60934
        output_console.print(f"\n  [bold]{site.name}[/bold]")
        output_console.print(f"    Distance: {distance_miles:.1f} miles ({site.distance_km:.1f} km)")
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
    output_console.print(
        "\n[dim]💡 Tip: Use 'nexstar vacation view' to check viewing conditions at these sites![/dim]\n"
    )


@app.command("plan")
def show_comprehensive_plan(
    location: str = typer.Argument(..., help="Vacation location (city, address, or coordinates)"),
    start_date: str | None = typer.Option(None, "--start-date", "-s", help="Vacation start date (YYYY-MM-DD)"),
    end_date: str | None = typer.Option(None, "--end-date", "-e", help="Vacation end date (YYYY-MM-DD)"),
    days_ahead: int = typer.Option(
        30, "--days", "-d", help="Days ahead to check for events if dates not specified (default: 30)"
    ),
    export: bool = typer.Option(False, "--export", "-E", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """
    Comprehensive astronomy vacation planning for a location.

    Pulls together all relevant astronomy data:
    - Viewing conditions (light pollution, sky quality)
    - Dark sky sites nearby
    - Aurora visibility (if applicable)
    - Upcoming eclipses
    - Meteor showers
    - Visible comets
    - Weather considerations

    Specify either --start-date and --end-date for a specific vacation period,
    or use --days to check events from today forward.
    """
    from datetime import datetime

    try:
        # Geocode location
        vacation_location = asyncio.run(geocode_location(location))
    except Exception as e:
        console.print(f"[red]Error: Could not geocode location '{location}': {e}[/red]")
        raise typer.Exit(1) from e

    # Parse dates if provided
    start_dt = None
    end_dt = None
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError as e:
            console.print("[red]Error: Invalid start date format. Use YYYY-MM-DD (e.g., 2025-06-15)[/red]")
            raise typer.Exit(1) from e

    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError as e:
            console.print("[red]Error: Invalid end date format. Use YYYY-MM-DD (e.g., 2025-06-20)[/red]")
            raise typer.Exit(1) from e

    # Validate date range
    if start_dt and end_dt:
        if start_dt >= end_dt:
            console.print("[red]Error: Start date must be before end date[/red]")
            raise typer.Exit(1)
        # Calculate days from date range
        days_ahead = (end_dt - start_dt).days
    elif start_dt or end_date:
        console.print(
            f"[yellow]Warning: Both --start-date and --end-date should be provided. Using --days={days_ahead} instead.[/yellow]"
        )
        start_dt = None
        end_dt = None

    if export:
        location_name = (
            vacation_location.name or f"{vacation_location.latitude:.1f}N-{vacation_location.longitude:.1f}E"
        )
        # Include date range in filename if provided
        date_suffix = ""
        if start_dt and end_dt:
            date_suffix = f"_{start_dt.strftime('%Y%m%d')}-{end_dt.strftime('%Y%m%d')}"
        export_path_obj = (
            Path(export_path)
            if export_path
            else _generate_export_filename("plan", location_name, days_ahead, date_suffix)
        )
        file_console = create_file_console()
        _show_comprehensive_plan_content(file_console, vacation_location, days_ahead, start_dt, end_dt)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_comprehensive_plan_content(console, vacation_location, days_ahead, start_dt, end_dt)


def _show_comprehensive_plan_content(
    output_console: Console | FileConsole,
    location: ObserverLocation,
    days_ahead: int,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> None:
    """Display comprehensive vacation planning information."""
    from datetime import UTC, datetime, timedelta

    location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

    # Determine the date range to use
    if start_date and end_date:
        # Use provided date range
        start_dt = start_date.replace(tzinfo=UTC) if start_date.tzinfo is None else start_date
        end_dt = end_date.replace(tzinfo=UTC) if end_date.tzinfo is None else end_date
        date_range_str = f"{start_dt.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')}"
        output_console.print(f"\n[bold cyan]Comprehensive Astronomy Plan for {location_name}[/bold cyan]")
        output_console.print(f"[dim]Vacation Period: {date_range_str} ({(end_dt - start_dt).days + 1} days)[/dim]\n")
    else:
        # Use days_ahead from today
        start_dt = datetime.now(UTC)
        end_dt = start_dt + timedelta(days=days_ahead)
        date_range_str = f"next {days_ahead} days"
        output_console.print(f"\n[bold cyan]Comprehensive Astronomy Plan for {location_name}[/bold cyan]")
        output_console.print(f"[dim]Checking events for the {date_range_str}[/dim]\n")

    # 1. Viewing Conditions
    output_console.print("[bold]1. Viewing Conditions[/bold]")
    viewing_info = get_vacation_viewing_info(location)
    _show_viewing_info_content(output_console, location, viewing_info)

    # 2. Dark Sky Sites
    output_console.print("\n[bold]2. Nearby Dark Sky Sites[/bold]")
    dark_sites = find_dark_sites_near(location, max_distance_km=500.0, min_bortle=BortleClass.CLASS_4)
    if dark_sites:
        # Show top 5 closest
        _show_dark_sites_content(output_console, location, dark_sites[:5], 500.0)
    else:
        output_console.print(
            "[dim]No official dark sky sites found nearby. Check light pollution map for dark areas.[/dim]\n"
        )

    # 3. Aurora Visibility (if in northern latitudes)
    if location.latitude >= 50.0 or location.latitude <= -50.0:
        output_console.print("\n[bold]3. Aurora Visibility[/bold]")
        try:
            # Check aurora for the start of the vacation period
            check_time = start_dt if start_date else datetime.now(UTC)
            aurora_forecast = check_aurora_visibility(location, check_time)
            if aurora_forecast is not None:
                if aurora_forecast.is_visible:
                    output_console.print("[green]✓ Aurora may be visible during your vacation![/green]")
                    output_console.print(f"   Kp index: {aurora_forecast.kp_index:.1f}")
                    output_console.print(f"   Visibility: {aurora_forecast.visibility_level}")
                else:
                    output_console.print(
                        f"[yellow]Aurora not currently visible (Kp: {aurora_forecast.kp_index:.1f})[/yellow]"
                    )
                    if location.latitude >= 50.0:
                        output_console.print(
                            f"   [dim]For your latitude ({location.latitude:.1f}°N), you typically need Kp ≥ {aurora_forecast.latitude_required:.1f}[/dim]"
                        )
            output_console.print(
                "\n[dim]💡 Tip: Use 'nexstar aurora when' for detailed aurora forecasts during your dates[/dim]\n"
            )
        except Exception as e:
            output_console.print(f"[dim]Could not check aurora visibility: {e}[/dim]\n")

    # 4. Upcoming Eclipses
    output_console.print("\n[bold]4. Upcoming Eclipses[/bold]")
    try:
        # Calculate years to search based on date range
        if start_date and end_date:
            # Search from start_date to end_date + 1 year buffer
            search_end = end_dt + timedelta(days=365)
            years_ahead = max(1, int((search_end - start_dt).days / 365) + 1)
        else:
            years_ahead = max(1, days_ahead // 365)

        from celestron_nexstar.api.astronomy.eclipses import Eclipse

        async def _get_eclipses() -> tuple[list[Eclipse], list[Eclipse]]:
            async with get_db_session() as db_session:
                lunar = await get_next_lunar_eclipse(db_session, location, years_ahead=years_ahead)
                solar = await get_next_solar_eclipse(db_session, location, years_ahead=years_ahead)
                return lunar, solar

        lunar_eclipses, solar_eclipses = asyncio.run(_get_eclipses())

        # Filter eclipses within date range
        all_eclipses = []
        for eclipse in lunar_eclipses + solar_eclipses:
            if start_date and end_date:
                if start_dt <= eclipse.date <= end_dt:
                    all_eclipses.append(eclipse)
            else:
                # Use days_ahead from now
                if eclipse.date <= datetime.now(UTC) + timedelta(days=days_ahead * 365 // 30):
                    all_eclipses.append(eclipse)

        all_eclipses = sorted(all_eclipses, key=lambda ecl: ecl.date)[:5]  # Show next 5

        if all_eclipses:
            for eclipse in all_eclipses:
                eclipse_type_str = eclipse.eclipse_type
                eclipse_type = "Lunar" if "lunar" in eclipse_type_str.lower() else "Solar"
                output_console.print(f"  • {eclipse_type} Eclipse: {eclipse.date.strftime('%Y-%m-%d')}")
                if eclipse.is_visible:
                    output_console.print("    [green]Visible from this location[/green]")
                else:
                    output_console.print("    [dim]Not visible from this location[/dim]")
        else:
            output_console.print("[dim]No eclipses during your vacation period[/dim]")
        output_console.print("\n[dim]💡 Tip: Use 'nexstar eclipse next' for detailed eclipse information[/dim]\n")
    except Exception as e:
        output_console.print(f"[dim]Could not check eclipses: {e}[/dim]\n")

    # 5. Meteor Showers
    output_console.print("\n[bold]5. Upcoming Meteor Showers[/bold]")
    try:
        if start_date and end_date:
            months_ahead = max(1, int((end_dt - start_dt).days / 30) + 1)
        else:
            months_ahead = max(1, days_ahead // 30)

        meteor_predictions = get_enhanced_meteor_predictions(location, months_ahead=months_ahead)

        # Filter by date range
        if start_date and end_date:
            meteor_predictions = [p for p in meteor_predictions if start_dt <= p.date <= end_dt]

        if meteor_predictions:
            for pred in meteor_predictions[:5]:  # Show next 5
                output_console.print(f"  • {pred.shower.name}: {pred.date.strftime('%Y-%m-%d')}")
                output_console.print(f"    ZHR: {pred.zhr_peak} meteors/hour (adjusted: {pred.zhr_adjusted:.0f})")
                output_console.print(f"    Quality: {pred.viewing_quality}")
        else:
            period_str = date_range_str if start_date and end_date else f"next {days_ahead} days"
            output_console.print(f"[dim]No major meteor showers during {period_str}[/dim]")
        output_console.print("\n[dim]💡 Tip: Use 'nexstar meteors next' for detailed meteor shower forecasts[/dim]\n")
    except Exception as e:
        output_console.print(f"[dim]Could not check meteor showers: {e}[/dim]\n")

    # 6. Visible Comets
    output_console.print("\n[bold]6. Visible Comets[/bold]")
    try:
        if start_date and end_date:
            months_ahead = max(1, int((end_dt - start_dt).days / 30) + 1)
        else:
            months_ahead = max(1, days_ahead // 30)

        from celestron_nexstar.api.astronomy.comets import CometVisibility

        async def _get_comets() -> list[CometVisibility]:
            async with get_db_session() as db_session:
                return await get_visible_comets(db_session, location, months_ahead=months_ahead)

        comets = asyncio.run(_get_comets())

        # Filter comets visible during date range (if we have visibility dates)
        if start_date and end_date and comets:
            # Filter comets that might be visible during the period
            # (This is approximate - comets module would need visibility dates)
            comets = comets[:5]  # Show top 5

        if comets:
            for comet_vis in comets[:5]:  # Show top 5
                comet_name = comet_vis.comet.name
                comet_mag = comet_vis.magnitude
                output_console.print(f"  • {comet_name}")
                output_console.print(f"    Magnitude: {comet_mag:.2f}")
                if comet_vis.notes:
                    output_console.print(f"    [dim]{comet_vis.notes}[/dim]")
        else:
            period_str = date_range_str if start_date and end_date else "currently"
            output_console.print(f"[dim]No bright comets visible {period_str}[/dim]")
        output_console.print("\n[dim]💡 Tip: Use 'nexstar comets visible' for detailed comet information[/dim]\n")
    except Exception as e:
        output_console.print(f"[dim]Could not check comets: {e}[/dim]\n")

    # 7. Weather Forecast
    output_console.print("\n[bold]7. Weather Forecast[/bold]")
    try:
        # Calculate hours needed for the vacation period
        if start_date and end_date:
            hours_needed = int((end_dt - start_dt).total_seconds() / 3600) + 24  # Add buffer
        else:
            hours_needed = days_ahead * 24 + 24

        # Limit to 7 days (168 hours) - API maximum
        hours_needed = min(hours_needed, 168)

        weather_forecast = asyncio.run(fetch_hourly_weather_forecast(location, hours=hours_needed))

        if weather_forecast:
            # Group by day and show summary
            daily_weather = defaultdict(list)

            for forecast in weather_forecast:
                if forecast.timestamp is not None:
                    day_key = forecast.timestamp.date()
                    daily_weather[day_key].append(forecast)

            # Show forecast for each day in vacation period
            current_date = start_dt.date() if start_date else datetime.now(UTC).date()
            end_date_only = end_dt.date() if end_date else (datetime.now(UTC) + timedelta(days=days_ahead)).date()

            table = Table(show_header=True, header_style="bold")
            table.add_column("Date", style="cyan")
            table.add_column("Cloud Cover")
            table.add_column("Seeing")
            table.add_column("Temp", justify="right")
            table.add_column("Conditions", style="dim")

            days_shown = 0
            while current_date <= end_date_only and days_shown < 7:
                day_forecasts = daily_weather.get(current_date, [])
                if day_forecasts:
                    # Get nighttime forecasts (after sunset, before sunrise)
                    nighttime_forecasts = [
                        f
                        for f in day_forecasts
                        if f.timestamp is not None and (f.timestamp.hour >= 20 or f.timestamp.hour < 6)
                    ]
                    if not nighttime_forecasts:
                        nighttime_forecasts = day_forecasts[:3]  # Fallback to first few

                    avg_cloud = (
                        sum(f.cloud_cover_percent or 0 for f in nighttime_forecasts) / len(nighttime_forecasts)
                        if nighttime_forecasts
                        else 0
                    )
                    avg_seeing = (
                        sum(f.seeing_score for f in nighttime_forecasts) / len(nighttime_forecasts)
                        if nighttime_forecasts
                        else 50
                    )
                    avg_temp = (
                        sum(getattr(f, "temperature_f", 0) for f in nighttime_forecasts) / len(nighttime_forecasts)
                        if nighttime_forecasts
                        else 0
                    )

                    # Format cloud cover
                    if avg_cloud < 20:
                        cloud_str = f"[green]{avg_cloud:.0f}%[/green]"
                    elif avg_cloud < 50:
                        cloud_str = f"[yellow]{avg_cloud:.0f}%[/yellow]"
                    else:
                        cloud_str = f"[red]{avg_cloud:.0f}%[/red]"

                    # Format seeing
                    if avg_seeing >= 80:
                        seeing_str = "[green]Excellent[/green]"
                    elif avg_seeing >= 60:
                        seeing_str = "[yellow]Good[/yellow]"
                    elif avg_seeing >= 40:
                        seeing_str = "[yellow]Fair[/yellow]"
                    else:
                        seeing_str = "[red]Poor[/red]"

                    condition = "Clear" if avg_cloud < 30 else "Cloudy" if avg_cloud > 70 else "Partly Cloudy"

                    table.add_row(
                        current_date.strftime("%Y-%m-%d"),
                        cloud_str,
                        seeing_str,
                        f"{avg_temp:.0f}°F" if avg_temp > 0 else "—",
                        condition,
                    )
                    days_shown += 1

                current_date += timedelta(days=1)

            if days_shown > 0:
                output_console.print(table)
            else:
                output_console.print("[dim]Weather forecast not available for this period[/dim]")
        else:
            output_console.print("[dim]Weather forecast not available[/dim]")
        output_console.print("\n[dim]💡 Tip: Weather forecasts are most accurate within 3-5 days[/dim]\n")
    except Exception as e:
        output_console.print(f"[dim]Could not check weather: {e}[/dim]\n")

    # 8. Sun/Moon Calendar
    output_console.print("\n[bold]8. Sun/Moon Calendar[/bold]")
    try:
        current_date = start_dt.date() if start_date else datetime.now(UTC).date()
        end_date_only = end_dt.date() if end_date else (datetime.now(UTC) + timedelta(days=days_ahead)).date()

        table = Table(show_header=True, header_style="bold")
        table.add_column("Date", style="cyan")
        table.add_column("Sunset")
        table.add_column("Sunrise")
        table.add_column("Moon Phase")
        table.add_column("Moon Illum.", justify="right")

        days_shown = 0
        while current_date <= end_date_only and days_shown < 14:  # Show up to 14 days
            date_dt = datetime.combine(current_date, datetime.min.time()).replace(tzinfo=UTC)

            sun_info = get_sun_info(location.latitude, location.longitude, date_dt)
            moon_info = get_moon_info(location.latitude, location.longitude, date_dt)

            if sun_info and sun_info.sunset_time:
                # Convert to local time (simplified - just show UTC for now)
                sunset_str = sun_info.sunset_time.strftime("%H:%M")
                sunrise_str = sun_info.sunrise_time.strftime("%H:%M") if sun_info.sunrise_time else "—"
            else:
                sunset_str = "—"
                sunrise_str = "—"

            if moon_info:
                # Get moon phase name
                moon_phase = str(moon_info.phase_name).replace("MoonPhase.", "").replace("_", " ").title()
                moon_illum = f"{moon_info.illumination * 100:.0f}%"
            else:
                moon_phase = "—"
                moon_illum = "—"

            table.add_row(current_date.strftime("%Y-%m-%d"), sunset_str, sunrise_str, moon_phase, moon_illum)
            days_shown += 1
            current_date += timedelta(days=1)

        output_console.print(table)
        output_console.print("\n[dim]💡 Tip: New moon and crescent phases are best for deep-sky observing[/dim]\n")
    except Exception as e:
        output_console.print(f"[dim]Could not calculate sun/moon calendar: {e}[/dim]\n")

    # 9. ISS Passes
    output_console.print("\n[bold]9. ISS Passes[/bold]")
    try:
        vacation_days = (end_dt - start_dt).days + 1 if start_date and end_date else days_ahead

        iss_passes = asyncio.run(
            get_iss_passes(
                location.latitude,
                location.longitude,
                start_time=start_dt if start_date else datetime.now(UTC),
                days=min(vacation_days, 14),  # Limit to 14 days
                min_altitude_deg=10.0,
            )
        )

        # Filter visible passes and show top 5
        visible_passes = [p for p in iss_passes if p.is_visible][:5]

        if visible_passes:
            for pass_obj in visible_passes:
                pass_date = pass_obj.rise_time.date() if pass_obj.rise_time else None
                rise_time = pass_obj.rise_time.strftime("%H:%M") if pass_obj.rise_time else "—"
                max_alt = f"{pass_obj.max_altitude_deg:.0f}°" if pass_obj.max_altitude_deg else "—"
                duration = f"{pass_obj.duration_seconds // 60} min" if pass_obj.duration_seconds else "—"

                output_console.print(
                    f"  • {pass_date}: Rise at {rise_time}, Max altitude {max_alt}, Duration {duration}"
                )
        else:
            period_str = date_range_str if start_date and end_date else f"next {days_ahead} days"
            output_console.print(f"[dim]No visible ISS passes during {period_str}[/dim]")
        output_console.print("\n[dim]💡 Tip: Use 'nexstar iss passes' for detailed ISS pass information[/dim]\n")
    except Exception as e:
        output_console.print(f"[dim]Could not check ISS passes: {e}[/dim]\n")

    # 10. Planetary Events
    output_console.print("\n[bold]10. Planetary Events[/bold]")
    try:
        if start_date and end_date:
            months_ahead = max(1, int((end_dt - start_dt).days / 30) + 1)
            years_ahead = max(1, int((end_dt - start_dt).days / 365) + 1)
        else:
            months_ahead = max(1, days_ahead // 30)
            years_ahead = max(1, days_ahead // 365)

        conjunctions = get_planetary_conjunctions(location, months_ahead=months_ahead)
        oppositions = get_planetary_oppositions(location, years_ahead=years_ahead)

        # Filter by date range
        all_planetary_events = []
        for event in conjunctions + oppositions:
            if start_date and end_date:
                if start_dt <= event.date <= end_dt:
                    all_planetary_events.append(event)
            else:
                if event.date <= datetime.now(UTC) + timedelta(days=days_ahead * 30):
                    all_planetary_events.append(event)

        all_planetary_events = sorted(all_planetary_events, key=lambda e: e.date)[:5]

        if all_planetary_events:
            for event in all_planetary_events:
                if event.event_type == "conjunction" and event.planet2:
                    output_console.print(
                        f"  • {event.planet1.title()} - {event.planet2.title()} Conjunction: {event.date.strftime('%Y-%m-%d')}"
                    )
                    output_console.print(f"    Separation: {event.separation_degrees:.2f}°")
                elif event.event_type == "opposition":
                    output_console.print(
                        f"  • {event.planet1.title()} at Opposition: {event.date.strftime('%Y-%m-%d')}"
                    )
                    output_console.print("    Best viewing time for this planet")
                if event.is_visible:
                    output_console.print("    [green]Visible from this location[/green]")
        else:
            period_str = date_range_str if start_date and end_date else f"next {days_ahead} days"
            output_console.print(f"[dim]No major planetary events during {period_str}[/dim]")
        output_console.print(
            "\n[dim]💡 Tip: Use 'nexstar planets conjunctions' and 'nexstar planets oppositions' for detailed information[/dim]\n"
        )
    except Exception as e:
        output_console.print(f"[dim]Could not check planetary events: {e}[/dim]\n")

    # 11. Space Events Calendar
    output_console.print("\n[bold]11. Space Events Calendar[/bold]")
    try:
        space_events = get_upcoming_events(start_date=start_dt, end_date=end_dt)

        if space_events:
            for space_event in space_events[:5]:  # Show top 5
                output_console.print(f"  • {space_event.name}: {space_event.date.strftime('%Y-%m-%d')}")
                output_console.print(f"    Type: {space_event.event_type.value}")
                if space_event.description:
                    desc = (
                        space_event.description[:80] + "..."
                        if len(space_event.description) > 80
                        else space_event.description
                    )
                    output_console.print(f"    [dim]{desc}[/dim]")
        else:
            period_str = date_range_str if start_date and end_date else f"next {days_ahead} days"
            output_console.print(f"[dim]No space events during {period_str}[/dim]")
        output_console.print(
            "\n[dim]💡 Tip: Use 'nexstar events upcoming' for detailed space event information[/dim]\n"
        )
    except Exception as e:
        output_console.print(f"[dim]Could not check space events: {e}[/dim]\n")

    # 12. Best Observing Nights
    output_console.print("\n[bold]12. Best Observing Nights[/bold]")
    try:
        # Get space events and planetary events for scoring (reuse from previous sections)
        try:
            space_events_for_scoring = get_upcoming_events(start_date=start_dt, end_date=end_dt)
        except Exception:
            space_events_for_scoring = []

        try:
            if start_date and end_date:
                months_ahead = max(1, int((end_dt - start_dt).days / 30) + 1)
                years_ahead = max(1, int((end_dt - start_dt).days / 365) + 1)
            else:
                months_ahead = max(1, days_ahead // 30)
                years_ahead = max(1, days_ahead // 365)

            conjunctions = get_planetary_conjunctions(location, months_ahead=months_ahead)
            oppositions = get_planetary_oppositions(location, years_ahead=years_ahead)
            all_planetary_events_for_scoring = []
            for event in conjunctions + oppositions:
                if start_date and end_date:
                    if start_dt <= event.date <= end_dt:
                        all_planetary_events_for_scoring.append(event)
                else:
                    if event.date <= datetime.now(UTC) + timedelta(days=days_ahead * 30):
                        all_planetary_events_for_scoring.append(event)
        except Exception:
            all_planetary_events_for_scoring = []

        # Analyze each night and score them
        current_date = start_dt.date() if start_date else datetime.now(UTC).date()
        end_date_only = end_dt.date() if end_date else (datetime.now(UTC) + timedelta(days=days_ahead)).date()

        night_scores = []
        days_analyzed = 0

        # Get weather forecast once for all days
        weather_forecast_all = asyncio.run(fetch_hourly_weather_forecast(location, hours=168))  # 7 days max
        daily_weather_all = defaultdict(list)
        for forecast in weather_forecast_all:
            if forecast.timestamp:
                daily_weather_all[forecast.timestamp.date()].append(forecast)

        while current_date <= end_date_only and days_analyzed < 14:
            date_dt = datetime.combine(current_date, datetime.min.time()).replace(tzinfo=UTC)

            # Get moon info
            moon_info = get_moon_info(location.latitude, location.longitude, date_dt)

            # Calculate score
            score = 0.0
            factors = []

            # Moon phase (0-40 points): New moon = 40, Full moon = 0
            if moon_info:
                moon_score = 40 * (1.0 - moon_info.illumination)
                score += moon_score
                factors.append(f"Moon: {moon_info.illumination * 100:.0f}%")
            else:
                factors.append("Moon: Unknown")

            # Weather (0-40 points): Clear = 40, Cloudy = 0
            if daily_weather_all.get(current_date):
                nighttime_forecasts = [
                    f
                    for f in daily_weather_all[current_date]
                    if f.timestamp is not None and (f.timestamp.hour >= 20 or f.timestamp.hour < 6)
                ]
                if nighttime_forecasts:
                    avg_cloud = sum(f.cloud_cover_percent or 0 for f in nighttime_forecasts) / len(nighttime_forecasts)
                    weather_score = 40 * (1.0 - avg_cloud / 100.0)
                    score += weather_score
                    factors.append(f"Weather: {avg_cloud:.0f}% clouds")
                else:
                    factors.append("Weather: Unknown")
            else:
                factors.append("Weather: Unknown")

            # Events bonus (0-20 points): Major events add points
            event_bonus = 0
            for space_event in space_events_for_scoring:
                if space_event.date.date() == current_date:
                    event_bonus += 5
            for planetary_event in all_planetary_events_for_scoring:
                if planetary_event.date.date() == current_date:
                    event_bonus += 3
            score += min(event_bonus, 20)
            if event_bonus > 0:
                factors.append(f"Events: +{event_bonus}")

            night_scores.append((current_date, score, factors))
            days_analyzed += 1
            current_date += timedelta(days=1)

        # Sort by score and show top 3
        night_scores.sort(key=lambda x: x[1], reverse=True)

        if night_scores:
            table = Table(show_header=True, header_style="bold")
            table.add_column("Date", style="cyan")
            table.add_column("Score", justify="right")
            table.add_column("Factors", style="dim")

            for date, score, factors in night_scores[:5]:  # Top 5
                if score >= 70:
                    score_str = f"[green]{score:.0f}/100[/green]"
                elif score >= 50:
                    score_str = f"[yellow]{score:.0f}/100[/yellow]"
                else:
                    score_str = f"[red]{score:.0f}/100[/red]"

                table.add_row(date.strftime("%Y-%m-%d"), score_str, ", ".join(factors))

            output_console.print(table)
        else:
            output_console.print("[dim]Could not analyze observing nights[/dim]")
        output_console.print("\n[dim]💡 Tip: Scores consider moon phase, weather, and special events[/dim]\n")
    except Exception as e:
        output_console.print(f"[dim]Could not analyze best nights: {e}[/dim]\n")

    # 13. Summary and Recommendations
    output_console.print("\n[bold]Summary & Recommendations[/bold]")
    output_console.print(
        f"  • Sky Quality: Bortle Class {viewing_info.bortle_class.value} (SQM: {viewing_info.sqm_value:.2f})"
    )
    if viewing_info.bortle_class <= BortleClass.CLASS_3:
        output_console.print("  • [green]Excellent dark sky location![/green]")
    elif viewing_info.bortle_class <= BortleClass.CLASS_5:
        output_console.print("  • [yellow]Moderate light pollution - consider nearby dark sites[/yellow]")
    else:
        output_console.print("  • [red]High light pollution - strongly recommend dark sky site[/red]")

    if dark_sites:
        closest = dark_sites[0]
        distance_miles = closest.distance_km / 1.60934
        output_console.print(f"  • Closest dark site: {closest.name} ({distance_miles:.1f} miles away)")

    output_console.print(
        "\n[dim]💡 Tip: Use 'nexstar telescope tonight' with this location for detailed viewing plans[/dim]\n"
    )


if __name__ == "__main__":
    app()

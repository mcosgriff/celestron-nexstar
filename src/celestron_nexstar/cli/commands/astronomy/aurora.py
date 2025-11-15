"""
Aurora Borealis (Northern Lights) Visibility Commands

Check if the aurora borealis is visible from your location based on
geomagnetic activity, weather conditions, and moon phase.
"""

from datetime import datetime
from pathlib import Path

import typer
from click import Context
from rich.console import Console
from rich.table import Table
from typer.core import TyperGroup

from celestron_nexstar.api.events.aurora import (
    AuroraForecast,
    AuroraProbability,
    check_aurora_visibility,
    get_aurora_visibility_windows,
    get_next_aurora_opportunity,
    get_solar_cycle_info,
)
from celestron_nexstar.api.location.observer import ObserverLocation, get_observer_location
from celestron_nexstar.cli.utils.export import FileConsole, create_file_console, export_to_text


class SortedCommandsGroup(TyperGroup):
    """Custom Typer group that sorts commands alphabetically within each help panel."""

    def list_commands(self, ctx: Context) -> list[str]:
        """Return commands sorted alphabetically."""
        commands = super().list_commands(ctx)
        return sorted(commands)


app = typer.Typer(help="Aurora borealis visibility commands", cls=SortedCommandsGroup)
console = Console()


def _generate_export_filename(command: str = "aurora") -> Path:
    """Generate export filename for aurora commands."""
    from celestron_nexstar.api.location.observer import get_observer_location

    location = get_observer_location()

    # Get location name (shortened, sanitized)
    if location.name:
        location_short = location.name.lower().replace(" ", "_").replace(",", "").replace(".", "")
        # Remove common suffixes and limit length
        location_short = location_short.replace("_(default)", "").replace("_observatory", "")
        location_short = location_short[:20]  # Limit length
    else:
        location_short = "unknown"

    # Get date
    date_str = datetime.now().strftime("%Y-%m-%d")

    filename = f"nexstar_aurora_{location_short}_{date_str}_{command}.txt"
    return Path(filename)


def _format_visibility_level(level: str) -> str:
    """Format visibility level with color."""
    colors = {
        "very_high": "[bold bright_green]Very High[/bold bright_green]",
        "high": "[bold green]High[/bold green]",
        "moderate": "[bold yellow]Moderate[/bold yellow]",
        "low": "[yellow]Low[/yellow]",
        "none": "[dim]None[/dim]",
    }
    return colors.get(level, level)


def _format_kp_index(kp: float) -> str:
    """Format Kp index with color based on activity level."""
    if kp >= 8.0:
        return f"[bold bright_red]{kp:.1f}[/bold bright_red] (Extreme)"
    elif kp >= 7.0:
        return f"[bold red]{kp:.1f}[/bold red] (Very High)"
    elif kp >= 6.0:
        return f"[bold yellow]{kp:.1f}[/bold yellow] (High)"
    elif kp >= 5.0:
        return f"[yellow]{kp:.1f}[/yellow] (Moderate)"
    elif kp >= 4.0:
        return f"[cyan]{kp:.1f}[/cyan] (Low-Moderate)"
    elif kp >= 3.0:
        return f"[dim]{kp:.1f}[/dim] (Low)"
    else:
        return f"[dim]{kp:.1f}[/dim] (Very Low)"


@app.command("tonight")
def show_tonight(
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Check if aurora borealis is visible tonight from your location."""
    location = get_observer_location()
    if not location:
        console.print(
            "[red]Error: No observer location set. Use 'nexstar location set' to configure your location.[/red]"
        )
        raise typer.Exit(1)

    # Check aurora visibility
    forecast = check_aurora_visibility(location)

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("tonight")
        file_console = create_file_console()
        _show_aurora_content(file_console, location, forecast)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_aurora_content(console, location, forecast)


def _show_aurora_content(
    output_console: Console | FileConsole, location: ObserverLocation, forecast: AuroraForecast | None
) -> None:
    """Display aurora visibility information."""

    location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

    output_console.print(f"\n[bold cyan]Aurora Borealis Visibility for {location_name}[/bold cyan]")
    output_console.print("[dim]Northern Lights visibility based on geomagnetic activity (Kp index)[/dim]\n")

    if forecast is None:
        output_console.print("[yellow]⚠ Unable to fetch geomagnetic activity data (Kp index)[/yellow]")
        output_console.print("[dim]This may be due to network issues or API unavailability.[/dim]")
        output_console.print("[dim]Try again in a few minutes.[/dim]\n")
        return

    # Main status
    if forecast.is_visible:
        output_console.print("[bold bright_green]✓ Aurora Borealis is VISIBLE tonight![/bold bright_green]\n")
    else:
        output_console.print("[dim]○ Aurora Borealis is not visible tonight[/dim]\n")

    # Detailed information table
    table = Table(show_header=True, header_style="bold")
    table.add_column("Parameter", style="cyan")
    table.add_column("Value", style="white")

    # Kp Index
    table.add_row("Geomagnetic Activity (Kp)", _format_kp_index(forecast.kp_index))

    # Add G-scale from space weather if available
    try:
        from celestron_nexstar.api.events.space_weather import get_space_weather_conditions

        swx = get_space_weather_conditions()
        if swx.g_scale:
            g_scale_display = f"G{swx.g_scale.level} ({swx.g_scale.display_name})"
            if swx.g_scale.level >= 3:
                g_scale_display = f"[bold red]{g_scale_display}[/bold red]"
            elif swx.g_scale.level >= 1:
                g_scale_display = f"[yellow]{g_scale_display}[/yellow]"
            else:
                g_scale_display = f"[green]{g_scale_display}[/green]"
            table.add_row("NOAA G-Scale", g_scale_display)

        # Add solar wind Bz if available (important for aurora)
        if swx.solar_wind_bz is not None:
            bz_display = f"{swx.solar_wind_bz:.1f} nT"
            if swx.solar_wind_bz < -5:
                bz_display = f"[green]{bz_display} (favorable for aurora)[/green]"
            elif swx.solar_wind_bz < 0:
                bz_display = f"[yellow]{bz_display}[/yellow]"
            else:
                bz_display = f"[white]{bz_display}[/white]"
            table.add_row("Solar Wind Bz", bz_display)
    except Exception:
        # Space weather data unavailable, skip
        pass

    # Visibility Probability (AgentCalc algorithm)
    prob_pct = forecast.visibility_probability * 100.0
    if prob_pct >= 70:
        prob_color = "[bold bright_green]"
        prob_desc = " (Strong odds)"
    elif prob_pct >= 30:
        prob_color = "[yellow]"
        prob_desc = " (Possible)"
    else:
        prob_color = "[red]"
        prob_desc = " (Low odds)"
    table.add_row("Visibility Probability", f"{prob_color}{prob_pct:.1f}%{prob_desc}[/{prob_color.strip('[]')}]")

    # Visibility Level
    table.add_row("Visibility Level", _format_visibility_level(forecast.visibility_level))

    # Location requirements (auroral boundary)
    lat_diff = abs(location.latitude) - forecast.latitude_required
    if lat_diff < 0:
        table.add_row(
            "Auroral Boundary",
            f"[yellow]Your latitude ({abs(location.latitude):.1f}°) is {abs(lat_diff):.1f}° below the boundary ({forecast.latitude_required:.1f}°)[/yellow]",
        )
    else:
        table.add_row(
            "Auroral Boundary",
            f"[green]Your latitude ({abs(location.latitude):.1f}°) is {lat_diff:.1f}° above the boundary ({forecast.latitude_required:.1f}°)[/green]",
        )

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
        table.add_row("Darkness", "[yellow]✗ Too bright (need darkness for aurora viewing)[/yellow]")

    # Cloud cover
    if forecast.cloud_cover_percent is not None:
        if forecast.cloud_cover_percent < 20:
            table.add_row("Cloud Cover", f"[green]{forecast.cloud_cover_percent:.0f}% (Clear skies)[/green]")
        elif forecast.cloud_cover_percent < 50:
            table.add_row("Cloud Cover", f"[yellow]{forecast.cloud_cover_percent:.0f}% (Partly cloudy)[/yellow]")
        else:
            table.add_row("Cloud Cover", f"[red]{forecast.cloud_cover_percent:.0f}% (Cloudy - blocks aurora)[/red]")
    else:
        table.add_row("Cloud Cover", "[dim]Unknown[/dim]")

    # Moon phase
    if forecast.moon_illumination is not None:
        moon_pct = forecast.moon_illumination * 100
        if moon_pct < 30:
            table.add_row("Moon Phase", f"[green]{moon_pct:.0f}% illuminated (Dark moon - ideal)[/green]")
        elif moon_pct < 70:
            table.add_row("Moon Phase", f"[yellow]{moon_pct:.0f}% illuminated (Moderate brightness)[/yellow]")
        else:
            table.add_row("Moon Phase", f"[red]{moon_pct:.0f}% illuminated (Bright moon - may wash out aurora)[/red]")
    else:
        table.add_row("Moon Phase", "[dim]Unknown[/dim]")

    # Peak viewing window
    if forecast.peak_viewing_start and forecast.peak_viewing_end:
        start_str = forecast.peak_viewing_start.strftime("%I:%M %p")
        end_str = forecast.peak_viewing_end.strftime("%I:%M %p")
        table.add_row("Peak Viewing Window", f"[green]{start_str} - {end_str}[/green]")

    # Forecast confidence
    if forecast.is_forecasted:
        table.add_row("Data Source", "[yellow]Forecasted (predicted)[/yellow]")
    else:
        table.add_row("Data Source", "[green]Observed (current)[/green]")

    output_console.print(table)

    # Viewing tips
    output_console.print("\n[bold]Viewing Tips:[/bold]")
    if forecast.is_visible:
        output_console.print("  • [green]Look toward the northern horizon[/green]")
        output_console.print("  • [green]Aurora is best viewed with naked eye or binoculars[/green]")
        output_console.print("  • [green]Allow 15-20 minutes for dark adaptation[/green]")
        output_console.print("  • [green]Aurora can appear as green, red, purple, or white curtains/bands[/green]")
        if forecast.cloud_cover_percent and forecast.cloud_cover_percent > 50:
            output_console.print(
                "  • [yellow]⚠ Heavy cloud cover may block the aurora - check weather forecast[/yellow]"
            )
        if forecast.moon_illumination and forecast.moon_illumination > 0.7:
            output_console.print("  • [yellow]⚠ Bright moon may reduce visibility of faint aurora[/yellow]")
    else:
        if forecast.latitude_required > abs(location.latitude):
            output_console.print(f"  • [dim]Your location ({abs(location.latitude):.1f}°N) is too far south[/dim]")
            # Calculate what Kp would be needed for this latitude
            needed_kp = None
            if abs(location.latitude) < 40.0:
                needed_kp = 9.0
            elif abs(location.latitude) < 45.0:
                needed_kp = 8.0
            elif abs(location.latitude) < 50.0:
                needed_kp = 7.0
            elif abs(location.latitude) < 55.0:
                needed_kp = 6.0
            elif abs(location.latitude) < 60.0:
                needed_kp = 5.0
            elif abs(location.latitude) < 65.0:
                needed_kp = 4.0
            elif abs(location.latitude) < 70.0:
                needed_kp = 3.0
            else:
                needed_kp = 2.0

            if needed_kp:
                output_console.print(f"  • [dim]To see aurora at your latitude, you need Kp ≥ {needed_kp:.0f}[/dim]")
            output_console.print(
                f"  • [dim]Current Kp index ({forecast.kp_index:.1f}) requires latitude ≥ {forecast.latitude_required:.1f}°[/dim]"
            )
        if not forecast.is_dark:
            output_console.print("  • [dim]Wait until after sunset for darkness[/dim]")
        if forecast.cloud_cover_percent and forecast.cloud_cover_percent > 50:
            output_console.print("  • [dim]Heavy cloud cover is blocking visibility[/dim]")

    output_console.print(
        "\n[dim]💡 Tip: Aurora activity can change quickly. Check again in 30-60 minutes for updates.[/dim]"
    )
    output_console.print("[dim]💡 Tip: Even if not visible now, geomagnetic storms can develop rapidly.[/dim]")
    output_console.print(
        "[dim]💡 Tip: Use 'nexstar space-weather status' for detailed space weather conditions.[/dim]\n"
    )


@app.command("when")
def show_when(
    days: int = typer.Option(3, "--days", "-d", help="Number of days to check (max: 3)"),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Find when aurora borealis will be visible from your location in the next few days."""
    location = get_observer_location()
    if not location:
        console.print(
            "[red]Error: No observer location set. Use 'nexstar location set' to configure your location.[/red]"
        )
        raise typer.Exit(1)

    # Limit days to 3 (NOAA forecast limit)
    days = min(days, 3)

    # Get visibility windows
    windows = get_aurora_visibility_windows(location, days=days)

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("when")
        file_console = create_file_console()
        _show_when_content(file_console, location, windows, days)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_when_content(console, location, windows, days)


def _show_when_content(
    output_console: Console | FileConsole,
    location: ObserverLocation,
    windows: list[tuple[datetime, datetime, float, str]],
    days: int,
) -> None:
    """Display aurora visibility windows."""
    from zoneinfo import ZoneInfo

    from timezonefinder import TimezoneFinder

    _tz_finder = TimezoneFinder()

    location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

    output_console.print(f"\n[bold cyan]Aurora Borealis Visibility Windows for {location_name}[/bold cyan]")
    output_console.print(f"[dim]Forecast for the next {days} days based on geomagnetic activity (Kp index)[/dim]\n")

    if not windows:
        output_console.print("[yellow]No aurora visibility windows found in the forecast period.[/yellow]")
        output_console.print(
            "[dim]Aurora activity may be too low for your latitude, or no geomagnetic storms are predicted.[/dim]\n"
        )

        # Show what Kp would be needed
        needed_kp = None
        if abs(location.latitude) < 40.0:
            needed_kp = 9.0
        elif abs(location.latitude) < 45.0:
            needed_kp = 8.0
        elif abs(location.latitude) < 50.0:
            needed_kp = 7.0
        elif abs(location.latitude) < 55.0:
            needed_kp = 6.0
        elif abs(location.latitude) < 60.0:
            needed_kp = 5.0
        elif abs(location.latitude) < 65.0:
            needed_kp = 4.0
        elif abs(location.latitude) < 70.0:
            needed_kp = 3.0

        if needed_kp:
            output_console.print(
                f"[dim]To see aurora at your latitude ({abs(location.latitude):.1f}°N), you need Kp ≥ {needed_kp:.0f}[/dim]"
            )
        output_console.print()
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
    table.add_column("Max Kp", justify="right")
    table.add_column("Visibility")

    for start_time, end_time, max_kp, visibility_level in windows:
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

        # Format Kp with color
        kp_str = _format_kp_index(max_kp)

        # Format visibility level
        vis_str = _format_visibility_level(visibility_level)

        table.add_row(start_str, end_str, duration_str, kp_str, vis_str)

    output_console.print(table)

    output_console.print("\n[bold]Viewing Tips:[/bold]")
    output_console.print("  • [green]Look toward the northern horizon during these windows[/green]")
    output_console.print("  • [green]Aurora is best viewed with naked eye or binoculars[/green]")
    output_console.print("  • [green]Allow 15-20 minutes for dark adaptation[/green]")
    output_console.print("  • [green]Check weather forecast for cloud cover during these times[/green]")
    output_console.print(
        "  • [yellow]⚠ Forecasts are predictions and may change - check 'nexstar aurora tonight' for current conditions[/yellow]"
    )
    output_console.print(
        "\n[dim]💡 Tip: Aurora activity can change quickly. Check again in a few hours for updated forecasts.[/dim]\n"
    )


@app.command("next")
def show_next(
    months: int = typer.Option(24, "--months", "-m", help="Number of months ahead to search (default: 24)"),
    min_probability: float = typer.Option(
        0.10, "--min-prob", help="Minimum probability threshold (0.0-1.0, default: 0.10)"
    ),
    limit: int = typer.Option(10, "--limit", "-l", help="Maximum number of opportunities to show (default: 10)"),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Find the next likely aurora viewing opportunities using probabilistic models."""
    location = get_observer_location()
    if not location:
        console.print(
            "[red]Error: No observer location set. Use 'nexstar location set' to configure your location.[/red]"
        )
        raise typer.Exit(1)

    # Get opportunities
    opportunities = get_next_aurora_opportunity(location, months_ahead=months, min_probability=min_probability)

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("next")
        file_console = create_file_console()
        _show_next_content(file_console, location, opportunities, limit, months)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_next_content(console, location, opportunities, limit, months)


def _show_next_content(
    output_console: Console | FileConsole,
    location: ObserverLocation,
    opportunities: list[AuroraProbability],
    limit: int,
    months: int,
) -> None:
    """Display next aurora opportunities with probabilities."""

    location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"
    min_lat = abs(location.latitude)

    # Determine what Kp is needed
    needed_kp = None
    if min_lat < 40.0:
        needed_kp = 9.0
    elif min_lat < 45.0:
        needed_kp = 8.0
    elif min_lat < 50.0:
        needed_kp = 7.0
    elif min_lat < 55.0:
        needed_kp = 6.0
    elif min_lat < 60.0:
        needed_kp = 5.0
    elif min_lat < 65.0:
        needed_kp = 4.0
    elif min_lat < 70.0:
        needed_kp = 3.0
    else:
        needed_kp = 2.0

    # Get solar cycle info
    cycle_info = get_solar_cycle_info()

    output_console.print(f"\n[bold cyan]Next Aurora Viewing Opportunities for {location_name}[/bold cyan]")
    output_console.print("[dim]Probabilistic forecast based on solar cycle and historical patterns[/dim]")
    output_console.print(f"[dim]Searching next {months} months, showing top {limit} opportunities[/dim]\n")

    # Display solar cycle context
    output_console.print("[bold]Solar Cycle Context:[/bold]")
    output_console.print(f"  Cycle: [cyan]{cycle_info.cycle_number}[/cyan] ({cycle_info.activity_level})")
    output_console.print(f"  Phase: [cyan]{cycle_info.current_phase:.1%}[/cyan] complete")
    if cycle_info.years_since_peak > 0:
        output_console.print(f"  Status: [yellow]{cycle_info.years_since_peak:.1f} years past peak[/yellow]")
    else:
        output_console.print(f"  Status: [green]{abs(cycle_info.years_since_peak):.1f} years until peak[/green]")
    output_console.print(f"  Activity Level: [cyan]{cycle_info.activity_multiplier:.1%}[/cyan] of maximum\n")

    if not opportunities:
        output_console.print("[yellow]No aurora opportunities found above the probability threshold.[/yellow]")
        output_console.print(
            f"[dim]Your location ({min_lat:.1f}°N) requires Kp ≥ {needed_kp:.0f} for aurora visibility.[/dim]"
        )
        output_console.print("[dim]Try lowering --min-prob or increasing --months to see more opportunities.[/dim]\n")
        return

    # Display opportunities table
    table = Table(show_header=True, header_style="bold")
    table.add_column("Month", style="cyan")
    table.add_column("Season")
    table.add_column("Probability", justify="right")
    table.add_column("Expected Max Kp", justify="right")
    table.add_column("Confidence")
    table.add_column("Notes", style="dim")

    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    for opp in opportunities[:limit]:
        month_str = f"{month_names[opp.month - 1]} {opp.start_date.year}"

        # Get the appropriate probability based on needed Kp
        if needed_kp >= 8.0:
            prob = opp.probability_kp_8
            prob_str = f"{prob:.1%}"
        elif needed_kp >= 7.0:
            prob = opp.probability_kp_7
            prob_str = f"{prob:.1%}"
        elif needed_kp >= 6.0:
            prob = opp.probability_kp_6
            prob_str = f"{prob:.1%}"
        elif needed_kp >= 5.0:
            prob = opp.probability_kp_5
            prob_str = f"{prob:.1%}"
        else:
            prob = 0.50
            prob_str = "~50%"

        # Color code probability
        if prob >= 0.30:
            prob_display = f"[bold green]{prob_str}[/bold green]"
        elif prob >= 0.15:
            prob_display = f"[green]{prob_str}[/green]"
        elif prob >= 0.08:
            prob_display = f"[yellow]{prob_str}[/yellow]"
        else:
            prob_display = f"[dim]{prob_str}[/dim]"

        # Format expected max Kp
        kp_str = _format_kp_index(opp.expected_max_kp)

        # Format confidence
        conf_colors = {
            "high": "[green]High[/green]",
            "medium": "[yellow]Medium[/yellow]",
            "low": "[dim]Low[/dim]",
        }
        conf_display = conf_colors.get(opp.confidence, opp.confidence)

        # Truncate notes if too long
        notes_display = opp.notes[:60] + "..." if len(opp.notes) > 60 else opp.notes

        table.add_row(month_str, opp.season, prob_display, kp_str, conf_display, notes_display)

    output_console.print(table)

    output_console.print("\n[bold]Understanding the Probabilities:[/bold]")
    output_console.print(f"  • [dim]Probability shows chance of Kp ≥ {needed_kp:.0f} during that month[/dim]")
    output_console.print("  • [dim]Based on solar cycle phase, seasonal patterns, and historical data[/dim]")
    output_console.print("  • [dim]Equinox months (March, September, October) typically have higher activity[/dim]")
    output_console.print("  • [dim]These are statistical predictions - actual activity may vary[/dim]")

    output_console.print("\n[bold]Planning Tips:[/bold]")
    output_console.print("  • [green]Book travel during high-probability months for best chances[/green]")
    output_console.print("  • [green]Monitor 'nexstar aurora when' as dates approach for specific forecasts[/green]")
    output_console.print("  • [green]Check 'nexstar aurora tonight' during your visit for real-time conditions[/green]")
    output_console.print(
        "  • [yellow]⚠ Even high-probability months don't guarantee aurora - weather and timing matter[/yellow]"
    )
    output_console.print(
        "\n[dim]💡 Tip: Use --min-prob to filter results (e.g., --min-prob 0.20 for 20%+ probability)[/dim]\n"
    )


if __name__ == "__main__":
    app()

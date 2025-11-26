"""
'What's Visible Tonight?' command

Shows observing conditions and recommended objects for tonight.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import typer
from click import Context
from rich.console import Console
from rich.table import Table
from typer.core import TyperGroup

from celestron_nexstar.api.catalogs.catalogs import CelestialObject, get_object_by_name
from celestron_nexstar.api.core import format_local_time, generate_export_filename
from celestron_nexstar.api.database.database import get_database
from celestron_nexstar.api.location.observer import ObserverLocation, get_observer_location
from celestron_nexstar.api.observation.observation_planner import ObservationPlanner, ObservingTarget
from celestron_nexstar.api.observation.planning_utils import (
    DifficultyLevel,
    compare_equipment,
    generate_observation_checklist,
    generate_quick_reference,
    generate_session_log_template,
    get_moon_phase_impact,
    get_object_difficulty,
    get_object_visibility_timeline,
    get_time_based_recommendations,
    get_transit_times,
)
from celestron_nexstar.api.observation.visibility import get_object_altitude_azimuth
from celestron_nexstar.cli.utils.export import FileConsole
from celestron_nexstar.cli.utils.selection import select_from_list


class SortedCommandsGroup(TyperGroup):
    """Custom Typer group that sorts commands alphabetically within each help panel."""

    def list_commands(self, ctx: Context) -> list[str]:
        """Return commands sorted alphabetically."""
        commands = super().list_commands(ctx)
        return sorted(commands)


app = typer.Typer(help="Telescope viewing commands", cls=SortedCommandsGroup)
console = Console()


@app.command("conditions", rich_help_panel="Conditions & Forecasts")
def show_conditions(
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Show tonight's observing conditions."""
    from celestron_nexstar.cli.utils.export import create_file_console, export_to_text

    if export:
        if export_path:
            export_path_obj = Path(export_path)
        else:
            export_path_obj = generate_export_filename("conditions", viewing_type="telescope")

        file_console = create_file_console()
        _show_conditions_content(file_console)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_conditions_content(console)


def _show_conditions_content(output_console: Console | FileConsole) -> None:
    """Generate and display conditions content."""
    try:
        planner = ObservationPlanner()
        conditions = planner.get_tonight_conditions()

        # Display header
        location_name = conditions.location_name or "Current Location"
        output_console.print(f"\n[bold cyan]Observing Conditions for {location_name}[/bold cyan]")
        time_str = format_local_time(conditions.timestamp, conditions.latitude, conditions.longitude)
        output_console.print(f"[dim]{time_str}[/dim]\n")

        # Overall quality
        quality = conditions.observing_quality_score
        if quality > 0.75:
            quality_text = "[green]Excellent[/green]"
        elif quality > 0.60:
            quality_text = "[yellow]Good[/yellow]"
        elif quality > 0.40:
            quality_text = "[yellow]Fair[/yellow]"
        else:
            quality_text = "[red]Poor[/red]"

        output_console.print(f"Overall Quality (general conditions): {quality_text} ({quality * 100:.0f}/100)\n")

        # Weather
        weather = conditions.weather
        output_console.print("[bold]Weather:[/bold]")
        if weather.cloud_cover_percent is not None:
            output_console.print(f"  Cloud Cover: {weather.cloud_cover_percent:.0f}%")
        if weather.temperature_c is not None:
            # API returns Fahrenheit when units=imperial (despite field name)
            # Display directly as Fahrenheit
            output_console.print(f"  Temperature: {weather.temperature_c:.1f}°F")
        if weather.dew_point_f is not None:
            output_console.print(f"  Dew Point: {weather.dew_point_f:.1f}°F")
        if weather.humidity_percent is not None:
            output_console.print(f"  Humidity: {weather.humidity_percent:.0f}%")
        if weather.wind_speed_ms is not None:
            # API returns mph when units=imperial (despite field name)
            # Display directly as mph
            output_console.print(f"  Wind Speed: {weather.wind_speed_ms:.1f} mph")
        if weather.visibility_km is not None:
            # API returns visibility in meters, convert to miles
            visibility_mi = weather.visibility_km * 0.621371
            output_console.print(f"  Visibility: {visibility_mi:.1f} mi")
        if weather.condition:
            output_console.print(f"  Condition: {weather.condition}")
        if weather.error:
            output_console.print(f"  [yellow]Warning: {weather.error}[/yellow]")
        output_console.print()

        # Seeing Conditions
        seeing = conditions.seeing_score
        if seeing >= 80:
            seeing_text = "[green]Excellent[/green]"
        elif seeing >= 60:
            seeing_text = "[yellow]Good[/yellow]"
        elif seeing >= 40:
            seeing_text = "[yellow]Fair[/yellow]"
        else:
            seeing_text = "[red]Poor[/red]"

        output_console.print("[bold]Seeing Conditions[/bold] (atmospheric steadiness for image sharpness):")
        output_console.print(f"  Seeing: {seeing_text} ({seeing:.0f}/100)")

        # Seeing-based recommendations
        if seeing >= 80:
            output_console.print(
                "  [dim]✓ Ideal for: High-magnification planetary detail, splitting close doubles, faint deep-sky[/dim]"
            )
        elif seeing >= 60:
            output_console.print("  [dim]✓ Good for: Planetary observing, bright deep-sky, double stars[/dim]")
        elif seeing >= 40:
            output_console.print("  [dim]✓ Suitable for: Bright objects, low-power deep-sky, wide doubles[/dim]")
        else:
            output_console.print("  [dim]⚠ Limited to: Bright planets, bright clusters, low-power viewing[/dim]")

        # Best seeing time windows
        if conditions.best_seeing_windows:
            window_strings = []
            for window_start, window_end in conditions.best_seeing_windows:
                start_str = format_local_time(window_start, conditions.latitude, conditions.longitude)
                end_str = format_local_time(window_end, conditions.latitude, conditions.longitude)
                # Extract time and AM/PM (parts[1] = time, parts[2] = AM/PM)
                parts_start = start_str.split()
                parts_end = end_str.split()
                start_time = " ".join(parts_start[1:3]) if len(parts_start) >= 3 else start_str
                end_time = " ".join(parts_end[1:3]) if len(parts_end) >= 3 else end_str
                window_strings.append(f"{start_time} - {end_time}")

            windows_text = ", ".join(window_strings)
            output_console.print(f"  [dim]Best seeing windows: {windows_text}[/dim]")

        # Hourly seeing forecast (if available - uses free Open-Meteo API)
        if conditions.hourly_seeing_forecast:
            output_console.print()
            output_console.print("[bold]Hourly Seeing Forecast:[/bold]")

            # Filter forecast to start 1 hour before sunset and go to sunrise
            # All times stored in UTC, converted to local only for display
            forecast_to_show = []
            now_utc = datetime.now(UTC)

            if conditions.sunset_time and conditions.sunrise_time:
                # Ensure both times are timezone-aware (UTC)
                sunset = conditions.sunset_time
                sunrise = conditions.sunrise_time
                if sunset.tzinfo is None:
                    sunset = sunset.replace(tzinfo=UTC)
                if sunrise.tzinfo is None:
                    sunrise = sunrise.replace(tzinfo=UTC)

                # Start 1 hour before sunset, rounded up to the next hour
                # User wants: "start at 16:00 since sunset is at 16:33"
                # Sunset at 16:33, 1 hour before = 15:33, round up to 16:00
                forecast_start_raw = sunset - timedelta(hours=1)
                # Round up to the next hour (ceiling)
                forecast_start_hour = forecast_start_raw.replace(minute=0, second=0, microsecond=0)
                # If the raw time is past the hour mark, round up to next hour
                if forecast_start_raw > forecast_start_hour:
                    forecast_start = forecast_start_hour + timedelta(hours=1)
                else:
                    forecast_start = forecast_start_hour
                forecast_end = sunrise

                # If sunrise is before sunset (next day), extend to next sunrise
                if forecast_end < forecast_start:
                    # Find next sunrise (add 24 hours)
                    forecast_end = sunrise + timedelta(days=1)

                # Round forecast_end up to the next hour to include the hour containing sunrise
                # e.g., if sunrise is 06:15, we want to include 06:00
                forecast_end_hour = forecast_end.replace(minute=0, second=0, microsecond=0)
                if forecast_end.minute > 0 or forecast_end.second > 0:
                    forecast_end_hour = forecast_end_hour + timedelta(hours=1)
                forecast_end = forecast_end_hour

                # Filter forecasts within the window (all in UTC
                # Include forecasts that fall within or overlap the window
                for forecast in conditions.hourly_seeing_forecast:
                    forecast_ts = forecast.timestamp
                    # Ensure forecast timestamp is UTC
                    if forecast_ts.tzinfo is None:
                        forecast_ts = forecast_ts.replace(tzinfo=UTC)
                    elif forecast_ts.tzinfo != UTC:
                        # Convert to UTC if in different timezone
                        forecast_ts = forecast_ts.astimezone(UTC)

                    # Round forecast timestamp to the hour for comparison
                    forecast_ts_hour = forecast_ts.replace(minute=0, second=0, microsecond=0)

                    # Check if forecast is within the window
                    # Window: from forecast_start (inclusive) to forecast_end (inclusive)
                    if forecast_start <= forecast_ts_hour <= forecast_end:
                        forecast_to_show.append(forecast)

                # If no forecasts found and we're past sunset, show from now to sunrise
                if not forecast_to_show and now_utc > sunset:
                    # We're past sunset, show from now until sunrise (tomorrow if needed)
                    end_time_dt = sunrise
                    if end_time_dt < now_utc:
                        end_time_dt = sunrise + timedelta(days=1)
                    for forecast in conditions.hourly_seeing_forecast:
                        forecast_ts = forecast.timestamp
                        if forecast_ts.tzinfo is None:
                            forecast_ts = forecast_ts.replace(tzinfo=UTC)
                        elif forecast_ts.tzinfo != UTC:
                            forecast_ts = forecast_ts.astimezone(UTC)
                        if now_utc <= forecast_ts <= end_time_dt:
                            forecast_to_show.append(forecast)

                # Sort by timestamp to ensure chronological order
                forecast_to_show.sort(
                    key=lambda f: f.timestamp if f.timestamp.tzinfo else f.timestamp.replace(tzinfo=UTC)
                )
            else:
                # Fallback: show next 12 hours if sunset/sunrise not available
                # But only show future forecasts
                for forecast in conditions.hourly_seeing_forecast:
                    forecast_ts = forecast.timestamp
                    if forecast_ts.tzinfo is None:
                        forecast_ts = forecast_ts.replace(tzinfo=UTC)
                    elif forecast_ts.tzinfo != UTC:
                        forecast_ts = forecast_ts.astimezone(UTC)
                    if forecast_ts >= now_utc:
                        forecast_to_show.append(forecast)
                        if len(forecast_to_show) >= 12:
                            break

            # Debug: If no forecasts found, log why
            if not forecast_to_show and conditions.sunset_time and conditions.sunrise_time:
                # This shouldn't happen, but if it does, at least show something useful
                # Try showing forecasts from 1 hour before sunset to sunrise without the "now" filter
                sunset = conditions.sunset_time
                sunrise = conditions.sunrise_time
                if sunset.tzinfo is None:
                    sunset = sunset.replace(tzinfo=UTC)
                if sunrise.tzinfo is None:
                    sunrise = sunrise.replace(tzinfo=UTC)
                forecast_start = sunset - timedelta(hours=1)
                forecast_end = sunrise
                if forecast_end < forecast_start:
                    forecast_end = sunrise + timedelta(days=1)

                for forecast in conditions.hourly_seeing_forecast:
                    forecast_ts = forecast.timestamp
                    if forecast_ts.tzinfo is None:
                        forecast_ts = forecast_ts.replace(tzinfo=UTC)
                    elif forecast_ts.tzinfo != UTC:
                        forecast_ts = forecast_ts.astimezone(UTC)
                    if forecast_start <= forecast_ts <= forecast_end:
                        forecast_to_show.append(forecast)
                forecast_to_show.sort(
                    key=lambda f: f.timestamp if f.timestamp.tzinfo else f.timestamp.replace(tzinfo=UTC)
                )

            if forecast_to_show:
                for forecast in forecast_to_show:
                    time_str = format_local_time(forecast.timestamp, conditions.latitude, conditions.longitude)
                    # Extract time and AM/PM (parts[1] = time, parts[2] = AM/PM)
                    parts = time_str.split()
                    time_only = " ".join(parts[1:3]) if len(parts) >= 3 else time_str

                    # Color code by seeing score
                    if forecast.seeing_score >= 80:
                        score_color = "[green]"
                    elif forecast.seeing_score >= 40:
                        score_color = "[yellow]"
                    else:
                        score_color = "[red]"

                    output_console.print(
                        f"  {time_only}: {score_color}{forecast.seeing_score:.0f}/100[/] "
                        f"[dim]({forecast.cloud_cover_percent or 0:.0f}% clouds, "
                        f"{forecast.wind_speed_mph or 0:.1f} mph wind)[/]"
                    )
            else:
                output_console.print("  [dim]No forecast data available for observing window[/dim]")
        output_console.print()

        # Light Pollution
        lp = conditions.light_pollution
        output_console.print("[bold]Sky Darkness:[/bold]")
        output_console.print(f"  Bortle Class: {lp.bortle_class.value} ({lp.description})")
        output_console.print(f"  SQM: {lp.sqm_value:.2f} mag/arcsec²")
        output_console.print(f"  Naked Eye Limit: {lp.naked_eye_limiting_magnitude:.2f} mag")
        output_console.print(f"  Telescope Limit: {conditions.limiting_magnitude:.2f} mag")
        output_console.print()

        # Moon Events
        output_console.print("[bold]Moon Events:[/bold]")
        if conditions.moon_phase:
            output_console.print(f"  Phase: {conditions.moon_phase}")
        output_console.print(f"  Illumination: {conditions.moon_illumination * 100:.1f}%")
        output_console.print(f"  Altitude: {conditions.moon_altitude:.1f}°")
        if conditions.moon_altitude < 0:
            output_console.print("  [dim]Below horizon[/dim]")
        if conditions.moonrise_time:
            moonrise_str = format_local_time(conditions.moonrise_time, conditions.latitude, conditions.longitude)
            # Extract time and AM/PM (parts[1] = time, parts[2] = AM/PM)
            parts = moonrise_str.split()
            moonrise_time = " ".join(parts[1:3]) if len(parts) >= 3 else moonrise_str
            output_console.print(f"  Moonrise: {moonrise_time}")
        if conditions.moonset_time:
            moonset_str = format_local_time(conditions.moonset_time, conditions.latitude, conditions.longitude)
            # Extract time and AM/PM (parts[1] = time, parts[2] = AM/PM)
            parts = moonset_str.split()
            moonset_time = " ".join(parts[1:3]) if len(parts) >= 3 else moonset_str
            output_console.print(f"  Moonset: {moonset_time}")
        output_console.print()

        # Sun Events
        output_console.print("[bold]Sun Events:[/bold]")

        # Sunrise/Sunset
        if conditions.sunrise_time:
            sunrise_str = format_local_time(conditions.sunrise_time, conditions.latitude, conditions.longitude)
            # Extract time and AM/PM (parts[1] = time, parts[2] = AM/PM)
            parts = sunrise_str.split()
            sunrise_time = " ".join(parts[1:3]) if len(parts) >= 3 else sunrise_str
            output_console.print(f"  Sunrise: {sunrise_time}")
        if conditions.sunset_time:
            sunset_str = format_local_time(conditions.sunset_time, conditions.latitude, conditions.longitude)
            # Extract time and AM/PM (parts[1] = time, parts[2] = AM/PM)
            parts = sunset_str.split()
            sunset_time = " ".join(parts[1:3]) if len(parts) >= 3 else sunset_str
            output_console.print(f"  Sunset: {sunset_time}")

        # Golden Hour
        if conditions.golden_hour_evening_start and conditions.golden_hour_evening_end:
            gh_evening_start = format_local_time(
                conditions.golden_hour_evening_start, conditions.latitude, conditions.longitude
            )
            gh_evening_end = format_local_time(
                conditions.golden_hour_evening_end, conditions.latitude, conditions.longitude
            )
            # Extract time and AM/PM (parts[1] = time, parts[2] = AM/PM)
            parts_start = gh_evening_start.split()
            parts_end = gh_evening_end.split()
            gh_start_time = " ".join(parts_start[1:3]) if len(parts_start) >= 3 else gh_evening_start
            gh_end_time = " ".join(parts_end[1:3]) if len(parts_end) >= 3 else gh_evening_end
            output_console.print(f"  Golden Hour (evening): {gh_start_time} - {gh_end_time}")
        if conditions.golden_hour_morning_start and conditions.golden_hour_morning_end:
            gh_morning_start = format_local_time(
                conditions.golden_hour_morning_start, conditions.latitude, conditions.longitude
            )
            gh_morning_end = format_local_time(
                conditions.golden_hour_morning_end, conditions.latitude, conditions.longitude
            )
            # Extract time and AM/PM (parts[1] = time, parts[2] = AM/PM)
            parts_start = gh_morning_start.split()
            parts_end = gh_morning_end.split()
            gh_start_time = " ".join(parts_start[1:3]) if len(parts_start) >= 3 else gh_morning_start
            gh_end_time = " ".join(parts_end[1:3]) if len(parts_end) >= 3 else gh_morning_end
            output_console.print(f"  Golden Hour (morning): {gh_start_time} - {gh_end_time}")

        # Blue Hour
        if conditions.blue_hour_evening_start and conditions.blue_hour_evening_end:
            bh_evening_start = format_local_time(
                conditions.blue_hour_evening_start, conditions.latitude, conditions.longitude
            )
            bh_evening_end = format_local_time(
                conditions.blue_hour_evening_end, conditions.latitude, conditions.longitude
            )
            # Extract time and AM/PM (parts[1] = time, parts[2] = AM/PM)
            parts_start = bh_evening_start.split()
            parts_end = bh_evening_end.split()
            bh_start_time = " ".join(parts_start[1:3]) if len(parts_start) >= 3 else bh_evening_start
            bh_end_time = " ".join(parts_end[1:3]) if len(parts_end) >= 3 else bh_evening_end
            output_console.print(f"  Blue Hour (evening): {bh_start_time} - {bh_end_time}")
        if conditions.blue_hour_morning_start and conditions.blue_hour_morning_end:
            bh_morning_start = format_local_time(
                conditions.blue_hour_morning_start, conditions.latitude, conditions.longitude
            )
            bh_morning_end = format_local_time(
                conditions.blue_hour_morning_end, conditions.latitude, conditions.longitude
            )
            # Extract time and AM/PM (parts[1] = time, parts[2] = AM/PM)
            parts_start = bh_morning_start.split()
            parts_end = bh_morning_end.split()
            bh_start_time = " ".join(parts_start[1:3]) if len(parts_start) >= 3 else bh_morning_start
            bh_end_time = " ".join(parts_end[1:3]) if len(parts_end) >= 3 else bh_morning_end
            output_console.print(f"  Blue Hour (morning): {bh_start_time} - {bh_end_time}")

        # Astronomical Twilight
        if conditions.astronomical_twilight_evening_start and conditions.astronomical_twilight_evening_end:
            at_evening_start = format_local_time(
                conditions.astronomical_twilight_evening_start, conditions.latitude, conditions.longitude
            )
            at_evening_end = format_local_time(
                conditions.astronomical_twilight_evening_end, conditions.latitude, conditions.longitude
            )
            # Extract time and AM/PM (parts[1] = time, parts[2] = AM/PM)
            parts_start = at_evening_start.split()
            parts_end = at_evening_end.split()
            at_start_time = " ".join(parts_start[1:3]) if len(parts_start) >= 3 else at_evening_start
            at_end_time = " ".join(parts_end[1:3]) if len(parts_end) >= 3 else at_evening_end
            output_console.print(f"  Astronomical Twilight (evening): {at_start_time} - {at_end_time}")
        if conditions.astronomical_twilight_morning_start and conditions.astronomical_twilight_morning_end:
            at_morning_start = format_local_time(
                conditions.astronomical_twilight_morning_start, conditions.latitude, conditions.longitude
            )
            at_morning_end = format_local_time(
                conditions.astronomical_twilight_morning_end, conditions.latitude, conditions.longitude
            )
            # Extract time and AM/PM (parts[1] = time, parts[2] = AM/PM)
            parts_start = at_morning_start.split()
            parts_end = at_morning_end.split()
            at_start_time = " ".join(parts_start[1:3]) if len(parts_start) >= 3 else at_morning_start
            at_end_time = " ".join(parts_end[1:3]) if len(parts_end) >= 3 else at_morning_end
            output_console.print(f"  Astronomical Twilight (morning): {at_start_time} - {at_end_time}")

        # Galactic Center Visibility
        if conditions.galactic_center_start and conditions.galactic_center_end:
            gc_start = format_local_time(conditions.galactic_center_start, conditions.latitude, conditions.longitude)
            gc_end = format_local_time(conditions.galactic_center_end, conditions.latitude, conditions.longitude)
            # Extract time and AM/PM (parts[1] = time, parts[2] = AM/PM)
            parts_start = gc_start.split()
            parts_end = gc_end.split()
            gc_start_time = " ".join(parts_start[1:3]) if len(parts_start) >= 3 else gc_start
            gc_end_time = " ".join(parts_end[1:3]) if len(parts_end) >= 3 else gc_end
            output_console.print(f"  Galactic Center: {gc_start_time} - {gc_end_time}")

        output_console.print()

        # Recommendations
        if conditions.recommendations:
            output_console.print("[bold green]Recommendations:[/bold green]")
            for rec in conditions.recommendations:
                output_console.print(f"  ✓ {rec}")
            output_console.print()

        # Warnings
        if conditions.warnings:
            output_console.print("[bold yellow]Warnings:[/bold yellow]")
            for warn in conditions.warnings:
                output_console.print(f"  ⚠ {warn}")
            output_console.print()

        # Space Weather Alerts
        if conditions.space_weather_alerts:
            output_console.print("[bold cyan]Space Weather:[/bold cyan]")
            for alert in conditions.space_weather_alerts:
                if "aurora" in alert.lower():
                    output_console.print(f"  🌌 {alert}")
                elif "radio" in alert.lower() or "GPS" in alert:
                    output_console.print(f"  📡 {alert}")
                else:
                    output_console.print(f"  ⚡ {alert}")
            if conditions.aurora_opportunity:
                output_console.print(
                    "  [bold green]💡 Enhanced aurora opportunity - Consider checking 'nexstar aurora tonight'[/bold green]"
                )
            output_console.print()

    except ValueError as e:
        output_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from None
    except Exception as e:
        output_console.print(f"[red]Error getting conditions:[/red] {e}")
        import traceback

        output_console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from None


@app.command("objects", rich_help_panel="Object Recommendations")
def show_objects(
    target_type: str | None = typer.Option(
        None,
        "--type",
        help="Filter by type: categories (planets, deep_sky, messier, etc.) or object types (galaxy, cluster, nebula, planet, star, etc.)",
    ),
    constellation: str | None = typer.Option(
        None,
        "--constellation",
        help="Filter by constellation name (case-insensitive, partial match supported)",
    ),
    limit: int = typer.Option(20, "--limit", help="Maximum objects to show"),
    best_for_seeing: bool = typer.Option(
        False, "--best-for-seeing", help="Show only objects ideal for current seeing conditions"
    ),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Show recommended objects for tonight."""
    from celestron_nexstar.cli.utils.export import create_file_console, export_to_text

    if export:
        if export_path:
            export_path_obj = Path(export_path)
        else:
            export_path_obj = generate_export_filename("objects", viewing_type="telescope")

        file_console = create_file_console()
        _show_objects_content(file_console, target_type, constellation, limit, best_for_seeing)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_objects_content(console, target_type, constellation, limit, best_for_seeing)


def _show_objects_content(
    output_console: Console | FileConsole,
    target_type: str | None = None,
    constellation: str | None = None,
    limit: int = 20,
    best_for_seeing: bool = False,
) -> None:
    """Generate and display objects content."""
    try:
        planner = ObservationPlanner()
        conditions = planner.get_tonight_conditions()

        # Interactive selection if target_type not provided
        from celestron_nexstar.api.core.enums import CelestialObjectType

        # Type can be None, list of ObservingTarget, or a single CelestialObjectType
        target_types: list[ObservingTarget] | CelestialObjectType | None = None

        if target_type is None:
            target_type = _select_object_type_interactive()
            if target_type is None:
                target_types = None  # User cancelled
            elif target_type == "all":
                target_types = None  # Show all types
            else:
                # Try as ObservingTarget first (categories)
                try:
                    target_types = [ObservingTarget(target_type)]
                except ValueError:
                    # Try as CelestialObjectType (specific object types)
                    try:
                        obj_type = CelestialObjectType(target_type)
                        target_types = obj_type  # Pass directly as CelestialObjectType
                    except ValueError:
                        output_console.print(f"[red]Invalid target type: {target_type}[/red]")
                        raise typer.Exit(code=1) from None
        else:
            # Parse target types - support both ObservingTarget categories and CelestialObjectType values
            if target_type.lower() == "all":
                target_types = None  # Show all types
            else:
                # Try as ObservingTarget first (categories)
                try:
                    target_types = [ObservingTarget(target_type.lower())]
                except ValueError:
                    # Try as CelestialObjectType (specific object types)
                    try:
                        obj_type = CelestialObjectType(target_type.lower())
                        # Pass the object type directly to the planner
                        # We'll handle this in get_recommended_objects
                        target_types = obj_type  # Special marker for direct object type
                    except ValueError:
                        output_console.print(f"[red]Invalid target type: {target_type}[/red]")
                        output_console.print(f"Valid categories: all, {', '.join([t.value for t in ObservingTarget])}")
                        output_console.print(f"Valid object types: {', '.join([t.value for t in CelestialObjectType])}")
                        raise typer.Exit(code=1) from None

        objects = planner.get_recommended_objects(
            conditions, target_types, max_results=limit, best_for_seeing=best_for_seeing, constellation=constellation
        )

        if not objects:
            output_console.print("[yellow]No objects currently visible with current conditions.[/yellow]")
            return

        # Create table
        table = Table(title=f"Recommended Objects for Tonight ({len(objects)} total)")
        table.add_column("Priority", style="cyan")
        table.add_column("Name", style="bold")
        table.add_column("Type", style="dim")
        table.add_column("Mag", justify="right")
        table.add_column("Alt", justify="right")
        table.add_column("Transit", style="dim")
        table.add_column("Moon Sep", justify="right", style="dim")
        table.add_column("Chance", justify="right", style="dim")
        table.add_column("Tips", style="dim")

        for obj_rec in objects[:limit]:
            priority_stars = "★" * (6 - obj_rec.priority)  # Invert: 1 = ★★★★★, 5 = ★
            obj = obj_rec.obj

            # Convert best viewing time to local timezone
            best_time = obj_rec.best_viewing_time
            if best_time.tzinfo is None:
                best_time = best_time.replace(tzinfo=UTC)

            from celestron_nexstar.api.core import get_local_timezone

            tz = get_local_timezone(conditions.latitude, conditions.longitude)
            if tz:
                local_time = best_time.astimezone(tz)
                time_str = local_time.strftime("%I:%M %p")
            else:
                time_str = best_time.strftime("%I:%M %p UTC")

            # Format viewing tips (show first 2, truncate if needed)
            tips_text = "; ".join(obj_rec.viewing_tips[:2]) if obj_rec.viewing_tips else ""
            if len(tips_text) > 33:
                tips_text = tips_text[:30] + "..."

            # Format moon separation
            moon_sep_text = "-"
            if obj_rec.moon_separation_deg is not None:
                if obj_rec.moon_separation_deg < 30:
                    moon_sep_text = f"[red]{obj_rec.moon_separation_deg:.0f}°[/red]"  # Too close
                elif obj_rec.moon_separation_deg < 60:
                    moon_sep_text = f"[yellow]{obj_rec.moon_separation_deg:.0f}°[/yellow]"  # Moderate
                else:
                    moon_sep_text = f"[green]{obj_rec.moon_separation_deg:.0f}°[/green]"  # Good separation

            # Format visibility probability
            prob = obj_rec.visibility_probability
            if prob >= 0.8:
                prob_text = f"[green]{prob:.0%}[/green]"
            elif prob >= 0.5:
                prob_text = f"[yellow]{prob:.0%}[/yellow]"
            elif prob >= 0.3:
                prob_text = f"[red]{prob:.0%}[/red]"
            else:
                prob_text = f"[dim red]{prob:.0%}[/dim red]"

            # Use common name if available, otherwise use catalog name
            display_name = obj.common_name or obj.name

            table.add_row(
                priority_stars,
                display_name,
                obj.object_type.value,
                f"{obj_rec.apparent_magnitude:.2f}" if obj_rec.apparent_magnitude else "-",
                f"{obj_rec.altitude:.0f}°",
                time_str,
                moon_sep_text,
                prob_text,
                tips_text,
            )

        output_console.print(table)
        output_console.print(f"\n[dim]Showing top {min(limit, len(objects))} of {len(objects)} visible objects[/dim]")

    except ValueError as e:
        output_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from None
    except Exception as e:
        output_console.print(f"[red]Error getting objects:[/red] {e}")
        import traceback

        output_console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from None


@app.command("imaging", rich_help_panel="Imaging")
def show_imaging(
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Show imaging forecasts: seeing for planetary, transparency for deep-sky, and exposure suggestions."""
    from celestron_nexstar.cli.utils.export import create_file_console, export_to_text

    if export:
        if export_path:
            export_path_obj = Path(export_path)
        else:
            export_path_obj = generate_export_filename("imaging", viewing_type="telescope")

        file_console = create_file_console()
        _show_imaging_content(file_console)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_imaging_content(console)


def _show_imaging_content(output_console: Console | FileConsole) -> None:
    """Generate and display imaging content."""
    try:
        planner = ObservationPlanner()
        conditions = planner.get_tonight_conditions()

        if not conditions.hourly_seeing_forecast:
            output_console.print("[yellow]Hourly forecast data not available. Weather API may be unavailable.[/yellow]")
            return

        # Filter forecasts to observing window (sunset to sunrise)
        sunset_time = conditions.sunset_time
        sunrise_time = conditions.sunrise_time

        if sunset_time is None or sunrise_time is None:
            output_console.print("[yellow]Sunset/sunrise times not available.[/yellow]")
            return

        # Ensure times are UTC
        if sunset_time.tzinfo is None:
            sunset_time = sunset_time.replace(tzinfo=UTC)
        if sunrise_time.tzinfo is None:
            sunrise_time = sunrise_time.replace(tzinfo=UTC)

        # Extend to next sunrise if needed
        if sunrise_time < sunset_time:
            sunrise_time = sunrise_time + timedelta(days=1)

        # Filter forecasts within observing window
        observing_forecasts = []
        for forecast in conditions.hourly_seeing_forecast:
            forecast_ts = forecast.timestamp
            if forecast_ts.tzinfo is None:
                forecast_ts = forecast_ts.replace(tzinfo=UTC)
            elif forecast_ts.tzinfo != UTC:
                forecast_ts = forecast_ts.astimezone(UTC)

            if sunset_time <= forecast_ts <= sunrise_time:
                observing_forecasts.append(forecast)

        if not observing_forecasts:
            output_console.print("[yellow]No forecast data available for the observing window.[/yellow]")
            return

        from celestron_nexstar.api.core import get_local_timezone

        tz = get_local_timezone(conditions.latitude, conditions.longitude)

        # Planetary Imaging - Seeing Forecast
        output_console.print("\n[bold cyan]Planetary Imaging - Seeing Forecast[/bold cyan]")
        output_console.print(
            "[dim]Seeing quality affects planetary detail capture. Excellent seeing (≥80) allows shorter exposures.[/dim]\n"
        )

        table_planetary = Table()
        table_planetary.add_column("Time", style="cyan")
        table_planetary.add_column("Seeing", justify="right")
        table_planetary.add_column("Quality")
        table_planetary.add_column("Wind", justify="right")
        table_planetary.add_column("Exposure")

        for forecast in observing_forecasts:
            forecast_ts = forecast.timestamp
            if forecast_ts.tzinfo is None:
                forecast_ts = forecast_ts.replace(tzinfo=UTC)
            elif forecast_ts.tzinfo != UTC:
                forecast_ts = forecast_ts.astimezone(UTC)

            # Format time
            if tz:
                local_time = forecast_ts.astimezone(tz)
                time_str = local_time.strftime("%I:%M %p")
            else:
                time_str = forecast_ts.strftime("%I:%M %p UTC")

            # Seeing quality assessment
            seeing = forecast.seeing_score
            if seeing >= 80:
                quality = "[green]Excellent[/green]"
                exposure = "[green]10-50ms[/green]"
            elif seeing >= 60:
                quality = "[yellow]Good[/yellow]"
                exposure = "[yellow]50-200ms[/yellow]"
            elif seeing >= 40:
                quality = "[dim]Fair[/dim]"
                exposure = "[dim]200-500ms[/dim]"
            else:
                quality = "[red]Poor[/red]"
                exposure = "[red]500ms-2s[/red]"

            # Wind speed
            wind_text = "-"
            if forecast.wind_speed_mph is not None:
                wind_text = f"{forecast.wind_speed_mph:.1f} mph"

            table_planetary.add_row(
                time_str,
                f"{seeing:.0f}/100",
                quality,
                wind_text,
                exposure,
            )

        output_console.print(table_planetary)

        # Deep-Sky Imaging - Transparency Forecast
        output_console.print("\n[bold cyan]Deep-Sky Imaging - Transparency Forecast[/bold cyan]")
        output_console.print(
            "[dim]Transparency (cloud cover) affects deep-sky exposure times. Clear skies allow longer exposures.[/dim]\n"
        )

        table_deepsky = Table()
        table_deepsky.add_column("Time", style="cyan")
        table_deepsky.add_column("Clouds", justify="right")
        table_deepsky.add_column("Transparency")
        table_deepsky.add_column("Humidity", justify="right")
        table_deepsky.add_column("Exposure")

        for forecast in observing_forecasts:
            forecast_ts = forecast.timestamp
            if forecast_ts.tzinfo is None:
                forecast_ts = forecast_ts.replace(tzinfo=UTC)
            elif forecast_ts.tzinfo != UTC:
                forecast_ts = forecast_ts.astimezone(UTC)

            # Format time
            if tz:
                local_time = forecast_ts.astimezone(tz)
                time_str = local_time.strftime("%I:%M %p")
            else:
                time_str = forecast_ts.strftime("%I:%M %p UTC")

            # Transparency assessment based on cloud cover
            clouds = forecast.cloud_cover_percent or 100.0
            if clouds < 10:
                transparency = "[green]Excellent[/green]"
                # Exposure times depend on light pollution and moon
                if conditions.moon_illumination < 0.1:  # New moon
                    if conditions.light_pollution.bortle_class.value <= 3:  # Dark sky
                        exposure = "[green]5-10 min[/green]"
                    elif conditions.light_pollution.bortle_class.value <= 5:  # Suburban
                        exposure = "[yellow]3-5 min[/yellow]"
                    else:  # Urban
                        exposure = "[yellow]1-3 min[/yellow]"
                elif conditions.moon_illumination < 0.5:  # Quarter moon
                    exposure = "[yellow]2-5 min[/yellow]"
                else:  # Bright moon
                    exposure = "[dim]30s-2 min[/dim]"
            elif clouds < 30:
                transparency = "[yellow]Good[/yellow]"
                exposure = "[yellow]1-3 min[/yellow]"
            elif clouds < 50:
                transparency = "[dim]Fair[/dim]"
                exposure = "[dim]30s-1 min[/dim]"
            elif clouds < 70:
                transparency = "[red]Poor[/red]"
                exposure = "[red]Not recommended[/red]"
            else:
                transparency = "[red]Very Poor[/red]"
                exposure = "[red]Not recommended[/red]"

            # Humidity
            humidity_text = "-"
            if forecast.humidity_percent is not None:
                humidity_text = f"{forecast.humidity_percent:.0f}%"

            table_deepsky.add_row(
                time_str,
                f"{clouds:.0f}%",
                transparency,
                humidity_text,
                exposure,
            )

        output_console.print(table_deepsky)

        # Exposure Time Recommendations Summary
        output_console.print("\n[bold cyan]Exposure Time Recommendations[/bold cyan]\n")

        # Find best seeing window for planetary
        best_planetary = max(observing_forecasts, key=lambda f: f.seeing_score)
        best_planetary_ts = best_planetary.timestamp
        if best_planetary_ts.tzinfo is None:
            best_planetary_ts = best_planetary_ts.replace(tzinfo=UTC)
        elif best_planetary_ts.tzinfo != UTC:
            best_planetary_ts = best_planetary_ts.astimezone(UTC)

        if tz:
            best_planetary_local = best_planetary_ts.astimezone(tz)
            best_planetary_time = best_planetary_local.strftime("%I:%M %p")
        else:
            best_planetary_time = best_planetary_ts.strftime("%I:%M %p UTC")

        output_console.print(f"[bold]Best Planetary Imaging Window:[/bold] {best_planetary_time}")
        output_console.print(f"  Seeing: {best_planetary.seeing_score:.0f}/100")
        if best_planetary.seeing_score >= 80:
            output_console.print("  [green]Recommended: 10-50ms exposures, stack 1000-5000 frames[/green]")
        elif best_planetary.seeing_score >= 60:
            output_console.print("  [yellow]Recommended: 50-200ms exposures, stack 500-2000 frames[/yellow]")
        else:
            output_console.print("  [dim]Recommended: 200-500ms exposures, stack 200-1000 frames[/dim]")

        # Find best transparency window for deep-sky
        best_deepsky = min(observing_forecasts, key=lambda f: f.cloud_cover_percent or 100.0)
        best_deepsky_ts = best_deepsky.timestamp
        if best_deepsky_ts.tzinfo is None:
            best_deepsky_ts = best_deepsky_ts.replace(tzinfo=UTC)
        elif best_deepsky_ts.tzinfo != UTC:
            best_deepsky_ts = best_deepsky_ts.astimezone(UTC)

        if tz:
            best_deepsky_local = best_deepsky_ts.astimezone(tz)
            best_deepsky_time = best_deepsky_local.strftime("%I:%M %p")
        else:
            best_deepsky_time = best_deepsky_ts.strftime("%I:%M %p UTC")

        output_console.print(f"\n[bold]Best Deep-Sky Imaging Window:[/bold] {best_deepsky_time}")
        clouds = best_deepsky.cloud_cover_percent or 100.0
        output_console.print(f"  Cloud Cover: {clouds:.0f}%")
        if clouds < 10:
            if conditions.moon_illumination < 0.1:
                output_console.print("  [green]Recommended: 5-10 min exposures (dark sky, new moon)[/green]")
            else:
                output_console.print("  [yellow]Recommended: 2-5 min exposures (bright moon)[/yellow]")
        elif clouds < 30:
            output_console.print("  [yellow]Recommended: 1-3 min exposures[/yellow]")
        else:
            output_console.print("  [red]Not recommended for deep-sky imaging[/red]")

        output_console.print(
            "\n[dim]Note: Exposure times are general guidelines. Adjust based on your camera, telescope, and target.[/dim]"
        )

    except Exception as e:
        output_console.print(f"[red]Error getting imaging forecast:[/red] {e}")
        import traceback

        output_console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from None


@app.command("tonight", rich_help_panel="Viewing Guides")
def show_tonight(
    target_type: str | None = typer.Option(
        None, "--type", help="Filter by type (all, planets, deep_sky, messier, etc.)"
    ),
    limit: int = typer.Option(20, "--limit", help="Maximum objects to show"),
    best_for_seeing: bool = typer.Option(
        False, "--best-for-seeing", help="Show only objects ideal for current seeing conditions"
    ),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Show complete observing plan for tonight (conditions + objects) for Celestron NexStar 6SE."""
    from pathlib import Path

    from celestron_nexstar.cli.utils.export import create_file_console, export_to_text

    # Handle export
    if export:
        if export_path:
            # User provided a custom path
            export_path_obj = Path(export_path)
        else:
            # Auto-generate filename
            export_path_obj = generate_export_filename("tonight", viewing_type="telescope")
        # Create file console for export (StringIO)
        file_console = create_file_console()
        # Use file console for output
        _show_tonight_content(file_console, target_type, limit, best_for_seeing)
        # Get content from StringIO
        content = file_console.file.getvalue()
        file_console.file.close()

        # Export to text file
        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    # Normal console output
    _show_tonight_content(console, target_type, limit, best_for_seeing)


def _show_tonight_content(
    output_console: Console | FileConsole,
    target_type: str | None = None,
    limit: int = 20,
    best_for_seeing: bool = False,
) -> None:
    """Generate and display tonight viewing content for telescope."""
    from celestron_nexstar.api.observation.optics import load_configuration

    # Check if telescope is configured
    config = load_configuration()

    # Add telescope identification header
    if config:
        telescope = config.telescope
        output_console.print(f"\n[bold cyan]{telescope.model.display_name} - Tonight's Viewing Guide[/bold cyan]")
        output_console.print(
            f"[dim]Telescope: {telescope.aperture_mm}mm aperture, f/{telescope.focal_ratio:.1f} ({telescope.focal_length_mm}mm focal length)[/dim]"
        )

        # Determine telescope type for description
        if telescope.aperture_mm < 125:
            optimal = "Planetary detail, bright deep-sky objects, double stars, lunar observing"
        elif telescope.aperture_mm < 200:
            optimal = "Planetary detail, bright to medium deep-sky objects, double stars, lunar observing"
        else:
            optimal = "Planetary detail, deep-sky objects, double stars, lunar observing, faint objects"

        output_console.print(f"[dim]Optimal for: {optimal}[/dim]\n")
    else:
        output_console.print("\n[bold cyan]Telescope Viewing Guide - Tonight[/bold cyan]")
        output_console.print("[yellow]⚠ No telescope configured[/yellow]")
        output_console.print("[dim]Configure your telescope using: nexstar optics configure[/dim]")
        output_console.print(
            "[dim]This guide shows general observing conditions and objects visible with any telescope.[/dim]\n"
        )

    # Show conditions
    _show_conditions_content(output_console)
    output_console.print("\n" + "=" * 80 + "\n")
    # Show objects
    _show_objects_content(output_console, target_type, limit, best_for_seeing)


@app.command("plan", rich_help_panel="Complete Plans")
def show_plan(
    target_type: str | None = typer.Option(
        None, "--type", help="Filter by type (all, planets, deep_sky, messier, etc.)"
    ),
    limit: int = typer.Option(20, "--limit", help="Maximum objects to show"),
    best_for_seeing: bool = typer.Option(
        False, "--best-for-seeing", help="Show only objects ideal for current seeing conditions"
    ),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Show complete observing plan for tonight (conditions + objects)."""
    from celestron_nexstar.cli.utils.export import create_file_console, export_to_text

    if export:
        export_path_obj = (
            Path(export_path) if export_path else generate_export_filename("plan", viewing_type="telescope")
        )

        file_console = create_file_console()
        _show_conditions_content(file_console)
        file_console.print("\n" + "=" * 80 + "\n")
        _show_objects_content(file_console, target_type, limit, best_for_seeing)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_conditions_content(console)
    console.print("\n" + "=" * 80 + "\n")
    _show_objects_content(console, target_type, limit, best_for_seeing)


def _select_object_type_interactive() -> str | None:
    """Interactively select an object type for filtering."""

    # Create a special "all" option
    class AllOption:
        """Special marker for 'all' option."""

        value = "all"
        display_name = "All Types"
        description = "Show all object types (no filtering)"

    from celestron_nexstar.api.core.enums import CelestialObjectType

    # Add separator-like entry for object types
    class Separator:
        """Visual separator in menu."""

        value = "__separator__"
        display_name = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        description = "Specific Object Types"

    # Combine categories and specific object types
    object_types: list[ObservingTarget | CelestialObjectType | AllOption | Separator] = [AllOption()]

    # Add categories first
    object_types.extend(list(ObservingTarget))

    # Add separator
    object_types.append(Separator())

    # Add specific object types
    object_types.extend(list(CelestialObjectType))

    # Object type descriptions
    descriptions = {
        ObservingTarget.PLANETS: "Solar system planets",
        ObservingTarget.MOON: "Earth's moon",
        ObservingTarget.DEEP_SKY: "Deep sky objects (galaxies, nebulae, clusters, NGC, IC, Caldwell)",
        ObservingTarget.DOUBLE_STARS: "Double and multiple star systems",
        ObservingTarget.VARIABLE_STARS: "Variable stars",
        ObservingTarget.MESSIER: "Messier catalog objects (popular curated list)",
        CelestialObjectType.STAR: "Individual stars",
        CelestialObjectType.PLANET: "Planets (same as 'planets' category)",
        CelestialObjectType.GALAXY: "Galaxies only",
        CelestialObjectType.NEBULA: "Nebulae only",
        CelestialObjectType.CLUSTER: "Star clusters only",
        CelestialObjectType.DOUBLE_STAR: "Double stars (same as 'double_stars' category)",
        CelestialObjectType.ASTERISM: "Asterisms (star patterns)",
        CelestialObjectType.CONSTELLATION: "Constellations",
        CelestialObjectType.MOON: "Moons (same as 'moon' category)",
    }

    def display_object_type(item: ObservingTarget | CelestialObjectType | AllOption | Separator) -> tuple[str, ...]:
        if isinstance(item, AllOption):
            return (item.display_name, item.description)
        if isinstance(item, Separator):
            return (item.display_name, item.description)
        display_name = item.value.replace("_", " ").title()
        description = descriptions.get(item, "Object type")
        return (display_name, description)

    selected = select_from_list(
        object_types,
        title="Select Object Type",
        display_func=display_object_type,
        headers=["Object Type", "Description"],
    )

    if selected is None:
        return None

    if isinstance(selected, AllOption):
        return "all"

    if isinstance(selected, Separator):
        return None  # Separator selected, shouldn't happen but handle it

    return selected.value


@app.command("timeline", rich_help_panel="Planning Tools")
def show_timeline(
    object_name: str = typer.Argument(..., help="Object name (e.g., M31, Jupiter, Vega)"),
    days: int = typer.Option(1, "--days", "-d", help="Number of days to show (default: 1)"),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file"),
    export_path: str | None = typer.Option(None, "--export-path", help="Custom export file path"),
) -> None:
    """Show object visibility timeline (rise, transit, set times)."""
    from celestron_nexstar.cli.utils.export import create_file_console, export_to_text

    if export:
        export_path_obj = (
            Path(export_path) if export_path else generate_export_filename("timeline", viewing_type="telescope")
        )
        file_console = create_file_console()
        _show_timeline_content(file_console, object_name, days)
        content = file_console.file.getvalue()
        file_console.file.close()
        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_timeline_content(console, object_name, days)


def _show_timeline_content(output_console: Console | FileConsole, object_name: str, days: int) -> None:
    """Display timeline content."""
    import asyncio

    async def get_obj() -> CelestialObject | None:
        objects = await get_object_by_name(object_name)
        return objects[0] if objects else None

    obj = asyncio.run(get_obj())
    if not obj:
        output_console.print(f"[red]Error: Object '{object_name}' not found.[/red]")
        return

    location = get_observer_location()
    if not location:
        output_console.print("[red]Error: No observer location set.[/red]")
        return

    timeline = get_object_visibility_timeline(obj, location.latitude, location.longitude, days=days)

    output_console.print(f"\n[bold cyan]Visibility Timeline: {obj.name}[/bold cyan]\n")

    if timeline.is_never_visible:
        output_console.print("[yellow]This object is never visible from your location.[/yellow]")
        return

    if timeline.is_always_visible:
        output_console.print("[green]This object is always visible (circumpolar).[/green]")
        if timeline.transit_time:
            time_str = format_local_time(timeline.transit_time, location.latitude, location.longitude)
            output_console.print(f"Transit (highest): {time_str}")
            output_console.print(f"Maximum altitude: {timeline.max_altitude:.1f}°")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Event", style="cyan")
    table.add_column("Time", style="green")
    table.add_column("Altitude", justify="right")

    if timeline.rise_time:
        time_str = format_local_time(timeline.rise_time, location.latitude, location.longitude)
        alt, _ = get_object_altitude_azimuth(obj, location.latitude, location.longitude, timeline.rise_time)
        table.add_row("Rise", time_str, f"{alt:.1f}°")

    if timeline.transit_time:
        time_str = format_local_time(timeline.transit_time, location.latitude, location.longitude)
        table.add_row("Transit (Highest)", time_str, f"{timeline.max_altitude:.1f}°")

    if timeline.set_time:
        time_str = format_local_time(timeline.set_time, location.latitude, location.longitude)
        alt, _ = get_object_altitude_azimuth(obj, location.latitude, location.longitude, timeline.set_time)
        table.add_row("Set", time_str, f"{alt:.1f}°")

    output_console.print(table)


@app.command("checklist", rich_help_panel="Planning Tools")
def show_checklist(
    export: bool = typer.Option(False, "--export", "-e", help="Export checklist to text file"),
    export_path: str | None = typer.Option(None, "--export-path", help="Custom export file path"),
) -> None:
    """Generate pre-observation checklist."""
    from celestron_nexstar.cli.utils.export import create_file_console, export_to_text

    checklist = generate_observation_checklist(equipment_type="telescope")

    if export:
        export_path_obj = (
            Path(export_path) if export_path else generate_export_filename("checklist", viewing_type="telescope")
        )
        file_console = create_file_console()
        _show_checklist_content(file_console, checklist)
        content = file_console.file.getvalue()
        file_console.file.close()
        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_checklist_content(console, checklist)


def _show_checklist_content(output_console: Console | FileConsole, checklist: list[str]) -> None:
    """Display checklist content."""
    output_console.print("\n[bold cyan]Pre-Observation Checklist[/bold cyan]\n")
    for i, item in enumerate(checklist, 1):
        output_console.print(f"  {i}. [ ] {item}")
    output_console.print()


@app.command("difficulty", rich_help_panel="Planning Tools")
def show_difficulty(
    object_name: str = typer.Argument(..., help="Object name (e.g., M31, Jupiter, Vega)"),
) -> None:
    """Show object difficulty rating."""
    import asyncio

    async def get_obj() -> CelestialObject | None:
        objects = await get_object_by_name(object_name)
        return objects[0] if objects else None

    obj = asyncio.run(get_obj())
    if not obj:
        console.print(f"[red]Error: Object '{object_name}' not found.[/red]")
        return

    difficulty = get_object_difficulty(obj)
    difficulty_colors = {
        DifficultyLevel.BEGINNER: "green",
        DifficultyLevel.INTERMEDIATE: "yellow",
        DifficultyLevel.ADVANCED: "orange1",
        DifficultyLevel.EXPERT: "red",
    }
    color = difficulty_colors.get(difficulty, "white")

    console.print(f"\n[bold cyan]Difficulty Rating: {obj.name}[/bold cyan]\n")
    console.print(f"Difficulty: [{color}]{difficulty.value.upper()}[/{color}]")
    if obj.magnitude:
        console.print(f"Magnitude: {obj.magnitude:.1f}")
    if obj.object_type:
        console.print(f"Type: {obj.object_type.value}")
    console.print()


@app.command("moon-impact", rich_help_panel="Planning Tools")
def show_moon_impact(
    object_type: str = typer.Argument(..., help="Object type (e.g., galaxy, planet, nebula)"),
) -> None:
    """Show how moon phase affects observing different object types."""
    from celestron_nexstar.api.astronomy.solar_system import get_moon_info
    from celestron_nexstar.api.location.observer import get_observer_location

    location = get_observer_location()
    if not location:
        console.print("[red]Error: No observer location set.[/red]")
        return

    moon_info = get_moon_info(location.latitude, location.longitude)
    moon_phase = moon_info.phase_name if moon_info else None
    moon_illum = moon_info.illumination if moon_info else None

    impact = get_moon_phase_impact(object_type, moon_phase, moon_illum)

    console.print(f"\n[bold cyan]Moon Phase Impact: {object_type}[/bold cyan]\n")
    if moon_info:
        console.print(f"Current moon phase: {moon_info.phase_name.value if moon_info.phase_name else 'Unknown'}")
        console.print(f"Moon illumination: {moon_info.illumination * 100:.0f}%")
    console.print(f"\nImpact level: {impact['impact_level']}")
    console.print(f"Recommended: {'Yes' if impact['recommended'] else 'No'}")
    notes = impact.get("notes", [])
    if notes and isinstance(notes, list):
        console.print("\nNotes:")
        for note in notes:
            console.print(f"  • {note}")
    console.print()


@app.command("quick-reference", rich_help_panel="Planning Tools")
def show_quick_reference(
    limit: int = typer.Option(20, "--limit", "-l", help="Number of objects to include (default: 20)"),
    export: bool = typer.Option(False, "--export", "-e", help="Export to text file"),
    export_path: str | None = typer.Option(None, "--export-path", help="Custom export file path"),
) -> None:
    """Generate quick reference card for common objects."""
    from celestron_nexstar.cli.utils.export import create_file_console, export_to_text

    # Get popular objects from database
    async def get_objects() -> list[CelestialObject]:
        db = get_database()
        # Use filter_objects to get a variety of objects
        objects = await db.filter_objects(limit=limit)
        return objects

    import asyncio

    objects = asyncio.run(get_objects())

    reference = generate_quick_reference(objects)

    if export:
        export_path_obj = (
            Path(export_path) if export_path else generate_export_filename("quickref", viewing_type="telescope")
        )
        file_console = create_file_console()
        file_console.print(reference)
        content = file_console.file.getvalue()
        file_console.file.close()
        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    console.print(f"\n[pre]{reference}[/pre]\n")


@app.command("log-template", rich_help_panel="Planning Tools")
def show_log_template(
    export: bool = typer.Option(False, "--export", "-e", help="Export template to text file"),
    export_path: str | None = typer.Option(None, "--export-path", help="Custom export file path"),
) -> None:
    """Generate observation session log template."""
    from celestron_nexstar.api.location.observer import get_observer_location
    from celestron_nexstar.cli.utils.export import create_file_console, export_to_text

    location = get_observer_location()
    location_name = location.name if location else None

    template = generate_session_log_template(location=location_name)

    if export:
        export_path_obj = (
            Path(export_path) if export_path else generate_export_filename("log", viewing_type="telescope")
        )
        file_console = create_file_console()
        file_console.print(template)
        content = file_console.file.getvalue()
        file_console.file.close()
        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    console.print(template)


@app.command("transit-times", rich_help_panel="Planning Tools")
def show_transit_times(
    limit: int = typer.Option(10, "--limit", "-l", help="Number of objects to show (default: 10)"),
    export: bool = typer.Option(False, "--export", "-e", help="Export to text file"),
    export_path: str | None = typer.Option(None, "--export-path", help="Custom export file path"),
) -> None:
    """Show transit times (when objects are highest) for tonight."""
    from celestron_nexstar.cli.utils.export import create_file_console, export_to_text

    location = get_observer_location()
    if not location:
        console.print("[red]Error: No observer location set.[/red]")
        return

    async def get_objects() -> list[CelestialObject]:
        db = get_database()
        # Use filter_objects to get a variety of objects
        objects = await db.filter_objects(limit=limit * 2)  # Get more to filter
        return objects

    import asyncio

    all_objects = asyncio.run(get_objects())

    transit_times = get_transit_times(all_objects[:limit], location.latitude, location.longitude)

    if export:
        export_path_obj = (
            Path(export_path) if export_path else generate_export_filename("transits", viewing_type="telescope")
        )
        file_console = create_file_console()
        _show_transit_times_content(file_console, transit_times, location)
        content = file_console.file.getvalue()
        file_console.file.close()
        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_transit_times_content(console, transit_times, location)


def _show_transit_times_content(
    output_console: Console | FileConsole, transit_times: dict[str, datetime], location: ObserverLocation
) -> None:
    """Display transit times content."""
    output_console.print("\n[bold cyan]Transit Times (Objects at Highest Point)[/bold cyan]\n")

    if not transit_times:
        output_console.print("[yellow]No objects found with transit times.[/yellow]\n")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Object", style="cyan")
    table.add_column("Transit Time", style="green")

    for obj_name, transit_time in sorted(transit_times.items(), key=lambda x: x[1]):
        time_str = format_local_time(transit_time, location.latitude, location.longitude)
        table.add_row(obj_name, time_str)

    output_console.print(table)
    output_console.print()


@app.command("compare-equipment", rich_help_panel="Planning Tools")
def show_equipment_comparison(
    object_name: str = typer.Argument(..., help="Object name (e.g., M31, Jupiter, Vega)"),
) -> None:
    """Compare what you can see with different equipment."""
    comparison = compare_equipment(object_name)

    console.print(f"\n[bold cyan]Equipment Comparison: {object_name}[/bold cyan]\n")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Equipment", style="cyan")
    table.add_column("Visible", justify="center")
    table.add_column("Notes")

    for equipment, data in comparison.items():
        visible_str = "[green]✓ Yes[/green]" if data.get("visible") else "[red]✗ No[/red]"
        notes = data.get("notes", "N/A")
        table.add_row(equipment.replace("_", " ").title(), visible_str, notes)

    console.print(table)
    console.print()


@app.command("time-slots", rich_help_panel="Planning Tools")
def show_time_slots(
    start_hour: int = typer.Option(20, "--start", "-s", help="Start hour (24-hour format, default: 20)"),
    end_hour: int = typer.Option(23, "--end", "-e", help="End hour (24-hour format, default: 23)"),
    interval: int = typer.Option(1, "--interval", "-i", help="Interval in hours (default: 1)"),
) -> None:
    """Show what to observe at different times during the night."""
    from celestron_nexstar.api.astronomy.solar_system import get_sun_info
    from celestron_nexstar.api.location.observer import get_observer_location

    location = get_observer_location()
    if not location:
        console.print("[red]Error: No observer location set.[/red]")
        return

    sun_info = get_sun_info(location.latitude, location.longitude)
    if not sun_info or not sun_info.sunset_time:
        console.print("[red]Error: Could not determine sunset time.[/red]")
        return

    # Create time slots
    sunset = sun_info.sunset_time
    if sunset.tzinfo is None:
        sunset = sunset.replace(tzinfo=UTC)

    # Get current time
    now = datetime.now(UTC)
    if sunset.tzinfo and now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    # Get today's date (use sunset date to ensure consistency)
    today_date = sunset.date()

    # Determine the start time:
    # 1. If current time is past start_hour, start from current hour (rounded up)
    # 2. Otherwise, start from start_hour
    # 3. But never start before sunset

    # Calculate desired start time based on start_hour
    desired_start = datetime.combine(today_date, datetime.min.time()).replace(
        hour=start_hour, minute=0, second=0, microsecond=0, tzinfo=UTC
    )

    # If we're already past the desired start hour, use current hour (rounded up)
    if now > desired_start:
        # Round current time up to next hour
        current_hour = now.hour
        if now.minute > 0 or now.second > 0:
            current_hour += 1
        if current_hour > 23:
            # Move to next day at midnight
            today_date += timedelta(days=1)
            current_hour = 0
        current = datetime.combine(today_date, datetime.min.time()).replace(
            hour=current_hour, minute=0, second=0, microsecond=0, tzinfo=UTC
        )
    else:
        current = desired_start

    # Ensure we don't start before sunset
    if current < sunset:
        # Round sunset up to next hour
        sunset_hour = sunset.hour
        if sunset.minute > 0 or sunset.second > 0:
            sunset_hour += 1
        if sunset_hour > 23:
            # Move to next day at midnight
            today_date += timedelta(days=1)
            sunset_hour = 0
        current = datetime.combine(today_date, datetime.min.time()).replace(
            hour=min(sunset_hour, 23), minute=0, second=0, microsecond=0, tzinfo=UTC
        )

    start_date = current.date()
    max_slots = 24  # Safety limit to prevent infinite loops

    time_slots: list[datetime] = []
    while len(time_slots) < max_slots:
        # Stop if we've moved to the next day
        if current.date() > start_date:
            break
        # Stop if we've gone past end_hour on the same day
        if current.hour > end_hour:
            break
        # Add the time slot
        time_slots.append(current)
        # Move to next interval
        current += timedelta(hours=interval)

    recommendations = asyncio.run(
        get_time_based_recommendations(time_slots, location.latitude, location.longitude, "telescope")
    )

    console.print("\n[bold cyan]Time-Based Recommendations[/bold cyan]\n")

    for time_slot, objects in recommendations.items():
        time_str = format_local_time(time_slot, location.latitude, location.longitude)
        console.print(f"[bold]{time_str}[/bold]")
        if objects:
            for obj in objects[:5]:  # Limit to 5 per time slot
                console.print(f"  • {obj.name}")
        else:
            console.print("  [dim]No specific recommendations[/dim]")
        console.print()

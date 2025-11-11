"""
'What's Visible Tonight?' command

Shows observing conditions and recommended objects for tonight.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import typer
from rich.console import Console
from rich.table import Table
from timezonefinder import TimezoneFinder

from ...api.observation_planner import ObservationPlanner, ObservingTarget
from ...cli.utils.export import FileConsole
from ...cli.utils.selection import select_from_list


app = typer.Typer(help="Telescope viewing commands")
console = Console()
_tz_finder = TimezoneFinder()


def _get_local_timezone(lat: float, lon: float) -> ZoneInfo | None:
    """Get timezone for a given latitude and longitude."""
    try:
        tz_name = _tz_finder.timezone_at(lat=lat, lng=lon)
        if tz_name:
            return ZoneInfo(tz_name)
    except Exception:
        pass
    return None


def _format_local_time(dt: datetime, lat: float, lon: float) -> str:
    """Format datetime in local timezone, falling back to UTC if timezone unavailable."""
    # Ensure datetime has timezone info
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    tz = _get_local_timezone(lat, lon)
    if tz:
        local_dt = dt.astimezone(tz)
        tz_name = local_dt.tzname() or (tz.key if hasattr(tz, "key") else "Local")
        return local_dt.strftime(f"%Y-%m-%d %I:%M %p {tz_name}")
    else:
        return dt.strftime("%Y-%m-%d %I:%M %p UTC")


@app.command("conditions", rich_help_panel="Conditions & Forecasts")
def show_conditions(
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Show tonight's observing conditions."""
    from ...cli.utils.export import create_file_console, export_to_text

    if export:
        if export_path:
            export_path_obj = Path(export_path)
        else:
            export_path_obj = _generate_export_filename("telescope", command="conditions")

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
        time_str = _format_local_time(conditions.timestamp, conditions.latitude, conditions.longitude)
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
                start_str = _format_local_time(window_start, conditions.latitude, conditions.longitude)
                end_str = _format_local_time(window_end, conditions.latitude, conditions.longitude)
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
                    time_str = _format_local_time(forecast.timestamp, conditions.latitude, conditions.longitude)
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
        output_console.print(f"  Naked Eye Limit: {lp.naked_eye_limiting_magnitude:.1f} mag")
        output_console.print(f"  Telescope Limit: {conditions.limiting_magnitude:.1f} mag")
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
            moonrise_str = _format_local_time(conditions.moonrise_time, conditions.latitude, conditions.longitude)
            # Extract time and AM/PM (parts[1] = time, parts[2] = AM/PM)
            parts = moonrise_str.split()
            moonrise_time = " ".join(parts[1:3]) if len(parts) >= 3 else moonrise_str
            output_console.print(f"  Moonrise: {moonrise_time}")
        if conditions.moonset_time:
            moonset_str = _format_local_time(conditions.moonset_time, conditions.latitude, conditions.longitude)
            # Extract time and AM/PM (parts[1] = time, parts[2] = AM/PM)
            parts = moonset_str.split()
            moonset_time = " ".join(parts[1:3]) if len(parts) >= 3 else moonset_str
            output_console.print(f"  Moonset: {moonset_time}")
        output_console.print()

        # Sun Events
        output_console.print("[bold]Sun Events:[/bold]")

        # Sunrise/Sunset
        if conditions.sunrise_time:
            sunrise_str = _format_local_time(conditions.sunrise_time, conditions.latitude, conditions.longitude)
            # Extract time and AM/PM (parts[1] = time, parts[2] = AM/PM)
            parts = sunrise_str.split()
            sunrise_time = " ".join(parts[1:3]) if len(parts) >= 3 else sunrise_str
            output_console.print(f"  Sunrise: {sunrise_time}")
        if conditions.sunset_time:
            sunset_str = _format_local_time(conditions.sunset_time, conditions.latitude, conditions.longitude)
            # Extract time and AM/PM (parts[1] = time, parts[2] = AM/PM)
            parts = sunset_str.split()
            sunset_time = " ".join(parts[1:3]) if len(parts) >= 3 else sunset_str
            output_console.print(f"  Sunset: {sunset_time}")

        # Golden Hour
        if conditions.golden_hour_evening_start and conditions.golden_hour_evening_end:
            gh_evening_start = _format_local_time(
                conditions.golden_hour_evening_start, conditions.latitude, conditions.longitude
            )
            gh_evening_end = _format_local_time(
                conditions.golden_hour_evening_end, conditions.latitude, conditions.longitude
            )
            # Extract time and AM/PM (parts[1] = time, parts[2] = AM/PM)
            parts_start = gh_evening_start.split()
            parts_end = gh_evening_end.split()
            gh_start_time = " ".join(parts_start[1:3]) if len(parts_start) >= 3 else gh_evening_start
            gh_end_time = " ".join(parts_end[1:3]) if len(parts_end) >= 3 else gh_evening_end
            output_console.print(f"  Golden Hour (evening): {gh_start_time} - {gh_end_time}")
        if conditions.golden_hour_morning_start and conditions.golden_hour_morning_end:
            gh_morning_start = _format_local_time(
                conditions.golden_hour_morning_start, conditions.latitude, conditions.longitude
            )
            gh_morning_end = _format_local_time(
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
            bh_evening_start = _format_local_time(
                conditions.blue_hour_evening_start, conditions.latitude, conditions.longitude
            )
            bh_evening_end = _format_local_time(
                conditions.blue_hour_evening_end, conditions.latitude, conditions.longitude
            )
            # Extract time and AM/PM (parts[1] = time, parts[2] = AM/PM)
            parts_start = bh_evening_start.split()
            parts_end = bh_evening_end.split()
            bh_start_time = " ".join(parts_start[1:3]) if len(parts_start) >= 3 else bh_evening_start
            bh_end_time = " ".join(parts_end[1:3]) if len(parts_end) >= 3 else bh_evening_end
            output_console.print(f"  Blue Hour (evening): {bh_start_time} - {bh_end_time}")
        if conditions.blue_hour_morning_start and conditions.blue_hour_morning_end:
            bh_morning_start = _format_local_time(
                conditions.blue_hour_morning_start, conditions.latitude, conditions.longitude
            )
            bh_morning_end = _format_local_time(
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
            at_evening_start = _format_local_time(
                conditions.astronomical_twilight_evening_start, conditions.latitude, conditions.longitude
            )
            at_evening_end = _format_local_time(
                conditions.astronomical_twilight_evening_end, conditions.latitude, conditions.longitude
            )
            # Extract time and AM/PM (parts[1] = time, parts[2] = AM/PM)
            parts_start = at_evening_start.split()
            parts_end = at_evening_end.split()
            at_start_time = " ".join(parts_start[1:3]) if len(parts_start) >= 3 else at_evening_start
            at_end_time = " ".join(parts_end[1:3]) if len(parts_end) >= 3 else at_evening_end
            output_console.print(f"  Astronomical Twilight (evening): {at_start_time} - {at_end_time}")
        if conditions.astronomical_twilight_morning_start and conditions.astronomical_twilight_morning_end:
            at_morning_start = _format_local_time(
                conditions.astronomical_twilight_morning_start, conditions.latitude, conditions.longitude
            )
            at_morning_end = _format_local_time(
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
            gc_start = _format_local_time(conditions.galactic_center_start, conditions.latitude, conditions.longitude)
            gc_end = _format_local_time(conditions.galactic_center_end, conditions.latitude, conditions.longitude)
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
    target_type: str | None = typer.Option(None, "--type", help="Filter by type (planets, deep_sky, messier, etc.)"),
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
    from ...cli.utils.export import create_file_console, export_to_text

    if export:
        if export_path:
            export_path_obj = Path(export_path)
        else:
            export_path_obj = _generate_export_filename("telescope", command="objects")

        file_console = create_file_console()
        _show_objects_content(file_console, target_type, limit, best_for_seeing)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_objects_content(console, target_type, limit, best_for_seeing)


def _show_objects_content(
    output_console: Console | FileConsole,
    target_type: str | None = None,
    limit: int = 20,
    best_for_seeing: bool = False,
) -> None:
    """Generate and display objects content."""
    try:
        planner = ObservationPlanner()
        conditions = planner.get_tonight_conditions()

        # Interactive selection if target_type not provided
        if target_type is None:
            target_type = _select_object_type_interactive()
            target_types = None if target_type is None else [ObservingTarget(target_type)]
        else:
            # Parse target types
            try:
                target_types = [ObservingTarget(target_type)]
            except ValueError:
                output_console.print(f"[red]Invalid target type: {target_type}[/red]")
                output_console.print(f"Valid types: {', '.join([t.value for t in ObservingTarget])}")
                raise typer.Exit(code=1) from None

        objects = planner.get_recommended_objects(
            conditions, target_types, max_results=limit, best_for_seeing=best_for_seeing
        )

        if not objects:
            output_console.print("[yellow]No objects currently visible with current conditions.[/yellow]")
            return

        # Create table
        table = Table(title=f"Recommended Objects for Tonight ({len(objects)} total)")
        table.add_column("Priority", style="cyan", width=8)
        table.add_column("Name", style="bold")
        table.add_column("Type", style="dim")
        table.add_column("Mag", justify="right")
        table.add_column("Alt", justify="right")
        table.add_column("Transit", style="dim")
        table.add_column("Moon Sep", justify="right", style="dim")
        table.add_column("Tips", style="dim", width=35)

        for obj_rec in objects[:limit]:
            priority_stars = "★" * (6 - obj_rec.priority)  # Invert: 1 = ★★★★★, 5 = ★
            obj = obj_rec.obj

            # Convert best viewing time to local timezone
            best_time = obj_rec.best_viewing_time
            if best_time.tzinfo is None:
                best_time = best_time.replace(tzinfo=UTC)

            tz = _get_local_timezone(conditions.latitude, conditions.longitude)
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

            table.add_row(
                priority_stars,
                obj.name,
                obj.object_type.value,
                f"{obj_rec.apparent_magnitude:.1f}" if obj_rec.apparent_magnitude else "-",
                f"{obj_rec.altitude:.0f}°",
                time_str,
                moon_sep_text,
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
    from ...cli.utils.export import create_file_console, export_to_text

    if export:
        if export_path:
            export_path_obj = Path(export_path)
        else:
            export_path_obj = _generate_export_filename("telescope", command="imaging")

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

        tz = _get_local_timezone(conditions.latitude, conditions.longitude)

        # Planetary Imaging - Seeing Forecast
        output_console.print("\n[bold cyan]Planetary Imaging - Seeing Forecast[/bold cyan]")
        output_console.print(
            "[dim]Seeing quality affects planetary detail capture. Excellent seeing (≥80) allows shorter exposures.[/dim]\n"
        )

        table_planetary = Table()
        table_planetary.add_column("Time", style="cyan", width=12)
        table_planetary.add_column("Seeing", justify="right", width=10)
        table_planetary.add_column("Quality", width=15)
        table_planetary.add_column("Wind", justify="right", width=8)
        table_planetary.add_column("Exposure", width=20)

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
        table_deepsky.add_column("Time", style="cyan", width=12)
        table_deepsky.add_column("Clouds", justify="right", width=10)
        table_deepsky.add_column("Transparency", width=15)
        table_deepsky.add_column("Humidity", justify="right", width=10)
        table_deepsky.add_column("Exposure", width=25)

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


def _generate_export_filename(
    viewing_type: str = "telescope", binocular_model: str | None = None, command: str = "tonight"
) -> Path:
    """Generate export filename based on viewing type, equipment, location, date, and command."""
    from datetime import datetime

    from ...api.observer import get_observer_location
    from ...api.optics import load_configuration

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

    # Generate filename based on viewing type
    if viewing_type == "telescope":
        config = load_configuration()
        if config:
            telescope_name = config.telescope.model.value.replace("nexstar_", "").replace("_", "")
        else:
            telescope_name = "no_telescope"
        filename = f"nexstar_{telescope_name}_{location_short}_{date_str}_{command}.txt"
    elif viewing_type == "binoculars":
        model_safe = (binocular_model or "10x50").replace("x", "x").replace("/", "_").lower()
        filename = f"binoculars_{model_safe}_{location_short}_{date_str}_{command}.txt"
    else:  # naked-eye
        filename = f"naked_eye_{location_short}_{date_str}_{command}.txt"

    return Path(filename)


@app.command("tonight", rich_help_panel="Viewing Guides")
def show_tonight(
    target_type: str | None = typer.Option(None, "--type", help="Filter by type (planets, deep_sky, messier, etc.)"),
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

    from ...cli.utils.export import create_file_console, export_to_text

    # Handle export
    if export:
        if export_path:
            # User provided a custom path
            export_path_obj = Path(export_path)
        else:
            # Auto-generate filename
            export_path_obj = _generate_export_filename("telescope", command="tonight")
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
    from ...api.optics import load_configuration

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
    target_type: str | None = typer.Option(None, "--type", help="Filter by type (planets, deep_sky, messier, etc.)"),
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
    from ...cli.utils.export import create_file_console, export_to_text

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("telescope", command="plan")

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
    object_types = list(ObservingTarget)

    # Object type descriptions
    descriptions = {
        ObservingTarget.PLANETS: "Solar system planets",
        ObservingTarget.MOON: "Earth's moon",
        ObservingTarget.DEEP_SKY: "Deep sky objects (galaxies, nebulae, clusters)",
        ObservingTarget.DOUBLE_STARS: "Double and multiple star systems",
        ObservingTarget.VARIABLE_STARS: "Variable stars",
        ObservingTarget.MESSIER: "Messier catalog objects",
        ObservingTarget.CALDWELL: "Caldwell catalog objects",
        ObservingTarget.NGC_IC: "NGC and IC catalog objects",
    }

    def display_object_type(ot: ObservingTarget) -> tuple[str, ...]:
        display_name = ot.value.replace("_", " ").title()
        description = descriptions.get(ot, "Object type")
        return (display_name, description)

    selected = select_from_list(
        object_types,
        title="Select Object Type (or 'q' to show all)",
        display_func=display_object_type,
        headers=["Object Type", "Description"],
    )

    return selected.value if selected else None

"""
'What's Visible Tonight?' command

Shows observing conditions and recommended objects for tonight.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import typer
from rich.console import Console
from rich.table import Table
from timezonefinder import TimezoneFinder

from ...api.observation_planner import ObservationPlanner, ObservingTarget


app = typer.Typer(help="Tonight's observing plan")
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
        return local_dt.strftime(f"%Y-%m-%d %H:%M {tz_name}")
    else:
        return dt.strftime("%Y-%m-%d %H:%M UTC")


@app.command("conditions")
def show_conditions() -> None:
    """Show tonight's observing conditions."""
    try:
        planner = ObservationPlanner()
        conditions = planner.get_tonight_conditions()

        # Display header
        location_name = conditions.location_name or "Current Location"
        console.print(f"\n[bold cyan]Observing Conditions for {location_name}[/bold cyan]")
        time_str = _format_local_time(conditions.timestamp, conditions.latitude, conditions.longitude)
        console.print(f"[dim]{time_str}[/dim]\n")

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

        console.print(f"Overall Quality (general conditions): {quality_text} ({quality * 100:.0f}/100)\n")

        # Weather
        weather = conditions.weather
        console.print("[bold]Weather:[/bold]")
        if weather.cloud_cover_percent is not None:
            console.print(f"  Cloud Cover: {weather.cloud_cover_percent:.0f}%")
        if weather.temperature_c is not None:
            # API returns Fahrenheit when units=imperial (despite field name)
            # Display directly as Fahrenheit
            console.print(f"  Temperature: {weather.temperature_c:.1f}°F")
        if weather.dew_point_f is not None:
            console.print(f"  Dew Point: {weather.dew_point_f:.1f}°F")
        if weather.humidity_percent is not None:
            console.print(f"  Humidity: {weather.humidity_percent:.0f}%")
        if weather.wind_speed_ms is not None:
            # API returns mph when units=imperial (despite field name)
            # Display directly as mph
            console.print(f"  Wind Speed: {weather.wind_speed_ms:.1f} mph")
        if weather.visibility_km is not None:
            # API returns visibility in meters, convert to miles
            visibility_mi = weather.visibility_km * 0.621371
            console.print(f"  Visibility: {visibility_mi:.1f} mi")
        if weather.condition:
            console.print(f"  Condition: {weather.condition}")
        if weather.error:
            console.print(f"  [yellow]Warning: {weather.error}[/yellow]")
        console.print()

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

        console.print("[bold]Seeing Conditions[/bold] (atmospheric steadiness for image sharpness):")
        console.print(f"  Seeing: {seeing_text} ({seeing:.0f}/100)")

        # Seeing-based recommendations
        if seeing >= 80:
            console.print("  [dim]✓ Ideal for: High-magnification planetary detail, splitting close doubles, faint deep-sky[/dim]")
        elif seeing >= 60:
            console.print("  [dim]✓ Good for: Planetary observing, bright deep-sky, double stars[/dim]")
        elif seeing >= 40:
            console.print("  [dim]✓ Suitable for: Bright objects, low-power deep-sky, wide doubles[/dim]")
        else:
            console.print("  [dim]⚠ Limited to: Bright planets, bright clusters, low-power viewing[/dim]")

        # Best seeing time window
        if conditions.best_seeing_window_start and conditions.best_seeing_window_end:
            start_str = _format_local_time(conditions.best_seeing_window_start, conditions.latitude, conditions.longitude)
            end_str = _format_local_time(conditions.best_seeing_window_end, conditions.latitude, conditions.longitude)
            # Extract just the time portion
            start_time = start_str.split()[-2] if " " in start_str else start_str
            end_time = end_str.split()[-2] if " " in end_str else end_str
            console.print(f"  [dim]Best seeing window: {start_time} - {end_time}[/dim]")

        # Hourly seeing forecast (if available - uses free Open-Meteo API)
        if conditions.hourly_seeing_forecast:
            console.print()
            console.print("[bold]Hourly Seeing Forecast:[/bold]")
            
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
                    end_time = sunrise
                    if end_time < now_utc:
                        end_time = sunrise + timedelta(days=1)
                    for forecast in conditions.hourly_seeing_forecast:
                        forecast_ts = forecast.timestamp
                        if forecast_ts.tzinfo is None:
                            forecast_ts = forecast_ts.replace(tzinfo=UTC)
                        elif forecast_ts.tzinfo != UTC:
                            forecast_ts = forecast_ts.astimezone(UTC)
                        if now_utc <= forecast_ts <= end_time:
                            forecast_to_show.append(forecast)
                
                # Sort by timestamp to ensure chronological order
                forecast_to_show.sort(key=lambda f: f.timestamp if f.timestamp.tzinfo else f.timestamp.replace(tzinfo=UTC))
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
                forecast_to_show.sort(key=lambda f: f.timestamp if f.timestamp.tzinfo else f.timestamp.replace(tzinfo=UTC))
            
            if forecast_to_show:
                for forecast in forecast_to_show:
                    time_str = _format_local_time(forecast.timestamp, conditions.latitude, conditions.longitude)
                    time_only = time_str.split()[-2] if " " in time_str else time_str

                    # Color code by seeing score
                    if forecast.seeing_score >= 80:
                        score_color = "[green]"
                    elif forecast.seeing_score >= 40:
                        score_color = "[yellow]"
                    else:
                        score_color = "[red]"

                    console.print(
                        f"  {time_only}: {score_color}{forecast.seeing_score:.0f}/100[/] "
                        f"[dim]({forecast.cloud_cover_percent or 0:.0f}% clouds, "
                        f"{forecast.wind_speed_mph or 0:.1f} mph wind)[/]"
                    )
            else:
                console.print("  [dim]No forecast data available for observing window[/dim]")
        console.print()

        # Light Pollution
        lp = conditions.light_pollution
        console.print("[bold]Sky Darkness:[/bold]")
        console.print(f"  Bortle Class: {lp.bortle_class.value} ({lp.description})")
        console.print(f"  SQM: {lp.sqm_value:.2f} mag/arcsec²")
        console.print(f"  Naked Eye Limit: {lp.naked_eye_limiting_magnitude:.1f} mag")
        console.print(f"  Telescope Limit: {conditions.limiting_magnitude:.1f} mag")
        console.print()

        # Moon
        console.print("[bold]Moon:[/bold]")
        if conditions.moon_phase:
            console.print(f"  Phase: {conditions.moon_phase}")
        console.print(f"  Illumination: {conditions.moon_illumination * 100:.0f}%")
        console.print(f"  Altitude: {conditions.moon_altitude:.1f}°")
        if conditions.moon_altitude < 0:
            console.print("  [dim]Below horizon[/dim]")
        console.print()

        # Sun and Moon Events
        console.print("[bold]Sun & Moon Events (Today):[/bold]")
        
        # Sunrise/Sunset
        if conditions.sunrise_time:
            sunrise_str = _format_local_time(conditions.sunrise_time, conditions.latitude, conditions.longitude)
            sunrise_time = sunrise_str.split()[-2] if " " in sunrise_str else sunrise_str
            console.print(f"  Sunrise: {sunrise_time}")
        if conditions.sunset_time:
            sunset_str = _format_local_time(conditions.sunset_time, conditions.latitude, conditions.longitude)
            sunset_time = sunset_str.split()[-2] if " " in sunset_str else sunset_str
            console.print(f"  Sunset: {sunset_time}")
        
        # Moonrise/Moonset
        if conditions.moonrise_time:
            moonrise_str = _format_local_time(conditions.moonrise_time, conditions.latitude, conditions.longitude)
            moonrise_time = moonrise_str.split()[-2] if " " in moonrise_str else moonrise_str
            console.print(f"  Moonrise: {moonrise_time}")
        if conditions.moonset_time:
            moonset_str = _format_local_time(conditions.moonset_time, conditions.latitude, conditions.longitude)
            moonset_time = moonset_str.split()[-2] if " " in moonset_str else moonset_str
            console.print(f"  Moonset: {moonset_time}")
        
        # Golden Hour
        if conditions.golden_hour_evening_start and conditions.golden_hour_evening_end:
            gh_evening_start = _format_local_time(conditions.golden_hour_evening_start, conditions.latitude, conditions.longitude)
            gh_evening_end = _format_local_time(conditions.golden_hour_evening_end, conditions.latitude, conditions.longitude)
            gh_start_time = gh_evening_start.split()[-2] if " " in gh_evening_start else gh_evening_start
            gh_end_time = gh_evening_end.split()[-2] if " " in gh_evening_end else gh_evening_end
            console.print(f"  Golden Hour (evening): {gh_start_time} - {gh_end_time}")
        if conditions.golden_hour_morning_start and conditions.golden_hour_morning_end:
            gh_morning_start = _format_local_time(conditions.golden_hour_morning_start, conditions.latitude, conditions.longitude)
            gh_morning_end = _format_local_time(conditions.golden_hour_morning_end, conditions.latitude, conditions.longitude)
            gh_start_time = gh_morning_start.split()[-2] if " " in gh_morning_start else gh_morning_start
            gh_end_time = gh_morning_end.split()[-2] if " " in gh_morning_end else gh_morning_end
            console.print(f"  Golden Hour (morning): {gh_start_time} - {gh_end_time}")
        
        # Blue Hour
        if conditions.blue_hour_evening_start and conditions.blue_hour_evening_end:
            bh_evening_start = _format_local_time(conditions.blue_hour_evening_start, conditions.latitude, conditions.longitude)
            bh_evening_end = _format_local_time(conditions.blue_hour_evening_end, conditions.latitude, conditions.longitude)
            bh_start_time = bh_evening_start.split()[-2] if " " in bh_evening_start else bh_evening_start
            bh_end_time = bh_evening_end.split()[-2] if " " in bh_evening_end else bh_evening_end
            console.print(f"  Blue Hour (evening): {bh_start_time} - {bh_end_time}")
        if conditions.blue_hour_morning_start and conditions.blue_hour_morning_end:
            bh_morning_start = _format_local_time(conditions.blue_hour_morning_start, conditions.latitude, conditions.longitude)
            bh_morning_end = _format_local_time(conditions.blue_hour_morning_end, conditions.latitude, conditions.longitude)
            bh_start_time = bh_morning_start.split()[-2] if " " in bh_morning_start else bh_morning_start
            bh_end_time = bh_morning_end.split()[-2] if " " in bh_morning_end else bh_morning_end
            console.print(f"  Blue Hour (morning): {bh_start_time} - {bh_end_time}")
        
        console.print()

        # Recommendations
        if conditions.recommendations:
            console.print("[bold green]Recommendations:[/bold green]")
            for rec in conditions.recommendations:
                console.print(f"  ✓ {rec}")
            console.print()

        # Warnings
        if conditions.warnings:
            console.print("[bold yellow]Warnings:[/bold yellow]")
            for warn in conditions.warnings:
                console.print(f"  ⚠ {warn}")
            console.print()

    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from None
    except Exception as e:
        console.print(f"[red]Error getting conditions:[/red] {e}")
        import traceback

        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from None


@app.command("objects")
def show_objects(
    target_type: str | None = typer.Option(None, "--type", help="Filter by type (planets, deep_sky, messier, etc.)"),
    limit: int = typer.Option(20, "--limit", help="Maximum objects to show"),
    best_for_seeing: bool = typer.Option(False, "--best-for-seeing", help="Show only objects ideal for current seeing conditions"),
) -> None:
    """Show recommended objects for tonight."""
    try:
        planner = ObservationPlanner()
        conditions = planner.get_tonight_conditions()

        # Parse target types
        target_types = None
        if target_type:
            try:
                target_types = [ObservingTarget(target_type)]
            except ValueError:
                console.print(f"[red]Invalid target type: {target_type}[/red]")
                console.print(f"Valid types: {', '.join([t.value for t in ObservingTarget])}")
                raise typer.Exit(code=1) from None

        objects = planner.get_recommended_objects(conditions, target_types, max_results=limit, best_for_seeing=best_for_seeing)

        if not objects:
            console.print("[yellow]No objects currently visible with current conditions.[/yellow]")
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
                time_str = local_time.strftime("%H:%M")
            else:
                time_str = best_time.strftime("%H:%M UTC")

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
                obj.common_name or obj.name,
                obj.object_type.value,
                f"{obj_rec.apparent_magnitude:.1f}" if obj_rec.apparent_magnitude else "-",
                f"{obj_rec.altitude:.0f}°",
                time_str,
                moon_sep_text,
                tips_text,
            )

        console.print(table)
        console.print(f"\n[dim]Showing top {min(limit, len(objects))} of {len(objects)} visible objects[/dim]")

    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from None
    except Exception as e:
        console.print(f"[red]Error getting objects:[/red] {e}")
        import traceback

        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from None


@app.command("plan")
def show_plan(
    target_type: str | None = typer.Option(None, "--type", help="Filter by type (planets, deep_sky, messier, etc.)"),
    limit: int = typer.Option(20, "--limit", help="Maximum objects to show"),
    best_for_seeing: bool = typer.Option(False, "--best-for-seeing", help="Show only objects ideal for current seeing conditions"),
) -> None:
    """Show complete observing plan for tonight (conditions + objects)."""
    show_conditions()
    console.print("\n" + "=" * 80 + "\n")
    show_objects(target_type=target_type, limit=limit, best_for_seeing=best_for_seeing)

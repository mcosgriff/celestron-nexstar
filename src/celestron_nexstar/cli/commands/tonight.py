"""
'What's Visible Tonight?' command

Shows observing conditions and recommended objects for tonight.
"""

from datetime import UTC, datetime
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

        console.print(f"Overall Quality: {quality_text} ({quality * 100:.0f}/100)\n")

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

        console.print("[bold]Seeing Conditions:[/bold]")
        console.print(f"  Seeing: {seeing_text} ({seeing:.0f}/100)")
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

        objects = planner.get_recommended_objects(conditions, target_types, max_results=limit)

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
        table.add_column("Best Time", style="dim")
        table.add_column("Reason", style="dim")

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

            table.add_row(
                priority_stars,
                obj.common_name or obj.name,
                obj.object_type.value,
                f"{obj_rec.apparent_magnitude:.1f}" if obj_rec.apparent_magnitude else "-",
                f"{obj_rec.altitude:.0f}°",
                time_str,
                obj_rec.reason,
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
) -> None:
    """Show complete observing plan for tonight (conditions + objects)."""
    show_conditions()
    console.print("\n" + "=" * 80 + "\n")
    show_objects(target_type=target_type, limit=limit)

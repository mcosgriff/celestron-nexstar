"""
Naked-Eye Viewing Commands

Shows what's visible tonight with the naked eye including ISS passes,
constellations, asterisms, and meteor showers. Perfect for stargazing
without any equipment.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import typer
from rich.console import Console
from rich.table import Table
from timezonefinder import TimezoneFinder

from ...api.compass import azimuth_to_compass_8point, format_object_path
from ...api.constellations import get_visible_asterisms, get_visible_constellations
from ...api.iss_tracking import get_iss_passes_cached
from ...api.observer import get_observer_location
from ...api.meteor_showers import get_active_showers, get_peak_showers, get_radiant_position
from ...api.models import get_db_session
from ...api.sun_moon import calculate_sun_times


app = typer.Typer(help="Naked-eye viewing commands")
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
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    tz = _get_local_timezone(lat, lon)
    if tz:
        local_dt = dt.astimezone(tz)
        return local_dt.strftime("%I:%M %p")
    else:
        return dt.strftime("%I:%M %p UTC")


@app.command("tonight")
def show_tonight() -> None:
    """
    Show what's visible tonight with the naked eye.

    Displays ISS passes, visible constellations, asterisms, and active meteor showers
    perfect for stargazing without any equipment. Uses your configured location.
    """
    try:
        # Get location
        location = get_observer_location()
        if not location:
            console.print("[red]Error:[/red] No location configured. Use 'nexstar location set' first.")
            raise typer.Exit(code=1)

        lat, lon = location.latitude, location.longitude
        location_name = location.name or f"{lat:.2f}°, {lon:.2f}°"

        # Get current time and sunset/sunrise
        now = datetime.now(UTC)
        sun_times = calculate_sun_times(lat, lon, now)
        sunset = sun_times["sunset"]
        sunrise = sun_times["sunrise"]

        # Display header
        console.print(f"\n[bold cyan]Naked-Eye Stargazing for {location_name}[/bold cyan]")
        console.print(f"[dim]Sunset: {_format_local_time(sunset, lat, lon)} | Sunrise: {_format_local_time(sunrise, lat, lon)}[/dim]\n")

        # ISS Passes
        console.print("[bold green]ISS Visible Passes[/bold green]")
        console.print("[dim]Bright satellite passes visible without equipment[/dim]\n")

        with get_db_session() as db:
            iss_passes = get_iss_passes_cached(lat, lon, start_time=now, days=7, min_altitude_deg=20.0, db_session=db)

        if iss_passes:
            table_iss = Table()
            table_iss.add_column("Date", style="cyan")
            table_iss.add_column("Rise Time", style="green")
            table_iss.add_column("Max Alt", justify="right")
            table_iss.add_column("Path", style="dim", width=35)
            table_iss.add_column("Duration", justify="right")
            table_iss.add_column("Quality")

            shown_count = 0
            for iss_pass in iss_passes:
                # Only show sunlit passes that are clearly visible to naked eye (>30° altitude)
                if not iss_pass.is_visible or iss_pass.max_altitude_deg < 30:
                    continue

                shown_count += 1
                if shown_count > 10:  # Limit to 10 best passes
                    break

                # Format date and time
                rise_time_str = _format_local_time(iss_pass.rise_time, lat, lon)
                date_str = iss_pass.rise_time.strftime("%a %b %d")

                # Format path
                path = format_object_path(
                    iss_pass.rise_azimuth_deg,
                    iss_pass.max_azimuth_deg,
                    iss_pass.max_altitude_deg,
                    iss_pass.set_azimuth_deg,
                )

                # Duration in minutes
                duration_min = iss_pass.duration_seconds // 60

                # Quality color
                quality = iss_pass.quality_rating
                if quality == "Excellent":
                    quality_text = "[green]Excellent[/green]"
                elif quality == "Very Good":
                    quality_text = "[green]Very Good[/green]"
                elif quality == "Good":
                    quality_text = "[yellow]Good[/yellow]"
                else:
                    quality_text = "[dim]Fair[/dim]"

                table_iss.add_row(
                    date_str,
                    rise_time_str,
                    f"{iss_pass.max_altitude_deg:.0f}°",
                    path,
                    f"{duration_min}m {iss_pass.duration_seconds % 60}s",
                    quality_text,
                )

            if shown_count > 0:
                console.print(table_iss)
                console.print("[dim]Only showing passes with max altitude >30° for best naked-eye visibility[/dim]")
            else:
                console.print("[yellow]No excellent naked-eye ISS passes in the next 7 days[/yellow]")
                console.print("[dim]Try lowering altitude requirement or check back later[/dim]")
        else:
            console.print("[yellow]No visible ISS passes in the next 7 days[/yellow]")

        console.print()

        # Meteor Showers
        console.print("[bold green]Active Meteor Showers[/bold green]")
        console.print("[dim]Best observed with naked eye - no equipment needed![/dim]\n")

        active_showers = get_active_showers(now)
        peak_showers = get_peak_showers(now, tolerance_days=3)

        if active_showers:
            table_showers = Table()
            table_showers.add_column("Shower", style="bold")
            table_showers.add_column("Status", style="cyan")
            table_showers.add_column("ZHR", justify="right")
            table_showers.add_column("Radiant", style="dim")
            table_showers.add_column("Best Time", style="dim")

            for shower in active_showers:
                # Check if at peak
                is_peak = shower in peak_showers
                status = "[green]At Peak[/green]" if is_peak else "Active"

                # Calculate radiant position at midnight
                midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
                if midnight < now:
                    midnight = midnight.replace(day=midnight.day + 1)
                alt, az = get_radiant_position(shower, lat, lon, midnight)

                radiant_dir = azimuth_to_compass_8point(az)
                radiant_text = f"{radiant_dir}, {alt:.0f}° high"

                # Best viewing time
                best_time = "After midnight" if alt > 30 else "Late evening"

                table_showers.add_row(
                    shower.name,
                    status,
                    str(shower.zhr_peak),
                    radiant_text,
                    best_time,
                )

            console.print(table_showers)
            console.print("[dim]ZHR = Zenithal Hourly Rate (meteors per hour under perfect conditions)[/dim]")
            console.print("[dim]Don't stare at the radiant - meteors appear throughout the sky[/dim]")
            console.print("[dim]Best viewing: Lie back, look at dark sky, give eyes 20+ minutes to adapt[/dim]")
        else:
            console.print("[yellow]No major meteor showers currently active[/yellow]")

        console.print()

        # Visible Constellations
        console.print("[bold green]Prominent Constellations (Tonight)[/bold green]")
        console.print("[dim]Easy-to-spot constellations for beginners[/dim]\n")

        # Calculate for midnight
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if midnight < now:
            midnight = midnight.replace(day=midnight.day + 1)

        visible_constellations = get_visible_constellations(lat, lon, midnight, min_altitude_deg=30.0)

        if visible_constellations:
            table_const = Table()
            table_const.add_column("Constellation", style="bold")
            table_const.add_column("Direction", justify="right")
            table_const.add_column("Altitude", justify="right")
            table_const.add_column("Key Star", style="dim")
            table_const.add_column("What to Look For", style="dim", width=35)

            for constellation, alt, az in visible_constellations[:10]:  # Top 10
                direction = azimuth_to_compass_8point(az)

                # Key star with magnitude
                key_star = f"{constellation.brightest_star} ({constellation.magnitude:.1f})"

                # Truncate description if too long
                description = constellation.description
                if len(description) > 33:
                    description = description[:30] + "..."

                table_const.add_row(
                    constellation.name,
                    direction,
                    f"{alt:.0f}°",
                    key_star,
                    description,
                )

            console.print(table_const)
        else:
            console.print("[yellow]No prominent constellations currently visible[/yellow]")

        console.print()

        # Visible Asterisms
        console.print("[bold green]Star Patterns to Find (Asterisms)[/bold green]")
        console.print("[dim]Famous patterns that are easy to recognize[/dim]\n")

        visible_asterisms = get_visible_asterisms(lat, lon, midnight, min_altitude_deg=30.0)

        if visible_asterisms:
            # Group by familiarity/importance
            priority_asterisms = ["Big Dipper", "Orion's Belt", "Summer Triangle", "Winter Triangle", "Pleiades"]

            table_ast = Table()
            table_ast.add_column("Pattern", style="bold")
            table_ast.add_column("Direction", justify="right")
            table_ast.add_column("Altitude", justify="right")
            table_ast.add_column("How to Find It", style="dim", width=45)

            # Show priority asterisms first
            shown = set()
            for asterism, alt, az in visible_asterisms:
                if asterism.name in priority_asterisms and asterism.name not in shown:
                    direction = azimuth_to_compass_8point(az)

                    # Truncate description if too long
                    description = asterism.description
                    if len(description) > 43:
                        description = description[:40] + "..."

                    table_ast.add_row(
                        asterism.name,
                        direction,
                        f"{alt:.0f}°",
                        description,
                    )
                    shown.add(asterism.name)

            # Then show others
            for asterism, alt, az in visible_asterisms[:10]:
                if asterism.name not in shown:
                    direction = azimuth_to_compass_8point(az)

                    description = asterism.description
                    if len(description) > 43:
                        description = description[:40] + "..."

                    table_ast.add_row(
                        asterism.name,
                        direction,
                        f"{alt:.0f}°",
                        description,
                    )
                    shown.add(asterism.name)

            console.print(table_ast)
        else:
            console.print("[yellow]No prominent asterisms currently visible[/yellow]")

        console.print("\n[bold cyan]Stargazing Tips (No Equipment Needed):[/bold cyan]")
        console.print("  • Find a dark location away from city lights")
        console.print("  • Allow 20-30 minutes for your eyes to fully adapt to darkness")
        console.print("  • Avoid looking at phones or bright lights (use red light if needed)")
        console.print("  • Lie back on a blanket or reclining chair for comfortable viewing")
        console.print("  • Start with bright stars and asterisms, then find fainter objects")
        console.print("  • Use averted vision: look slightly to the side to see fainter objects")
        console.print("  • Best viewing: New moon or when moon has set\n")

    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from None
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        import traceback

        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from None

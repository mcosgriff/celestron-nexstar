"""
Naked-Eye Viewing Commands

Shows what's visible tonight with the naked eye including ISS passes,
constellations, asterisms, and meteor showers. Perfect for stargazing
without any equipment.
"""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import typer
from rich.console import Console
from rich.table import Table
from timezonefinder import TimezoneFinder

from ...api.catalogs import CelestialObject
from ...api.compass import azimuth_to_compass_8point, format_object_path
from ...api.constellations import get_prominent_constellations, get_visible_asterisms, get_visible_constellations
from ...api.database import get_database
from ...api.enums import CelestialObjectType
from ...api.iss_tracking import get_iss_passes_cached
from ...api.meteor_showers import get_active_showers, get_peak_showers, get_radiant_position
from ...api.models import get_db_session
from ...api.observer import get_observer_location
from ...api.sun_moon import calculate_sun_times
from ...api.utils import ra_dec_to_alt_az
from ...cli.utils.export import FileConsole, create_file_console, export_to_text


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


def _get_current_season(dt: datetime) -> str:
    """
    Get the current season based on date.

    Args:
        dt: Datetime to check

    Returns:
        Season name: "Spring", "Summer", "Fall", or "Winter"
    """
    month = dt.month

    # Simple month-based season determination
    # Spring: Mar, Apr, May
    # Summer: Jun, Jul, Aug
    # Fall: Sep, Oct, Nov
    # Winter: Dec, Jan, Feb
    if month in (3, 4, 5):
        return "Spring"
    elif month in (6, 7, 8):
        return "Summer"
    elif month in (9, 10, 11):
        return "Fall"
    else:  # 12, 1, 2
        return "Winter"


def _get_visible_stars(
    lat: float,
    lon: float,
    observation_time: datetime,
    min_altitude_deg: float,
    max_magnitude: float = 6.0,
    limit: int = 20,
) -> list[tuple[CelestialObject, float, float]]:
    """
    Get visible stars above horizon at given time.

    Queries the database directly - all star data comes from the database,
    not from YAML files. Stars should be imported via 'nexstar data import yale_bsc'
    or 'nexstar data import custom' before using this command.

    Args:
        lat: Observer latitude
        lon: Observer longitude
        observation_time: Time of observation
        min_altitude_deg: Minimum altitude for visibility
        max_magnitude: Maximum magnitude (fainter limit)
        limit: Maximum number of stars to return

    Returns:
        List of (star_object, altitude_deg, azimuth_deg) tuples sorted by magnitude (brightest first)
    """
    db = get_database()

    # Query stars directly from database (not from YAML)
    # Stars must be imported first via: nexstar data import yale_bsc
    stars = db.filter_objects(
        object_type=CelestialObjectType.STAR,
        max_magnitude=max_magnitude,
        limit=500,  # Get more than we need to filter by altitude
    )

    visible = []
    for star in stars:
        if star.magnitude is None:
            continue

        # Calculate altitude and azimuth
        alt, az = ra_dec_to_alt_az(
            star.ra_hours,
            star.dec_degrees,
            lat,
            lon,
            observation_time,
        )

        if alt >= min_altitude_deg:
            visible.append((star, alt, az))

    # Sort by magnitude (brightest first), then by altitude
    visible.sort(key=lambda x: (x[0].magnitude or 99, -x[1]))

    return visible[:limit]


def _generate_export_filename(command: str = "tonight") -> Path:
    """Generate export filename for naked-eye viewing."""
    from datetime import datetime

    from ...api.observer import get_observer_location

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

    # Generate filename
    filename = f"naked_eye_{location_short}_{date_str}_{command}.txt"
    return Path(filename)


@app.command("tonight")
def show_tonight(
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """
    Show what's visible tonight with the naked eye.

    Displays ISS passes, visible constellations, asterisms, and active meteor showers
    perfect for stargazing without any equipment. Uses your configured location.
    """
    from pathlib import Path

    # Handle export
    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("tonight")
        # Create file console for export (StringIO)
        file_console = create_file_console()
        # Use file console for output
        _show_tonight_content(file_console)
        # Get content from StringIO
        content = file_console.file.getvalue()
        file_console.file.close()

        # Export to text file
        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    # Normal console output
    _show_tonight_content(console)


def _show_tonight_content(output_console: Console | FileConsole) -> None:
    """
    Generate and display tonight viewing content.

    Args:
        output_console: Console to write output to (can be file console for export)
    """
    try:
        # Get location
        location = get_observer_location()
        if not location:
            output_console.print("[red]Error:[/red] No location configured. Use 'nexstar location set' first.")
            raise typer.Exit(code=1)

        lat, lon = location.latitude, location.longitude
        location_name = location.name or f"{lat:.2f}°, {lon:.2f}°"

        # Get current time and sunset/sunrise
        now = datetime.now(UTC)
        sun_times = calculate_sun_times(lat, lon, now)
        sunset = sun_times["sunset"]
        sunrise = sun_times["sunrise"]

        # Display header with identification
        output_console.print(f"\n[bold cyan]Naked-Eye Stargazing for {location_name}[/bold cyan]")
        output_console.print("[dim]Viewing Method: Naked-eye (no equipment needed)[/dim]")
        output_console.print("[dim]Limiting Magnitude: ~6.0 (varies with sky darkness and dark adaptation)[/dim]")
        sunset_str = _format_local_time(sunset, lat, lon) if sunset else "—"
        sunrise_str = _format_local_time(sunrise, lat, lon) if sunrise else "—"
        output_console.print(f"[dim]Sunset: {sunset_str} | Sunrise: {sunrise_str}[/dim]\n")

        # ISS Passes
        output_console.print("[bold green]ISS Visible Passes[/bold green]")
        output_console.print("[dim]Bright satellite passes visible without equipment[/dim]\n")

        with get_db_session() as db:
            iss_passes = asyncio.run(
                get_iss_passes_cached(lat, lon, start_time=now, days=7, min_altitude_deg=20.0, db_session=db)
            )

        if iss_passes:
            table_iss = Table()
            table_iss.add_column("Date", style="cyan")
            table_iss.add_column("Rise Time", style="green")
            table_iss.add_column("Max Alt", justify="right")
            table_iss.add_column("Path", style="dim")  # No width - will expand to fill space
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
                output_console.print(table_iss)
                output_console.print(
                    "[dim]Only showing passes with max altitude >30° for best naked-eye visibility[/dim]"
                )
            else:
                output_console.print("[yellow]No excellent naked-eye ISS passes in the next 7 days[/yellow]")
                output_console.print("[dim]Try lowering altitude requirement or check back later[/dim]")
        else:
            output_console.print("[yellow]No visible ISS passes in the next 7 days[/yellow]")

        output_console.print()

        # Meteor Showers
        output_console.print("[bold green]Active Meteor Showers[/bold green]")
        output_console.print("[dim]Best observed with naked eye - no equipment needed![/dim]\n")

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

            output_console.print(table_showers)
            output_console.print("[dim]ZHR = Zenithal Hourly Rate (meteors per hour under perfect conditions)[/dim]")
            output_console.print("[dim]Don't stare at the radiant - meteors appear throughout the sky[/dim]")
            output_console.print("[dim]Best viewing: Lie back, look at dark sky, give eyes 20+ minutes to adapt[/dim]")
        else:
            output_console.print("[yellow]No major meteor showers currently active[/yellow]")

        output_console.print()

        # Visible Constellations
        output_console.print("[bold green]Prominent Constellations (Tonight)[/bold green]")
        output_console.print("[dim]Easy-to-spot constellations for beginners[/dim]\n")

        # Calculate for midnight
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if midnight < now:
            midnight = midnight.replace(day=midnight.day + 1)

        # Get visible constellations (using lower threshold to catch more)
        visible_constellations = get_visible_constellations(lat, lon, midnight, min_altitude_deg=15.0)

        # Track which constellations have low centers (below normal viewing threshold)
        # Normal threshold is 30° for naked-eye
        normal_threshold = 30.0
        low_altitude_constellations = set()

        # Mark constellations already in the list that are below normal threshold
        for constellation, alt, _az in visible_constellations:
            if alt < normal_threshold:
                low_altitude_constellations.add(constellation.name)

        # Also include constellations that have visible stars, even if center is low
        # Get visible stars first to find their constellations
        visible_stars_for_const = _get_visible_stars(
            lat, lon, midnight, min_altitude_deg=30.0, max_magnitude=6.0, limit=100
        )

        # Find unique constellations from visible stars
        constellations_with_stars = set()
        for star, _, _ in visible_stars_for_const:
            if star.constellation:
                constellations_with_stars.add(star.constellation)

        # Add constellations that have visible stars but aren't already in the list
        all_prominent = get_prominent_constellations()
        existing_names = {c.name for c, _, _ in visible_constellations}

        for constellation in all_prominent:
            if constellation.name in constellations_with_stars and constellation.name not in existing_names:
                # Calculate altitude for this constellation
                alt, az = ra_dec_to_alt_az(
                    constellation.ra_hours,
                    constellation.dec_degrees,
                    lat,
                    lon,
                    midnight,
                )
                # Include even if slightly below threshold (as long as it has visible stars)
                if alt >= 0:  # Above horizon
                    visible_constellations.append((constellation, alt, az))
                    # Mark if center is below normal threshold
                    if alt < normal_threshold:
                        low_altitude_constellations.add(constellation.name)

        # Re-sort by altitude
        visible_constellations.sort(key=lambda x: x[1], reverse=True)

        # Separate into fully visible and partially visible
        fully_visible = [
            (c, alt, az) for c, alt, az in visible_constellations if c.name not in low_altitude_constellations
        ]
        partially_visible = [
            (c, alt, az) for c, alt, az in visible_constellations if c.name in low_altitude_constellations
        ]

        if fully_visible:
            current_season = _get_current_season(now)

            table_const = Table()
            table_const.add_column("Constellation", style="bold")
            table_const.add_column("Direction", justify="right")
            table_const.add_column("Altitude", justify="right")
            table_const.add_column("Key Star", style="dim")
            table_const.add_column("What to Look For", style="dim")  # No width - will expand to fill space

            for constellation, alt, az in fully_visible[:10]:  # Top 10
                direction = azimuth_to_compass_8point(az)

                # Key star with magnitude
                key_star = f"{constellation.brightest_star} ({constellation.magnitude:.1f})"

                # Add season note if out of season
                description = constellation.description
                if constellation.season != current_season:
                    description = f"{description} (best in {constellation.season.lower()}, visible out of season)"

                table_const.add_row(
                    constellation.name,
                    direction,
                    f"{alt:.0f}°",
                    key_star,
                    description,
                )

            output_console.print(table_const)
            output_console.print(
                "[dim]💡 Tip: Estimate altitude with your hand - hold arm outstretched: fist = 10°, thumb = 2°, pinky = 1°[/dim]"
            )
        else:
            output_console.print("[yellow]No prominent constellations currently visible[/yellow]")

        # Partially visible constellations
        if partially_visible:
            output_console.print()
            output_console.print("[bold yellow]Constellations Partially Visible[/bold yellow]")
            output_console.print("[dim]Some stars visible, but whole constellation is low in the sky[/dim]\n")

            current_season = _get_current_season(now)

            table_partial = Table()
            table_partial.add_column("Constellation", style="bold")
            table_partial.add_column("Direction", justify="right")
            table_partial.add_column("Altitude", justify="right")
            table_partial.add_column("Key Star", style="dim")
            table_partial.add_column("Note", style="dim")  # No width - will expand to fill space

            for constellation, alt, az in partially_visible:
                direction = azimuth_to_compass_8point(az)

                # Key star with magnitude
                key_star = f"{constellation.brightest_star} ({constellation.magnitude:.1f})"

                # Check if constellation is out of season
                season_note = ""
                if constellation.season != current_season:
                    season_note = f" (best in {constellation.season.lower()}, visible out of season)"

                table_partial.add_row(
                    constellation.name,
                    direction,
                    f"{alt:.0f}°",
                    key_star,
                    f"Only some stars visible - whole constellation low{season_note}",
                )

            output_console.print(table_partial)

        output_console.print()

        # Visible Stars
        output_console.print("[bold green]Bright Stars (Tonight)[/bold green]")
        output_console.print("[dim]Naked-eye visible stars (magnitude ≤ 6.0)[/dim]\n")

        visible_stars = _get_visible_stars(lat, lon, midnight, min_altitude_deg=30.0, max_magnitude=6.0, limit=15)

        if visible_stars:
            table_stars = Table()
            table_stars.add_column("Star", style="bold")
            table_stars.add_column("Direction", justify="right")
            table_stars.add_column("Altitude", justify="right")
            table_stars.add_column("Magnitude", justify="right")
            table_stars.add_column("Constellation", style="dim")
            table_stars.add_column("Notes", style="dim")  # No width - will expand to fill space

            for star, alt, az in visible_stars:
                direction = azimuth_to_compass_8point(az)

                # Star name (prefer common name if available)
                star_name = star.common_name or star.name

                # Magnitude
                mag_str = f"{star.magnitude:.1f}" if star.magnitude else "—"

                # Constellation
                constellation_name: str = star.constellation or "—"

                # Description/notes
                notes = star.description or ""

                table_stars.add_row(
                    star_name,
                    direction,
                    f"{alt:.0f}°",
                    mag_str,
                    constellation_name,
                    notes,
                )

            output_console.print(table_stars)
            output_console.print(
                "[dim]💡 Tip: Estimate altitude with your hand - hold arm outstretched: fist = 10°, thumb = 2°, pinky = 1°[/dim]"
            )
        else:
            output_console.print("[yellow]No bright stars currently visible[/yellow]")

        output_console.print()

        # Visible Asterisms
        output_console.print("[bold green]Star Patterns to Find (Asterisms)[/bold green]")
        output_console.print("[dim]Famous patterns that are easy to recognize[/dim]\n")

        visible_asterisms = get_visible_asterisms(lat, lon, midnight, min_altitude_deg=30.0)

        if visible_asterisms:
            # Group by familiarity/importance
            priority_asterisms = ["Big Dipper", "Orion's Belt", "Summer Triangle", "Winter Triangle", "Pleiades"]

            table_ast = Table()
            table_ast.add_column("Pattern", style="bold")
            table_ast.add_column("Direction", justify="right")
            table_ast.add_column("Altitude", justify="right")
            table_ast.add_column("How to Find It", style="dim")  # No width - will expand to fill space

            # Show priority asterisms first
            shown = set()
            for asterism, alt, az in visible_asterisms:
                if asterism.name in priority_asterisms and asterism.name not in shown:
                    direction = azimuth_to_compass_8point(az)

                    description = asterism.description or ""

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

                    description = asterism.description or ""

                    table_ast.add_row(
                        asterism.name,
                        direction,
                        f"{alt:.0f}°",
                        description,
                    )
                    shown.add(asterism.name)

            output_console.print(table_ast)
            output_console.print(
                "[dim]💡 Tip: Estimate altitude with your hand - hold arm outstretched: fist = 10°, thumb = 2°, pinky = 1°[/dim]"
            )
        else:
            output_console.print("[yellow]No prominent asterisms currently visible[/yellow]")

        output_console.print("\n[bold cyan]Stargazing Tips (No Equipment Needed):[/bold cyan]")
        output_console.print("  • Find a dark location away from city lights")
        output_console.print("  • Allow 20-30 minutes for your eyes to fully adapt to darkness")
        output_console.print("  • Avoid looking at phones or bright lights (use red light if needed)")
        output_console.print("  • Lie back on a blanket or reclining chair for comfortable viewing")
        output_console.print("  • Start with bright stars and asterisms, then find fainter objects")
        output_console.print("  • Use averted vision: look slightly to the side to see fainter objects")
        output_console.print(
            "  • [bold]Estimating altitude:[/bold] Hold your arm outstretched - your fist = ~10°, thumb = ~2°, pinky = ~1°"
        )
        output_console.print("  • Best viewing: New moon or when moon has set\n")

    except ValueError as e:
        output_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from None
    except Exception as e:
        output_console.print(f"[red]Error:[/red] {e}")
        import traceback

        output_console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from None

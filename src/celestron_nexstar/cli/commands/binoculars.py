"""
Binocular Viewing Commands

Shows what's visible tonight through binoculars including ISS passes,
constellations, asterisms, and meteor showers.
"""

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import typer
from rich.console import Console
from rich.table import Table
from timezonefinder import TimezoneFinder

from ...api.compass import azimuth_to_compass_8point, format_object_path
from ...api.constellations import get_prominent_constellations, get_visible_asterisms, get_visible_constellations
from ...api.database import get_database
from ...api.enums import CelestialObjectType, SkyBrightness
from ...api.iss_tracking import get_iss_passes_cached
from ...api.meteor_showers import get_active_showers, get_peak_showers, get_radiant_position
from ...api.models import get_db_session
from ...api.observer import get_observer_location
from ...api.optics import COMMON_BINOCULARS
from ...api.sun_moon import calculate_sun_times
from ...api.utils import ra_dec_to_alt_az
from ...cli.utils.export import create_file_console, export_to_text


app = typer.Typer(help="Binocular viewing commands")
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
    max_magnitude: float = 9.0,
    limit: int = 20,
) -> list[tuple]:
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
        max_magnitude: Maximum magnitude (fainter limit) - higher for binoculars
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


def _generate_export_filename(binocular_model: str, command: str = "tonight") -> Path:
    """Generate export filename for binocular viewing."""
    from datetime import datetime

    from ...api.observer import get_observer_location

    location = get_observer_location()

    # Get binocular model (sanitized)
    model_safe = binocular_model.replace("x", "x").replace("/", "_").lower()

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
    filename = f"binoculars_{model_safe}_{location_short}_{date_str}_{command}.txt"
    return Path(filename)


@app.command("tonight")
def show_tonight(
    binoculars: str = typer.Option("10x50", "--model", "-m", help="Binocular model (e.g., 10x50, 7x50, 15x70)"),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(None, "--export-path", help="Custom export file path (overrides auto-generated filename)"),
) -> None:
    """
    Show what's visible tonight with binoculars.

    Displays ISS passes, visible constellations, asterisms, and active meteor showers
    optimized for binocular viewing. Uses your configured location.
    """
    from pathlib import Path

    # Handle export
    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename(binoculars, "tonight")
        # Create file console for export (StringIO)
        file_console = create_file_console()
        # Use file console for output
        _show_tonight_content(binoculars, file_console)
        # Get content from StringIO
        content = file_console.file.getvalue()
        file_console.file.close()

        # Export to text file
        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    # Normal console output
    _show_tonight_content(binoculars, console)


def _show_tonight_content(binoculars: str, output_console: Console) -> None:
    """
    Generate and display tonight viewing content for binoculars.

    Args:
        binoculars: Binocular model string
        output_console: Console to write output to (can be file console for export)
    """
    try:
        # Validate binocular model
        if binoculars not in COMMON_BINOCULARS:
            output_console.print(f"[red]Unknown binocular model: {binoculars}[/red]")
            output_console.print(f"Available models: {', '.join(COMMON_BINOCULARS.keys())}")
            raise typer.Exit(code=1)

        optics = COMMON_BINOCULARS[binoculars]

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
        output_console.print(f"\n[bold cyan]Binocular Viewing for {location_name}[/bold cyan]")
        output_console.print(f"[dim]Viewing Method: Binoculars - {optics.display_name}[/dim]")
        output_console.print(f"[dim]Specifications: {optics.magnification}x magnification, {optics.aperture_mm}mm aperture, {optics.exit_pupil_mm:.1f}mm exit pupil[/dim]")
        limiting_mag = optics.limiting_magnitude(SkyBrightness.GOOD)
        output_console.print(f"[dim]Limiting Magnitude: ~{limiting_mag:.1f} (with good sky conditions)[/dim]")
        output_console.print(f"[dim]Sunset: {_format_local_time(sunset, lat, lon)} | Sunrise: {_format_local_time(sunrise, lat, lon)}[/dim]\n")

        # ISS Passes
        output_console.print("[bold green]ISS Visible Passes[/bold green]")
        output_console.print("[dim]International Space Station passes visible from your location[/dim]\n")

        with get_db_session() as db:
            iss_passes = get_iss_passes_cached(lat, lon, start_time=now, days=7, min_altitude_deg=10.0, db_session=db)

        if iss_passes:
            table_iss = Table(expand=True)
            table_iss.add_column("Date", style="cyan", width=12)
            table_iss.add_column("Rise Time", style="green", width=12)
            table_iss.add_column("Max Alt", justify="right", width=10)
            table_iss.add_column("Path", style="dim")  # No width - will expand to fill space
            table_iss.add_column("Duration", justify="right", width=12)
            table_iss.add_column("Quality", width=12)

            for iss_pass in iss_passes[:10]:  # Show next 10 passes
                # Only show passes that are actually visible (sunlit)
                if not iss_pass.is_visible:
                    continue

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

            output_console.print(table_iss)
            output_console.print("[dim]Quality based on maximum altitude: Excellent >70°, Very Good >50°, Good >30°[/dim]")
        else:
            output_console.print("[yellow]No visible ISS passes in the next 7 days[/yellow]")

        output_console.print()

        # Meteor Showers
        output_console.print("[bold green]Active Meteor Showers[/bold green]")
        output_console.print("[dim]Best viewed with naked eye or binoculars for wide-field sweeping[/dim]\n")

        active_showers = get_active_showers(now)
        peak_showers = get_peak_showers(now, tolerance_days=3)

        if active_showers:
            table_showers = Table(expand=True)
            table_showers.add_column("Shower", style="bold", width=20)
            table_showers.add_column("Status", style="cyan", width=12)
            table_showers.add_column("ZHR", justify="right", width=8)
            table_showers.add_column("Radiant", style="dim", width=20)
            table_showers.add_column("Notes", style="dim")  # No width - will expand to fill space

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

                # Peak date
                peak_date = f"{shower.peak_month}/{shower.peak_day}"
                notes = f"Peak: {peak_date}, {shower.velocity_km_s} km/s"

                table_showers.add_row(
                    shower.name,
                    status,
                    str(shower.zhr_peak),
                    radiant_text,
                    notes,
                )

            output_console.print(table_showers)
            output_console.print("[dim]ZHR = Zenithal Hourly Rate (meteors per hour under ideal conditions)[/dim]")
            output_console.print("[dim]Actual rates are typically 25-50% of ZHR due to non-ideal conditions[/dim]")
        else:
            output_console.print("[yellow]No major meteor showers currently active[/yellow]")

        output_console.print()

        # Visible Constellations
        output_console.print("[bold green]Prominent Constellations (Tonight)[/bold green]")
        output_console.print("[dim]Best constellations visible from your location[/dim]\n")

        # Calculate for midnight
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if midnight < now:
            midnight = midnight.replace(day=midnight.day + 1)

        # Get visible constellations (using lower threshold to catch more)
        visible_constellations = get_visible_constellations(lat, lon, midnight, min_altitude_deg=10.0)

        # Track which constellations have low centers (below normal viewing threshold)
        # Normal threshold is 20° for binoculars
        normal_threshold = 20.0
        low_altitude_constellations = set()

        # Mark constellations already in the list that are below normal threshold
        for constellation, alt, az in visible_constellations:
            if alt < normal_threshold:
                low_altitude_constellations.add(constellation.name)

        # Also include constellations that have visible stars, even if center is low
        # Get visible stars first to find their constellations
        limiting_mag = optics.limiting_magnitude(SkyBrightness.GOOD)
        visible_stars_for_const = _get_visible_stars(lat, lon, midnight, min_altitude_deg=20.0, max_magnitude=limiting_mag, limit=100)

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
        fully_visible = [(c, alt, az) for c, alt, az in visible_constellations if c.name not in low_altitude_constellations]
        partially_visible = [(c, alt, az) for c, alt, az in visible_constellations if c.name in low_altitude_constellations]

        if fully_visible:
            current_season = _get_current_season(now)

            table_const = Table(expand=True)
            table_const.add_column("Constellation", style="bold", width=15)
            table_const.add_column("Direction", justify="right", width=10)
            table_const.add_column("Altitude", justify="right", width=10)
            table_const.add_column("Season", style="dim", width=20)
            table_const.add_column("Highlights", style="dim")  # No width - will expand to fill space

            for constellation, alt, az in fully_visible[:12]:  # Top 12
                direction = azimuth_to_compass_8point(az)

                description = constellation.description

                # Check if constellation is out of season
                season_display = constellation.season
                if constellation.season != current_season:
                    season_display = f"{constellation.season} (best in {constellation.season.lower()}, visible out of season)"

                table_const.add_row(
                    constellation.name,
                    direction,
                    f"{alt:.0f}°",
                    season_display,
                    description,
                )

            output_console.print(table_const)
            output_console.print("[dim]💡 Tip: Estimate altitude with your hand - hold arm outstretched: fist = 10°, thumb = 2°, pinky = 1°[/dim]")
        else:
            output_console.print("[yellow]No prominent constellations currently visible[/yellow]")

        # Partially visible constellations
        if partially_visible:
            output_console.print()
            output_console.print("[bold yellow]Constellations Partially Visible[/bold yellow]")
            output_console.print("[dim]Some stars visible, but whole constellation is low in the sky[/dim]\n")

            current_season = _get_current_season(now)

            table_partial = Table(expand=True)
            table_partial.add_column("Constellation", style="bold", width=15)
            table_partial.add_column("Direction", justify="right", width=10)
            table_partial.add_column("Altitude", justify="right", width=10)
            table_partial.add_column("Season", style="dim", width=20)
            table_partial.add_column("Note", style="dim")  # No width - will expand to fill space

            for constellation, alt, az in partially_visible:
                direction = azimuth_to_compass_8point(az)

                description = constellation.description

                # Check if constellation is out of season
                season_display = constellation.season
                if constellation.season != current_season:
                    season_display = f"{constellation.season} (best in {constellation.season.lower()}, visible out of season)"

                table_partial.add_row(
                    constellation.name,
                    direction,
                    f"{alt:.0f}°",
                    season_display,
                    "Only some stars visible - whole constellation low",
                )

            output_console.print(table_partial)

        output_console.print()

        # Visible Stars
        output_console.print("[bold green]Bright Stars (Tonight)[/bold green]")
        # Calculate limiting magnitude for binoculars (using good sky conditions)
        limiting_mag = optics.limiting_magnitude(SkyBrightness.GOOD)
        output_console.print(f"[dim]Stars visible with {optics.display_name} (magnitude ≤ {limiting_mag:.1f})[/dim]\n")

        # Use binocular limiting magnitude (typically 9-10 for 10x50)
        visible_stars = _get_visible_stars(lat, lon, midnight, min_altitude_deg=20.0, max_magnitude=limiting_mag, limit=20)

        if visible_stars:
            table_stars = Table(expand=True)
            table_stars.add_column("Star", style="bold", width=20)
            table_stars.add_column("Direction", justify="right", width=10)
            table_stars.add_column("Altitude", justify="right", width=10)
            table_stars.add_column("Magnitude", justify="right", width=12)
            table_stars.add_column("Constellation", style="dim", width=15)
            table_stars.add_column("Notes", style="dim")  # No width - will expand to fill space

            for star, alt, az in visible_stars:
                direction = azimuth_to_compass_8point(az)

                # Star name (prefer common name if available)
                star_name = star.common_name or star.name

                # Magnitude
                mag_str = f"{star.magnitude:.1f}" if star.magnitude else "—"

                # Constellation
                constellation = star.constellation or "—"

                # Description/notes
                notes = star.description or ""

                table_stars.add_row(
                    star_name,
                    direction,
                    f"{alt:.0f}°",
                    mag_str,
                    constellation,
                    notes,
                )

            output_console.print(table_stars)
            output_console.print("[dim]💡 Tip: Estimate altitude with your hand - hold arm outstretched: fist = 10°, thumb = 2°, pinky = 1°[/dim]")
        else:
            output_console.print("[yellow]No bright stars currently visible[/yellow]")

        output_console.print()

        # Visible Asterisms
        output_console.print("[bold green]Famous Star Patterns (Asterisms)[/bold green]")
        output_console.print("[dim]Easily recognizable patterns visible through binoculars[/dim]\n")

        visible_asterisms = get_visible_asterisms(lat, lon, midnight, min_altitude_deg=20.0)

        if visible_asterisms:
            table_ast = Table(expand=True)
            table_ast.add_column("Asterism", style="bold", width=20)
            table_ast.add_column("Direction", justify="right", width=10)
            table_ast.add_column("Altitude", justify="right", width=10)
            table_ast.add_column("Size", justify="right", width=8)
            table_ast.add_column("Description", style="dim")  # No width - will expand to fill space

            for asterism, alt, az in visible_asterisms[:10]:  # Top 10
                direction = azimuth_to_compass_8point(az)

                description = asterism.description or ""

                table_ast.add_row(
                    asterism.name,
                    direction,
                    f"{alt:.0f}°",
                    f"{asterism.size_degrees:.0f}°" if asterism.size_degrees else "—",
                    description,
                )

            output_console.print(table_ast)
            output_console.print("[dim]💡 Tip: Estimate altitude with your hand - hold arm outstretched: fist = 10°, thumb = 2°, pinky = 1°[/dim]")
        else:
            output_console.print("[yellow]No prominent asterisms currently visible[/yellow]")

        output_console.print("\n[bold cyan]Viewing Tips for Binoculars:[/bold cyan]")
        output_console.print("  • Allow 20-30 minutes for dark adaptation")
        output_console.print("  • Use a tripod or stable support for extended viewing")
        output_console.print(f"  • Your {optics.display_name} have a {optics.exit_pupil_mm:.1f}mm exit pupil")
        output_console.print(f"  • Light gathering: {optics.light_gathering_power:.0f}x more than naked eye")
        output_console.print("  • Start with wide-field asterisms, then zoom in on constellations")
        output_console.print("  • For meteor showers, sweep the sky slowly around the radiant\n")

    except ValueError as e:
        output_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from None
    except Exception as e:
        output_console.print(f"[red]Error:[/red] {e}")
        import traceback

        output_console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from None
